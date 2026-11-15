# 同类策划型数据库网站对照：信息架构与 UI 模式（M3 / T9 验收前）

> **译注（2026-11-04）**：本文是英文原版
> [`2026-11-03-comparable-curated-database-sites.md`](2026-11-03-comparable-curated-database-sites.md)
> 的中文译本，仅供本地阅读；**英文原版为权威版本**。各站点的原话引文按逐字
> （verbatim）原则保留英文原文——它们本身就是"证据引用"，翻译会破坏其证据性质；
> 个别长引文附中文大意。两份文档均未入库（untracked，仅本地）。

- **日期**：2026-11-03（全部在线页面均于当日抓取；Wayback 快照各自携带
  抓取日期，使用处均已标注）
- **问题归属**：M3 网站线——在 T9 公开验收之前建立参照系，同时为 M4+ 的
  UI 演进收集模式素材
- **方法**：四个对照站点仅以在线抓取（curl / web reader）为准——**不使用
  训练记忆中的任何断言**。每条站点级结论均标注其抓取来源 URL。自报体量数字
  只取自站点自己的页面（首页计数器、发布说明），查不到的标注"未查到"。
  在线抓取不可行处（登录墙、纯 JS 应用壳），如实说明并改用带日期的
  Wayback 快照作为历史证据，明确标注。MAIC-DB 侧事实来自本地规格书与
  模板，按路径引用。
- **范围声明**：本文档不改变已验收的 M3 范围（规格书
  `docs/m3-website-spec.md` §3 Q1–Q11）。§5 中的候选模式仅为未来 ticket
  的输入。Web 界面会变；未来决策依赖任何单站结论前请重新核实。

## 1. 目的

本轮研究由三个问题驱动：

1. 在 T9（部署站点的公开验收）之前，同类小型学术策划数据库如何呈现
   MAIC-DB 同样呈现的四个面——家族导航、实体页信息密度、证据链、
   下载/引用——MAIC-DB 在其中处于什么位置？
2. 哪些模式值得引入 M4+（候选 ticket），各自的代价是什么？
3. 对一个核心承诺是"每个数值距离其测量行与逐字证据引文仅一步之遥"
   的站点而言，哪些模式是明确的反面教材？

四个对照站点由任务简报选定：Channelpedia（同域——离子通道）、
Guide to Pharmacology（结构最接近——家族 → 靶点 → 配体活性 + 文献引用）、
BitterDB（体量与团队规模最接近——约千级分子、小型实验室团队）、
Stanford HIVdb（证据链范式——评分可溯源到文献）。

## 2. MAIC-DB 基线（四个面，建成现状）

本节全部事实来自本地仓库，按路径引用；渲染 HTML 引文已对照本地运行中的
预览（`http://localhost:8000/`，2026-11-03）核验。

### 2.1 信息架构：family → channel → measurement

- 层级 family(7) → channel(12) → measurement(1100 = 948 生物物理 +
  136 生物活性 + 16 未映射），外加 211 篇文献
  （`docs/m3-website-spec.md` §4；首页渲染 "1100 curated measurements /
  12 channels / 7 families / 211 publications"）。
- 五类页面：home、browse（12 张通道卡按 7 个家族分组）、通道卡、
  参数比较（16 个参数）、downloads；另有全局搜索（规格书 §3 Q8、§5）。
- URL 方案：`/channels/<slug>/` 用小写基因符号 slug，
  `/parameters/<parameter>/`、`/downloads/`（规格书 §3 Q7、§5；
  `site/templates/browse.html`、`site/templates/parameters.html`）。
- browse 卡片按两种口径显示每通道计数并点名口径：`n_parameterized_rows`
  加生物活性与定性数据的附加行（riders）
  （`site/templates/browse.html` 14–27 行；双口径规则见规格书 §4）。
- 参数页按**存储单位分桶**渲染 12 通道 × n/min/median/max，页首带
  单位分桶披露与冻结层披露，每个表格单元格可展开为其 measurement id
  （已核验 `/parameters/conductance/` 渲染："Buckets are split by stored
  unit: values are rendered as recorded, units are never merged or
  converted…"〔数据桶按存储单位拆分：数值按原记录渲染，单位从不合并或
  换算〕；"Frozen layer — PIEZO1/PIEZO2 rows are frozen-layer data whose
  evidence quotes have not been re-verified…"〔冻结层——PIEZO1/PIEZO2 行
  为冻结层数据，其证据引文未经过再核验〕）。

### 2.2 证据链：逐字引文 + 置信度 + 条件键

- 每个测量行是一个 `<details>` 元素，展开后显示六字段证据 `<dl>`：
  引文（逐字）、出处、置信度、提取注记、条件键、n——生物物理行与
  生物活性行渲染完全一致；生物活性行额外加实验描述
  （`site/templates/card.html` 4–19 行，`evidence_dl` 宏）。
- 深链为 measurement id 上的锚点（`#<measurement_id>`；规格书
  §3 Q10——不做 1100 个微页面）。
- PIEZO1/PIEZO2 卡带冻结层横幅；不渲染任何 "verified" 标签
  （规格书 §3/§4 §6.7 规则；已在渲染出的 `/channels/piezo1/` 上核验，
  该页含 `frozen-banner` 元素）。
- 已核验的渲染示例（`/channels/piezo1/`，行 `PIEZO1-EX-00004`）：
  摘要行 "73.0 pS (as reported: 73 pS)"；展开字段——Quote:
  "The unitary conductance at -33mV was 73 pS (0.5 mM Mg2+ in
  pipette)."；Location: "Figure legend (C-terminal truncation figure;
  cell-attached patches)"；Confidence: "medium"；Extractor note:
  （中文，原样显示——引文/注记永不翻译）；Condition key:
  "hPIEZO1-G2218Stop_HEK293_cell-attached_-33mV_0.5mM-Mg-pipette_Fig8(SI)"；
  n: "(not recorded)"。

