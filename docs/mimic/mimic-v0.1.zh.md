# MIMIC v0.1 — 内部草稿

> **译注（2026-11-07）**：本文是英文原版 [`mimic-v0.1.md`](mimic-v0.1.md) 的中文译本，**仅供人工阅读**；英文原版为权威版本，本译文**不得作为任何工作的依据或参考**。字段名、枚举值、表名、SQL、命令与数字保持原样。

> **状态：内部草稿，不对外发布。** 本文档是供项目自身策展与分析工作
> 使用的工作草稿。它不是已发布的标准，不带有版本 DOI，也不得被外部
> 引用（决定于 2026-11-06）。本文档同样不定义任何新的存储：根据同一
> 决定，此处描述的每一处映射都位于**派生分析层**，绝不作为对 vault
> 策展数据的回写。

- **日期**：2026-11-06
- **依据**：README "The MIMIC Standard"（五个类别）、现有的
  `biophysics_experiment` 列，以及实测语料
  （[corpus baseline](../research/2026-11-06-corpus-baseline.md)）。
- **复现**：逐字段的覆盖率数字可由
  `uv run python scripts/corpus-stats.py` 重新导出；§4/§10 中的层级合取
  以及 §6.1 中的 `stimulus_type` 计数由 `tests/test_corpus_stats.py` 中的
  普查 SQL 固定。§6.4 的拆分被明确推迟，且不带有任何按值计数。

## 1. 目的

MIMIC（Minimum Information about a Mechanically Induced Current，机械
诱导电流的最小信息）是本项目希望一项机械生物学测量所满足的字段级
契约。Schema 已经预留了这些列；本草案决定哪些字段是**使一行数据具备
可比性所必需的**、它们采用哪些词表，以及"缺失"意味着什么——从而
可以依据一份成文规则而非直觉，来构建校验器与覆盖率报告。

## 2. 范围

| 范围内（v0.1） | 范围外（推迟至 v0.2） |
|---|---|
| `biophysics_experiment` 行（data-v1.0 为 948 行） | `bioactivity` 行（化合物测定需要其自身的最低要求：测定形式、细胞系、读出） |
| 字段层级、词表、缺失值语义 | `variant` / `structure` 关联规则 |
| 行级、出版物级与语料级评分 | MIMIC 评分的站点渲染 |
| `condition_key` 方言问题 | 对策展数据的任何回写 |

## 3. 设计原则

1. **分层级，而非单一门槛。** 单一"完整"门槛会拒绝几乎所有语料
   （§5）。v0.1 使用三个层级：**L1**（缺少即无法比较两行数据的
   字段）、**L2**（读者判断实验所需的字段）、**L3**（提升复用性的
   字段）。
2. **受控词表或已声明的自由文本。** 可枚举字段是一个带有成文转义
   取值的枚举；真正开放的字段（溶液、构建体）是自由文本，并明确
   声明为自由文本。
3. **来源证据不属于层级。** 证据链已 99.8% 完整（948 行中的 946 行；
   仅 `evidence_location` 存在缺口），它是任何一行的前提条件，而非
   评分对象。
4. **三态缺失。** 校验器必须区分*未记录*、*不适用*与*未解析的散文*；
   派生层承载这一区分，源数据不必如此。
5. **派生，绝不破坏。** 映射与规范化产生一份以 `measurement_id` 为键
   的独立分析输出；策展值绝不会被本标准重写。

## 4. 层级

| 层级 | 含义 | 字段 |
|---|---|---|
| **L1** | 两行数据可进行比较的最低要求 | 来源证据集 + `recording_mode` + `stimulus_type` |
| **L2** | 读者可据此判断实验 | + `cell_type` + `expression_system` |
| **L3** | 可用于建模 / 元分析 | + `n` + `temperature_c` + `ph` + 浴液/电极内液 + 保持电位 |

### 实测符合度（data-v1.0，累积）

逐行普查 SQL（每一步在前一步的基础上增加一个谓词；来源证据集为
`measurement_id`、`evidence_quote`、`confidence`、
`condition_key`）：

| 层级步骤 | 行数 | 占 948 的比例 |
|---|---|---|
| 来源证据集 | 948 | 100.0% |
| + `recording_mode` | 909 | 95.9% |
| + `stimulus_type`（**L1 完整**） | 808 | **85.2%** |
| + `cell_type`、`expression_system`（**L2 完整**） | 676 | **71.3%** |
| + `n` | 335 | 35.3% |
| + `temperature_c` | 23 | 2.4% |
| + `ph` | 11 | 1.2% |
| + `bath_solution` | 11 | 1.2% |
| + `pipette_solution` | 11 | 1.2% |
| + `holding_potential_mv`（**L3 完整**） | 11 | 1.2% |

