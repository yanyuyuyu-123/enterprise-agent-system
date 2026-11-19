"""生成一整年煤炭业务数据：清旧数据 → 主数据 → 全年流水 → 多格式导出 → 制度入知识库。

用法（在 ticket-agent 目录下）：
    .\\.venv\\Scripts\\python.exe scripts\\generate_coal_year.py
    .\\.venv\\Scripts\\python.exe scripts\\generate_coal_year.py --start 2025-11-01 --end 2026-10-31
"""

# ruff: noqa: E501

from __future__ import annotations

import argparse
import csv
import random
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.models.business import (
    CashFlow,
    Customer,
    FinanceRecord,
    Inventory,
    Product,
    PurchaseOrder,
    PurchaseOrderItem,
    SalesOrder,
    SalesOrderItem,
    StockMovement,
    StockMovementItem,
    Supplier,
    Warehouse,
)
from app.models.knowledge import KnowledgeDocument
from app.models.org import User
from app.models.production import ProductionRecord
from app.models.report import Report
from app.models.work_order import WorkOrder, WorkOrderExpense, WorkOrderRecord
from app.services import ingest_service, knowledge_service, report_service
from app.services.permission_service import load_principal

random.seed(20261113)

DEFAULT_START = date(2025, 11, 1)
DEFAULT_END = date(2026, 10, 31)
OUT_ROOT = Path(r"c:\个人项目\数据\煤炭业务数据")

RAW_NAME = "原煤"
WASHED_NAME = "精煤"
RAW_SALE_PRICE = Decimal("1000")
WASHED_PRICE_RANGE = (1500, 2000)

CUSTOMERS = [
    ("唐山恒北热电有限公司", "张建国", "13800000000", "河北省唐山市路北区建设路 88 号"),
    ("滨州海源发电有限公司", "李海涛", "13800000000", "山东省滨州市北海新区港城路 12 号"),
    ("上海沪冶资源贸易有限公司", "王振宇", "13800000000", "上海市宝山区同济路 1088 号"),
    ("鞍山盛铁燃料有限公司", "刘志强", "13800000000", "辽宁省鞍山市铁西区环钢路 66 号"),
    ("邢台冀达物流有限公司", "赵文斌", "13800000000", "河北省邢台市中兴西大街 199 号"),
    ("太原晋源煤业销售有限公司", "陈立新", "13800000000", "山西省太原市迎泽区新建南路 28 号"),
    ("渭南秦东发电有限公司", "孙国强", "13800000000", "陕西省渭南市临渭区东风大街 9 号"),
    ("德州鲁恒化工有限公司", "周明辉", "13800000000", "山东省德州市德城区天衢西路 45 号"),
    ("日照海钢贸易有限公司", "郑晓东", "13800000000", "山东省日照市岚山区沿海路 1 号"),
    ("张家港锦丰钢铁贸易有限公司", "吴建华", "13800000000", "江苏省张家港市锦丰镇沙钢大道 1 号"),
    ("淮北相山矿业销售有限公司", "徐海峰", "13800000000", "安徽省淮北市相山区人民路 168 号"),
    ("西安秦煤运销有限公司", "马晓军", "13800000000", "陕西省西安市高新区锦业路 2 号"),
    ("南京金陵能源有限公司", "高炳文", "13800000000", "江苏省南京市栖霞区甘家巷 98 号"),
    ("郑州豫能化工有限公司", "罗建军", "13800000000", "河南省郑州市郑东新区商务外环 22 号"),
    ("鄂尔多斯泰和煤炭运销有限公司", "巴特尔", "13800000000", "内蒙古鄂尔多斯市东胜区伊煤路 6 号"),
    ("大连港燃料贸易有限公司", "崔永刚", "13800000000", "辽宁省大连市中山区港湾街 12 号"),
    ("娄底涟水钢铁有限公司", "黄志远", "13800000000", "湖南省娄底市娄星区涟钢路 1 号"),
    ("三明闽光钢铁有限公司", "林建平", "13800000000", "福建省三明市梅列区工业中路 1 号"),
    ("天津滨海保税燃料有限公司", "郝天宇", "13800000000", "天津市滨海新区海滨大道 266 号"),
    ("重庆渝钢能源有限公司", "谭伟民", "13800000000", "重庆市大渡口区钢花路 8 号"),
]

SUPPLIERS = [
    ("大同左云一号煤矿", "王矿长", "13800000000", "山西省大同市左云县店湾镇"),
    ("鄂尔多斯铜川煤矿", "李矿长", "13800000000", "内蒙古鄂尔多斯市东胜区铜川镇"),
    ("榆林大柳塔煤业", "张矿长", "13800000000", "陕西省榆林市神木市大柳塔镇"),
    ("朔州安太堡露天煤矿", "刘矿长", "13800000000", "山西省朔州市平鲁区安太堡"),
    ("长治襄垣煤业", "赵矿长", "13800000000", "山西省长治市襄垣县侯堡镇"),
    ("宁夏灵武煤业", "陈矿长", "13800000000", "宁夏灵武市宁东镇"),
    ("昌吉准东煤业", "孙矿长", "13800000000", "新疆昌吉州准东经济技术开发区"),
    ("六盘水盘州煤业", "周矿长", "13800000000", "贵州省六盘水市盘州市红果镇"),
]

EXPENSE_SUBJECTS = [
    ("电费", 38000, 52000),
    ("水费", 6000, 9000),
    ("运输费", 45000, 78000),
    ("设备维修费", 12000, 36000),
    ("办公费", 1500, 4800),
    ("差旅费", 2000, 8000),
    ("安全费用", 9000, 16000),
]

EXPENSE_TYPES = [
    ("travel", "差旅费"),
    ("transport", "交通费"),
    ("office", "办公费"),
    ("entertainment", "招待费"),
    ("purchase", "采购杂费"),
    ("other", "其他"),
]

