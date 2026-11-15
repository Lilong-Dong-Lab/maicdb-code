# MAIC-DB 语料库基线：文献与数据（元研究第 1 轮）

> **译注（2026-11-07）**：本文是英文原版 [`2026-11-06-corpus-baseline.md`](2026-11-06-corpus-baseline.md) 的中文译本，**仅供人工阅读**；英文原版为权威版本，本译文**不得作为任何工作的依据或参考**。字段名、枚举值、表名、SQL、命令、期刊名与数字保持原样。

- **日期**：2026-11-06
- **问题归属**：数据分析工作线 —— 在为 MIMIC 标准（内部草稿 v0.1）下定义之前，先测量语料库里实际有什么
- **方法**：用 `scripts/corpus-stats.py` 对已发布制品（`db/maicdb.sqlite`，data-v1.0）执行一次只读扫描。下文每个数字都是查询结果，没有一个是手工转录的。期刊名通过脚本里的别名表做规范化，每个规范拼写背后的原始变体作为一条数据质量问题列出（规范拼写由 vault 负责维护）。
- **复现**：

  ```bash
  uv run python scripts/corpus-stats.py                    # Markdown
  uv run python scripts/corpus-stats.py --json /tmp/c.json # raw stats
  ```

  两次运行产生逐字节相同的输出（由 `test_stats_are_deterministic` 验证）。§4 部分——即脚本输出去掉 H1、各级标题降一层之后的内容——由 `test_embedded_report_matches_generated_output` 整体与一次新运行比对，因此不会过时；它上面的各项发现属于叙述性内容，只有其测试点名的数字被钉住。

## 1. 本基线的用途

站点目前把语料库逐行渲染出来。这一遍问的是更靠前的问题——语料库本身是什么形态——以便 MIMIC 草稿与元研究计划是依据被测事实、而不是依据印象来写。它不改变任何数据、模式或站点输出；按照范围决策，它只是一层派生分析。

## 2. 关键数字

| 问题 | 答案 |
|---|---|
| 论文数 / 生物物理行 / 生物活性行 | 211 / 948 / 136 |
| 通道 / 家族 | 12 / 7 |
| 发表年份 | 1986–2026（2018 年达峰，15 篇论文） |
| 每篇论文的行数 | 中位数 4，最大 32；8 篇论文没有贡献任何生物物理/生物活性行（其中 6 篇在三张测量表中的任何一张里都没有行） |
| 参数行 | 16 个已注册参数，从 263（conductance）到 3（osmotic threshold） |
| 置信度 | high 537（56.6%），medium 400（42.2%），low 11（1.2%） |
| 期刊字符串 | 67 个原始值 → 规范化后 56 个（7 个变体组） |
| 条件键 | 939 个唯一值 / 948；569 个结构化，379 个散文式 |
| 覆盖率为 0% 的 MIMIC 设计字段 | 探测的 24 个中有 9 个（stimulus velocity/waveform/duration、probe geometry/diameter、sampling rate、filter、analysis method、n_cells） |

## 3. 对两条工作线重要的发现

**F1 —— 策展密度并不跟随文献数量。** 每个通道的行数从 160（PIEZO1）到 18（TRESK）不等，但每个通道的论文数要平坦得多（24 篇 TMC … 6 篇 TRESK）：TRESK 有 6 篇论文却有 34 行生物活性数据，而 PIEZO2 有 8 篇论文却有 0 行生物活性数据。任何“研究不足的通道”的论断都必须说明它指的是哪一条轴。

**F2 —— 参数覆盖极度偏斜。** `conductance`（263）、`p50`（152）和 `tau_inact`（93）承担了 936 个含值行中的 54.3%；`ca_permeability`（4）、`osmotic_threshold`（3）和 `thermal_threshold`（9）几近为空。按通道的矩阵显示，这些缺口是结构性的而不是随机的：没有任何通道覆盖全部 16 个参数，且 12 个通道中有 3 个（TRESK 14、PIEZO2 12、TREK-2 10）在至少 10 个参数上为零行。

**F3 —— 单位异质性是集中的，且有一列看起来类型标错了。** `t50` 分裂为 `mN/m`（26）和 `dyn/cm`（15）——数值上相同（1 mN/m = 1 dyn/cm），所以这是拼写问题，不是换算决策。`p50` 分裂为 `mmHg`（148）/ `psi`（4）——一次真正的换算；`x50` 分裂为 `nm`（37）/ `um`（9）（×1000）；`osmotic_threshold` 混用 `%`、`% HTS`、`mOsm`（没有书面规则就无法比较）。最大的异质性出在 `threshold_fold_shift`，它带有三个语义上互不相容的单位——`%`（13）、`fold`（6）和 **`nm`（12）**——另有 4 行有值但无单位。在一个 fold-shift 列里出现长度，多半是源提取中的列语义错误，而不是单位选择问题；在有任何分析要合并该列之前，需要由 vault 裁决。