### 2.3 EN/ZH 双语树

- 每页存在两份：EN 无前缀，ZH 在 `/zh/` 下（两树合计 64 个构建出的
  HTML 页，已在 `site/_site/` 核验）；每页的语言切换器将页面与其
  对应版本互链（`site/templates/base.html` 19 行；规格书 §3 Q3）。
- UI 字符串只存在于 locale 字典；curated 中文内容是
  `site/zh-content.json` 中的表现层；证据引文与中文提取注记在两个
  locale 中均按原样显示（规格书 §3 Q3、§6）。

### 2.4 下载与引用页

从渲染出的 `/downloads/`（localhost:8000，2026-11-03）与
`site/templates/downloads.html` 核验：

- 四个工件文件，与 Zenodo 记录字节一致：`db/maicdb.sqlite`
  (3.1 MB)、`db/maicdb.sql` (2.2 MB)、`db/load-manifest.json` (1.2 kB)、
  `CITATION.cff` (1.3 kB)。
- 两个 DOI：版本 DOI `10.5281/zenodo.23620159`（固定 v1.0.0）与概念
  DOI `10.5281/zenodo.23620158`（始终最新）。
- 许可：数据 CC-BY-4.0、代码 MIT；同样出现在全局页脚，连同两个 DOI
  （`site/templates/base.html` 42–48 行，含 AI 代理贡献者披露）。
- 未映射披露："16 archived unmapped measurement rows — kept for
  provenance, mapped to no registered parameter block, with no page of
  their own on this site"（16 条已归档的未映射测量行——保留作溯源，
  未映射到任何已注册参数块，在本站没有独立页面）（规格书 §3 Q11）。

## 3. 逐站发现

每站小节把**事实**（带来源 URL）与**判断**（MAIC-DB 侧观点，标注）分开。

### 3.1 Channelpedia（EPFL）— https://channelpedia.epfl.ch

**体量（站点自报，首页，2026-11-03 抓取）。**"It is web-based, freely
accessible and currently contains 180 annotated ion channels,
electrophysiology data for all Kv ion channels and 50 Hodgkin-Huxley
models."（基于 Web、免费开放，目前含 180 个注释离子通道、全部 Kv
通道的电生理数据、50 个 Hodgkin-Huxley 模型。）以及 "Currently,
Channelpedia contains about 180,000 abstracts related to ion channels
from Pubmed."（目前含约 18 万条来自 PubMed 的离子通道相关摘要。）
（https://channelpedia.epfl.ch）。量级：通道数约为 MAIC-DB 的 150 倍，
但每通道的策划参数密度远低于我们（见下）。

**信息架构。** 左侧导航是深层家族树——K → Kv → Kv1 → Kv1.1（在每页
导航中可见，如 https://channelpedia.epfl.ch/expdata）——直达
`/wikipages/<id>` 的每通道 wiki 页
（https://channelpedia.epfl.ch/wikipages/1 = Kv1.1/KCNA4）。通道页是
一个带固定板块的长单页；Kv1.1 页上观察到的板块标题：Experimental
data、Variants、Crystal Structure、Pharmacological Characteristics、
（AlphaFold 尺寸）、逐实验条目、Markov Model、Hodgkin and Huxley
type model、表达/分布板块。独立的 `/pubmeds` 页承载条目所引用的
编号文献表。