POLICY_DOCS = [
    {
        "title": "费用报销管理制度",
        "category": "policy",
        "file_name": "费用报销管理制度.docx",
        "folder": "11-费用报销管理制度",
        "content": [
            (
                "第一章 总则",
                [
                    "第一条 为规范公司费用报销行为，控制成本费用，提高资金使用效率，特制定本制度。",
                    "第二条 本制度适用于公司各部门及全体员工，包括差旅费、交通费、办公费、招待费、采购杂费及其他日常费用。",
                    "第三条 费用报销坚持“真实、合规、及时”原则，所有报销必须有真实业务背景和合法有效凭证。",
                ],
            ),
            (
                "第二章 报销标准",
                [
                    "第四条 差旅费：省内出差住宿标准 350 元/人/晚，省外出差住宿标准 450 元/人/晚；出差补贴按 80 元/人/天计发。",
                    "第五条 交通费：市内公共交通据实报销；自驾按 1.2 元/公里核定；长途出行优先选择高铁二等座。",
                    "第六条 业务招待费：单次不超过 2000 元，全年招待费不得超过部门年度预算的 8%，须提前审批。",
                    "第七条 办公费：单笔 500 元以下由部门负责人审批，500 元以上须报财务负责人审批。",
                    "第八条 采购杂费：须附采购清单、入库单及发票，三者金额一致方可报销。",
                ],
            ),
            (
                "第三章 报销流程",
                [
                    "第九条 员工在系统内提交报销工单，填写报销类型、金额、事由，并上传发票影像。",
                    "第十条 部门负责人审核业务真实性，财务负责人审核票据合规性与预算余额。",
                    "第十一条 单笔金额超过 5000 元的报销，须经总经理审批后付款。",
                    "第十二条 审核通过后由出纳在 3 个工作日内完成付款，付款方式优先银行转账。",
                ],
            ),
            (
                "第四章 时限与责任",
                [
                    "第十三条 费用发生后 30 日内须提交报销申请，跨年度费用原则上不予报销。",
                    "第十四条 报销人對票据真实性负责；提供虚假票据的，除追回款项外，按公司奖惩规定处理。",
                    "第十五条 财务部每月对报销情况进行抽查，抽查比例不低于 10%。",
                    "第十六条 本制度由财务部负责解释，自发布之日起执行。",
                ],
            ),
        ],
    },
    {
        "title": "财务管理制度",
        "category": "policy",
        "file_name": "财务管理制度.docx",
        "folder": "13-公司制度规范",
        "content": [
            (
                "第一章 总则",
                [
                    "第一条 为加强公司财务管理，规范会计核算与资金运作，制定本制度。",
                    "第二条 公司实行统一核算、分级管理的财务体制，财务部对总经理负责。",
                    "第三条 会计年度自公历 1 月 1 日起至 12 月 31 日止，采用权责发生制核算。",
                ],
            ),
            (
                "第二章 收入与应收管理",
                [
                    "第四条 煤炭销售以客户签收过磅单确认收入，销售订单审核通过后同步生成收入与应收账款记录。",
                    "第五条 销售回款原则上采用“先款后货”，长期合作客户可给予不超过 60 天的账期。",
                    "第六条 应收账款按账龄分为 30 天以内、31-60 天、61-90 天、90 天以上四档，分别计提 0%、5%、10%、30% 坏账准备。",
                    "第七条 财务部每月 5 日前出具应收账款账龄分析表，逾期 60 天以上的由业务部门专项催收。",
                ],
            ),
            (
                "第三章 成本与费用管理",
                [
                    "第八条 原煤采购成本按加权平均法核算，洗选加工成本按当月精煤产量分摊。",
                    "第九条 每月末进行存货盘点，账实差异超过 0.3% 的须查明原因并报财务负责人审批。",
                    "第十条 费用支出实行预算管理，超预算支出须履行专项审批程序。",
                ],
            ),
            (
                "第四章 资金与报表",
                [
                    "第十一条 单笔 10 万元以上的资金支付须经总经理审批，50 万元以上须集体决策。",
                    "第十二条 出纳与会计岗位分离，印鉴、网银 U 盾分人保管。",
                    "第十三条 财务部于次月 10 日前完成月度财务报表编制，包括收入、成本、费用、利润及应收应付情况。",
                    "第十四条 本制度由财务部负责解释，自发布之日起执行。",
                ],
            ),
        ],
    },
    {
        "title": "公司制度规范汇编",
        "category": "process",
        "file_name": "公司制度规范汇编.docx",
        "folder": "13-公司制度规范",
        "content": [
            (
                "第一章 考勤与休假",
                [
                    "第一条 公司实行标准工时制，生产一线实行三班轮换，班次为早班 8:00-16:00、中班 16:00-24:00、夜班 0:00-8:00。",
                    "第二条 员工迟到 30 分钟以内每次扣发当日绩效 10%，月累计超过 3 次按旷工半天处理。",
                    "第三条 请假须提前在系统提交申请，事假 3 天以内由部门负责人审批，3 天以上报总经理审批。",
                ],
            ),
            (
                "第二章 安全生产",
                [
                    "第四条 进入生产区域必须佩戴安全帽、防尘口罩，禁止携带火种。",
                    "第五条 每日班前会进行安全交底，每季度组织一次应急演练。",
                    "第六条 发现设备异常或安全隐患，任何人有权停止作业并立即上报，不得瞒报。",
                    "第七条 安全巡查由保安队每日执行，巡查记录须当日录入系统，发现隐患 2 小时内派单整改。",
                ],
            ),
            (
                "第三章 采购与销售",
                [
                    "第八条 原煤采购由采购部统一组织，单笔 50 万元以上采购须三家以上供应商比价。",
                    "第九条 供应商实行年度评审，质量、价格、交付及时率三项加权评分低于 70 分的暂停合作。",
                    "第十条 煤炭销售价格按品种执行公司定价：原煤 1000 元/吨，精煤 1500-2000 元/吨，具体价格由业务部在区间内根据市场情况确定。",
                    "第十一条 销售合同签订前须核查客户信用额度，超额度订单须财务负责人审批。",
                ],
            ),
            (
                "第四章 工单与协同",
                [
                    "第十二条 设备维修、费用报销、安全巡查、运输异常四类事项统一通过工单系统流转。",
                    "第十三条 工单按紧急程度分为紧急、高、普通、低四级，紧急工单 4 小时内响应。",
                    "第十四条 工单超时未处理的，系统自动预警并推送至部门负责人。",
                    "第十五条 本汇编由综合管理部负责解释，自发布之日起执行。",
                ],
            ),
        ],
    },
]


