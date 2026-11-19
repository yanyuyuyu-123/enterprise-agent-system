"""创建首个管理员账号：`python -m app.bootstrap`。

系统管理员由人事负责人担任（规划 2.1），密码从 `.env` 的
`BOOTSTRAP_ADMIN_PASSWORD` 读取，不写进迁移脚本。
"""

from __future__ import annotations

from sqlalchemy import select

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models.org import Department, Position, User, UserPosition

ADMIN_EMPLOYEE_NO = "A0001"


def main() -> None:
    if not settings.bootstrap_admin_password:
        raise SystemExit("请先在 .env 设置 BOOTSTRAP_ADMIN_PASSWORD")

    with SessionLocal() as db:
        existing = db.scalar(select(User).where(User.employee_no == ADMIN_EMPLOYEE_NO))
        if existing is not None:
            print(f"管理员已存在：{ADMIN_EMPLOYEE_NO}")
            return

        position = db.scalar(select(Position).where(Position.code == "hr_head"))
        if position is None:
            raise SystemExit("岗位数据缺失，请先执行 alembic upgrade head")

        department = db.scalar(select(Department).where(Department.code == "hr"))
        user = User(
            employee_no=ADMIN_EMPLOYEE_NO,
            name="系统管理员",
            password_hash=hash_password(settings.bootstrap_admin_password),
            department_id=department.id if department else None,
        )
        db.add(user)
        db.flush()
        db.add(UserPosition(user_id=user.id, position_id=position.id, is_primary=True))
        db.commit()
        print(f"已创建管理员：{ADMIN_EMPLOYEE_NO}（人事负责人）")


if __name__ == "__main__":
    main()
