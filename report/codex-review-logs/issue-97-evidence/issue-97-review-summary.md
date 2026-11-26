# #97 biophysics Evidence provenance 双审循环记录

审查对象：当前未提交的 #97 实现；基线 `c997eecf55eca0a0d151e28f80d7adcd1cfc8f37`。轮次：r1 报 10 项 → r2 报 3 项 → r3 报 1 项 → 最终复验 0 项。

## 问题与修正映射

| 轮次 | 来源 | 问题 | 修正 |
|---|---|---|---|
| r1 | AR/NR | 站点页面与 CLI 未呈现 normalized Evidence | `site/templates/card.html` 与 `_render_card()` / `_render_provenance()` 完整渲染 Evidence |
| r1 | AR | claim 泄漏 enum repr / None | `_claim_for()` 使用受控 label 与 measurement fallback；_artifact 重建 |
| r1 | AR/NR | bioactivity / unmapped 披露断链 | canonical disclosure 统一由 evidence 层供给，bioactivity payload/site/CLI 均呈现 |
| r1 | AR/NR | schema/table/version 文档失同步 | 更新 `ALL_TABLES`、db README、主 README、loader mapping、analytics baseline |
| r1 | AR/NR | publication 只给内部 ID | public Evidence payload 解析为完整 publication 对象 |
| r1 | AR | resolver 顺序候选问题 | 后续在 r2 精确收敛为仅按 `maicdb_id` 排序 |
| r1 | AR | claim 可空性与常量重复候选问题 | 收敛为 `claim NOT NULL` 与 canonical disclosure |
| r2 | AR | 单实验 resolver 仍以内部 ID 主排序 | 删除 `EvidenceItem.id` 排序 |
| r2 | AR | CLI 输出 Python enum repr | 使用公共受控值 `measurement/high/unreviewed` |
| r2 | AR | NULL publication payload 残留内部字段 | 只保留 `publication: None` |
| r3 | AR | CLI 测试缺 type/confidence 断言 | `tests/test_query.py` 补齐三个公共值断言 |

## 保留项

- #98 前不做 all-fact-family authority cutover；standard Web API 与更细条件下载仍属后续票。
- channel 页实验锚点是本站既有 experiment 入口解释，不新增独立实验页。
- SQLite 二进制文件不作为跨进程字节稳定 contract；项目 contract 是同 vault state 的 SQL dump byte-stable。
- 已发布 Zenodo v1.0.0 citation/DOI 不在 #97 中凭空替换；新 dataset 版本需发布流程授权。
- 生成式 DDL/data dump 的既有尾随空白保持原样。

## 收敛轮结论（问题总数 0）

- `ruff check .` 通过。
- 最终全量 pytest：394 passed, 8 skipped, 1 个沙箱 socket 权限失败（非代码缺陷）。
- 专项 pytest：evidence/query/schema/site build/site downloads 全部通过。
- 真实 artifact：960 biophysics experiment = 960 Evidence item = 960 Evidence subject；稳定 trace `PIEZO1-EX-00005 → MAIC:EV:00409`。
- 站点两次构建 byte-identical。
- 同 vault state 两次 loader SQL dump byte-identical；入库 SQL dump 与固定 `dd49d8e` 数据 tree 复现一致（仅归一化运行路径/manifest dump path）。
- 最终收敛审查报告：`## 总结论 问题总数： 0`。

## 结论

共修复 15 项实质问题/测试缺口，最终收敛到 0。主要教训是“payload 有字段”不等于“最终站点/CLI/导出面完成呈现”；公开对象必须在同一 resolution path 中同时约束字段形状、受控值和顺序。