def money(value: float | Decimal | int) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def qty(value: float | Decimal | int) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def daterange(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def month_ranges(start: date, end: date) -> list[tuple[date, date]]:
    ranges: list[tuple[date, date]] = []
    cursor = start.replace(day=1)
    while cursor <= end:
        if cursor.month == 12:
            next_month = cursor.replace(year=cursor.year + 1, month=1, day=1)
        else:
            next_month = cursor.replace(month=cursor.month + 1, day=1)
        ranges.append((max(cursor, start), min(next_month - timedelta(days=1), end)))
        cursor = next_month
    return ranges


class Numberer:
    """按“前缀+日期”生成连续单据号，保证唯一。"""

    def __init__(self) -> None:
        self._seq: dict[str, int] = defaultdict(int)

    def next(self, prefix: str, day: date, width: int = 3) -> str:
        key = f"{prefix}{day:%Y%m%d}"
        self._seq[key] += 1
        return f"{key}{self._seq[key]:0{width}d}"


def reset_business_data(db) -> None:
    print("清理旧业务数据…")
    from sqlalchemy import text

    db.execute(
        text(
            """
            TRUNCATE TABLE
                work_order_expense, work_order_records, work_order_approvals,
                work_order_attachments, work_order_device, work_order_patrol,
                work_order_transport, work_orders,
                stock_movement_items, stock_movements, stock_check_items, stock_checks,
                sales_order_items, sales_orders, purchase_order_items, purchase_orders,
                finance_records, cash_flows, inventory, production_records,
                report_viewers, reports, customers, suppliers, products, warehouses
            RESTART IDENTITY CASCADE
            """
        )
    )
    db.commit()


def build_master(db) -> dict[str, Any]:
    print("写入主数据…")
    warehouses = {
        RAW_NAME: Warehouse(
            code="WH-YM", name="原煤储煤场", address="矿区一号储煤场", is_active=True
        ),
        WASHED_NAME: Warehouse(
            code="WH-JM", name="精煤储煤仓", address="洗选中心精煤仓", is_active=True
        ),
    }
    db.add_all(warehouses.values())
    db.flush()

    products = {
        RAW_NAME: Product(
            code="YM-4500",
            name=RAW_NAME,
            spec="热值 4500-5000 大卡，灰分 ≤28%",
            unit="吨",
            category="煤炭",
            purchase_price=money(780),
            sale_price=money(RAW_SALE_PRICE),
            is_active=True,
        ),
        WASHED_NAME: Product(
            code="JM-6500",
            name=WASHED_NAME,
            spec="热值 6500 大卡，灰分 ≤10.5%",
            unit="吨",
            category="煤炭",
            purchase_price=money(1180),
            sale_price=money(1750),
            is_active=True,
        ),
    }
    db.add_all(products.values())
    db.flush()

    customers = [
        Customer(
            code=f"C{i:03d}",
            name=name,
            contact_name=contact,
            phone=phone,
            address=address,
            credit_limit=money(random.randint(200, 800) * 10000),
            status="active",
        )
        for i, (name, contact, phone, address) in enumerate(CUSTOMERS, start=1)
    ]
    suppliers = [
        Supplier(
            code=f"S{i:03d}",
            name=name,
            contact_name=contact,
            phone=phone,
            address=address,
            payment_type="credit" if i % 2 == 0 else "cash",
            status="active",
        )
        for i, (name, contact, phone, address) in enumerate(SUPPLIERS, start=1)
    ]
    db.add_all(customers + suppliers)
    db.flush()
    return {
        "warehouses": warehouses,
        "products": products,
        "customers": customers,
        "suppliers": suppliers,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default=DEFAULT_START.isoformat())
    parser.add_argument("--end", default=DEFAULT_END.isoformat())
    parser.add_argument("--out", default=str(OUT_ROOT))
    parser.add_argument("--keep-data", action="store_true", help="不清空现有业务数据")
    args = parser.parse_args()
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    out_root = Path(args.out) / f"{start:%Y%m%d}-{end:%Y%m%d}"

    db = SessionLocal()
    try:
        if not args.keep_data:
            reset_business_data(db)
        master = build_master(db)
        generate_year(db, master, start, end)
        print("生成月度财务报表…")
        generate_reports(db, start, end)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    dataset = collect_datasets(start, end)
    print(f"导出文件到 {out_root} …")
    write_files(dataset, out_root)
    upload_policies(out_root)
    print("完成：", out_root)


def _user(db, employee_no: str) -> User:
    row = db.scalar(select(User).where(User.employee_no == employee_no))
    if row is None:
        raise SystemExit(f"缺少账号 {employee_no}")
    return row


def _stamp(day: date, hour: int = 9) -> datetime:
    return datetime(day.year, day.month, day.day, hour, 0, tzinfo=UTC)


def _finance(
    db,
    numbers: Numberer,
    *,
    record_type: str,
    amount: Decimal,
    day: date,
    source_type: str,
    source_id: int | None,
    counterparty_type: str = "none",
    counterparty_id: int | None = None,
    department_id: int | None,
    account_subject: str | None = None,
    creator: User,
    reviewer: User | None = None,
    remark: str | None = None,
) -> None:
    now = _stamp(day, 10)
    db.add(
        FinanceRecord(
            record_no=numbers.next("FR", day),
            record_type=record_type,
            amount=amount,
            record_date=day,
            accounting_period=f"{day:%Y-%m}",
            counterparty_type=counterparty_type,
            counterparty_id=counterparty_id,
            source_type=source_type,
            source_id=source_id,
            account_subject=account_subject,
            department_id=department_id,
            status="approved",
            created_by=creator.id,
            reviewer_id=(reviewer or creator).id,
            reviewed_at=now,
            remark=remark,
            is_mock=False,
            created_at=now,
            updated_at=now,
        )
    )


def _movement(
    db,
    numbers: Numberer,
    stock: dict[tuple[int, int], Decimal],
    *,
    day: date,
    movement_type: str,
    warehouse: Warehouse,
    product: Product,
    quantity: Decimal,
    department_id: int,
    source_type: str,
    source_id: int | None,
    creator: User,
    executor: User,
    reviewer: User,
    remark: str | None = None,
) -> tuple[StockMovement, Decimal]:
    key = (warehouse.id, product.id)
    before = stock.get(key, Decimal("0"))
    sign = Decimal("1") if movement_type == "inbound" else Decimal("-1")
    after = before + sign * quantity
    if after < 0:
        raise SystemExit(f"{day} {warehouse.name}/{product.name} 库存不足，无法出库")
    stock[key] = after
    now = _stamp(day, 8)
    movement = StockMovement(
        movement_no=numbers.next("SM", day),
        movement_type=movement_type,
        warehouse_id=warehouse.id,
        department_id=department_id,
        source_type=source_type,
        source_id=source_id,
        status="approved",
        created_by=creator.id,
        executor_id=executor.id,
        executed_at=now,
        reviewer_id=reviewer.id,
        reviewed_at=now,
        version=1,
        remark=remark,
        is_mock=False,
        created_at=now,
        updated_at=now,
    )
    db.add(movement)
    db.flush()
    db.add(
        StockMovementItem(
            movement_id=movement.id,
            line_no=1,
            product_id=product.id,
            quantity=quantity,
            before_quantity=before,
            after_quantity=after,
        )
    )
    return movement, after


def generate_year(db, master: dict[str, Any], start: date, end: date) -> None:
    print(f"生成 {start} ~ {end} 业务流水…")
    numbers = Numberer()
    users = {
        "gm": _user(db, "M0001"),
        "accountant": _user(db, "AC0001"),
        "cashier": _user(db, "CA0001"),
        "finance_head": _user(db, "F0001"),
        "sales": _user(db, "S0001"),
        "purchaser": _user(db, "V2P01"),
        "producer": _user(db, "WK0001"),
    }
    dept_finance = users["accountant"].department_id or users["finance_head"].department_id
    dept_sales = users["sales"].department_id
    dept_purchase = users["purchaser"].department_id or dept_sales
    dept_production = users["producer"].department_id

    products: dict[str, Product] = master["products"]
    warehouses: dict[str, Warehouse] = master["warehouses"]
    customers: list[Customer] = master["customers"]
    suppliers: list[Supplier] = master["suppliers"]
    raw = products[RAW_NAME]
    washed = products[WASHED_NAME]
    wh_raw = warehouses[RAW_NAME]
    wh_washed = warehouses[WASHED_NAME]

    stock: dict[tuple[int, int], Decimal] = {}
    # 期初库存
    for warehouse, product, amount in (
        (wh_raw, raw, Decimal("5000")),
        (wh_washed, washed, Decimal("3000")),
    ):
        _movement(
            db,
            numbers,
            stock,
            day=start - timedelta(days=1),
            movement_type="inbound",
            warehouse=warehouse,
            product=product,
            quantity=amount,
            department_id=dept_purchase,
            source_type="manual",
            source_id=None,
            creator=users["accountant"],
            executor=users["cashier"],
            reviewer=users["finance_head"],
            remark="期初库存",
        )

    teams = ["生产一班", "生产二班", "生产三班"]
    collected: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))

    for day in daterange(start, end):
        # 1) 原煤生产
        raw_output = qty(random.randint(1450, 1780))
        unit_cost_raw = money(random.uniform(200, 225))
        db.add(
            ProductionRecord(
                record_no=numbers.next("PR", day),
                record_date=day,
                team=random.choice(teams),
                product_id=raw.id,
                quantity=raw_output,
                unit_cost=unit_cost_raw,
                total_cost=money(raw_output * unit_cost_raw),
                wash_yield=None,
                department_id=dept_production,
                status="approved",
                created_by=users["producer"].id,
                remark="综采工作面日产量",
                created_at=_stamp(day, 18),
                updated_at=_stamp(day, 18),
            )
        )
        db.flush()
        _movement(
            db,
            numbers,
            stock,
            day=day,
            movement_type="inbound",
            warehouse=wh_raw,
            product=raw,
            quantity=raw_output,
            department_id=dept_production,
            source_type="manual",
            source_id=None,
            creator=users["producer"],
            executor=users["producer"],
            reviewer=users["finance_head"],
            remark="生产入库",
        )
        _finance(
            db,
            numbers,
            record_type="cost",
            amount=money(raw_output * unit_cost_raw),
            day=day,
            source_type="manual",
            source_id=None,
            department_id=dept_production,
            account_subject="原煤生产成本",
            creator=users["accountant"],
            reviewer=users["finance_head"],
            remark="原煤开采成本",
        )

        # 2) 洗选：领取原煤 → 产出精煤
        wash_input = min(qty(random.randint(1400, 1600)), stock[(wh_raw.id, raw.id)])
        _movement(
            db,
            numbers,
            stock,
            day=day,
            movement_type="outbound",
            warehouse=wh_raw,
            product=raw,
            quantity=wash_input,
            department_id=dept_production,
            source_type="manual",
            source_id=None,
            creator=users["producer"],
            executor=users["producer"],
            reviewer=users["finance_head"],
            remark="洗选领用",
        )
        yield_rate = Decimal(str(round(random.uniform(0.58, 0.64), 4)))
        washed_output = qty(wash_input * yield_rate)
        unit_cost_washed = money(random.uniform(165, 195))
        db.add(
            ProductionRecord(
                record_no=numbers.next("PR", day),
                record_date=day,
                team=random.choice(teams),
                product_id=washed.id,
                quantity=washed_output,
                unit_cost=unit_cost_washed,
                total_cost=money(washed_output * unit_cost_washed),
                wash_yield=qty(yield_rate * 100),
                department_id=dept_production,
                status="approved",
                created_by=users["producer"].id,
                remark="重介洗选产出",
                created_at=_stamp(day, 19),
                updated_at=_stamp(day, 19),
            )
        )
        db.flush()
        _movement(
            db,
            numbers,
            stock,
            day=day,
            movement_type="inbound",
            warehouse=wh_washed,
            product=washed,
            quantity=washed_output,
            department_id=dept_production,
            source_type="manual",
            source_id=None,
            creator=users["producer"],
            executor=users["producer"],
            reviewer=users["finance_head"],
            remark="生产入库",
        )
        _finance(
            db,
            numbers,
            record_type="cost",
            amount=money(washed_output * unit_cost_washed),
            day=day,
            source_type="manual",
            source_id=None,
            department_id=dept_production,
            account_subject="精煤洗选成本",
            creator=users["accountant"],
            reviewer=users["finance_head"],
            remark="精煤洗选成本",
        )

        # 3) 采购原煤：每 5 天一张采购单
        if day.toordinal() % 5 == 0:
            supplier = random.choice(suppliers)
            purchase_qty = qty(random.randint(2000, 3200))
            price = money(random.uniform(720, 820))
            order = PurchaseOrder(
                order_no=numbers.next("PO", day),
                supplier_id=supplier.id,
                purchaser_id=users["purchaser"].id,
                department_id=dept_purchase,
                order_date=day,
                expected_date=day + timedelta(days=3),
                status="approved",
                total_amount=money(purchase_qty * price),
                reviewer_id=users["finance_head"].id,
                reviewed_at=_stamp(day, 11),
                version=1,
                remark="原煤采购",
                is_mock=False,
                created_at=_stamp(day, 9),
                updated_at=_stamp(day, 11),
            )
            db.add(order)
            db.flush()
            db.add(
                PurchaseOrderItem(
                    purchase_order_id=order.id,
                    line_no=1,
                    product_id=raw.id,
                    quantity=purchase_qty,
                    unit_price=price,
                    amount=money(purchase_qty * price),
                )
            )
            movement, _ = _movement(
                db,
                numbers,
                stock,
                day=day,
                movement_type="inbound",
                warehouse=wh_raw,
                product=raw,
                quantity=purchase_qty,
                department_id=dept_purchase,
                source_type="purchase_order",
                source_id=order.id,
                creator=users["purchaser"],
                executor=users["cashier"],
                reviewer=users["finance_head"],
                remark=f"采购入库 {order.order_no}",
            )
            _finance(
                db,
                numbers,
                record_type="payable",
                amount=order.total_amount,
                day=day,
                source_type="purchase_order",
                source_id=order.id,
                counterparty_type="supplier",
                counterparty_id=supplier.id,
                department_id=dept_purchase,
                account_subject="原煤采购",
                creator=users["accountant"],
                reviewer=users["finance_head"],
                remark="采购应付",
            )
            _finance(
                db,
                numbers,
                record_type="cost",
                amount=money(purchase_qty * price),
                day=day,
                source_type="stock_movement",
                source_id=movement.id,
                counterparty_type="supplier",
                counterparty_id=supplier.id,
                department_id=dept_purchase,
                account_subject="原煤采购成本",
                creator=users["accountant"],
                reviewer=users["finance_head"],
                remark="采购入库成本",
            )
            pay_day = day + timedelta(days=random.randint(15, 40))
            if pay_day <= end:
                db.add(
                    CashFlow(
                        flow_no=numbers.next("CF", pay_day),
                        direction="out",
                        amount=order.total_amount,
                        flow_date=pay_day,
                        payment_method="银行转账",
                        related_order_type="purchase_order",
                        related_order_id=order.id,
                        status="approved",
                        department_id=dept_finance,
                        created_by=users["cashier"].id,
                        reviewer_id=users["accountant"].id,
                        reviewed_at=_stamp(pay_day, 15),
                        remark="采购付款",
                        is_mock=False,
                        created_at=_stamp(pay_day, 14),
                        updated_at=_stamp(pay_day, 15),
                    )
                )

        # 4) 销售：每天 3 单
        month = day.month
        seasonal = Decimal("1.10") if month in (11, 12, 1, 2) else Decimal("1.00")
        for _ in range(random.choice((2, 3, 3, 4))):
            customer = random.choice(customers)
            product = washed if random.random() < 0.6 else raw
            warehouse = wh_washed if product.id == washed.id else wh_raw
            available = stock.get((warehouse.id, product.id), Decimal("0"))
            if available < 300:
                continue
            if product.id == raw.id:
                price = money(RAW_SALE_PRICE)
                amount_label = random.randint(350, 750)
            else:
                price = money(Decimal(random.randint(*WASHED_PRICE_RANGE)) * seasonal)
                price = min(price, money(WASHED_PRICE_RANGE[1]))
                amount_label = random.randint(550, 1150)
            sale_qty = qty(min(Decimal(str(amount_label)), available * Decimal("0.35")))
            if sale_qty < 200:
                continue
            order = SalesOrder(
                order_no=numbers.next("SO", day),
                customer_id=customer.id,
                salesperson_id=users["sales"].id,
                department_id=dept_sales,
                order_date=day,
                status="approved",
                total_amount=money(sale_qty * price),
                reviewer_id=users["finance_head"].id,
                reviewed_at=_stamp(day, 11),
                version=1,
                remark=f"{product.name}销售",
                is_mock=False,
                created_at=_stamp(day, 9),
                updated_at=_stamp(day, 11),
            )
            db.add(order)
            db.flush()
            db.add(
                SalesOrderItem(
                    sales_order_id=order.id,
                    line_no=1,
                    product_id=product.id,
                    quantity=sale_qty,
                    unit_price=price,
                    amount=money(sale_qty * price),
                )
            )
            _movement(
                db,
                numbers,
                stock,
                day=day,
                movement_type="outbound",
                warehouse=warehouse,
                product=product,
                quantity=sale_qty,
                department_id=dept_sales,
                source_type="sales_order",
                source_id=order.id,
                creator=users["sales"],
                executor=users["cashier"],
                reviewer=users["finance_head"],
                remark=f"销售出库 {order.order_no}",
            )
            for record_type in ("income", "receivable"):
                _finance(
                    db,
                    numbers,
                    record_type=record_type,
                    amount=order.total_amount,
                    day=day,
                    source_type="sales_order",
                    source_id=order.id,
                    counterparty_type="customer",
                    counterparty_id=customer.id,
                    department_id=dept_sales,
                    account_subject="煤炭销售",
                    creator=users["accountant"],
                    reviewer=users["finance_head"],
                    remark="销售收入" if record_type == "income" else "销售应收",
                )

            roll = random.random()
            pay_day = day + timedelta(days=random.randint(12, 60))
            if pay_day <= end and roll < 0.85:
                paid = order.total_amount
            elif pay_day <= end and roll < 0.95:
                paid = money(order.total_amount * Decimal("0.5"))
            else:
                paid = Decimal("0")
            if paid > 0:
                collected[order.id] += paid
                db.add(
                    CashFlow(
                        flow_no=numbers.next("CF", pay_day),
                        direction="in",
                        amount=paid,
                        flow_date=pay_day,
                        payment_method=random.choice(("银行转账", "银行承兑汇票", "电汇")),
                        related_order_type="sales_order",
                        related_order_id=order.id,
                        status="approved",
                        department_id=dept_finance,
                        created_by=users["cashier"].id,
                        reviewer_id=users["accountant"].id,
                        reviewed_at=_stamp(pay_day, 15),
                        remark="销售回款",
                        is_mock=False,
                        created_at=_stamp(pay_day, 14),
                        updated_at=_stamp(pay_day, 15),
                    )
                )

        # 5) 日常费用
        for subject, low, high in random.sample(EXPENSE_SUBJECTS, k=2):
            amount = money(random.uniform(low, high))
            _finance(
                db,
                numbers,
                record_type="expense",
                amount=amount,
                day=day,
                source_type="manual",
                source_id=None,
                department_id=dept_finance,
                account_subject=subject,
                creator=users["accountant"],
                reviewer=users["finance_head"],
                remark=f"{subject}支出",
            )

        # 6) 月末工资与折旧
        if (day + timedelta(days=1)).month != day.month:
            for subject, amount in (("工资薪金", 860000), ("折旧费用", 240000)):
                _finance(
                    db,
                    numbers,
                    record_type="expense",
                    amount=money(amount),
                    day=day,
                    source_type="manual",
                    source_id=None,
                    department_id=dept_finance,
                    account_subject=subject,
                    creator=users["accountant"],
                    reviewer=users["finance_head"],
                    remark=f"当月{subject}",
                )

        # 7) 员工报销：每周两单
        if day.weekday() in (2, 5):
            creator = random.choice(
                [users["sales"], users["purchaser"], users["producer"], users["cashier"]]
            )
            expense_type, label = random.choice(EXPENSE_TYPES)
            amount = money(random.uniform(180, 4800))
            order_no = numbers.next("WO", day)
            db.add(
                WorkOrder(
                    order_no=order_no,
                    category="expense_reimbursement",
                    title=f"{label}报销 {amount} 元",
                    description=f"{creator.name}提交{label}报销，金额 {amount} 元，票据齐全。",
                    priority="normal",
                    status="completed",
                    source_type=None,
                    department_id=creator.department_id,
                    creator_id=creator.id,
                    assignee_id=creator.id,
                    reviewer_id=users["finance_head"].id,
                    assigned_at=_stamp(day, 9),
                    started_at=_stamp(day, 10),
                    submitted_at=_stamp(day, 11),
                    completed_at=_stamp(day, 16),
                    version=2,
                    is_mock=False,
                    created_at=_stamp(day, 9),
                    updated_at=_stamp(day, 16),
                )
            )
            db.flush()
            work_order = db.scalar(select(WorkOrder).where(WorkOrder.order_no == order_no))
            db.add(
                WorkOrderExpense(
                    work_order_id=work_order.id, expense_type=expense_type, amount=amount
                )
            )
            db.add(
                WorkOrderRecord(
                    work_order_id=work_order.id,
                    action="create",
                    from_status=None,
                    to_status="supplementing",
                    operator_id=creator.id,
                    operator_name=creator.name,
                    operator_position=None,
                    content="提交报销工单",
                    created_at=_stamp(day, 9),
                )
            )
            _finance(
                db,
                numbers,
                record_type="expense",
                amount=amount,
                day=day,
                source_type="work_order",
                source_id=work_order.id,
                department_id=creator.department_id,
                account_subject=label,
                creator=users["accountant"],
                reviewer=users["finance_head"],
                remark=f"员工报销 {order_no}",
            )

        if day.day == 1:
            db.commit()

    for (warehouse_id, product_id), amount in stock.items():
        db.add(
            Inventory(
                warehouse_id=warehouse_id,
                product_id=product_id,
                quantity=amount,
            )
        )
    db.commit()
    print("业务流水写入完成。")