**F4 —— 证据溯源是语料库中最强的部分。** quote、confidence、condition key 与 measurement id 都在 100%；location 在 99.8%。相比之下，MIMIC 实验元数据字段很薄：temperature 9.0%，`n` 53.1%，pH 57.7%。

**F5 —— 证据位置聚集在叙述性文本中。** 1084 行中有 779 行（71.9%）指向 Results 正文，122 行指向表格，101 行指向图注，45 行指向摘要。来自摘要的行是最弱的证据类别，而且可以精确计数。

**F6 —— 条件键有两种方言。** 569 行使用结构化的下划线形式，379 行使用散文形式。与 MIMIC 对齐的键语法只能施加于结构化的那一半；散文那一半必须重新策展，或标记为非结构化——草稿必须说明是哪一种。

**F7 —— 期刊拼写需要在 vault 里做一次规范化。** 规范化通过 7 个变体组把 67 个原始字符串收拢为 56 个规范名称（`J Biol Chem` / `Journal of Biological Chemistry`、`PNAS` 及其四个变体、`J Neurosci` / `Journal of Neuroscience` / `The Journal of Neuroscience`、`eLife` / `Elife`、`PLoS ONE` / `PLoS One`，……）。在上游修好之前，针对期刊的元研究会误导人。

**F8 —— 出版物行并不意味着有数据。** 211 篇论文中有 8 篇没有贡献任何生物物理或生物活性行；其中两篇（publication 35 和 90）确实带有 `unmapped_measurement` 行，因此在三张测量表合计下来有 6 篇论文完全没有行。它们要么应当被说明理由（背景论文），要么应当被删除，答案应落在数据说明里。

## 4. 生成的报告

由 `scripts/corpus-stats.py` 从 `db/maicdb.sqlite`（只读）派生。每个数字都是查询结果；没有任何数值是手工转录的。

### 1. 语料库规模

| 表 | 行数 |
|---|---|
| bioactivity | 136 |
| biophysics_experiment | 948 |
| channel | 12 |
| compound | 86 |
| external_reference | 6 |
| publication | 211 |
| unmapped_measurement | 16 |
| variant | 125 |

### 2. 论文文献计量

- 年份范围：**1986–2026**
- 不同期刊字符串（原始）：**67**
- 规范化后不同期刊：**56**
- 每篇出版物的行数：211 篇论文共 1084 行（中位数 4.0，最大 32，8 篇无行）

#### 每年论文数

| 年份 | 论文数 |
|---|---|
| 1986 | 1 |
| 1993 | 1 |
| 1995 | 1 |
| 1996 | 1 |
| 1997 | 3 |
| 1998 | 3 |
| 1999 | 3 |
| 2000 | 3 |
| 2001 | 4 |
| 2002 | 8 |
| 2003 | 4 |
| 2004 | 8 |
| 2005 | 6 |
| 2006 | 4 |
| 2007 | 4 |
| 2008 | 3 |
| 2010 | 6 |
| 2011 | 10 |
| 2012 | 9 |
| 2013 | 14 |
| 2014 | 9 |
| 2015 | 12 |
| 2016 | 9 |
| 2017 | 13 |
| 2018 | 15 |
| 2019 | 11 |
| 2020 | 10 |
| 2021 | 11 |
| 2022 | 4 |
| 2023 | 5 |
| 2024 | 12 |
| 2025 | 2 |
| 2026 | 2 |

#### 主要期刊（规范化后）

| 期刊 | 论文数 |
|---|---|
| Proceedings of the National Academy of Sciences | 23 |
| Journal of Biological Chemistry | 22 |
| The Journal of General Physiology | 20 |
| eLife | 15 |
| Nature Communications | 13 |
| Biophysical Journal | 12 |
| The Journal of Neuroscience | 11 |
| Neuron | 8 |
| The EMBO Journal | 8 |
| PLOS ONE | 7 |
| Cell Reports | 6 |
| British Journal of Pharmacology | 4 |
| Nature | 4 |
| Scientific Reports | 4 |
| The Journal of Physiology | 4 |

#### 期刊拼写变体（数据质量清单）

- **Journal of Biological Chemistry** ← `J Biol Chem`, `Journal of Biological Chemistry`
- **PLOS ONE** ← `PLoS ONE`, `PLoS One`
- **Proceedings of the National Academy of Sciences** ← `PNAS`, `Proc Natl Acad Sci U S A`, `Proc Natl Acad Sci USA`, `Proceedings of the National Academy of Sciences`, `Proceedings of the National Academy of Sciences USA`
- **The EMBO Journal** ← `EMBO J`, `The EMBO Journal`
- **The Journal of General Physiology** ← `J Gen Physiol`, `The Journal of General Physiology`
- **The Journal of Neuroscience** ← `J Neurosci`, `Journal of Neuroscience`, `The Journal of Neuroscience`
- **eLife** ← `Elife`, `eLife`

