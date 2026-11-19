"""计算工具：对现有数据做四则运算，供 Agent 实时计算使用。"""

from __future__ import annotations

import ast
import operator
import re
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

_BINARY = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.FloorDiv: operator.floordiv,
}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
MAX_EXPONENT = 8


def _eval_node(node: ast.AST) -> Decimal:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
        return Decimal(str(node.value))
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > MAX_EXPONENT:
            raise ValueError("指数过大")
        return Decimal(str(_BINARY[type(node.op)](left, right)))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return Decimal(str(_UNARY[type(node.op)](_eval_node(node.operand))))
    raise ValueError("不支持的表达式")


def evaluate(expression: str) -> Decimal:
    """安全计算四则运算表达式，不使用 eval。"""
    return _eval_node(ast.parse(expression, mode="eval"))


def _normalize(text: str) -> str:
    table = str.maketrans({"×": "*", "÷": "/", "（": "(", "）": ")", "＋": "+", "－": "-"})
    text = text.translate(table).replace(" ", "")
    for word, symbol in (
        ("乘以", "*"),
        ("除以", "/"),
        ("加上", "+"),
        ("减去", "-"),
        ("等于多少", ""),
        ("等于", ""),
    ):
        text = text.replace(word, symbol)
    return text


def extract_expression(text: str) -> str | None:
    """从自然语言里挑出最长的算式片段。"""
    normalized = _normalize(text)
    for expr in sorted(re.findall(r"\d[\d+\-*/().%]*\d", normalized), key=len, reverse=True):
        if re.search(r"[+\-*/%]", expr):
            return expr
    return None


def format_result(value: Decimal) -> str:
    text = format(value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP), "f")
    text = text.rstrip("0").rstrip(".")
    return text or "0"


def run(question: str) -> dict[str, Any]:
    expression = extract_expression(question)
    if not expression:
        return {
            "status": "failed",
            "answer": "没有识别到可计算的算式，请直接给出数字和运算符，例如：9733 × 1000。",
            "sources": [],
            "missing": ["计算表达式"],
        }
    try:
        value = evaluate(expression)
    except (SyntaxError, ValueError, ZeroDivisionError, ArithmeticError):
        return {
            "status": "failed",
            "answer": f"算式 {expression} 无法计算，请检查数字和运算符。",
            "sources": [],
            "missing": ["有效算式"],
        }
    return {
        "status": "ok",
        "answer": f"计算结果：{expression} = {format_result(value)}",
        "sources": [
            {
                "type": "calculator",
                "id": "arithmetic",
                "title": "实时计算",
                "locator": expression,
            }
        ],
        "missing": [],
    }
