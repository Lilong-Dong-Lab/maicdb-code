# 审查任务：#97 biophysics Evidence provenance 完整性核查（issue-97-nr1，non-adversarial）

你是一名细致的数据发布编辑，任务是**核查当前未提交 #97 实现是否完整落地**：逐条比对验收标准与 ADR，找遗漏、失同步和断链，不争论措辞偏好。

## 对象与基线

- 工作目录：`/home/xinfang/.codex/worktrees/issue-97-evidence-provenance-spine/maicdb-code`
- 审查对象：相对基线 `c997eecf55eca0a0d151e28f80d7adcd1cfc8f37` 的当前未提交 diff。
- 权威需求：`/home/xinfang/repository/maicdb-code/report/codex-review-logs/tracer-tickets/tickets/01-evidence-provenance-spine.md`、`docs/adr/0007-evidence-construct-xref-statistics.md`、`GLOSSARY.md`。
- 重点文件：证据模型/迁移 `src/maicdb/models.py`、`src/maicdb/evidence.py`、`src/maicdb/loader.py`；查询/站点/导出 `src/maicdb/query.py`；schema/发布 `src/maicdb/schema.sql`、`db/load-manifest.json`、`db/maicdb.sql`；测试 `tests/test_evidence.py`、`tests/test_query.py`、`tests/test_site_downloads.py`、站点与 artifact 相关测试。

## 逐条验收核查清单

1. Schema 是否定义 stable database identifier、claim、source、publication、quote、location、controlled evidence type、controlled confidence、curator note、review state、review timestamp，并且约束真实存在。
2. Evidence item 与 subject 是否 many-to-many；fixture 是否覆盖同一 Evidence 支持多个 subject、同一 subject 引用多个 Evidence 两方向。
3. Migration 是否从 biophysics legacy 字段派生且不丢/不重、保留 subjects/identifiers/FK，并递增 schema version；重复运行是否幂等。
4. Legacy fields 是否仍可读；代码/文档是否未在 #98 parity 前 claim authority。
5. Biophysics query payload、channel page、experiment page/anchor、全部 existing exports 是否通过同一 shared resolution path 呈现 Evidence；不能只查函数名，要追踪数据流和模板。
6. Bioactivity、unmapped measurement 是否在同页面/导出中带 explicit legacy/unmigrated disclosure；biophysics 是否不携带误导性 disclosure。
7. Public payload/export 是否无 vault-only editorial history。
8. 测试是否覆盖 schema constraints、migration round-trip、many-to-many reuse、query/site provenance、export parity。
9. Artifact-backed tests 是否证明一个真实 biophysics Evidence trace，并证明每个 biophysics fact 可 resolve Evidence 或 explicit disclosure。
10. Twice rebuild determinism 与 published artifact contract 是否完整执行；manifest/下载页/SQL/SQLite/citation 是否同步。

## 完整性核查维度

1. 声明落地全链：票面每个词在 schema、loader、query、site、export、tests 中是否有真实落点。
2. 遗漏位置扫描：同一 evidence/migration/publication 概念在其他模型、枚举、模板、文档、site locale 中是否同步。
3. 交叉一致性：schema version、lockfile、manifest、artifact 大小、下载页文案、citation、SQL dump 是否互相一致。
4. 结构完整性：计数、列顺序、序列化字段、many-to-many 判定、fixture 覆盖与测试断言是否互相支撑。
5. 中间态：一半新一半旧、悬空字段、unused abstraction、只在测试中硬编码而没有产品路径支撑的断言。

## 报告纪律

- 只报实质遗漏/失同步/断链；每条给出位置、证据（代码/命令输出）、对应验收条目和最小修复建议。
- 不报：#98 明确提前排除的 all-fact-family authority cutover、standard Web API、更细条件下载；用户已接受的 channel-page experiment anchor 等价解释；既有生成的 DDL 空白格式。
- 不得修改仓库文件；请使用 read-only 审查命令。
- 输出逐条核查表：每条 AC 标为 Pass / Fail / Blocked-with-reason，再列出所有实质问题的详细证据。
- 最后一节必须是：`## 总结论 问题总数： N`（只统计实质问题）。