温度在 v0.1 中**不是** L1 字段：将其提升会使合格语料从 85.2%（808 行）
降至 5.6%（53 行，L1 ∩ temperature）。它保持在 L3，环境方面的缺口作为
一项语料层面的发现予以报告，而非作为行级门槛；完整 L3 符合度为 11 行
（1.2%）。

上述层级计数针对的是**原始**语料，因此包含 §6.1 在 v0.1 中禁用的 238 行
`stimulus_type = OTHER`。排除 `OTHER` 后，L1 = 578（61.0%），
L2 = 467（49.3%）。

## 5. 字段规范

覆盖率的定义是"取值为非 NULL 的行数 / 948"，基于 data-v1.0。

### 5.1 刺激

| 字段 | 层级 | 类型 | 覆盖率 | 说明 |
|---|---|---|---|---|
| `stimulus_type` | **L1** | 枚举（§6.1） | 86.9% | `OTHER` 占 238 行（25%），`NULL` 为 124 行——该枚举是最大的词表任务 |
| `stimulus_waveform` | L3 | 枚举（step、ramp、pulse、sinusoidal、other） | 0% | 列已预留，从未填充 |
| `stimulus_velocity` + unit | L3 | 数值 + 单位 | 0% | 速率依赖型阈值所需 |
| `stimulus_duration_ms` | L3 | 数值 | 0% | — |
| `probe_geometry` | L3 | 枚举（pipette、blunt probe、bead、AFM tip、membrane-only、other） | 0% | — |
| `probe_diameter_um` | L3 | 数值 | 0% | — |

### 5.2 记录

| 字段 | 层级 | 类型 | 覆盖率 | 说明 |
|---|---|---|---|---|
| `recording_mode` | **L1** | 枚举（§6.2） | 95.9% | — |
| `holding_potential_mv` | L3 | 数值 | 65.3% | 按家族逐一测量后可考虑升为 L2 |
| `sampling_rate_khz` | L3 | 数值 | 0% | — |
| `filter_khz` | L3 | 数值 | 0% | — |
| `analysis_method` | L3 | 枚举（§6.3） | 0% | 列已预留；目前方法仅隐含于 `extractor_note` 中（945 条注释中有 189 条提及拟合） |

### 5.3 细胞背景

| 字段 | 层级 | 类型 | 覆盖率 | 说明 |
|---|---|---|---|---|
| `cell_type` | **L2** | 受控标签（原代细胞类型或宿主细胞系） | 82.4% | 目前为自由文本；需要 §6.4 的拆分 |
| `expression_system` | **L2** | 受控标签 + 细节 | 95.7% | 目前为自由文本，单行最长 296 个字符（907 行已填充中有 444 行超过 90 个字符）；分解推迟，见 §6.4 |

### 5.4 环境

| 字段 | 层级 | 类型 | 覆盖率 | 说明 |
|---|---|---|---|---|
| `temperature_c` | L3 | 数值（°C） | 9.0% | 17–38 °C，中位数 24——环境类字段中最薄弱的一项 |
| `ph` | L3 | 数值 | 57.7% | 5.0–9.5，中位数 7.3 |
| `bath_solution` | L3 | 自由文本 | 77.5% | 声明为自由文本；组成成分词表属于 v0.2 |
| `pipette_solution` | L3 | 自由文本 | 68.6% | 同上 |

### 5.5 分析

| 字段 | 层级 | 类型 | 覆盖率 | 说明 |
|---|---|---|---|---|
| `n` | L3 | 整数，或按原样记录的区间/文本（该列为 TEXT） | 53.1% | 把 71% 与 35% 区分开的字段；503 行已填充中有 16 行保存的是 `3-6`、`>4` 一类取值，因此校验器必须按"整数或区间"解析，而不能直接按 int 解析 |
| `n_cells` | L3 | 整数 | 0% | 在两者被分别定义之前，与 `n` 冗余 |

### 5.6 来源证据（前提条件，不参与评分）

| 字段 | 覆盖率 | 说明 |
|---|---|---|
| `measurement_id`、`evidence_quote`、`confidence`、`condition_key` | 100% | `confidence` 目前没有成文评分标准——§6.5 对此作出规定 |
| `evidence_location` | 99.8% | 分类体系见语料基线（Results 71.9%） |
| `extractor_note` | 99.7% | 按所记录的语言原样记录，绝不翻译 |

