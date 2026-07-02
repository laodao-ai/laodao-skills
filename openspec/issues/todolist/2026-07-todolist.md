# 2026-07 TODO

> 项目：<未注明>

## 状态总览

| ID | 模块 | 描述 | 类型 | 状态 | 时间 | 关联Change | 批次 |
|----|------|------|------|------|------|------------|------|
| T1 | `issues.py` | reindex 回显子进程 scan 的 problems 到 stderr（补齐独立跑 reindex 时表↔块不一致的可见性，D5 承诺） | 可观测性 | OPEN | 2026-07-03 00:26 | issues-pool-batch-mgmt |  |
| T2 | `recorder` | 字段含 ｜ 破 markdown 表：统一转义或拒绝含 ｜ 的字段（module/summary/批次名等，防位置解析读错列的数据腐蚀，系统性） | 代码质量 | OPEN | 2026-07-03 00:26 | issues-pool-batch-mgmt |  |
| T3 | `issues.py` | 加终态集跨脚本一致性守卫测试（issues.py TERMINAL_STATUSES ⊆ 对应 recorder STATUS_CODES，防未来改终态码漂移） | 代码质量 | OPEN | 2026-07-03 00:26 | issues-pool-batch-mgmt |  |
| T4 | `issues.py` | batch add 加 --if-exists skip 幂等选项；batch rename 后自动 reindex（或 SKILL 提示 rename 后跑 reindex） | 功能增强 | OPEN | 2026-07-03 00:26 | issues-pool-batch-mgmt |  |
| T5 | `recorder` | 补 WONTDO / 0成员人标IN_PROGRESS 分支测试；抽 _find_row_file 消除 triage 与 set-status 定位逻辑重复（4处） | 代码质量 | OPEN | 2026-07-03 00:26 | issues-pool-batch-mgmt |  |
