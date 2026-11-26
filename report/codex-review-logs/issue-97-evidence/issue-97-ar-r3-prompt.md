# 审查任务：#97 biophysics Evidence provenance 修正复验（issue-97-ar-r3，最终收敛轮）

你是严苛的数据模型与发布产品审稿人，同时承担对抗性与完整性核查。r2 报 3 项，已全部修复并完成专项验证。请只读审查当前未提交 diff 相对基线 `c997eecf55eca0a0d151e28f80d7adcd1cfc8f37` 的终态，确认 r2 修复无新错误，不重复已关闭且未变化的保留项。

## r2 问题与修复映射

1. **Resolver 排序键未收敛**：`resolve_biophysics_evidence()` 已删除 `.order_by(EvidenceItem.id)`，仅按 `EvidenceItem.maicdb_id` 排序；fixture 改为内部 ID 与 stable accession 反序，断言顺序为 `MAIC:EV:00001/00002/00003`。
2. **CLI 泄漏 Python enum repr**：`_render_card()` 与 `_render_provenance()` 现用 `_enum_value()` 输出受控公共值；CLI 测试断言 `review_state: unreviewed`，不再固定 `EvidenceReviewState.UNREVIEWED`。
3. **NULL publication payload 残留字段**：`biophysics_evidence()` 现只输出 `publication` 键；`publication_id` 为 NULL 时为 `publication: None`，不再残留顶层 `publication_id/doi/title/...`；新增公开 shape 测试。

## 已验证

- `ruff check .`：通过。
- 专项测试：`86 passed, 1 warning`（evidence/query/schema/site build/site downloads）。
- `db/load-manifest.json` 实际 1,366 bytes；下载页按 SI 显示 1.4 kB；r2 prompt 中的 1,444 已修正。

## 不报清单

- #98 前的 all-fact-family authority cutover、standard Web API、更细条件下载。
- channel-page experiment anchor 等价解释；不要求新增独立 experiment 页面。
- SQLite 二进制文件跨进程 byte-stability；项目 contract 是同 vault state 的 SQL dump byte-stability。
- 已发布 Zenodo v1.0.0 citation/DOI；未获授权不发明新 dataset version。
- 生成式 DDL/data dump 的既有尾随空白。
- manifest `dump` 的调用路径差异。

## 要求

1. 逐项复验上述 3 项修复。
2. 快速回归 #97 关键 AC 与 r1 已关闭项。
3. 如发现新实质问题，必须给出可复现证据和最小修复。
4. 不得修改文件。
5. 最后一节必须精确输出：`## 总结论 问题总数： 0`（若仍有问题则输出实际 N）。