def generate_reports(db, start: date, end: date) -> list[Report]:
    reports: list[Report] = []
    for month_start, month_end in month_ranges(start, end):
        try:
            report, _ = report_service.generate(
                db, "monthly", period_start=month_start, period_end=month_end
            )
            reports.append(report)
        except Exception as exc:  # noqa: BLE001 - 单月失败不影响其他月份
            print(f"  {month_start:%Y-%m} 报表生成失败：{exc}")
    return reports


def _read_rows(db, statement) -> tuple[list[str], list[list[Any]]]:
    result = db.execute(statement)
    headers = list(result.keys())
    rows = [[("" if value is None else value) for value in row] for row in result.fetchall()]
    return headers, rows


def collect_datasets(start: date, end: date) -> list[dict[str, Any]]:
    """从数据库读取 13 类数据，供导出使用。"""
    from sqlalchemy import text

    db = SessionLocal()
    datasets: list[dict[str, Any]] = []
    try:
        queries: list[tuple[str, str, str]] = [
            (
                "01-客户档案",
                "客户档案",
                """
                SELECT code AS 客户编码, name AS 客户名称, contact_name AS 联系人, phone AS 联系电话,
                       address AS 地址, credit_limit AS 信用额度, status AS 状态,
                       created_at::date AS 建档日期
                FROM customers WHERE deleted_at IS NULL ORDER BY code
                """,
            ),
            (
                "02-供应商档案",
                "供应商档案",
                """
                SELECT code AS 供应商编码, name AS 供应商名称, contact_name AS 联系人,
                       phone AS 联系电话, address AS 地址, payment_type AS 结算方式,
                       status AS 状态, created_at::date AS 建档日期
                FROM suppliers WHERE deleted_at IS NULL ORDER BY code
                """,
            ),
            (
                "03-销售订单",
                "销售订单",
                """
                SELECT so.order_no AS 订单号, so.order_date AS 订单日期, c.name AS 客户,
                       p.name AS 产品, i.quantity AS 数量吨, i.unit_price AS 单价,
                       i.amount AS 金额, so.status AS 状态
                FROM sales_orders so
                JOIN sales_order_items i ON i.sales_order_id = so.id
                JOIN customers c ON c.id = so.customer_id
                JOIN products p ON p.id = i.product_id
                WHERE so.deleted_at IS NULL
                ORDER BY so.order_date, so.order_no
                """,
            ),
            (
                "04-采购订单",
                "采购订单",
                """
                SELECT po.order_no AS 订单号, po.order_date AS 订单日期, s.name AS 供应商,
                       p.name AS 产品, i.quantity AS 数量吨, i.unit_price AS 单价,
                       i.amount AS 金额, po.status AS 状态
                FROM purchase_orders po
                JOIN purchase_order_items i ON i.purchase_order_id = po.id
                JOIN suppliers s ON s.id = po.supplier_id
                JOIN products p ON p.id = i.product_id
                WHERE po.deleted_at IS NULL
                ORDER BY po.order_date, po.order_no
                """,
            ),
            (
                "05-每日生产记录",
                "每日生产记录",
                """
                SELECT pr.record_date AS 日期, pr.team AS 班组, p.name AS 产品,
                       pr.quantity AS 产量吨, pr.unit_cost AS 单位成本,
                       pr.total_cost AS 总成本, pr.wash_yield AS 洗选回收率,
                       pr.remark AS 备注
                FROM production_records pr
                JOIN products p ON p.id = pr.product_id
                WHERE pr.deleted_at IS NULL
                ORDER BY pr.record_date, pr.record_no
                """,
            ),
            (
                "06-库存台账",
                "库存台账",
                """
                SELECT sm.movement_no AS 单据号, sm.executed_at::date AS 日期,
                       CASE sm.movement_type WHEN 'inbound' THEN '入库' ELSE '出库' END AS 类型,
                       w.name AS 仓库, p.name AS 产品, si.quantity AS 数量吨,
                       si.before_quantity AS 变动前, si.after_quantity AS 结存,
                       CASE sm.source_type WHEN 'purchase_order' THEN '采购入库'
                            WHEN 'sales_order' THEN '销售出库' ELSE '其他' END AS 来源,
                       sm.remark AS 备注
                FROM stock_movements sm
                JOIN stock_movement_items si ON si.movement_id = sm.id
                JOIN warehouses w ON w.id = sm.warehouse_id
                JOIN products p ON p.id = si.product_id
                WHERE sm.deleted_at IS NULL AND w.name IN ('原煤储煤场','精煤储煤仓')
                ORDER BY sm.executed_at, sm.movement_no
                """,
            ),
            (
                "07-销售回款",
                "销售回款",
                """
                SELECT cf.flow_no AS 流水号, cf.flow_date AS 回款日期, c.name AS 客户,
                       so.order_no AS 关联订单, cf.amount AS 回款金额,
                       cf.payment_method AS 收款方式, cf.status AS 状态
                FROM cash_flows cf
                JOIN sales_orders so ON so.id = cf.related_order_id
                JOIN customers c ON c.id = so.customer_id
                WHERE cf.direction = 'in' AND cf.related_order_type = 'sales_order'
                ORDER BY cf.flow_date, cf.flow_no
                """,
            ),
            (
                "08-应收账款",
                "应收账款",
                """
                SELECT so.order_no AS 订单号, so.order_date AS 订单日期, c.name AS 客户,
                       r.amount AS 应收金额,
                       COALESCE(col.paid, 0) AS 已回款,
                       r.amount - COALESCE(col.paid, 0) AS 未回款,
                       CURRENT_DATE - so.order_date AS 账龄天数,
                       CASE WHEN r.amount - COALESCE(col.paid, 0) <= 0 THEN '已结清'
                            WHEN CURRENT_DATE - so.order_date > 90 THEN '逾期90天以上'
                            WHEN CURRENT_DATE - so.order_date > 60 THEN '逾期61-90天'
                            WHEN CURRENT_DATE - so.order_date > 30 THEN '逾期31-60天'
                            ELSE '30天内' END AS 账龄区间
                FROM finance_records r
                JOIN sales_orders so ON so.id = r.source_id AND r.source_type = 'sales_order'
                JOIN customers c ON c.id = so.customer_id
                LEFT JOIN (
                    SELECT related_order_id, SUM(amount) AS paid
                    FROM cash_flows WHERE direction = 'in' GROUP BY related_order_id
                ) col ON col.related_order_id = so.id
                WHERE r.record_type = 'receivable' AND r.status = 'approved'
                ORDER BY so.order_date
                """,
            ),
            (
                "09-费用明细",
                "费用明细",
                """
                SELECT record_no AS 记录号, record_date AS 日期,
                       COALESCE(account_subject, '其他') AS 费用科目, amount AS 金额,
                       status AS 状态, COALESCE(remark, '') AS 备注
                FROM finance_records
                WHERE record_type = 'expense' AND source_type <> 'work_order'
                ORDER BY record_date, record_no
                """,
            ),
            (
                "10-员工报销记录",
                "员工报销记录",
                """
                SELECT wo.order_no AS 工单号, wo.created_at::date AS 日期,
                       u.name AS 报销人, we.expense_type AS 报销类型,
                       we.amount AS 金额, wo.status AS 状态, wo.title AS 说明
                FROM work_orders wo
                JOIN users u ON u.id = wo.creator_id
                JOIN work_order_expense we ON we.work_order_id = wo.id
                WHERE wo.category = 'expense_reimbursement' AND wo.deleted_at IS NULL
                ORDER BY wo.created_at
                """,
            ),
        ]
        for folder, title, sql in queries:
            headers, rows = _read_rows(db, text(sql))
            datasets.append({"folder": folder, "title": title, "headers": headers, "rows": rows})

        report_headers = [
            "月份",
            "销售收入",
            "销售成本",
            "毛利",
            "费用合计",
            "净利润",
            "期末应收",
            "期末应付",
            "回款金额",
            "付款金额",
        ]
        report_rows = [
            list(row)
            for row in db.execute(
                text(
                    """
                    WITH f AS (
                        SELECT accounting_period,
                               SUM(CASE WHEN record_type='income' THEN amount ELSE 0 END) AS income,
                               SUM(CASE WHEN record_type='cost' THEN amount ELSE 0 END) AS cost,
                               SUM(CASE WHEN record_type='expense' THEN amount ELSE 0 END) AS expense,
                               SUM(CASE WHEN record_type='receivable' THEN amount ELSE 0 END) AS receivable,
                               SUM(CASE WHEN record_type='payable' THEN amount ELSE 0 END) AS payable
                        FROM finance_records WHERE status='approved' GROUP BY accounting_period
                    ),
                    c AS (
                        SELECT to_char(flow_date,'YYYY-MM') AS ym,
                               SUM(CASE WHEN direction='in' THEN amount ELSE 0 END) AS cash_in,
                               SUM(CASE WHEN direction='out' THEN amount ELSE 0 END) AS cash_out
                        FROM cash_flows WHERE status='approved' GROUP BY ym
                    )
                    SELECT f.accounting_period, f.income, f.cost, f.income - f.cost AS gross,
                           f.expense, f.income - f.cost - f.expense AS net_profit,
                           f.receivable, f.payable, COALESCE(c.cash_in,0), COALESCE(c.cash_out,0)
                    FROM f LEFT JOIN c ON c.ym = f.accounting_period
                    ORDER BY f.accounting_period
                    """
                )
            ).fetchall()
        ]
        datasets.append(
            {
                "folder": "12-财务报表",
                "title": "月度财务报表",
                "headers": report_headers,
                "rows": report_rows,
                "report_only": True,
            }
        )
    finally:
        db.close()
    return datasets