### 3. 通道

| 通道 | 家族 | 生物物理行 | 生物活性行 | 论文数 |
|---|---|---|---|---|
| PIEZO1 | PIEZO | 160 | 14 | 23 |
| TMC | TMC | 153 | 19 | 24 |
| ASIC | DEG_ENaC_ASIC | 108 | 24 | 19 |
| MscS | MSCL_MSCS | 103 | 1 | 23 |
| OSCA | OSCA_TMEM63 | 92 | 2 | 12 |
| MscL | MSCL_MSCS | 89 | 0 | 18 |
| TRPV4 | TRP | 70 | 37 | 23 |
| TREK-1 | K2P | 46 | 4 | 13 |
| TREK-2 | K2P | 42 | 0 | 16 |
| TRAAK | K2P | 39 | 1 | 10 |
| PIEZO2 | PIEZO | 28 | 0 | 8 |
| TRESK | K2P | 18 | 34 | 6 |

### 4. 参数覆盖（每个通道中含值的行）

| 通道 | p50 | t50 | x50 | slope | tau_act | tau_inact | tau_deact | conductance | reversal_potential | delta_p50 | ion_selectivity_ratio | ca_permeability | threshold_fold_shift | macroscopic_rise_time | thermal_threshold | osmotic_threshold |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ASIC | 0 | 0 | 0 | 1 | 21 | 14 | 14 | 14 | 28 | 0 | 11 | 4 | 0 | 0 | 0 | 0 |
| MscL | 21 | 15 | 0 | 3 | 0 | 1 | 1 | 39 | 0 | 1 | 0 | 0 | 8 | 0 | 0 | 0 |
| MscS | 21 | 14 | 0 | 0 | 1 | 3 | 11 | 27 | 5 | 9 | 4 | 0 | 8 | 0 | 0 | 0 |
| OSCA | 36 | 0 | 4 | 0 | 13 | 12 | 2 | 13 | 2 | 0 | 8 | 0 | 0 | 2 | 0 | 0 |
| PIEZO1 | 56 | 9 | 4 | 2 | 0 | 28 | 4 | 31 | 14 | 6 | 5 | 0 | 1 | 0 | 0 | 0 |
| PIEZO2 | 0 | 0 | 0 | 0 | 0 | 15 | 0 | 4 | 4 | 0 | 0 | 0 | 0 | 4 | 0 | 0 |
| TMC | 2 | 0 | 38 | 0 | 1 | 9 | 0 | 47 | 17 | 0 | 27 | 0 | 12 | 0 | 0 | 0 |
| TRAAK | 2 | 1 | 0 | 2 | 4 | 2 | 4 | 19 | 4 | 0 | 0 | 0 | 0 | 0 | 1 | 0 |
| TREK-1 | 12 | 1 | 0 | 3 | 1 | 9 | 0 | 13 | 5 | 0 | 0 | 0 | 0 | 1 | 0 | 0 |
| TREK-2 | 1 | 1 | 0 | 2 | 0 | 0 | 0 | 30 | 0 | 0 | 3 | 0 | 0 | 0 | 2 | 0 |
| TRESK | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 17 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| TRPV4 | 1 | 0 | 0 | 0 | 4 | 0 | 4 | 9 | 17 | 0 | 8 | 0 | 6 | 6 | 6 | 3 |

| 参数 | 行数 |
|---|---|
| p50 | 152 |
| t50 | 41 |
| x50 | 46 |
| slope | 13 |
| tau_act | 45 |
| tau_inact | 93 |
| tau_deact | 40 |
| conductance | 263 |
| reversal_potential | 97 |
| delta_p50 | 16 |
| ion_selectivity_ratio | 66 |
| ca_permeability | 4 |
| threshold_fold_shift | 35 |
| macroscopic_rise_time | 13 |
| thermal_threshold | 9 |
| osmotic_threshold | 3 |

### 5. 每个参数的单位拼写

- **p50**: `mmHg` ×148, `psi` ×4
- **t50**: `mN/m` ×26, `dyn/cm` ×15
- **x50**: `nm` ×37, `um` ×9
- **osmotic_threshold**: `%` ×1, `% HTS` ×1, `mOsm` ×1
- **delta_p50**: `mmHg` ×16
- **threshold_fold_shift**: `%` ×13, `nm` ×12, `fold` ×6

### 6. 置信度

| 置信度 | 行数 |
|---|---|
| high | 537 |
| medium | 400 |
| low | 11 |

#### 按家族的置信度

