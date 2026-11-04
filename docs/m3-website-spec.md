# M3 website spec — static site over the published data artifact

> **Status**: draft for review (grilling consensus 2026-11-01, Q1–Q11 all
> settled; this file is the written record). Tickets live on GitHub Issues
> under the M3 map issue; see §8.
> **Roadmap slot**: vault `handoff.md` §7-M3 — static website (search,
> family browse, channel card with provenance expansion, downloads page;
> GitHub Pages).
> **Gate**: the repo's public flip (issue #19 runbook,
> `docs/m3-flip-runbook.md`) is a direct blocker of the *deploy* ticket
> only — development proceeds privately with local preview.

## 1. Goal

A static website serving the v1.0.0 data artifact read-only: every number
traceable to its measurement row and verbatim evidence quote, one click
away. The site is a thin consumer of the M1 `maicdb.query` library — the
library builds the data, pages never reimplement it.

## 2. Non-goals (v1)

- Custom domain (Pages project site
  `https://lilong-dong-lab.github.io/maicdb-code/` with relative-path
  assets; custom domain is a possible follow-up ticket).
- Full-text publication search or numeric range queries.
- Any server-side component; MCP/REST are M4.
- Unit-spelling normalization (issue #13 stays a human decision line;
  the site renders as-recorded unit buckets — the disclosure
  convention is Q5's rendering revision).

## 3. Settled decisions (Q1–Q11, 2026-11-01)

| # | Decision |
|---|---|
| Q1 | Python + Jinja2 build → static HTML; vanilla JS, no framework, no Node toolchain. Site code lives in this repo, `site/`. Sole new Python dep: Jinja2 (build-time; justified in the first site PR). |
| Q2 | Data split: one JSON per channel (12) + one aggregate index; hierarchy family(7) → channel(12) → measurement(1100). |
| Q3 | **Bilingual deliverable** (revised 2026-11-02: M3 ships EN + ZH). Architecture is i18n-ready from day one: UI strings only ever in locale dictionaries (`strings.en.json` / `strings.zh.json`), Chinese pages under the `/zh/` prefix (EN unprefixed), the build loops over locales, every page carries a language switcher. Short UI strings are translated inside each page ticket; curated-content translation (channel summaries, parameter labels, frozen-layer wording) is one dedicated ticket. Evidence quotes are **never** translated (verbatim principle); Chinese extractor notes display as-recorded in both locales. |
| Q4 | Issue #12 is NOT a blocker: the v1.0.0 artifact has **zero** NULL `measurement_id` rows (census pinned by PR #29) and card rows already carry `measurement_id`. Fix opportunistically inside the data-layer ticket. |
| Q5 | Issue #13: render as-recorded unit buckets — one row per (gene, stored unit), never merged; normalization is the parallel human line, lands with a future data release. **Rendering revised 2026-11-04 (site-design pass): the three convention notes render on no page. The sign-convention and ratio-median notes stay in the data layer (query.py attaches them to its card/comparison output) and in the locale dictionaries; the unit-bucket sentence stays in the locale dictionaries only. The dictionaries carry all three as the non-rendering record, and the suite asserts their absence from every rendered page.** **Exception, restored the same day: the frozen-layer disclosure (PIEZO1/PIEZO2) stays a rendered banner on channel cards and comparison pages** — it marks evidence quotes that were not re-verified, and the reader keeps that signal (see §5). |
| Q6 | GitHub Pages project site; all assets relative paths. |
| Q7 | Vocabulary: **channel** is the entity (12; the page unit); **family** groups them (7); **gene symbol** names a channel (an attribute, not an entity). Recorded in `GLOSSARY.md`; README_CN wording fixed with this spec. URL slugs are lowercase gene symbols (`/channels/piezo1/`, `trek-1` keeps its hyphen). |
| Q8 | Five page kinds: home, browse (grouped by family), channel card, **parameter comparison** (new — the fifth kind, backing the A1-panel numbers), downloads; plus global search. |
| Q9 | Search scope: channel name/aliases/UniProt + family + parameter names. Build-time flat search-index JSON, client-side case-insensitive substring match; no third-party JS search library. |
| Q10 | Provenance deep links are anchors: `/channels/<slug>/#<measurement_id>`, JS expands and scrolls to the row. No 1100 micro-pages. |
| Q11 | Card pages include a bioactivity block (9 channels have data; same evidence expansion). `unmapped_measurement` (16 rows) is disclosed on the downloads page, no page of its own. |

## 4. Data facts (verified read-only against `db/maicdb.sqlite`, 2026-11-01)

- Hierarchy: family(7) → channel(12) → measurement(1100
  = 948 biophysics + 136 bioactivity + 16 unmapped).
  - DEG_ENaC_ASIC: ASIC 108 · K2P: TREK-1 46, TREK-2 42, TRAAK 39,
    TRESK 18 · MSCL_MSCS: MscS 103, MscL 89 · OSCA_TMEM63: OSCA 92 ·
    PIEZO: PIEZO1 160, PIEZO2 28 · TMC: TMC 153 · TRP: TRPV4 70.
  - bioactivity: TRPV4 37, TRESK 34, ASIC 24, TMC 19, PIEZO1 14, TREK-1 4,
    OSCA 2, MscS 1, TRAAK 1.
- Parameters (16 registered, rows in biophysics): conductance 263,
  p50 152, reversal_potential 97, tau_inact 93, ion_selectivity_ratio 66,
  x50 46, tau_act 45, t50 41, tau_deact 40, threshold_fold_shift 35,
  delta_p50 16, slope 13, macroscopic_rise_time 13, thermal_threshold 9,
  ca_permeability 4, osmotic_threshold 3.
- NULL `measurement_id` census: 0 / 0 / 0 across the three fact tables.
- Two row-count calibers (found building the T2 index): the 948-row
  table census vs **936 parameterized rows** — 12 rows repo-wide carry a
  qualitative as-reported value only (LINEAR, OUTWARD_RECTIFYING, ranges
  like "185-224") with every parameter column NULL, so they belong to no
  parameter block (1×PIEZO2, 1×ASIC, 1×TREK-1, 3×TREK-2, 6×TRPV4). The
  site's per-channel counts use the parameterized caliber and name it
  (`n_parameterized_rows`); browse-page display of the qualitative rows
  is a T4 call.
- Channel identity fields (from `channel_card()`): maicdb_id,
  gene_symbol, gene_aliases, organism, organism_taxid, uniprot_accession,
  protein_name, family, activation_mechanism, ortholog_group, summary.
- Aggregation semantics from the library: groups by (gene, stored unit),
  units never merged; direction-blind ratio parameters carry
  median=None + note; PIEZO1/PIEZO2 outputs must carry the §6.7
  frozen-layer disclosure and never an affirmative "verified" label.

## 5. Site structure

```
/                         home: scale overview (1100/12/7/211), search box,
                          left guide tree (FAMILY → family → channel,
                          PARAMETERS → parameter), right column: welcome /
                          background, how-to-use, download/cite entry
/channels/                browse: 12 channel cards grouped by family(7)
/channels/<slug>/         channel card (slug = lowercase gene_symbol)
/parameters/<parameter>/  comparison: 12 channels × count/min/median/max,
                          one row per (gene, stored unit); client-side
                          Show (page size) / Search / column-sort controls
                          (progressive enhancement — the static table
                          carries every row, so the page stays readable
                          and crawlable without JS)
/downloads/               data artifact files, Zenodo DOIs, CITATION.cff,
                          unmapped disclosure
/zh/…                     Chinese edition of every page
                          (/zh/channels/piezo1/ etc.); language switcher
                          links each page to its counterpart
```

### Channel card (the core page)

1. Identity header: gene symbol, aliases, family, organism, UniProt,
   mechanism, ortholog group, summary.
2. Frozen-layer banner (PIEZO1/PIEZO2 only): the §6.7 wording, same
   semantics as the CLI card — test asserts the boilerplate is attached
   and no "verified" label renders.
3. Parameter blocks (16 registered; zero-row blocks reported with
   n_rows=0): value + unit, `value_as_reported`/`unit_as_reported`
   alongside, sign-convention note on threshold parameters.
4. Evidence expansion per row: quote, location, confidence,
   extractor_note, condition_key, n — hidden until the row is expanded;
   deep link `#<measurement_id>` opens and scrolls to it.
5. Bioactivity block where data exists (9 channels).

### Global search

Build-time `search-index.json` (channel names/aliases/UniProt, families,
parameter names+labels); client-side substring match over that flat list;
results link to card / parameter pages.

## 6. Data layer & determinism

- `site/` build script imports `maicdb.query` against `db/maicdb.sqlite`
  (read-only URI; a site build never mutates the artifact — extend the
  existing DB-hash guard to cover the build).
- Outputs: `site/_data/index.json` (family→channel→parameter counts),
  `site/_data/channels/<slug>.json` (one per channel, card payload),
  `site/_data/search-index.json`, plus rendered HTML **per locale**
  (`_site/` for EN, `_site/zh/` for ZH).
- **Translations are a presentation layer, never a data change**: the
  data artifact is untouched. Curated Chinese text (channel summaries,
  parameter labels, frozen-layer wording) lives in a site-side
  `zh-content.json`. The Chinese §6.7 frozen-layer wording is newly
  written (the data-notes source states the rule in English); its
  semantics must match the English boilerplate, asserted by test on
  semantics, not substrings — the M1 pattern.
- Byte-stable contract: same DB + same code → byte-identical outputs
  (no timestamps); pytest asserts it, mirroring the loader/`export`
  contracts. Suite pins re-derived via `scripts/check-suite-matrix.sh`
  in the CI-touching ticket.
- Issue #12 fix rides here: channel-card rows gain the channel's
  `maicdb_id` (making the defensive NULL path fully testable), with the
  census pin from PR #29 as the guard.

## 7. Testing

- `tests/test_site_build.py` (name indicative): build twice → identical
  bytes; per-page smoke assertions (12 card pages exist, PIEZO cards
  render no repo-side convention prose — the unit-bucket, sign-
  convention and ratio-median sentences stay off the page while the
  underlying data semantics stay visible (rows, markers); the
  frozen-layer banner is the Q5 exception and stays rendered;
  anchor ids = measurement_ids); bilingual assertions (both locale
  trees built, every EN page has a `/zh/` counterpart and a switcher
  link); fixture values cite data-notes / census SQL per the repo's
  provenance rule for real-data claims.
- Existing suite stays green; CI pins updated once, in the CI ticket.

## 8. Ticket graph (GitHub Issues; agent-ready unless marked human)

```
T2 data layer (build script + JSON outputs + #12 fix + locale loop)
T3 site skeleton (templates, layout, home, assets, build entry,
                  locale dictionaries + language switcher)
        ├─ T4 browse + channel card pages      (blocked by T2, T3)
        ├─ T5 parameter comparison pages       (blocked by T2, T3)
        ├─ T6 downloads page + global search   (blocked by T2, T3)
        └─ T7 CI build pipeline (deploy job disabled pre-flip)
                                             (blocked by T2, T3)
T-LOC curated Chinese content (summaries, parameter labels, §6.7
    wording newly written, semantics test-locked; UI strings
    already per-ticket)                       (blocked by T4, T5, T6)
T8 PUBLIC FLIP — runbook §1–§5  [HUMAN, ready-for-human]
T9 deploy to Pages + public acceptance, BOTH locales
                                            (blocked by T7, T8, T-LOC)
```

Each page ticket (T4–T6) follows the repo discipline: branch → suite
green → PR → fresh independent reviewer → vault digest → merge. The flip
(T8) executes `docs/m3-flip-runbook.md` verbatim; T9 re-runs §1's scan,
enables the deploy job, and performs the §3.4 post-flip spot-checks in
both locales. M3 is complete when T9's public acceptance passes on the
EN and ZH trees. Scope note: the bilingual deliverable puts M3 at the
upper end of the roadmap's 2–3 rounds (≈3).
