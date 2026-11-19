"""测试基座：跑在独立数据库上，避免污染开发库；关闭登录限流与外部模型。"""

from __future__ import annotations

import os
import subprocess

os.environ["LOGIN_RATE_LIMIT_PER_MINUTE"] = "0"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import make_url

from app.core.config import settings

TEST_DB = "ticket_test"

settings.login_rate_limit_per_minute = 0
settings.deepseek_api_key = ""

# 切换数据库必须发生在导入 app.core.db 之前：
# 测试库由开发库克隆而来，保留演示账号与基础数据，但测试写入不会落回开发库。
_BASE_DB_URL = make_url(settings.database_url)
settings.database_url = _BASE_DB_URL.set(database=TEST_DB).render_as_string(hide_password=False)

from app.core.db import SessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models.org import Position, User, UserPosition  # noqa: E402
from tests.helpers import PWD  # noqa: E402


def _postgres_container() -> str:
    """找到映射了开发库端口的 Postgres 容器，找不到就用默认容器名。"""
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", f"publish={_BASE_DB_URL.port}", "--format", "{{.Names}}"],
            check=True,
            capture_output=True,
            text=True,
        )
        names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if names:
            return names[0]
    except (OSError, subprocess.CalledProcessError):
        pass
    return "ticket-postgres"


def _recreate_test_database() -> None:
    """用 pg_dump 克隆开发库到测试库，保证测试库独立且数据完整。"""
    container = _postgres_container()
    user = _BASE_DB_URL.username or "ticket"
    source_db = _BASE_DB_URL.database or "ticket"

    def psql(*args: str, stdin: bytes | None = None) -> None:
        subprocess.run(
            ["docker", "exec", *(["-i"] if stdin is not None else []), container, *args],
            check=True,
            capture_output=True,
            input=stdin,
        )

    psql(
        "psql",
        "-U",
        user,
        "-d",
        "postgres",
        "-v",
        "ON_ERROR_STOP=1",
        "-c",
        f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)',
    )
    psql(
        "psql",
        "-U",
        user,
        "-d",
        "postgres",
        "-v",
        "ON_ERROR_STOP=1",
        # 指定 C collation，避免模板库 collation 版本与宿主机 libc 不一致导致建库失败
        "-c",
        f"CREATE DATABASE \"{TEST_DB}\" TEMPLATE template0 LC_COLLATE 'C' LC_CTYPE 'C'",
    )
    dump = subprocess.run(
        [
            "docker",
            "exec",
            container,
            "pg_dump",
            "-U",
            user,
            "-d",
            source_db,
            "--no-owner",
            "--no-privileges",
        ],
        check=True,
        capture_output=True,
    ).stdout
    psql("psql", "-U", user, "-d", TEST_DB, "-v", "ON_ERROR_STOP=1", "-q", stdin=dump)


@pytest.fixture(scope="session", autouse=True)
def test_database() -> None:
    _recreate_test_database()


def _ensure_user(
    db,
    *,
    employee_no: str,
    name: str,
    position_code: str,
    status: str = "active",
    department_id: int | None = None,
) -> None:
    if db.scalar(select(User.id).where(User.employee_no == employee_no)) is not None:
        return
    position_id = db.scalar(select(Position.id).where(Position.code == position_code))
    user = User(
        employee_no=employee_no,
        name=name,
        password_hash=hash_password(PWD),
        status=status,
        department_id=department_id,
    )
    db.add(user)
    db.flush()
    db.add(UserPosition(user_id=user.id, position_id=position_id, is_primary=True))
    db.commit()


@pytest.fixture(scope="session", autouse=True)
def seeded_accounts(test_database: None) -> None:
    with SessionLocal() as db:
        _ensure_user(db, employee_no="M0001", name="总经理", position_code="general_manager")
        _ensure_user(
            db, employee_no="R0002", name="维修工乙", position_code="repairman", department_id=4
        )
        _ensure_user(
            db,
            employee_no="D0001",
            name="停用账号",
            position_code="production_worker",
            status="disabled",
            department_id=4,
        )
        # V2 业务账号
        _ensure_user(
            db, employee_no="V2P01", name="采购员", position_code="purchaser", department_id=3
        )
        _ensure_user(
            db, employee_no="V2S01", name="业务员", position_code="salesperson", department_id=3
        )
        _ensure_user(
            db, employee_no="V2B01", name="业务负责人", position_code="biz_head", department_id=3
        )
        _ensure_user(
            db,
            employee_no="V2M01",
            name="业务经理",
            position_code="biz_manager",
            department_id=3,
        )
        _ensure_user(
            db,
            employee_no="V2W01",
            name="仓库负责人",
            position_code="warehouse_head",
            department_id=3,
        )
        _ensure_user(
            db, employee_no="V2C01", name="制单员", position_code="document_clerk", department_id=3
        )
        _ensure_user(
            db, employee_no="V2T01", name="理货员", position_code="tally_clerk", department_id=3
        )
        _ensure_user(
            db, employee_no="V2A01", name="会计", position_code="accountant", department_id=2
        )
        _ensure_user(db, employee_no="V2CA1", name="出纳", position_code="cashier", department_id=2)
        _ensure_user(
            db,
            employee_no="V2F01",
            name="财务负责人",
            position_code="finance_head",
            department_id=2,
        )
        _ensure_user(
            db,
            employee_no="V2K01",
            name="生产工人乙",
            position_code="production_worker",
            department_id=4,
        )
        # 知识库写入权限仅开放给人事负责人与总经理，测试专用账号
        _ensure_user(
            db,
            employee_no="K0001",
            name="人事负责人测试",
            position_code="hr_head",
            department_id=1,
        )


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="session")
def tokens(client: TestClient):
    cache: dict[str, str] = {}

    def get(employee_no: str) -> str:
        if employee_no not in cache:
            response = client.post(
                "/api/v1/auth/login",
                json={"employee_no": employee_no, "password": PWD},
            )
            assert response.status_code == 200, response.text
            cache[employee_no] = response.json()["data"]["access_token"]
        return cache[employee_no]

    return get


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