**证据链。** 每条实验数据条目是从论文摘要复制/转述的短段落加方括号
编号（如 "Recordings were performed at potentials ranging from −50 to
+70 mV with 20 mV increments [1]." 或 "…displayed functional
differences compared with wild-type … [1835]"）——方括号编号显然索引
站点级 PubMed 表 `/pubmeds`（由编号规律 + 导航推断，页面上未明说）；
抓取的 HTML 中条目本身未发现直接的 PubMed 超链（已核验：Kv1.1 页中
`pubmed*<数字>` 形式的 href 为 0；唯一的 PubMed 链接是全局 `/pubmeds`
导航链接）。**没有逐字引文、没有置信度字段、没有条件键、没有逐值
溯源**。Wiki 板块可编辑："All registered users can edit the wiki-like
sections, just clicking on Edit at the top-right of each sub-section."
（所有注册用户都可以编辑 wiki 式板块，只需点击各子板块右上角的
Edit。）（FAQ，https://channelpedia.epfl.ch/faq）。

**下载与引用。** 无自助批量下载。FAQ（"能否一次下载整批离子通道
数据？"）："Yes, we have an infrastructure suited to share large amount
of data. Please contact us at bbp.channelpedia@epfl.ch, indicating
which dataset you are interested for downloading."（可以，我们有适合
共享大量数据的基础设施。请致信……并注明你想下载的数据集。）原始
HEKA 文件同样按需邮件联系（同页）。抓取的页面上未发现许可或引用
区块。无 DOI。

**值得借鉴（判断）。**
- 每通道专属的 Hodgkin-Huxley / Markov 模型板块：对 MAIC-DB 的 M4+
  而言，一个"基于 MAIC-DB 参数构建的模型"板块（哪怕只是外部链接）
  是这些数值被计算性复用的天然归宿。
- 按细胞 ID 关联原始数据（"The cell ID is a unique ID assigned to
  each cell as soon as it is recorded; it is the main reference to
  relate every file and every image"——细胞 ID 是每个细胞一记录就
  分配的唯一标识，是关联每个文件与每张图的主要参照，FAQ）——一种
  严格的逐记录标识符哲学，MAIC-DB 已用 `measurement_id` 同构实现；
  可借鉴的是**面向实验室的"标识符为什么重要"的叙述**。
- 
**值得避免（判断）。**
- 以 wiki 开放编辑为内容模型：对一个主张"冻结、已验证溯源"的数据库，
  社区直接编辑恰恰削弱这个保证。（MAIC-DB 的 vault + 评审门流程是
  相反的另一极。）
- 以转述摘要充当"证据"：读者无法核对论文到底说了什么，只能看到策展人
  的概括。
- 批量数据只能发邮件找人——一种随人员流动而衰减的可用性依赖。

### 3.2 Guide to Pharmacology（IUPHAR/BPS）— https://www.guidetopharmacology.org

**访问现状（重大变化）。** 截至 2026-11-03，数据库本体位于注册墙后：
"GtoPdb now requires users to register to use the website."（GtoPdb
现在要求用户注册后方可使用本网站。）（首页横幅）。墙页进一步说明：
"The IUPHAR/BPS Guide to Pharmacology now requires all users to
register and login in order to access the database… Commercial
organisations that use GtoPdb must pay access-fees… If you would
prefer not to register with GtoPdb at this time, you can still use
the database and website by using the guest login below. This login
will remain in place for a limited time…"（……商业机构须付费……
暂不愿注册者可用下方访客登录，限时开放……）。墙在
`/GRAC/LigandListForward?type=Approved`、`/GRAC/AboutPageForward`、
`/download.jsp` 上均被触发（均 2026-11-03 抓取，均返回登录页）；访客
登录按钮由 JS 注入、不存在于静态 HTML 中，因此数据库页面截至该日
**无法静态抓取**。首页本身与博客仍开放。注册制于 2026-07 公告
（https://blog.guidetopharmacology.org/2026/07/29/user-registration-is-coming-to-gtopdb/）。

**体量（站点自报）。** 首页无靶点/配体计数器（2026-11-03 抓取）。
官方发布公告有："GtoPdb now contains: 3,147 human targets, 1,837 of
which have curated quantitative ligand interactions. … 13,989 ligands,
10,072 of which have curated quantitative target interactions. …
Data curated from 50,429 references."（目前含 3,147 个人类靶点，其中
1,837 个有策划的定量配体互作……13,989 个配体……数据策划自 50,429 篇
文献。）（release 2026.3 帖，2026-09-16，
https://blog.guidetopharmacology.org/2026/09/16/database-release-2026-3/）。
当前版本横幅："Version 2026.3.1 (12th October 2026)"（首页）。GtoPdb
在每个轴上都比 MAIC-DB 大一到两个数量级。

