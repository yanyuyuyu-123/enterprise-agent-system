# 工单审核实体提取

从用户原话中提取审核信息，只输出 JSON，不要解释。

字段：

- order_no：工单号，例如 WO202611100001
- decision：审核结果，只能是 approve（通过）或 reject（驳回）
- comment：审核意见；驳回时必须给出，通过时可省略

示例：

用户：审核通过 WO202611100001
输出：{"order_no": "WO202611100001", "decision": "approve"}

用户：驳回 WO202611100001，现场照片不清晰
输出：{"order_no": "WO202611100001", "decision": "reject", "comment": "现场照片不清晰"}
