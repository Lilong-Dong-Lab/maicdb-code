# 审查任务：#97 biophysics Evidence provenance 对抗性复核（issue-97-ar1，adversarial）

你是一名严苛的数据模型与发布产品审稿人，任务是**攻击**当前未提交的 #97 实现：假设每一处都可能出错，主动找实质性漏洞。

## 对象与基线

- 工作目录：`/home/xinfang/.codex/worktrees/issue-97-evidence-provenance-spine/maicdb-code`
- 审查对象：相对基线 `c997eecf55eca0a0d151e28f80d7adcd1cfc8f37` 的当前未提交 diff。
- 路径：`GLOSSARY.md`、`db/load-manifest.json`、`db/maicdb.sql`、`db/maicdb.sqlite`、`pyproject.toml`、`uv.lock`、`src/maicdb/accessions.py`、`src/maicdb/enums.py`、`src/maicdb/evidence.py`、`src/maicdb/loader.py`、`src/maicdb/models.py`、`src/maicdb/query.py`、`src/maicdb/schema.sql`、`tests/test_evidence.py`、`tests/test_query.py`、`tests/test_site_downloads.py`、`docs/adr/0007-evidence-construct-xref-statistics.md`。
- 权威需求：`/home/xinfang/repository/maicdb-code/report/codex-review-logs/tracer-tickets/tickets/01-evidence-provenance-spine.md` 与仓库内 ADR-0007。

## 攻击靶点

1. Evidence schema、枚举、ID 规则、时间与公开/私域边界。
2. biophysics legacy 字段到 Evidence item 的迁移语义、幂等性、覆盖率和主外键保留。
3. query、site、experiment 展示锚点、JSON/CSV export 是否共享同一 resolution path，且 bioactivity/unmapped 是否明确披露未迁出。
4. 权限与权威性措辞：#98 前不得声称 all-fact-family authority，也不得宣称编辑历史已公开。
5. 发布 artifact 与下载页：计数、文件大小、schema version、manifest、citation 是否与真实 artifact 同步。
6. 测试是否真的能约束 schema、migration、many-to-many、query/site/export、真实 artifact 覆盖与确定性；测试是否遗漏会导致需求误判。

## 实施者已知的候选疑点（必须逐项验证，不得只凭直觉驳回）

1. `_claim_for()` 在 `experiment_label` 为空时使用 `parameter_set`，可能把 enum 成员或格式变成可见 claim。
2. Evidence `claim` schema 可空，但迁移总是生成 claim；票面要求 claim，应在语义上判断可空性是否合理。
3. `resolve_biophysics_evidence()` 以内部 `id` 排序，而批量路径以 `maicdb_id` 排序，是否造成接口顺序不一致。
4. `evidence.py` 中 migration-state 常量与 unmigrated disclosure 是否与 query 层重复或未使用。
5. public Evidence 只输出 `publication_id`，是否满足“publication”可追溯要求，不能替本项目发明新需求。
6. channel-page anchor 是否已被项目现有站点规格等效接受为“experiment page”，需要依据代码和规格判断，不凭幻想新增页面。

## 对抗性审查维度

1. 语义忠实性：改动是否存在过度主张、过度弱化、字段语义漂移或与票面/ADR 冲突。
2. 新引入错误：SQL/SQLite 兼容、enum 持久化、migration 幂等、循环导入、接口兼容、导出转义、时间稳定性。
3. 上下文/基准逻辑衔接：新模型与 legacy bridge、schema version、manifest、下载页面、site 构建是否一致。
4. 数字与引用：960、0.3.0、下载大小、真实 trace 计数、Evidence 覆盖计数必须逐个验证。
5. 安全/公开边界：是否泄漏 vault-only editorial history，是否暴露不该公开内部主键。

## 报告纪律

- 只报实质问题，不报纯风格偏好；每条问题必须给出文件与行号或可复现命令输出，说明违反的票面/ADR/项目既有契约，并给最小修复建议。
- 不报：#98 明确留给后续的 all-fact-family authority cutover、standard Web API、更细下载粒度；已由用户明确接受的 channel-page experiment anchor 等价解释；生成式 `db/maicdb.sql` / `schema.sql` 的既有 DDL 空白格式。
- 不得修改仓库文件；请使用 read-only 审查命令。
- 最终回复必须包含每个问题的标题、证据、影响、建议修复，以及最后一节：`## 总结论 问题总数： N`（只统计实质问题）。