**信息架构**（来自靶点页的 Wayback 快照，抓取于 2025-02-19——因在线
页面在墙后：
http://web.archive.org/web/20250219223557/https://www.guidetopharmacology.org/GRAC/ObjectDisplayForward?objectId=529）。
类型分类（GPCR、Ion channels、NHR、Transporters、Enzymes…）→ 家族 →
靶点页。靶点页（CaV1.2）的面包屑携带家族（"Ca v 1.2 | Voltage-gated
calcium channels (Ca V )"），页首是约 25 个板块的 "Contents:" 迷你
目录：Gene and Protein Information、Previous and Unofficial Names、
Database Links、Associated Proteins、Functional Characteristics
（Ion Selectivity and Conductance、Voltage Dependence）、Activators、
Gating Inhibitors、Channel Blockers、Immunopharmacology、Tissue
Distribution、Functional Assays、Physiological Functions、
Physiological Consequences of Altering Gene Expression、Phenotypes/
Alleles and Disease Models、Clinically-Relevant Mutations and
Pathophysiology、Biologically Significant Variants、References、
Contributors、"How to cite this page"。这是 MAIC-DB 通道卡在结构上
最近的亲缘，板块数约为我们的 3–5 倍。

**证据链**（同一快照）。配体-活性行渲染为：配体名 + 物种代码
（Mm/Rn）+ 作用（Antagonist）+ 数值（"pIC 50 7.0 – 8.0"）+ 一个条件
字段（"Holding voltage: -80.0 mV"〔钳制电压〕）+ 方括号文献编号，
带可展开子行（⤷）重复数值及其引用，如 "nisoldipine Mm Antagonist
7.0 – 8.0 pIC 50 … 79 ⤷ pIC 50 7.0 – 8.0 [ 79 ] Holding voltage:
-80.0 mV"。文献编号解析到页底 References 全引文列表（带 PubMed 链接，
如 "[PMID: 28592699]"）。即：**逐值引用 + 一个条件字段**——但没有
逐字引文、没有逐值置信度；信任单位是文献，不是被提取的那句话。

**下载与引用。** 下载页本身在墙后（`/download.jsp`，2026-11-03
抓取）。开放的首页指向存档在 Zenodo 的发布报告："Reports are also
accessible, along with database update presentations, on our Zenodo
archive. latest report DOI: 10.5281/zenodo.23667960."。许可：
CC BY-SA 4.0（每页页脚链接，含登录墙页）。靶点页带 "How to cite
this page" 板块与格式选择器：Vancouver、Harvard、ACM、BibTeX、RIS
（上引快照）。

**值得借鉴（判断）。**
- 行内文献编号 + 页底文献列表——四站中信息密度最高的可读引用模式；
  MAIC-DB 的等价物（measurement-id 锚点）是更强的溯源，但 GtoP 证明
  引用既可以深也可以紧凑。
- 实体页上带格式选择的 "How to cite this page"：以后给 MAIC-DB 卡片
  页加这个很便宜（EN/ZH 双语），与 CITATION.cff 互补。
- 每次发布的 Zenodo report DOI：我们版本 DOI 的轻量级兄弟，非常适合
  发布说明/报告类工件。

**值得避免（判断）。**
- 注册墙本身：它使数据库对匿名读者、爬虫、存档服务与教学用途都不可
  抓取——而且这发生在一个长期开放的资源身上，理由是可持续性，这正是
  公开 T9 验收要避免的失败模式。无论未来出现什么经费压力，给实体页
  加墙对 MAIC-DB 的核心承诺都应视为破坏性变更。
- ShareAlike（BY-SA）数据许可相对我们的 CC-BY-4.0 选择而言，给下游
  复用添了麻烦。

### 3.3 BitterDB（希伯来大学）— http://bitterdb.agri.huji.ac.il/dbbitter.php