def _md_cell(value: Any) -> str:
    text = str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def write_files(datasets: list[dict[str, Any]], out_root: Path) -> None:
    for item in datasets:
        folder = out_root / item["folder"]
        folder.mkdir(parents=True, exist_ok=True)
        write_csv(folder / f"{item['title']}.csv", item["headers"], item["rows"])
        write_md(folder / f"{item['title']}.md", item["title"], item["headers"], item["rows"])
        write_txt(folder / f"{item['title']}.txt", item["title"], item["headers"], item["rows"])
        write_xlsx(folder / f"{item['title']}.xlsx", item["title"], item["headers"], item["rows"])
        write_docx(folder / f"{item['title']}.docx", item["title"], item["headers"], item["rows"])
        write_pdf(folder / f"{item['title']}.pdf", item["title"], item["headers"], item["rows"])
        print(f"  {item['folder']}：{len(item['rows'])} 行")


def write_csv(path: Path, headers: list[str], rows: list[list[Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)


def write_md(path: Path, title: str, headers: list[str], rows: list[list[Any]]) -> None:
    lines = [f"# {title}", "", f"共 {len(rows)} 条记录。", ""]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "|".join(["---"] * len(headers)) + "|")
    for row in rows:
        lines.append("| " + " | ".join(_md_cell(cell) for cell in row) + " |")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_txt(path: Path, title: str, headers: list[str], rows: list[list[Any]]) -> None:
    lines = [title, f"共 {len(rows)} 条记录", ""]
    lines.append("\t".join(headers))
    for row in rows:
        lines.append("\t".join("" if cell is None else str(cell) for cell in row))
    path.write_text("\n".join(lines), encoding="utf-8")


def write_xlsx(path: Path, title: str, headers: list[str], rows: list[list[Any]]) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = title[:30]
    sheet.append(headers)
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F4E79")
        cell.alignment = Alignment(horizontal="center", vertical="center")
    for row in rows:
        sheet.append(row)
    for index, header in enumerate(headers, start=1):
        width = max(len(str(header)) * 2 + 4, 12)
        sheet.column_dimensions[get_column_letter(index)].width = min(width, 40)
    sheet.freeze_panes = "A2"
    workbook.save(path)


def write_docx(
    path: Path, title: str, headers: list[str], rows: list[list[Any]], limit: int = 800
) -> None:
    from docx import Document
    from docx.shared import Pt

    document = Document()
    document.add_heading(title, level=1)
    document.add_paragraph(
        f"共 {len(rows)} 条记录" + (f"，本文件展示前 {limit} 条" if len(rows) > limit else "")
    )
    table = document.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    for index, header in enumerate(headers):
        cell = table.rows[0].cells[index]
        cell.text = str(header)
        for run in cell.paragraphs[0].runs:
            run.font.bold = True
            run.font.size = Pt(8)
    for row in rows[:limit]:
        cells = table.add_row().cells
        for index, value in enumerate(row):
            cells[index].text = "" if value is None else str(value)
            for paragraph in cells[index].paragraphs:
                for run in paragraph.runs:
                    run.font.size = Pt(8)
    document.save(path)


def write_pdf(
    path: Path, title: str, headers: list[str], rows: list[list[Any]], limit: int = 500
) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    try:
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    except Exception:
        pass
    font = "STSong-Light"
    style = ParagraphStyle("cn", fontName=font, fontSize=8, leading=10)
    title_style = ParagraphStyle("title", fontName=font, fontSize=15, leading=20, spaceAfter=6)
    doc = SimpleDocTemplate(
        str(path),
        pagesize=landscape(A4),
        leftMargin=18,
        rightMargin=18,
        topMargin=18,
        bottomMargin=18,
        title=title,
    )
    story: list[Any] = [Paragraph(title, title_style)]
    note = f"共 {len(rows)} 条记录" + (
        f"，PDF 仅展示前 {limit} 条，完整数据见同名 xlsx/csv" if len(rows) > limit else ""
    )
    story.append(Paragraph(note, style))
    story.append(Spacer(1, 6))
    data = [headers] + [
        [Paragraph("" if value is None else str(value), style) for value in row]
        for row in rows[:limit]
    ]
    table = Table(data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), font),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#BFBFBF")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F5FA")]),
            ]
        )
    )
    story.append(table)
    doc.build(story)


