"""车辆模块改为半挂车队：牵引车+挂车、货物与吨位

Revision ID: 0030
Revises: 0029
Create Date: 2026-11-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VEHICLE_TYPES_V1 = "('sedan','mpv','pickup','minibus','ev','truck')"
VEHICLE_TYPES_V2 = "('tractor','dump','tanker','van')"
DEMO_APP_NOS = (
    "CA202609180001",
    "CA202609210002",
    "CA202609250003",
    "CA202610030004",
    "CA202610080005",
    "CA202610120006",
    "CA202610180007",
    "CA202610230008",
    "CA202610280009",
    "CA202611020010",
    "CA202611060011",
    "CA202611100012",
)


def upgrade() -> None:
    # 先清掉公务小车演示数据，并统一车型口径，避免新 CHECK 约束校验失败
    op.execute(
        "DELETE FROM car_applications WHERE application_no IN ("
        + ",".join(f"'{no}'" for no in DEMO_APP_NOS)
        + ")"
    )
    op.execute(
        "UPDATE vehicles SET deleted_at = now() "
        "WHERE is_mock = true AND deleted_at IS NULL"
    )
    # 车辆档案：换成牵引车+挂车口径
    op.add_column("vehicles", sa.Column("trailer_no", sa.String(32), nullable=True))
    op.add_column(
        "vehicles",
        sa.Column("load_ton", sa.Numeric(6, 1), nullable=False, server_default="0"),
    )
    op.drop_column("vehicles", "seats")
    op.drop_constraint("ck_vehicles_type", "vehicles", type_="check")
    op.execute(
        "UPDATE vehicles SET vehicle_type = 'tractor' "
        f"WHERE vehicle_type NOT IN {VEHICLE_TYPES_V2}"
    )
    op.create_check_constraint(
        "ck_vehicles_type", "vehicles", f"vehicle_type IN {VEHICLE_TYPES_V2}"
    )
    op.execute("ALTER TABLE vehicles ALTER COLUMN vehicle_type SET DEFAULT 'tractor'")

    # 派车申请：货物、吨位替代人数与用车性质
    op.add_column("car_applications", sa.Column("cargo", sa.String(64), nullable=True))
    op.add_column(
        "car_applications",
        sa.Column("tonnage", sa.Numeric(6, 1), nullable=False, server_default="0"),
    )
    op.drop_constraint("ck_car_applications_nature", "car_applications", type_="check")
    op.drop_column("car_applications", "use_nature")
    op.drop_column("car_applications", "passengers")
    op.drop_column("car_applications", "person_num")

    # 半挂车队演示车辆
    op.execute(
        """
        INSERT INTO vehicles
          (code, plate_no, model, vehicle_type, trailer_no, load_ton,
           driver_name, driver_phone, status, mileage_km, remark, is_mock)
        SELECT v.code, v.plate_no, v.model, v.vehicle_type, v.trailer_no, v.load_ton,
               v.driver_name, v.driver_phone, v.status, v.mileage_km, '半挂车队演示车辆', true
        FROM (VALUES
          ('T001','渝B12345','解放J6P 6X4','tractor','渝B1234挂',32.0,'张伟','13800000001','available',325000.0),
          ('T002','渝B23456','陕汽德龙X3000','tractor','渝B2345挂',33.5,'李强','13800000002','available',298000.0),
          ('T003','渝B34567','东风天龙KL','tractor','渝B3456挂',30.0,'王磊','13800000003','in_use',286000.0),
          ('T004','渝B45678','重汽豪沃T7H','tractor','渝B4567挂',34.0,'赵军','13800000004','available',352000.0),
          ('T005','渝B56789','福田欧曼EST','tractor','渝B5678挂',31.5,'刘洋','13800000005','maintenance',310000.0),
          ('T006','渝D67890','上汽红岩杰狮','tractor','渝D6789挂',33.0,'陈晨','13800000006','available',232000.0)
        ) AS v(code, plate_no, model, vehicle_type, trailer_no, load_ton,
               driver_name, driver_phone, status, mileage_km)
        WHERE NOT EXISTS (SELECT 1 FROM vehicles x WHERE x.code = v.code)
        """
    )

    # 近两个月的运煤车次，便于统计与报告演示
    op.execute(
        """
        INSERT INTO car_applications
          (application_no, applicant_id, applicant_name, department_id,
           start_address, end_address, start_time, end_time,
           cargo, tonnage, project, reason, vehicle_id, plate_no, driver_name,
           status, mileage_km, fuel_cost, toll_fee, parking_fee, other_fee,
           total_cost, created_at)
        SELECT v.app_no, u.id, u.name, u.department_id,
               v.start_addr, v.end_addr,
               now() - v.days * interval '1 day',
               now() - v.days * interval '1 day' + interval '7 hours',
               v.cargo, v.tonnage, v.project, v.reason,
               veh.id, veh.plate_no, veh.driver_name, 'completed',
               v.mileage, round(v.mileage * 0.85, 2), v.toll, v.parking, v.other,
               round(v.mileage * 0.85, 2) + v.toll + v.parking + v.other,
               now() - v.days * interval '1 day'
        FROM (VALUES
          ('CA202609180001','T001','綦江打通煤矿','珞璜电厂煤场',58,'精煤',32.0,'煤炭运输','电煤保供',120,30,0,0),
          ('CA202609210002','T002','綦江石壕煤矿','万盛洗煤厂',54,'原煤',31.5,'煤炭运输','入洗调运',160,55,10,0),
          ('CA202609250003','T004','江津珞璜港','永川电厂煤场',50,'精煤',33.0,'煤炭运输','码头疏港',95,20,0,0),
          ('CA202610030004','T001','南川水江煤矿','涪陵白涛化工园',44,'煤炭',32.0,'煤炭运输','化工用煤',130,35,0,0),
          ('CA202610080005','T006','铜梁围龙煤矿','合川双槐电厂',39,'原煤',30.0,'煤炭运输','电煤补库',45,0,15,0),
          ('CA202610120006','T002','万州港','达州钢厂',35,'焦炭',31.5,'焦炭运输','钢厂供料',280,90,20,10),
          ('CA202610180007','T004','贵州习水煤矿','江津珞璜电厂',29,'原煤',34.0,'煤炭运输','跨省调运',320,110,0,0),
          ('CA202610230008','T001','永川红炉煤矿','荣昌电厂煤场',24,'精煤',32.0,'煤炭运输','月度合同',110,25,0,0),
          ('CA202610280009','T006','丰都湛普煤矿','长寿经开区煤场',19,'煤炭',30.0,'煤炭运输','园区供煤',70,10,0,0),
          ('CA202611020010','T002','大足邮亭煤矿','大足电厂煤场',14,'原煤',31.5,'煤炭运输','库存补充',150,45,0,0),
          ('CA202611060011','T001','涪陵码头','万州港',10,'精煤',32.0,'煤炭运输','水陆联运',190,60,15,0),
          ('CA202611100012','T004','北碚天府煤矿','两江新区热电厂',6,'煤炭',33.0,'煤炭运输','冬季保供',85,20,0,0)
        ) AS v(app_no, veh_code, start_addr, end_addr, days,
               cargo, tonnage, project, reason, mileage, toll, parking, other)
        JOIN vehicles veh ON veh.code = v.veh_code
        JOIN users u ON u.employee_no = 'B0001'
        WHERE NOT EXISTS (
          SELECT 1 FROM car_applications c WHERE c.application_no = v.app_no
        )
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM car_applications WHERE application_no IN ("
        + ",".join(f"'{no}'" for no in DEMO_APP_NOS)
        + ")"
    )
    op.execute(
        "DELETE FROM vehicles WHERE is_mock = true AND code IN "
        "('T001','T002','T003','T004','T005','T006')"
    )
    op.execute(
        "UPDATE vehicles SET deleted_at = NULL WHERE is_mock = true AND code LIKE 'V%'"
    )

    op.add_column(
        "car_applications",
        sa.Column("use_nature", sa.String(16), nullable=False, server_default="business"),
    )
    op.add_column(
        "car_applications",
        sa.Column("person_num", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column("car_applications", sa.Column("passengers", sa.String(255), nullable=True))
    op.create_check_constraint(
        "ck_car_applications_nature",
        "car_applications",
        "use_nature IN ('business','private')",
    )
    op.drop_column("car_applications", "tonnage")
    op.drop_column("car_applications", "cargo")

    op.add_column(
        "vehicles", sa.Column("seats", sa.Integer(), nullable=False, server_default="5")
    )
    op.drop_constraint("ck_vehicles_type", "vehicles", type_="check")
    op.create_check_constraint(
        "ck_vehicles_type", "vehicles", f"vehicle_type IN {VEHICLE_TYPES_V1}"
    )
    op.execute("ALTER TABLE vehicles ALTER COLUMN vehicle_type SET DEFAULT 'sedan'")
    op.drop_column("vehicles", "load_ton")
    op.drop_column("vehicles", "trailer_no")
