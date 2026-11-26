# 审查任务：#97 biophysics Evidence provenance 修正复验（issue-97-ar-r2，收敛轮）

你是严苛的数据模型与发布产品审稿人，同时承担对抗性与完整性核查。r1 报出问题，已按下述内容修复并复验。请**只审查当前未提交 diff 相对基线 `c997eecf55eca0a0d151e28f80d7adcd1cfc8f37` 的终态**，验证修复正确落地、无新错误，并快速回归关键契约。

## r1 问题与修复映射

1. **站点页面未呈现 normalized Evidence**：`site/templates/card.html` 现基于 `r.evidence` 渲染 stable `MAIC:EV:*`、claim、source、publication、quote、location、type、confidence、curator note、review state、review timestamp；双语字符串已同步；新增真实站点 HTML 测试。
2. **CLI provenance 未呈现 normalized Evidence**：`_render_card()` 与 `_render_provenance()` 现在逐项渲染完整 Evidence；新增 CLI 测试。
3. **claim 泄漏 enum repr / None**：`_claim_for()` 改用 controlled parameter-set label；无 label 时使用可解释 measurement fallback；960 条 artifact claim 已重建并检查无 `ParameterSet.` / `: None`；新增 mapping 测试。
4. **bioactivity / unmapped 披露断链**：`UNMIGRATED_EVIDENCE_DISCLOSURE` 作为 canonical constant；`bioactivity_card()` 每行携带 disclosure；站点模板与 CLI 渲染 disclosure；`provenance()` 非 biophysics 已有 disclosure；新增测试。
5. **resolver 顺序不一致**：`resolve_biophysics_evidence()` 改为按 `maicdb_id` 排序；新增多 Evidence 顺序测试。
6. **claim 可空性**：`EvidenceItem.claim` 改为 NOT NULL，DDL 和 schema dump 同步；测试 fixture 改为显式 claim。
7. **重复/unused 常量**：query 层引用 evidence 层 canonical disclosure，不再复制文字；新增一致性测试。
8. **schema/table 文档失同步**：`ALL_TABLES` 增加 `EvidenceItem` / `EvidenceSubject`（12 models）；`db/README.md`、主 README、loader mapping 与 analytics baseline 更新到 v0.3/12 tables/1125 rows。
9. **完整 publication trace**：`biophysics_evidence()` outer join `publication`，公开 payload 输出 `{id, doi, title, journal, year, authors, pmid, citation_text}`，站点/CLI 可显示。
10. **artifact claim/版本面**：重建 960 Evidence items；SQL dump `claim TEXT NOT NULL`；manifest/下载页大小测试同步。

## 明确不报项（沿用 r1 prompt，勿重复）

- #98 前的 all-fact-family authority cutover、standard Web API、更细条件下载。
- 用户已接受的 channel-page experiment anchor 等价解释，不要求新增独立 experiment 页面。
- SQLite 二进制文件的 byte-stable contract：项目既有 contract 明确是同 vault state 的两次重建 SQL dump byte-stable；本次验证两次 SQL dump 一致且发布 SQL dump 可按固定 vault tree 复现。SQLite 文件只要求数据/结构正确，不要求跨进程字节一致。
- `CITATION.cff` 的 v1.0.0 DOI/version 与日期：这是已发布 Zenodo 历史版本，未获用户授权发布新 dataset version，不凭空发明新 DOI；下载页当前仍然引用该已记录 citation。
- 生成的 `db/maicdb.sql` / `src/maicdb/schema.sql` 中 SQLite DDL 的既有尾随空白格式。
- `manifest["dump"]` 的运行输出路径：这是调用参数，不是数据内容；入库 contract 保留 `db/maicdb.sql`。

## 已验证状态

- `ruff check .`：通过。
- 全量 pytest：394 passed, 8 skipped, 1 sandbox-only failure（`socket` 权限导致，非代码问题）。
- 专项 pytest（evidence/query/schema/site/downloads）：通过。
- 两次站点构建：`diff -r` 为空。
- 两次 vault load：SQL dump byte-identical；入库 SQL dump 与固定 `dd49d8e` 数据 tree 的重建结果在仅归一化 `data_freeze_tag`/manifest path 后 byte-identical。
- 下载大小 pin：SQLite 5,185,536；SQL 3,682,117；manifest 1,366；citation 1,338。

## 收敛审查要求

1. 逐条确认上述 10 个修复真实落地且未产生新问题。
2. 快速核查 #97 十条 AC 终态；尤其是站点 HTML、CLI、export、真实 artifact 覆盖、无 vault-only editorial history。
3. 检查是否有 r1 之外的新实质问题；不重复已关闭的保留项。
4. 不得修改文件，只读审查。
5. 最后必须输出：`## 总结论 问题总数： N`。