## 6. 受控词表（v0.1）

### 6.1 `stimulus_type`

该枚举有十个成员（`src/maicdb/enums.py`）；v0.1 全部保留，并将两个
逃生取值拆开处理，而不发明新的顶层名称：

| 取值 | 行数 | 处理 |
|---|---|---|
| `PRESSURE_CLAMP` | 314 | 保留 |
| `SUCTION` | 110 | 保留 |
| `INDENTATION` | 95 | 保留 |
| `TOUCH` | 22 | 保留 |
| `HYPOTONIC` | 15 | 保留 |
| `SHEAR_STRESS` | 12 | 保留 |
| `POSITIVE_PRESSURE` | 11 | 保留 |
| `MEMBRANE_STRETCH` | 7 | 保留（定义为"无探针的脂双层形变"） |
| `OSMOTIC` | 0 | 保留（枚举成员，在 data-v1.0 中未使用） |
| `OTHER` | 238 | **v0.1 中禁用**：必须替换为某个取值，或替换为 `OTHER: <free detail>` 加 `stimulus_waveform`；这 238 行是首个策展待办项 |
| `NULL` | 124 | 视为*未记录*，而非*不适用* |

### 6.2 `recording_mode`

现有取值足够：`WHOLE_CELL`、`CELL_ATTACHED`、`INSIDE_OUT`、
`OUTSIDE_OUT`、`TEVC`、`RECONSTITUTED_PROTEOLIPOSOME`、`PLANAR_PATCH`、
`PERFORATED_PATCH`。v0.1 以与 §6.1 相同的方式废止 `OTHER`（12 行），
并要求双电极模式在 `cell_type` 中指明卵母细胞背景。

### 6.3 `analysis_method`

新枚举（目前覆盖率 0%）：`BOLTZMANN_FIT`、`HILL_FIT`、`LINEAR_FIT`、
`SINGLE_EXPONENTIAL_FIT`、`MULTI_EXPONENTIAL_FIT`、`THRESHOLD_CROSSING`、
`MANUAL_READ`、`OTHER`。自由文本细节仍保存在 `extractor_note` 中。

### 6.4 `expression_system` → 宿主 + 方法 + 细节

当前这一列在一个字符串中混合了三类事实。v0.1 定义其分解方式（派生层；
由 `measurement_id` 保持关联）：

| 组成 | 取值 | data-v1.0 状态 |
|---|---|---|
| `host_system` | `HEK293`、`CHO`、`XENOPUS_OOCYTE`、`E_COLI_SPHEROPLAST`、`RECONSTITUTED_MEMBRANE`、`NATIVE_CELL`、`OTHER` | 907 行已填充的自由文本；拆分规则**尚未确定**，因此此处不陈述任何按值计数 |
| `expression_method` | `TRANSIENT`、`STABLE`、`ENDOGENOUS`、`PURIFIED_RECONSTITUTED`、`UNKNOWN` | 同步派生 |
| `expression_detail` | 自由文本，逐字保留 | 保留原始字符串 |

拆分规则属于 v0.2 的工作。已测得的事实是：907 行已填充、最长字符串 296
个字符、444 行超过 90 个字符。一次临时处理产生过一份宿主系统分布，但
由于其规则从未确定，无法从本文档开头所引用的来源重新导出，因此该分布
被有意不予报告。映射决定应归入带有规则本身的数据说明表，而非本文档。

### 6.5 `confidence`

唯一一个覆盖率达 100% 却没有成文评分标准的字段。v0.1 定义如下：

| 取值 | 判定标准 |
|---|---|
| `high` | 取值在正文或表格中明确陈述；单位明确；条件无歧义 |
| `medium` | 取值可从图 / 图注读出，或其中一个条件组成部分由抽取器推断 |
| `low` | 取值由多处陈述重构，或条件已知不完整 |

应用于语料时，该标准仍会产生 537/400/11 的分布；重新审计抽样是检验其
是否被一致应用的检查手段（后续工作）。

## 7. `condition_key`

两种方言并存：569 条结构化（`253J_native_inside-out_-60mV_sym150KCl`）
与 379 条散文式（`Acutely dissociated mouse Müller glia, ... 25°C`）。

v0.1 规则：结构化形式是目标语法——

```
<construct>_<cell>_<recording>_<potential>_<solution>
```

