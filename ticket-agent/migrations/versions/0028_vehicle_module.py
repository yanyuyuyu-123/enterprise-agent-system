"""车辆管理：车辆档案、用车申请与统计

Revision ID: 0028
Revises: 0027
Create Date: 2026-11-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RESOURCES_WITH_VEHICLE = (
    "resource IN ('work_order','work_order_assign','work_order_review','work_order_transfer',"
    "'report','knowledge_document','operation_log','system_log','account','org','device',"
    "'purchase_order','sales_order','customer','supplier','product','inventory',"
    "'finance_record','config','alert','voice','safe_stock','vehicle','car_application')"
)
RESOURCES_WITHOUT_VEHICLE = (
    "resource IN ('work_order','work_order_assign','work_order_review','work_order_transfer',"
    "'report','knowledge_document','operation_log','system_log','account','org','device',"
    "'purchase_order','sales_order','customer','supplier','product','inventory',"
    "'finance_record','config','alert','voice','safe_stock')"
)


def upgrade() -> None:
    op.create_table(
        "vehicles",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("plate_no", sa.String(32), nullable=False),
        sa.Column("model", sa.String(64), nullable=True),
        sa.Column("vehicle_type", sa.String(16), nullable=False, server_default="sedan"),
        sa.Column("seats", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("driver_name", sa.String(64), nullable=True),
        sa.Column("driver_phone", sa.String(20), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="available"),
        sa.Column("mileage_km", sa.Numeric(12, 1), nullable=False, server_default="0"),
        sa.Column("remark", sa.String(255), nullable=True),
        sa.Column("is_mock", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('available','in_use','maintenance','disabled')", name="ck_vehicles_status"
        ),
        sa.CheckConstraint(
            "vehicle_type IN ('sedan','mpv','pickup','minibus','ev','truck')",
            name="ck_vehicles_type",
        ),
    )
    op.create_unique_constraint("uq_vehicles_code", "vehicles", ["code"])
    op.create_unique_constraint("uq_vehicles_plate", "vehicles", ["plate_no"])

    op.create_table(
        "car_applications",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("application_no", sa.String(32), nullable=False),
        sa.Column("applicant_id", sa.BigInteger(), nullable=False),
        sa.Column("applicant_name", sa.String(64), nullable=False),
        sa.Column("department_id", sa.BigInteger(), nullable=True),
        sa.Column("start_address", sa.String(255), nullable=False),
        sa.Column("end_address", sa.String(255), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("use_nature", sa.String(16), nullable=False, server_default="business"),
        sa.Column("person_num", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("passengers", sa.String(255), nullable=True),
        sa.Column("project", sa.String(128), nullable=True),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column("vehicle_id", sa.BigInteger(), nullable=True),
        sa.Column("plate_no", sa.String(32), nullable=True),
        sa.Column("driver_name", sa.String(64), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("mileage_km", sa.Numeric(12, 1), nullable=False, server_default="0"),
        sa.Column("fuel_cost", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("toll_fee", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("parking_fee", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("other_fee", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("total_cost", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("approver_id", sa.BigInteger(), nullable=True),
        sa.Column("approver_name", sa.String(64), nullable=True),
        sa.Column("approve_comment", sa.String(255), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("remark", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["applicant_id"], ["users.id"], name="fk_car_applicant"),
        sa.ForeignKeyConstraint(["department_id"], ["departments.id"], name="fk_car_department"),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], name="fk_car_vehicle"),
        sa.ForeignKeyConstraint(["approver_id"], ["users.id"], name="fk_car_approver"),
        sa.CheckConstraint(
            "status IN ('pending','approved','rejected','cancelled','completed')",
            name="ck_car_applications_status",
        ),
        sa.CheckConstraint(
            "use_nature IN ('business','private')", name="ck_car_applications_nature"
        ),
    )
    op.create_unique_constraint(
        "uq_car_applications_no", "car_applications", ["application_no"]
    )
    op.create_index("idx_car_applications_status", "car_applications", ["status"])
    op.create_index("idx_car_applications_start", "car_applications", ["start_time"])
    op.create_index("idx_car_applications_applicant", "car_applications", ["applicant_id"])

    # 权限资源白名单放开车辆相关资源
    op.drop_constraint("ck_position_permissions_resource", "position_permissions", type_="check")
    op.create_check_constraint(
        "ck_position_permissions_resource", "position_permissions", RESOURCES_WITH_VEHICLE
    )

    # 所有人可提用车申请、可查自己的申请
    op.execute(
        """
        INSERT INTO position_permissions (position_id, resource, action, data_scope)
        SELECT p.id, 'car_application', v.action, 'self'
        FROM positions p
        CROSS JOIN (VALUES ('create'), ('read')) AS v(action)
        WHERE p.deleted_at IS NULL
          AND NOT EXISTS (
            SELECT 1 FROM position_permissions pp
            WHERE pp.position_id = p.id
              AND pp.resource = 'car_application'
              AND pp.action = v.action
              AND pp.data_scope = 'self'
          )
        """
    )

    # 管理层与调度可查看更大范围、可审批
    op.execute(
        """
        INSERT INTO position_permissions (position_id, resource, action, data_scope)
        SELECT p.id, v.resource, v.action, v.data_scope
        FROM positions p
        JOIN (VALUES
          ('general_manager','car_application','read','company'),
          ('biz_head','car_application','read','company'),
          ('logistics_head','car_application','read','company'),
          ('biz_manager','car_application','read','department'),
          ('dispatcher','car_application','read','department'),
          ('general_manager','car_application','approve','company'),
          ('biz_head','car_application','approve','company'),
          ('logistics_head','car_application','approve','company'),
          ('biz_manager','car_application','approve','department'),
          ('dispatcher','car_application','approve','department'),
          ('general_manager','vehicle','read','company'),
          ('biz_head','vehicle','read','company'),
          ('logistics_head','vehicle','read','company'),
          ('biz_manager','vehicle','read','department'),
          ('dispatcher','vehicle','read','department'),
          ('transporter','vehicle','read','self')
        ) AS v(code, resource, action, data_scope) ON p.code = v.code
        WHERE p.deleted_at IS NULL
          AND NOT EXISTS (
            SELECT 1 FROM position_permissions pp
            WHERE pp.position_id = p.id
              AND pp.resource = v.resource
              AND pp.action = v.action
              AND pp.data_scope = v.data_scope
          )
        """
    )

    # 演示车辆
    op.execute(
        """
        INSERT INTO vehicles
          (code, plate_no, model, vehicle_type, seats, driver_name, driver_phone,
           status, mileage_km, remark, is_mock)
        SELECT v.code, v.plate_no, v.model, v.vehicle_type, v.seats,
               v.driver_name, v.driver_phone, v.status, v.mileage_km, '演示车辆', true
        FROM (VALUES
          ('V001','渝A12345','丰田凯美瑞','sedan',5,'张伟','13800000001','available',125000.0),
          ('V002','渝A23456','大众帕萨特','sedan',5,'李强','13800000002','available',98000.0),
          ('V003','渝A34567','别克GL8','mpv',7,'王磊','13800000003','in_use',86000.0),
          ('V004','渝A45678','江铃域虎','pickup',5,'赵军','13800000004','available',152000.0),
          ('V005','渝A56789','丰田考斯特','minibus',19,'刘洋','13800000005','maintenance',210000.0),
          ('V006','渝A67890','比亚迪汉EV','ev',5,'陈晨','13800000006','available',32000.0)
        ) AS v(code, plate_no, model, vehicle_type, seats, driver_name, driver_phone, status, mileage_km)
        WHERE NOT EXISTS (SELECT 1 FROM vehicles x WHERE x.code = v.code)
        """
    )

    # 近两个月的已完成行程，便于统计与报告演示
    op.execute(
        """
        INSERT INTO car_applications
          (application_no, applicant_id, applicant_name, department_id,
           start_address, end_address, start_time, end_time, use_nature,
           person_num, project, reason, vehicle_id, plate_no, driver_name,
           status, mileage_km, fuel_cost, toll_fee, parking_fee, other_fee,
           total_cost, created_at)
        SELECT v.app_no, u.id, u.name, u.department_id,
               v.start_addr, v.end_addr,
               now() - v.days * interval '1 day',
               now() - v.days * interval '1 day' + interval '7 hours',
               'business', v.persons, v.project, v.reason,
               veh.id, veh.plate_no, veh.driver_name, 'completed',
               v.mileage, round(v.mileage * 0.85, 2), v.toll, v.parking, v.other,
               round(v.mileage * 0.85, 2) + v.toll + v.parking + v.other,
               now() - v.days * interval '1 day'
        FROM (VALUES
          ('CA202609180001','V001','重庆市渝北区公司总部','重庆市长寿区化工园区',58,3,'客户走访','拜访重点客户',120,30,0,0),
          ('CA202609210002','V002','重庆市渝北区公司总部','重庆市綦江区煤矿',54,2,'矿区巡查','现场安全检查',160,55,10,0),
          ('CA202609250003','V004','重庆市渝北区公司总部','重庆市江津区物流园',50,3,'物流对接','对接运输承运商',95,20,0,0),
          ('CA202610030004','V001','重庆市渝北区公司总部','重庆市永川区电厂',44,2,'客户走访','合同续签洽谈',130,35,0,0),
          ('CA202610080005','V006','重庆市渝北区公司总部','重庆市两江新区管委会',39,4,'项目申报','提交项目材料',45,0,15,0),
          ('CA202610120006','V002','重庆市渝北区公司总部','重庆市万州区港区',35,2,'物流对接','协调码头装船',280,90,20,10),
          ('CA202610180007','V004','重庆市渝北区公司总部','重庆市黔江区石场',29,3,'现场勘查','煤质取样',320,110,0,0),
          ('CA202610230008','V001','重庆市渝北区公司总部','重庆市合川区客户仓',24,2,'客户走访','月度回访',110,25,0,0),
          ('CA202610280009','V006','重庆市渝北区公司总部','重庆市长寿区经开区',19,3,'项目申报','园区会议',70,10,0,0),
          ('CA202611020010','V002','重庆市渝北区公司总部','重庆市大足区煤场',14,2,'矿区巡查','库存盘点抽查',150,45,0,0),
          ('CA202611060011','V001','重庆市渝北区公司总部','重庆市涪陵区码头',10,3,'物流对接','协调发运计划',190,60,15,0),
          ('CA202611100012','V004','重庆市渝北区公司总部','重庆市铜梁区客户厂区',6,2,'客户走访','质量异议处理',85,20,0,0)
        ) AS v(app_no, veh_code, start_addr, end_addr, days,
               persons, project, reason, mileage, toll, parking, other)
        JOIN vehicles veh ON veh.code = v.veh_code
        JOIN users u ON u.employee_no = 'B0001'
        WHERE NOT EXISTS (
          SELECT 1 FROM car_applications c WHERE c.application_no = v.app_no
        )
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM position_permissions WHERE resource IN ('vehicle','car_application')"
    )
    op.drop_constraint("ck_position_permissions_resource", "position_permissions", type_="check")
    op.create_check_constraint(
        "ck_position_permissions_resource", "position_permissions", RESOURCES_WITHOUT_VEHICLE
    )
    op.drop_index("idx_car_applications_applicant", table_name="car_applications")
    op.drop_index("idx_car_applications_start", table_name="car_applications")
    op.drop_index("idx_car_applications_status", table_name="car_applications")
    op.drop_table("car_applications")
    op.drop_constraint("uq_vehicles_plate", "vehicles", type_="unique")
    op.drop_constraint("uq_vehicles_code", "vehicles", type_="unique")
    op.drop_table("vehicles")