**体量（站点自报，首页，2026-11-03 抓取）。**"BitterDB underwent a
major update in 2024: BitterDB now holds over 2400 bitter molecules."
（BitterDB 于 2024 年完成大更新：现持有超过 2400 个苦味分子。）同页
按物种给出受体计数，如人类："26 functional bitter taste receptors
(TAS2Rs). Of these, 23 have experimentally validated ligands and the
remaining 3 are orphans"（26 个功能性苦味受体，其中 23 个有实验验证
配体，其余 3 个为孤儿受体）；小鼠 35（26 有配体）；鸡 3；猫 12
（8 有配体）；另有鸭嘴兽、针鼹、牛、鲨鱼等。与 MAIC-DB 体量最接近
（千级行数、小型实验室团队）。

**信息架构。** 单个长 PHP 页（`dbbitter.php`）加锚点导航（Search、
Compounds、Receptors、Alignments、Catalog、Classifiers、Blast、
Download、Help）——一种前 SPA 时代的"一切在一页"模式。两类实体、
各有实体页：`Receptor.php?id=N` 与 `compound.php?id=N`（链接模式见
于 `Receptor.php?id=1` 与 `dbbitter.php` 的抓取 HTML）。受体页
（hTAS2R1，`Receptor.php?id=1`）显示：别名、外链（UniProt、GPCRDB、
GeneCards、Human Protein Atlas、IUPHAR/BPS）、物种、染色体位置、
"Number of known ligands: 82"、分子量、全长序列，以及 Known
Ligands 列表（每个化合物链到其页面）加所选化合物的 SDF 下载。
化合物浏览表本身是 JS DataTables 部件（页面头部可见 jQuery
DataTables CSS 引入），故落地页上化合物行没有静态 href。

**证据链。** 化合物页（strychnine〔士的宁〕，`compound.php?id=100`）
显示名称、id、"Natural" 徽标、"Detailed experimental validation
described in the associated resource."（详细实验验证见关联资源。）
一行，以及 "References for the compound bitterness" 编号文献表——
每条是带 PubMed 链接的完整引文（如 "[1] Meyerhof W, Batram C, …
(2010). The molecular receptive ranges of human TAS2R bitter taste
receptors. Chem Senses 35(2): 157-70. PubMed 20022913"）。引用粒度
是每化合物（每实体），不是每测量；无逐字引文、无置信度、无条件键。
抓取的页面上受体侧配体列表同样不带逐对引用。

**下载与引用。** 冻结的按年下载目录，直接从首页链接：
`downloads/2019/?file=…` 与 `downloads/2024/?file=…`，各约 12 个 CSV
（BitterCompoundsPropA_2024.csv、compound snamesA_2024.csv、
ligandReceptorsA_2024.csv、mutationData_2024.csv、snpData_2024.csv、
compRefA_2024.csv、dbreferencesA_2024.csv、IUPHAR_cidA_2024.csv、
ReceptorSearchA_2024.csv、cbitterresourceA_2024.csv、
compzinclinksA_2024.csv、drugbankcidA_2024.csv——均在
`dbbitter.php` 上以 href 观察到）。无 DOI、无 CITATION 文件；引用
模型是"引用我们的 NAR 论文"（首页链至 2012 年 NAR 数据库专辑论文
作为应引用之物）。许可："This work is licensed under a Creative
Commons Attribution-NonCommercial-NoDerivatives 4.0 International
License."（首页页脚）。全站无逐页引用。

**值得借鉴（判断）。**
- 冻结的按年下载目录（2019/2024）与我们版本 DOI 是同一个想法的
  近零工具成本版——但 MAIC-DB 已有更强的形态（带版本的 DOI +
  manifest），无可引入。
- 双向实体链接：化合物页列出受体、受体页列出化合物。MAIC-DB 的
  生物活性块是单向的（通道 → 化合物）；未来的化合物索引页
  （M4+ 候选，非 M3）能闭环。
- "orphan vs validated" 受体词汇（"23 有实验验证配体，其余 3 个为
  孤儿"）——一种紧凑的覆盖度披露模式；MAIC-DB 的类比物是逐参数
  覆盖计数，browse 卡片已经在渲染。

**值得避免（判断）。**
- 数据用 CC BY-NC-ND：禁商用 + 禁演绎对复用是最大程度的限制；对照
  之下我们的 CC-BY-4.0 选择显得更对。
- 主张型数据库却用文献级引用：想知道*为什么*士的宁被列为 TAS2R7 的
  苦味物，读者得到的是一份书目，不是可追溯的提取。
- 浏览表只有 JS（DataTables）、无静态行级链接：除经受体页链接的
  入口页外，搜索引擎与存档器看不见化合物集合。
- 引用 = "引我们 2012 年的论文"、无逐发布引用工件：下游用户无法
  固定他们下载的版本。（我们的版本 DOI + CITATION.cff 正是为了
  防这个。）