其中 `not-recorded` 作为缺失组成部分的显式标记。散文式键在派生层中被
标注为 `UNSTRUCTURED`，且**不会**被静默解析；解析器可以从其中抽取
组成部分，但任何抽取出的取值都带有自身的来源证据，且绝不覆盖原始键。

## 8. 缺失值语义

派生层按字段区分：

| 标签 | 含义 |
|---|---|
| `NOT_RECORDED` | 源值为 NULL，且论文未说明 |
| `UNPARSED` | 源值为自由文本，规则无法映射（例如 §6.4 规则无法归类的宿主系统字符串） |
| `NOT_APPLICABLE` | 该字段在此设计中不可能存在（例如仅有膜片的压力钳实验中的探针几何） |
| `PRESENT` | 存在取值，并附来源证据 |

`NOT_APPLICABLE` 是策展人作出的断言，必须说明理由；默认值绝不为
`NOT_APPLICABLE`。

## 9. 评分

- **行级**：L1 / L2 / L3 完整，外加逐字段状态标签。
- **出版物级**：该论文各行在每一层级上的占比。
- **语料级**：§4 中的累积表，由校验器重新导出。
- 一行数据可以是 L1 完整的，却仍然不满足来源证据前提（data-v1.0 中有
  两行的 `evidence_location` 为 NULL，因此它们在位置这一组成部分上
  不合格）——校验器分别报告这两者。

## 10. 基线符合度（v0.1 对 data-v1.0 的解读）

| 指标 | 值 |
|---|---|
| L1 行数 | 808 / 948 (85.2%) |
| L2 行数 | 676 / 948 (71.3%) |
| L3 行数（`n`） | 335 / 948 (35.3%) |
| L3 行数（全部环境字段） | 11 / 948 (1.2%) |
| 排除 `stimulus_type = OTHER` 后的 L1 行数 | 578 / 948 (61.0%) |
| 排除 `stimulus_type = OTHER` 后的 L2 行数 | 467 / 948 (49.3%) |
| L1 上表现最差的家族 | K2P 54/145 (37.2%)、TRP 22/70 (31.4%)——`stimulus_type` 缺口：K2P 仅在 59/145 行填充，TRP 仅在 33/70 行填充；其余五个家族为 99.5–100% |
| `stimulus_type = OTHER` 待办量 | 238 行 |
| `expression_system` 自由文本行数 | 907（拆分推迟至 v0.2） |
| 散文式条件键 | 379 行 |

## 11. 待决问题（v0.2 之前需要作出的决定）

1. **温度层级**：保持 L3（当前提议），还是在覆盖率超过某一阈值后
   提升至 L2？阈值提议本身需要一次决定。
2. **`n` 与 `n_cells`**：界定二者区别，或废止其中之一。
3. **K2P / TRP 的 L1 失败**：这是策展缺口（可从源 PDF 重新抽取），
   还是纯脂质实验的固有属性、应当放宽 `stimulus_type`？
4. **Bioactivity 自身的标准**：`IC50/EC50/KD/KI` 行需要测定形式与
   细胞系方面的最低要求；v0.2 需要给出提议。
5. **单位政策**（来自语料基线，F3）：`mN/m` ≡ `dyn/cm` 是拼写决定；
   `psi → mmHg` 与 `um → nm` 是换算。在任何分析合并分桶之前，这条
   规则应置于何处？

## 12. 附录

### A. Schema 映射

| MIMIC 类别 | 列 |
|---|---|
| Stimulus | `stimulus_type`、`stimulus_waveform`、`stimulus_velocity(_unit)`、`stimulus_duration_ms`、`probe_geometry`、`probe_diameter_um` |
| Recording | `recording_mode`、`holding_potential_mv`、`sampling_rate_khz`、`filter_khz`、`analysis_method` |
| Cell context | `cell_type`、`expression_system` |
| Environment | `temperature_c`、`ph`、`bath_solution`、`pipette_solution` |
| Analysis | `n`、`n_cells` |
| Provenance | `measurement_id`、`evidence_quote`、`evidence_location`、`confidence`、`extractor_note`、`condition_key` |

### B. 下一个产物

`scripts/mimic-validate.py`（只读）：按行与按出版物输出 §9 的评分，以
确定性 JSON 形式给出，并带 §8 的状态标签。它不得写入数据库，且其语料
总计必须能够复现 §4 中的表格。

### C. 参考文献

- README "The MIMIC Standard"
- `docs/research/2026-11-06-corpus-baseline.md`（实测语料形态）
- `docs/m3-website-spec.md` §4（产物普查）