| 家族 | 置信度 | 行数 |
|---|---|---|
| DEG_ENaC_ASIC | high | 91 |
| DEG_ENaC_ASIC | medium | 17 |
| K2P | high | 87 |
| K2P | medium | 58 |
| MSCL_MSCS | high | 72 |
| MSCL_MSCS | medium | 120 |
| OSCA_TMEM63 | high | 90 |
| OSCA_TMEM63 | medium | 2 |
| PIEZO | high | 159 |
| PIEZO | low | 2 |
| PIEZO | medium | 27 |
| TMC | high | 13 |
| TMC | low | 1 |
| TMC | medium | 139 |
| TRP | high | 25 |
| TRP | low | 8 |
| TRP | medium | 37 |

### 7. 证据位置分类

| 分桶 | 行数 |
|---|---|
| results | 779 |
| table | 122 |
| figure legend | 101 |
| abstract | 45 |
| results and discussion | 19 |
| other | 13 |
| (null) | 2 |
| discussion | 2 |
| methods | 1 |

### 8. 环境报告

| 字段 | 行数 | 最小值 | 中位数 | 最大值 |
|---|---|---|---|---|
| ph | 547 | 5.0 | 7.3 | 9.5 |
| temperature_c | 85 | 17.0 | 24.0 | 38.0 |

### 9. 生物活性区块

- 行数：**136**，化合物：**69**，通道：**9**
- 活性类型：`IC50` ×91、`EC50` ×21、`KD` ×13、`KI` ×8、`PEC50` ×3

### 10. MIMIC 字段覆盖快照

#### stimulus

| 字段 | 行数 | 占生物物理行的百分比 |
|---|---|---|
| stimulus_type | 824 | 86.9% |
| stimulus_waveform | 0 | 0.0% |
| stimulus_velocity | 0 | 0.0% |
| stimulus_duration_ms | 0 | 0.0% |
| probe_geometry | 0 | 0.0% |
| probe_diameter_um | 0 | 0.0% |

#### recording

| 字段 | 行数 | 占生物物理行的百分比 |
|---|---|---|
| recording_mode | 909 | 95.9% |
| sampling_rate_khz | 0 | 0.0% |
| filter_khz | 0 | 0.0% |
| holding_potential_mv | 619 | 65.3% |
| analysis_method | 0 | 0.0% |

#### cell_context

| 字段 | 行数 | 占生物物理行的百分比 |
|---|---|---|
| expression_system | 907 | 95.7% |
| cell_type | 781 | 82.4% |

#### environment

| 字段 | 行数 | 占生物物理行的百分比 |
|---|---|---|
| temperature_c | 85 | 9.0% |
| ph | 547 | 57.7% |
| bath_solution | 735 | 77.5% |
| pipette_solution | 650 | 68.6% |

#### analysis

| 字段 | 行数 | 占生物物理行的百分比 |
|---|---|---|
| n | 503 | 53.1% |
| n_cells | 0 | 0.0% |

#### provenance

| 字段 | 行数 | 占生物物理行的百分比 |
|---|---|---|
| measurement_id | 948 | 100.0% |
| evidence_quote | 948 | 100.0% |
| evidence_location | 946 | 99.8% |
| confidence | 948 | 100.0% |
| condition_key | 948 | 100.0% |

### 11. 条件键

- 行数：**948**，唯一：**939**
- 结构化（下划线、无空格）：**569**；散文式（含空格）：**379**

上文所有百分比所用的语料库规模：948 行生物物理行。

## 5. 接下来做什么（建议，按顺序）

1. **MIMIC 草稿 v0.1（内部，不用于发布）**，依据 F4/F5/F6 撰写：字段分层、自由文本字段的受控词表，以及双方言条件键规则。交付物：`docs/mimic/mimic-v0.1.md`。
2. **时间趋势遍**（需要再加一条查询）：字段完整度 × 发表年代，用来回答较新的论文是否会更常满足 MIMIC L1；在同一脚本中增加一个 `--trend` 段。
3. **期刊规范化**，在 vault（数据权威）里做，然后重新跑这份基线；上面的变体清单就是输入。
4. **单位规则**：判定 `mN/m` ≡ `dyn/cm`（仅拼写差异）、`psi → mmHg` 与 `um → nm` 的换算策略，以及渗透阈值规则；在有任何分析要合并分桶之前，把它们记录为一条数据说明决策。
5. **元研究问题**（每一个都是一篇后续研究笔记）：策展 vs 文献量；完整度趋势；置信度 × 位置类型；PIEZO 主导地位与冻结层偏差。

## 6. 来源

- `db/maicdb.sqlite`（data-v1.0 制品，以只读方式打开）
- `scripts/corpus-stats.py`（本报告的生产者；期刊别名与 MIMIC 列组都在脚本里）
- `tests/test_corpus_stats.py`（钉住上面的数字）
- `docs/m3-website-spec.md` §4（本遍再次确认的普查数值）