### 3.4 Stanford HIVdb — https://hivdb.stanford.edu

**访问现状。** 当前站点是 JavaScript 单页应用：探测的每个路径
（`/`、`/dr-summary/`、`/page/release-notes/`、
`/page/scoring-algorithms/`、`/page/program-notes/`、`/dr/`、
`/dr/genotypes/`、`/page/genotype-treatment/`、`/pages/genotype-rx.html`）
都返回同一个约 1.6 KB 的壳，body 为 `<noscript>You need to enable
JavaScript to run this app.</noscript><div id="root"></div>` 加一个
打包的 `/static/js/main.*.js`（2026-11-03 抓取）。**当前 UI 无法静态
抓取**——对存档器也一样。壳自身的 meta 描述自述范围："A curated
database containing nearly all published HIV RT and protease
sequences…"。自报体量计数：未查到（统计页在 SPA 内部）。

**历史证据（Wayback，抓取于 2019-12-16；SPA 之前的站点）。**
经典站点
（http://web.archive.org/web/20191216101612/https://hivdb.stanford.edu/）
是服务端渲染的多页站，板块：Home、Genotype-Rx、Genotype-Pheno、
Genotype-Clinical、HIVDB Program、About，外加 Database Statistics
与 User Guide & Database Documents 链接。基因型-治疗页
（`/pages/genotype-rx.html` 快照，同日）提供查询工具（治疗档案、
突变档案、详细查询）与可下载数据集（"Download protease, RT &
integrase genotype-treatment dataset"）。

**证据链范式。** 程序页快照（该次抓取中 by-mutations URL 重定向到
CPR 工具页）以 HIVdb 自己的话说明设计目标："Its purpose is
educational and as such it provides extensive comments and a highly
transparent scoring system that is hyperlinked to data in the HIV Drug
Resistance Database."（其目的是教育性的，因此提供详尽注释与高度
透明的评分系统，并与 HIV 耐药数据库中的数据超链接。）——并带显式
双重版本："Sierra version 2.4.2 (last updated on 2019-11-01), HIVdb
version 8.9-1 (last updated on 2019-10-25)"。评分算法本身（规则
文件，ASI 格式）长期公开，这是"评分可溯源到文献"背后的机制。注意
与 MAIC-DB 的认识论差异：HIVdb 的评分是**导出量**——由带版本的
算法在策划过的突变-文献链接上计算，透明性来自公开算法；MAIC-DB
的证据链是**逐行策划的**（逐字引文 + 策展人赋予的置信度）。此范式
在当前站点上的渲染无法静态核验。

**值得借鉴（判断）。**
- 言出且行至的透明契约——"每个评分超链到其背后的数据"——与
  "每个数值距离其测量行与逐字证据引文仅一步之遥"是同一份契约；
  HIVdb 是存在证明：这份契约说响了，**就是**一个策划数据库的品牌。
- 工具页上的双重版本显示（程序/算法版本 + 数据版本，各带日期）：
  MAIC-DB 的类比物（数据集版本 DOI + 概念 DOI + 构建溯源）有朝一日
  可以做成一条小小的"我在看什么"信息条，M4 查询工具出现后尤其。
  - 带版本、逐发布的可下载批量数据集（2019 页）——同样，我们已有
    DOI 背书的等价物。

**值得避免（判断）。**
- 整个数据库以 JS SPA 发布、无服务端渲染回退：资源对爬虫不可见、
  Wayback Machine 无法以任何有用的形式存档、无 JS 不可用。对公共
  品数据库这是自伤；MAIC-DB 的静态 HTML 选择（规格书 §3 Q1）被此例
  验证。

## 4. 对照矩阵

四个面 × 五个站点。"…" = 无法静态核验（原因见各节）。除标注外均为
2026-11-03 在线抓取。