def upload_policies(out_root: Path) -> None:
    """把制度类文档写入知识库并同步解析成分块。"""
    print("导入制度文档到知识库…")
    db = SessionLocal()
    try:
        manager = db.scalar(select(User).where(User.employee_no == "A0001"))
        if manager is None:
            print("  跳过：缺少综合管理账号 A0001")
            return
        principal = load_principal(db, manager)
        for item in POLICY_DOCS:
            existing = db.scalar(
                select(KnowledgeDocument).where(
                    KnowledgeDocument.title == item["title"],
                    KnowledgeDocument.deleted_at.is_(None),
                )
            )
            if existing is not None:
                print(f"  已存在，跳过：{item['title']}")
                continue
            folder = out_root / item["folder"]
            folder.mkdir(parents=True, exist_ok=True)
            docx_path = folder / item["file_name"]
            write_policy_docx(docx_path, item)
            write_policy_texts(folder, item)
            try:
                data = docx_path.read_bytes()
                created = knowledge_service.upload_document(
                    db,
                    principal,
                    file_name=item["file_name"],
                    data=data,
                    title=item["title"],
                    category=item["category"],
                    visibility_scope="company",
                    is_mock=False,
                )
                _wait_parsed(db, created["id"])
                print(f"  已入库：{item['title']}（id={created['id']}）")
            except Exception as exc:  # noqa: BLE001 - 单个文档失败不影响其余
                print(f"  入库失败：{item['title']} -> {exc}")
    finally:
        db.close()