| 面 | MAIC-DB（本地构建） | Channelpedia | GtoPdb | BitterDB | HIVdb |
|---|---|---|---|---|---|
| **家族导航** | 扁平两级：browse 页按 7 家族分组 12 卡；无面包屑；有按参数的横切（`/parameters/`） | 深导航树 K→Kv→Kv1→Kv1.1（4–5 层，180 通道） | 类型→家族→靶点，家族显示在靶点页面包屑；每靶点约 25 板块 Contents 目录（2025-02-19 快照；在线页在墙后） | 无家族层：两个扁平实体列表（化合物、受体）带物种过滤；单长页 + 锚点 | 经典站有板块导航（Genotype-Rx/Pheno/Clinical）（2019-12-16 快照）；当前 SPA 不可核验 |
| **实体页密度** | 卡 = 标识（11 字段）+ 最多 16 个参数块 + 生物活性；每行可展开；两种计数口径点名 | 每通道一个长 wiki 页：实验、变异、结构、药理、表达、模型；社区可编辑 | 靶点页约 25 板块含配体互作表；四站中最密（2025 快照） | 受体页：别名、外链、位置、配体数、序列、配体列表 + SDF；化合物页：徽标 + 文献表——稀疏 | …（SPA）；历史上是工具/结果页而非实体卡 |
| **证据链** | 逐行：逐字引文 + 出处 + 置信度 + 提取注记 + 条件键 + n；锚点深链；冻结层横幅；引文永不翻译 | 逐条目：转述摘要 + 方括号编号 → 站点 PubMed 表；无引文/置信度/条件；wiki 可编辑 | 逐值：文献编号 → 页底全引文带 PMID；一个条件字段（钳制电压）；无引文/置信度（2025 快照） | 逐实体：编号文献表带 PMID 链接；无逐值引用、无引文/置信度/条件 | 算法式：带版本的评分规则 + "hyperlinked to data"（自述，2019）；当前渲染不可核验 |
| **下载与引用** | 4 个文件与 Zenodo 字节一致；版本 + 概念 DOI；CC-BY-4.0/MIT；CITATION.cff；未映射（16）披露；AI 贡献者页脚 | 无自助下载；批量数据邮件申请；未发现许可/DOI | 下载页在墙内；Zenodo report DOI（最新 10.5281/zenodo.23667960）；CC BY-SA 4.0；逐页 "How to cite" 5 种格式 | 按年冻结 CSV 包（约 12 文件 × 2019/2024）；无 DOI；CC BY-NC-ND 4.0；引论文模型 | 带版本的可下载数据集（2019）；当前页不可核验 |

**MAIC-DB 差异最大的三处**（判断）：证据链粒度（其他家引用的是文献或
算法；MAIC-DB 引用的是句子）；双语完整度（四家均无第二语言树；
BitterDB 页眉有希伯来大学名但没有镜像的 locale 树）；开放静态可访问性
（Channelpedia 与 BitterDB 今天可匿名抓取；GtoPdb 的数据库页与
HIVdb 整站不可——分别为墙与 JS 壳）。

## 5. 结论

### 5.1 差异化主张：成立

研究问题中的假设——MAIC-DB 的行级逐字证据链（每个测量：逐字引文 +
置信度 + 条件键，锚点可寻址）比同类策划数据库更严格——对照 2026-11-03
抓取的四站**成立**：

- Channelpedia：转述 + 编号文献；无逐值链。
- GtoPdb（2025 快照）：逐值文献编号 + 一个条件字段——精神上最接近，
  但信任单位仍是文献而非被提取的句子，且没有置信度维度。
- BitterDB：仅逐实体书目。
- HIVdb：透明性来自公开的带版本算法叠加策划链接；强，但属于另一种
  （导出量的）认识论。

所检站点没有一个做到：每个数据行呈现**原文的精确句子、它在论文中的
位置、策展人赋予的置信度、实验条件键**。这个组合是 MAIC-DB 在此同类
组中站得住的新颖性，而冻结层横幅（两个通道上的显式"未再核验"标记）
超出了四站上观察到的任何做法。

静态、免 JS、匿名可抓取这一属性——本组中今天只有 BitterDB 同享——
应被视为同一差异化的一部分，而非实现细节：GtoPdb 的墙与 HIVdb 的
SPA 壳都把数据库从匿名记录中抹去了。

### 5.2 候选引入清单（供未来 ticket；均不开 M3 范围）

每条注明所触面与代价。全部为判断。

1. **通道卡上的 "How to cite this page" 块**（源自 GtoPdb；面：
   下载/引用）。代价：小模板改动 × 双 locale；内容已在
   CITATION.cff。M4 打磨候选。
2. **逐发布的 Zenodo report DOI**，用于发布说明/数据注记摘要
   （源自 GtoPdb；面：下载/引用）。代价：每发布一次 Zenodo 存档，
   downloads 页链接。低。
3. **生物活性行的化合物侧索引**（源自 BitterDB 的双向链接；面：
   信息架构）。代价：一种新页面类型 + 搜索索引条目；化合物在 M3
   不是实体（规格书 Q7），所以这首先是 M4+ 的数据模型问题。
4. **每通道的模型区**（源自 Channelpedia；面：实体页密度）。
   代价：需要尚不存在的模型内容；只有当有人用 MAIC-DB 参数建模型时
   才值得。
5. **"我在看什么"版本信息条**——内容页上浮出数据集版本 + 构建溯源
   （源自 HIVdb 的双重版本；面：实体页密度）。代价：琐碎的模板改动，
   但给 64 页添噪音；考虑与 M4 查询工具一起做——在那里，*计算出的*
   答案的溯源才真正要紧。
6. **明确的反面清单，记录在案**：注册墙（GtoPdb）、纯 JS 壳
   （HIVdb）、邮件门控的批量数据（Channelpedia）、NC-ND 许可与
   只引论文（BitterDB）。避免它们的代价：除维持现有静态站 + DOI +
   CC-BY 姿态外为零。

尽管表面相似而**刻意不引入**的模式：行内编号文献（GtoPdb）——
measurement-id 锚点已严格包含更多信息；按年下载目录（BitterDB）——
版本 DOI + manifest 是同一想法更强的形态。

## 6. 来源

全部在线 URL 于 2026-11-03 抓取（除标注外 HTTP 200）。Wayback 快照
各自携带抓取日期。

### MAIC-DB（本地仓库）

- `docs/m3-website-spec.md`（§3 Q1–Q11、§4 数据事实、§5 站点结构）
- `site/templates/base.html`、`browse.html`、`card.html`、
  `parameters.html`、`downloads.html`
- 渲染页，本地预览 `http://localhost:8000/`：`/`、`/downloads/`、
  `/channels/piezo1/`、`/parameters/conductance/`
- `site/_site/` 与 `site/_site/zh/` 树（64 个 HTML 页，结构清单）

### Channelpedia

- https://channelpedia.epfl.ch （首页；自报 180 通道 / 50 HH 模型 /
  约 180,000 摘要）
- https://channelpedia.epfl.ch/wikipages/1 （Kv1.1 wiki 页；板块、
  实验条目、引用标记）
- https://channelpedia.epfl.ch/expdata （导航树）
- https://channelpedia.epfl.ch/faq （数据共享问答：批量数据与 HEKA
  文件走邮件；wiki 编辑政策；细胞 ID 定义）

### Guide to Pharmacology

- https://www.guidetopharmacology.org/ （首页；注册横幅、版本
  2026.3.1、CC BY-SA 4.0 页脚、Zenodo report DOI
  10.5281/zenodo.23667960）
- 登录墙页（2026-11-03 抓取）：
  https://www.guidetopharmacology.org/GRAC/LigandListForward?type=Approved 、
  https://www.guidetopharmacology.org/GRAC/AboutPageForward 、
  https://www.guidetopharmacology.org/download.jsp 、
  https://www.guidetopharmacology.org/GRAC/ReceptorFamiliesForward?type=IC
- https://blog.guidetopharmacology.org/2026/09/16/database-release-2026-3/
  （自报 3,147 人类靶点 / 13,989 配体 / 50,429 文献）
- https://blog.guidetopharmacology.org/2026/07/29/user-registration-is-coming-to-gtopdb/
  （注册制公告）
- Wayback 快照（2025-02-19 抓取），CaV1.2 靶点页：
  http://web.archive.org/web/20250219223557/https://www.guidetopharmacology.org/GRAC/ObjectDisplayForward?objectId=529

### BitterDB

- http://bitterdb.agri.huji.ac.il/dbbitter.php （首页；自报 >2,400
  分子、按物种受体计数、下载 CSV 链接、CC BY-NC-ND 4.0 页脚）
- http://bitterdb.agri.huji.ac.il/Receptor.php?id=1 （hTAS2R1 受体页）
- http://bitterdb.agri.huji.ac.il/compound.php?id=100 （士的宁化合物
  页；文献表引用模型）

### Stanford HIVdb

- https://hivdb.stanford.edu/ 及路径 `/dr-summary/`、`/dr/`、
  `/page/release-notes/`、`/page/scoring-algorithms/`、
  `/dr/genotypes/`、`/page/genotype-treatment/`、
  `/pages/genotype-rx.html`（全部：相同的约 1.6 KB JS 应用壳；SPA
  结论）
- Wayback 快照（2019-12-16 抓取），首页：
  http://web.archive.org/web/20191216101612/https://hivdb.stanford.edu/
- Wayback 快照（2019-12-16 抓取），genotype-rx 页：
  http://web.archive.org/web/20191216/https://hivdb.stanford.edu/pages/genotype-rx.html
- Wayback 快照（2019-12-16 抓取），by-mutations/CPR 程序页：
  http://web.archive.org/web/20191216101612/https://hivdb.stanford.edu/hivdb/by-mutations/