def _wait_parsed(db, document_id: int, timeout: int = 90) -> None:
    """等待后台解析完成；若仍无分块则同步解析一次。"""
    import time

    from app.models.knowledge import KnowledgeChunk

    for _ in range(timeout):
        db.expire_all()
        status = db.scalar(
            select(KnowledgeDocument.status).where(KnowledgeDocument.id == document_id)
        )
        if status == "ready":
            return
        time.sleep(1)
    count = db.scalar(
        select(func.count())
        .select_from(KnowledgeChunk)
        .where(KnowledgeChunk.document_id == document_id)
    )
    if not count:
        ingest_service.parse_document(document_id, 1)
    db.expire_all()


def write_policy_docx(path: Path, item: dict[str, Any]) -> None:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt

    document = Document()
    title = document.add_heading(item["title"], level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    document.add_paragraph("发布单位：企业综合管理部    执行日期：2025-11-01    版本：V1.0")
    for heading, paragraphs in item["content"]:
        document.add_heading(heading, level=1)
        for text in paragraphs:
            paragraph = document.add_paragraph(text)
            paragraph.paragraph_format.first_line_indent = Pt(21)
    document.save(path)


def write_policy_texts(folder: Path, item: dict[str, Any]) -> None:
    lines = [f"# {item['title']}", ""]
    for heading, paragraphs in item["content"]:
        lines.append(f"## {heading}")
        lines.extend(paragraphs)
        lines.append("")
    text = "\n".join(lines)
    (folder / f"{item['title']}.md").write_text(text, encoding="utf-8")
    (folder / f"{item['title']}.txt").write_text(text, encoding="utf-8")
    write_pdf(
        folder / f"{item['title']}.pdf",
        item["title"],
        ["章节", "条款"],
        [[heading, text] for heading, paragraphs in item["content"] for text in paragraphs],
        limit=200,
    )


if __name__ == "__main__":
    main()
