# Comparable curated-database websites: information architecture and UI patterns (M3 / T9 pre-acceptance)

- **Date**: 2026-11-03 (all live pages fetched this date; Wayback snapshots carry
  their own capture dates and are marked wherever used)
- **Question owner**: M3 website track — build a reference frame before the T9
  public acceptance, and collect pattern material for M4+ UI evolution
- **Method**: live fetches (curl / web reader) of the four comparison sites
  only — no claims from training memory. Every site-level claim cites the URL
  it was fetched from. Self-reported scale numbers come from the sites'
  own pages (homepage counters, release notes) or are marked "not found".
  Where a live fetch was impossible (login wall, JS-only app shell), that is
  stated and a dated Wayback snapshot is used as the historical evidence,
  clearly labeled as such. MAIC-DB-side facts come from the local spec and
  templates, cited by path.
- **Scope note**: this document does not change the accepted M3 scope
  (spec `docs/m3-website-spec.md` §3 Q1–Q11). Candidate patterns in §5 are
  inputs for future tickets only. Web UIs change; re-verify before relying on
  any single-site claim in a future decision.

## 1. Purpose

Three questions motivated this pass:

1. Before T9 (public acceptance of the deployed site), how do comparable
   small academic curated databases present the same four faces MAIC-DB
   presents — family navigation, entity-page density, evidence chaining,
   downloads/citation — and where does MAIC-DB sit among them?
2. Which patterns are worth importing into M4+ (candidate tickets), and what
   does each cost?
3. Which patterns are explicit cautionary tales for a site whose core promise
   is "every number one click from its measurement row and verbatim evidence
   quote"?

The four comparison sites were chosen in the task brief: Channelpedia (same
domain — ion channels), Guide to Pharmacology (closest structure —
family → target → ligand activity + references), BitterDB (closest scale and
team size — ~thousand molecules, small lab team), Stanford HIVdb (evidence
chaining paradigm — scores traceable to literature).

## 2. MAIC-DB baseline (the four faces, as built)

All facts in this section are from the local repository, cited by path; the
rendered-HTML quotes were verified against the running local preview
(`http://localhost:8000/`, 2026-11-03).

### 2.1 Information architecture: family → channel → measurement

- Hierarchy family(7) → channel(12) → measurement(1100 = 948 biophysics +
  136 bioactivity + 16 unmapped), plus 211 publications
  (`docs/m3-website-spec.md` §4; homepage renders "1100 curated measurements /
  12 channels / 7 families / 211 publications").
- Five page kinds: home, browse (12 channel cards grouped by 7 families),
  channel card, parameter comparison (16 parameters), downloads; plus global
  search (spec §3 Q8, §5).
- URL scheme: `/channels/<slug>/` with lowercase-gene-symbol slugs,
  `/parameters/<parameter>/`, `/downloads/` (spec §3 Q7, §5;
  `site/templates/browse.html`, `site/templates/parameters.html`).
- Browse cards show counts per channel in two calibers, named:
  `n_parameterized_rows` plus bioactivity and qualitative riders
  (`site/templates/browse.html` lines 14–27; the two-caliber rule is spec §4).
- Parameter pages render 12 channels × n/min/median/max **per stored unit
  bucket**, with the unit-bucket disclosure and the frozen-layer disclosure
  in the page header, and every table cell expands to its measurement ids
  (verified render of `/parameters/conductance/`: "Buckets are split by stored
  unit: values are rendered as recorded, units are never merged or
  converted…"; "Frozen layer — PIEZO1/PIEZO2 rows are frozen-layer data whose
  evidence quotes have not been re-verified…").

### 2.2 Evidence chain: verbatim quote + confidence + condition key

- Every measurement row is a `<details>` element whose expansion reveals a
  six-field evidence `<dl>`: quote (verbatim), location, confidence,
  extractor_note, condition_key, n — identical rendering for biophysics and
  bioactivity rows; bioactivity rows add the assay description
  (`site/templates/card.html` lines 4–19, the `evidence_dl` macro).
- Deep links are anchors on the measurement id (`#<measurement_id>`; spec
  §3 Q10 — no 1100 micro-pages).
- PIEZO1/PIEZO2 cards carry the frozen-layer banner; no "verified" label
  renders (spec §3 / §4 §6.7 rule; verified on the rendered
  `/channels/piezo1/`, which contains the `frozen-banner` element).
- Verified render example (`/channels/piezo1/`, row `PIEZO1-EX-00004`):
  summary line "73.0 pS (as reported: 73 pS)"; expanded fields — Quote:
  "The unitary conductance at -33mV was 73 pS (0.5 mM Mg2+ in pipette).";
  Location: "Figure legend (C-terminal truncation figure; cell-attached
  patches)"; Confidence: "medium"; Extractor note: (Chinese, as-recorded —
  quotes/notes are never translated); Condition key:
  "hPIEZO1-G2218Stop_HEK293_cell-attached_-33mV_0.5mM-Mg-pipette_Fig8(SI)";
  n: "(not recorded)".

### 2.3 EN/ZH dual tree

- Every page exists twice: EN unprefixed, ZH under `/zh/` (64 built HTML
  pages across both trees, verified in `site/_site/`); a language switcher on
  every page links each page to its counterpart
  (`site/templates/base.html` line 19; spec §3 Q3).
- UI strings live only in locale dictionaries; curated Chinese content is a
  presentation layer in `site/zh-content.json`; evidence quotes and Chinese
  extractor notes display as-recorded in both locales (spec §3 Q3, §6).

### 2.4 Downloads & citation page

Verified from the rendered `/downloads/` (localhost:8000, 2026-11-03) and
`site/templates/downloads.html`:

- Four artifact files, byte-identical to the Zenodo record: `db/maicdb.sqlite`
  (3.1 MB), `db/maicdb.sql` (2.2 MB), `db/load-manifest.json` (1.2 kB),
  `CITATION.cff` (1.3 kB).
- Two DOIs: version DOI `10.5281/zenodo.23620159` (pins v1.0.0) and concept
  DOI `10.5281/zenodo.23620158` (always latest).
- Licenses: data CC-BY-4.0, code MIT; also repeated in the global footer with
  both DOIs (`site/templates/base.html` lines 42–48, including the AI-agents
  contributorship disclosure).
- Unmapped disclosure: "16 archived unmapped measurement rows — kept for
  provenance, mapped to no registered parameter block, with no page of their
  own on this site" (spec §3 Q11).

## 3. Site-by-site findings

Each site section separates **facts** (with source URLs) from **judgements**
(MAIC-DB-side opinion, labeled).

### 3.1 Channelpedia (EPFL) — https://channelpedia.epfl.ch

**Scale (self-reported, homepage, fetched 2026-11-03).** "It is web-based,
freely accessible and currently contains 180 annotated ion channels,
electrophysiology data for all Kv ion channels and 50 Hodgkin-Huxley models."
and "Currently, Channelpedia contains about 180,000 abstracts related to ion
channels from Pubmed." (https://channelpedia.epfl.ch). Order of magnitude:
~150× the channel count of MAIC-DB, but per-channel curated-parameter density
is far lower (see below).

**Information architecture.** A deep left-nav family tree — K → Kv → Kv1 →
Kv1.1 (observed in the navigation of every page, e.g.
https://channelpedia.epfl.ch/expdata) — down to per-channel wiki pages at
`/wikipages/<id>` (https://channelpedia.epfl.ch/wikipages/1 = Kv1.1/KCNA4).
The channel page is a long single page with fixed sections; section headings
observed on the Kv1.1 page: Experimental data, Variants, Crystal Structure,
Pharmacological Characteristics, (AlphaFold size), per-experiment entries,
Markov Model, Hodgkin and Huxley type model, expression/distribution
sections. A separate `/pubmeds` page holds the numbered literature table the
entries cite into.

**Evidence chaining.** Each experimental-data entry is a short paragraph
copied/paraphrased from the paper's abstract plus a bracketed number (e.g.
"Recordings were performed at potentials ranging from −50 to +70 mV with 20 mV
increments [1]." or "…displayed functional differences compared with wild-type
… [1835]") — the bracketed numbers apparently index the site-wide PubMed
table at `/pubmeds` (inference from numbering + nav, not stated on the page);
no direct PubMed hyperlink on the entry itself was found in the fetched HTML
(verified: 0 `pubmed*<digits>` hrefs in the Kv1.1 page; the only PubMed link
is the global `/pubmeds` nav link). There is no verbatim quote, no confidence field,
no condition key, no per-value trace. The wiki sections are editable: "All
registered users can edit the wiki-like sections, just clicking on Edit at
the top-right of each sub-section." (FAQ, https://channelpedia.epfl.ch/faq).

**Downloads & citation.** No self-service bulk download. FAQ ("Is it possible
to download a whole set of ion channel data at once?"): "Yes, we have an
infrastructure suited to share large amount of data. Please contact us at
bbp.channelpedia@epfl.ch, indicating which dataset you are interested for
downloading." Raw HEKA files likewise on request (same page). No license or
citation block was found on the pages fetched. No DOI.

**Worth borrowing (judgement).**
- The dedicated Hodgkin-Huxley / Markov model section per channel: for MAIC-DB
  M4+, a "models built from MAIC-DB parameters" section (even just external
  links) would be the natural home for computational reuse of the numbers.
- Raw-data association by cell ID ("The cell ID is a unique ID assigned to
  each cell as soon as it is recorded; it is the main reference to relate
  every file and every image", FAQ) — a disciplined per-record identifier
  philosophy MAIC-DB already mirrors with `measurement_id`; the borrowing is
  the *lab-facing* description of why IDs matter.

**Worth avoiding (judgement).**
- Wiki-open editing as the content model: for a database whose claim is
  frozen, verified provenance, community editing directly undercuts the
  guarantee. (MAIC-DB's vault + review-gate flow is the opposite pole.)
- Paraphrased abstracts as "evidence": a reader cannot check what the paper
  actually said, only what the curator summarized.
- Bulk data available only by emailing a person — an availability dependency
  that decays with staff turnover.

### 3.2 Guide to Pharmacology (IUPHAR/BPS) — https://www.guidetopharmacology.org

**Access reality (major change).** As of 2026-11-03 the database proper sits
behind a registration wall: "GtoPdb now requires users to register to use the
website." (homepage banner). The wall page further states: "The IUPHAR/BPS
Guide to Pharmacology now requires all users to register and login in order
to access the database… Commercial organisations that use GtoPdb must pay
access-fees… If you would prefer not to register with GtoPdb at this time,
you can still use the database and website by using the guest login below.
This login will remain in place for a limited time…" The wall was hit on
`/GRAC/LigandListForward?type=Approved`, `/GRAC/AboutPageForward` and
`/download.jsp` (all fetched 2026-11-03, all returned the login page); the
guest-login button is injected by JS and not present in the static HTML, so
the database pages **cannot be statically fetched** as of this date. The
homepage itself and the blog remain open. Registration was announced for
2026-07 (https://blog.guidetopharmacology.org/2026/07/29/user-registration-is-coming-to-gtopdb/).

**Scale (self-reported).** The homepage carries no target/ligand counters
(fetched 2026-11-03). The official release announcement blog does:
"GtoPdb now contains: 3,147 human targets, 1,837 of which have curated
quantitative ligand interactions. … 13,989 ligands, 10,072 of which have
curated quantitative target interactions. … Data curated from 50,429
references." (release 2026.3 post, 2026-09-16,
https://blog.guidetopharmacology.org/2026/09/16/database-release-2026-3/).
Current version banner: "Version 2026.3.1 (12th October 2026)" (homepage).
GtoPdb is one-to-two orders of magnitude larger than MAIC-DB on every axis.

**Information architecture** (from a Wayback snapshot of a target page,
captured 2025-02-19 — used because the live page is behind the wall:
http://web.archive.org/web/20250219223557/https://www.guidetopharmacology.org/GRAC/ObjectDisplayForward?objectId=529).
Type categories (GPCR, Ion channels, NHR, Transporters, Enzymes…) → family →
target page. The target page (CaV1.2) carries the family in its breadcrumb
("Ca v 1.2 | Voltage-gated calcium channels (Ca V )") and opens with a
"Contents:" mini-TOC of ~25 sections: Gene and Protein Information, Previous
and Unofficial Names, Database Links, Associated Proteins, Functional
Characteristics (Ion Selectivity and Conductance, Voltage Dependence),
Activators, Gating Inhibitors, Channel Blockers, Immunopharmacology,
Tissue Distribution, Functional Assays, Physiological Functions,
Physiological Consequences of Altering Gene Expression, Phenotypes/Alleles
and Disease Models, Clinically-Relevant Mutations and Pathophysiology,
Biologically Significant Variants, References, Contributors, "How to cite
this page". This is the closest structural relative of the MAIC-DB channel
card, at roughly 3–5× the section count.

**Evidence chaining** (same snapshot). Ligand-activity rows render as:
ligand name + species code (Mm/Rn) + action (Antagonist) + value
("pIC 50 7.0 – 8.0") + a condition field ("Holding voltage: -80.0 mV") + a
bracketed reference number, with an expandable sub-row (⤷) repeating the
value with its citation, e.g. "nisoldipine Mm Antagonist 7.0 – 8.0 pIC 50 …
79 ⤷ pIC 50 7.0 – 8.0 [ 79 ] Holding voltage: -80.0 mV". Reference numbers
resolve to a page-bottom References list of full citations with PubMed links
(e.g. "[PMID: 28592699]"). So: per-value citation + one condition field —
but no verbatim quote and no per-value confidence; the unit of trust is the
reference, not the extracted sentence.

**Downloads & citation.** The downloads page itself is behind the wall
(`/download.jsp`, fetched 2026-11-03). The open homepage points at release
reports archived on Zenodo: "Reports are also accessible, along with database
update presentations, on our Zenodo archive. latest report DOI:
10.5281/zenodo.23667960." License: CC BY-SA 4.0 (footer link on every page
fetched, including the login wall). Target pages carry a "How to cite this
page" section with format selector: Vancouver, Harvard, ACM, BibTeX, RIS
(snapshot above).

**Worth borrowing (judgement).**
- Per-row inline reference numbers with a page-bottom reference list — the
  densest readable citation pattern among the four; MAIC-DB's equivalent
  (measurement-id anchors) is stronger provenance but GtoP shows citation can
  be compact as well as deep.
- "How to cite this page" with format selection on entity pages: cheap to add
  to MAIC-DB card pages later (EN/ZH both), complements the CITATION.cff.
- Per-release Zenodo report DOIs: a lighter-weight sibling of our version
  DOI, well suited to release-notes/report artifacts.

**Worth avoiding (judgement).**
- The registration wall itself: it makes the database unfetchable for
  anonymous readers, crawlers, archival services, and teaching use, and it
  happened to a long-standing open resource for sustainability reasons —
  the exact failure mode a public T9 acceptance exists to avoid. Whatever
  future funding pressure arises, walling the entity pages should be treated
  as a breaking change for MAIC-DB's core promise.
- ShareAlike (BY-SA) data licensing complicates downstream reuse relative to
  our CC-BY-4.0 choice.

### 3.3 BitterDB (Hebrew University) — http://bitterdb.agri.huji.ac.il/dbbitter.php

**Scale (self-reported, homepage, fetched 2026-11-03).** "BitterDB underwent
a major update in 2024: BitterDB now holds over 2400 bitter molecules."
Per-organism receptor counts on the same page, e.g. human: "26 functional
bitter taste receptors (TAS2Rs). Of these, 23 have experimentally validated
ligands and the remaining 3 are orphans"; mouse: 35 (26 with ligands);
chicken: 3; cat: 12 (8 with ligands); plus platypus, echidna, cattle, shark,
etc. Closest to MAIC-DB in scale (thousands of rows, small lab team).

**Information architecture.** A single long PHP page (`dbbitter.php`) with
anchor navigation (Search, Compounds, Receptors, Alignments, Catalog,
Classifiers, Blast, Download, Help) — a pre-SPA "everything on one page"
pattern. Two entity kinds with per-entity pages: `Receptor.php?id=N` and
`compound.php?id=N` (link patterns observed in the fetched HTML of
`Receptor.php?id=1` and `dbbitter.php`). The receptor page (hTAS2R1,
`Receptor.php?id=1`) shows: alternative names, outbound links (UniProt,
GPCRDB, GeneCards, Human Protein Atlas, IUPHAR/BPS), organism, chromosomal
location, "Number of known ligands: 82", molecular weight, full sequence,
and a Known Ligands list linking each compound to its page plus an SDF
download of selected compounds. The compound browse table itself is a JS
DataTables widget (jQuery DataTables CSS imports observed in the page head),
so compound rows have no static hrefs on the landing page.

**Evidence chaining.** The compound page (strychnine, `compound.php?id=100`)
shows name, id, a "Natural" badge, the line "Detailed experimental validation
described in the associated resource." and a "References for the compound
bitterness" numbered reference table — each entry a full citation with a
PubMed link (e.g. "[1] Meyerhof W, Batram C, … (2010). The molecular
receptive ranges of human TAS2R bitter taste receptors. Chem Senses 35(2):
157-70. PubMed 20022913"). Citation granularity is per-compound (per-entity),
not per-measurement; no verbatim quotes, no confidence, no condition keys.
Receptor-side ligand lists likewise carry no per-pair citation on the page
fetched.

**Downloads & citation.** Frozen per-year download directories, linked
directly from the homepage: `downloads/2019/?file=…` and `downloads/2024/?file=…`
with ~12 CSVs each (BitterCompoundsPropA_2024.csv, compound snamesA_2024.csv,
ligandReceptorsA_2024.csv, mutationData_2024.csv, snpData_2024.csv,
compRefA_2024.csv, dbreferencesA_2024.csv, IUPHAR_cidA_2024.csv,
ReceptorSearchA_2024.csv, cbitterresourceA_2024.csv, compzinclinksA_2024.csv,
drugbankcidA_2024.csv — all observed as hrefs on `dbbitter.php`). No DOI, no
CITATION file; the citation model is "cite our NAR paper" (homepage links the
2012 NAR database-issue paper as the thing to cite). License: "This work is
licensed under a Creative Commons Attribution-NonCommercial-NoDerivatives 4.0
International License." (homepage footer). No citation-per-page anywhere.

**Worth borrowing (judgement).**
- The frozen per-year download directory (2019/2024) is the same *idea* as
  our version DOI at near-zero tooling cost — but MAIC-DB already has the
  stronger form (versioned DOI + manifest), so nothing to import.
- Bidirectional entity linking: compound pages list receptors and receptor
  pages list compounds. MAIC-DB's bioactivity block is one-directional
  (channel → compound); a future compound index page (M4+ candidate, not M3)
  would close the loop.
- The "orphan vs validated" receptor vocabulary ("23 have experimentally
  validated ligands and the remaining 3 are orphans") — a compact coverage
  disclosure pattern; MAIC-DB's analogue would be per-parameter coverage
  counts, which browse cards already render.

**Worth avoiding (judgement).**
- CC BY-NC-ND on the data: no-commercial + no-derivatives is maximally
  restrictive for reuse; our CC-BY-4.0 choice looks better in this light.
- Reference-level citation for a claims database: a reader wanting to know
  *why* strychnine is listed as bitter for TAS2R7 gets a bibliography, not a
  traceable extraction.
- JS-only browse tables (DataTables) without static per-row links: search
  engines and archivers cannot see the compound collection except through the
  entry pages linked from receptor pages.
- Citation = "cite our 2012 paper" with no per-release citation artifact:
  downstream users cannot pin the version they downloaded. (Our version DOI +
  CITATION.cff exist precisely to prevent this.)

### 3.4 Stanford HIVdb — https://hivdb.stanford.edu

**Access reality.** The current site is a JavaScript single-page app: every
path probed (`/`, `/dr-summary/`, `/page/release-notes/`,
`/page/scoring-algorithms/`, `/page/program-notes/`, `/dr/`, `/dr/genotypes/`,
`/page/genotype-treatment/`, `/pages/genotype-rx.html`) returns the same
~1.6 KB shell whose body is `<noscript>You need to enable JavaScript to run
this app.</noscript><div id="root"></div>` plus one bundled
`/static/js/main.*.js` (fetched 2026-11-03). **The current UI cannot be
statically fetched** — including for archivers. The shell's own meta
description self-describes scope: "A curated database containing nearly all
published HIV RT and protease sequences…". Self-reported scale counts: not
found (the statistics pages live inside the SPA).

**Historical evidence (Wayback, captured 2019-12-16; the pre-SPA site).**
The classic site (http://web.archive.org/web/20191216101612/https://hivdb.stanford.edu/)
was a server-rendered multi-page site with sections: Home, Genotype-Rx,
Genotype-Pheno, Genotype-Clinical, HIVDB Program, About, plus Database
Statistics and User Guide & Database Documents links. The genotype-treatment
page (snapshot of `/pages/genotype-rx.html`, same capture date) offered
query tools (treatment profiles, mutation profiles, detailed queries) and
downloadable datasets ("Download protease, RT & integrase
genotype-treatment dataset").

**Evidence-chaining paradigm.** The program page snapshot (fetch of the
by-mutations URL redirected to the CPR tool page in that capture) states the
design goal in HIVdb's own words: "Its purpose is educational and as such it
provides extensive comments and a highly transparent scoring system that is
hyperlinked to data in the HIV Drug Resistance Database." — with explicit
dual versioning: "Sierra version 2.4.2 (last updated on 2019-11-01), HIVdb
version 8.9-1 (last updated on 2019-10-25)". The scoring algorithm itself
(rule files, ASI format) has long been published openly, which is the
mechanism behind "scores traceable to literature". Note the epistemic
difference from MAIC-DB: HIVdb scores are *derived* quantities computed by a
versioned algorithm over curated mutation–literature links, and the
transparency comes from publishing the algorithm; MAIC-DB's evidence chain is
*per-row curated* (verbatim quote + confidence assigned by a curator). The
current-site rendering of this paradigm could not be verified statically.

**Worth borrowing (judgement).**
- The stated-and-practiced transparency contract — "every score hyperlinked
  to the data behind it" — is the same contract as "every number one click
  from its measurement row and verbatim evidence quote"; HIVdb is the
  existence proof that this contract, stated loudly, *is* the brand of a
  curated database.
- Dual version display (program/algorithm version + data version, each with
  a date) on user-facing tool pages: MAIC-DB's analogue (dataset version DOI
  + concept DOI + build provenance) could someday be surfaced as a small
  "what am I looking at" strip, especially once M4 query tools exist.
- Versioned, downloadable bulk datasets per release (2019 page) — again, we
  already have the DOI-backed equivalent.

**Worth avoiding (judgement).**
- Shipping the entire database as a JS SPA with no server-rendered fallback:
  the resource becomes invisible to crawlers, cannot be archived by the Wayback
  Machine in any useful form, and is unusable without JS. For a public-good
  database this is a self-inflicted wound; MAIC-DB's static-HTML choice
  (spec §3 Q1) is validated by this example.

## 4. Comparison matrix

Four faces × five sites. "…" = could not be verified statically (reason
given). Live fetches 2026-11-03 unless marked.

| Face | MAIC-DB (local build) | Channelpedia | GtoPdb | BitterDB | HIVdb |
|---|---|---|---|---|---|
| **Family navigation** | Flat two-level: browse page groups 12 cards by 7 families; breadcrumb-free; per-parameter cross-cut (`/parameters/`) | Deep nav tree K→Kv→Kv1→Kv1.1 (4–5 levels, 180 channels) | Type→family→target, family shown in target-page breadcrumb; ~25-section Contents TOC per target (2025-02-19 snapshot; live page walled) | No family layer: two flat entity lists (compounds, receptors) with organism filters; single long page + anchors | Classic site had section nav (Genotype-Rx/Pheno/Clinical) (2019-12-16 snapshot); current SPA unverifiable |
| **Entity-page density** | Card = identity (11 fields) + up-to-16 parameter blocks + bioactivity; every row expandable; two count calibers named | One long wiki page per channel: experiments, variants, structure, pharmacology, expression, models; community-editable | Target page ≈25 sections incl. ligand interaction tables; densest of the four (2025 snapshot) | Receptor page: names, out-links, location, ligand count, sequence, ligand list + SDF; compound page: badge + reference table — sparse | … (SPA); historically tool/result pages rather than entity cards |
| **Evidence chain** | Per-row: verbatim quote + location + confidence + extractor note + condition key + n; anchor deep link; frozen-layer banner; quotes never translated | Per-entry: paraphrased abstract + bracketed number → site PubMed table; no quote/confidence/condition; wiki-editable | Per-value: reference number → full citation w/ PMID at page bottom; one condition field (holding voltage); no quote/confidence (2025 snapshot) | Per-entity: numbered reference list w/ PMID links; no per-value citation, no quote/confidence/condition | Algorithmic: versioned scoring rules + "hyperlinked to data" (self-description, 2019); current rendering unverifiable |
| **Downloads & citation** | 4 files byte-identical to Zenodo; version + concept DOI; CC-BY-4.0/MIT; CITATION.cff; unmapped (16) disclosed; AI-contributorship footer | None self-service; bulk data by email request; no license/DOI found | Wall-gated downloads page; Zenodo report DOIs (latest 10.5281/zenodo.23667960); CC BY-SA 4.0; per-page "How to cite" with 5 formats | Per-year frozen CSV bundles (~12 files × 2019/2024); no DOI; CC BY-NC-ND 4.0; cite-the-paper model | Versioned downloadable datasets (2019); current page unverifiable |

**Where MAIC-DB differs most** (judgement): on evidence-chain granularity
(everyone else cites documents or algorithms; MAIC-DB quotes sentences), on
bilingual completeness (none of the four offers a second-language tree;
BitterDB's pages carry a Hebrew university name in the masthead but no
mirrored locale tree), and on open static accessibility (Channelpedia and
BitterDB are anonymously fetchable today; GtoPdb's database pages and all of
HIVdb are not — walled and JS-shelled respectively).

## 5. Conclusions

### 5.1 Differentiation claim: confirmed

The research question's hypothesis — that MAIC-DB's row-level verbatim
evidence chain (verbatim quote + confidence + condition key per measurement,
anchor-addressable) is stricter than what comparable curated databases offer
— is **confirmed** against all four sites as fetched on 2026-11-03:

- Channelpedia: paraphrase + numbered reference; no per-value chain.
- GtoPdb (2025 snapshot): per-value reference number + one condition field —
  the closest in spirit, but the unit of trust is still the document, not the
  extracted sentence, and there is no confidence dimension.
- BitterDB: per-entity bibliography only.
- HIVdb: transparency via a published versioned algorithm over curated links;
  strong, but a different (derived-quantity) epistemics.

No site examined presents, per data row: the exact source sentence, where in
the paper it sits, a curator-assigned confidence, and the experimental
condition key. That combination is MAIC-DB's defensible novelty in this
cohort, and the frozen-layer banner (an explicit "not re-verified" marker on
two channels) goes beyond anything observed on the four sites.

The static, no-JS-required, anonymously-fetchable property — shared today
only with BitterDB in this cohort — should be treated as part of the same
differentiation, not an implementation detail: GtoPdb's wall and HIVdb's SPA
shell both erase the database from the anonymous record.

### 5.2 Candidate import list (for future tickets; none open M3 scope)

Each entry names the face it touches and its cost. All are judgements.

1. **"How to cite this page" block on channel cards** (from GtoPdb; face:
   downloads/citation). Cost: small template change × both locales; content
   already exists in CITATION.cff. Candidate ticket in M4 polish.
2. **Per-release Zenodo report DOI** for release notes / data-notes digests
   (from GtoPdb; face: downloads/citation). Cost: one Zenodo deposit per
   release, linked from the downloads page. Low.
3. **Compound-side index of bioactivity rows** (from BitterDB's bidirectional
   linking; face: IA). Cost: a new page kind + search-index entries;
   compounds are not an entity in M3 (spec Q7), so this is an M4+ data-model
   question first.
4. **Models section per channel** (from Channelpedia; face: entity-page
   density). Cost: needs model content that does not exist yet; only worth it
   when someone builds models from MAIC-DB parameters.
5. **"What am I looking at" version strip** — dataset version + build
   provenance surfaced on content pages (from HIVdb's dual versioning; face:
   entity-page density). Cost: trivial template change, but adds noise to
   64 pages; consider only alongside M4 query tools where provenance of a
   *computed* answer matters.
6. **Explicit anti-goals, recorded**: registration walls (GtoPdb), JS-only
   shells (HIVdb), email-gated bulk data (Channelpedia), NC-ND licensing and
   cite-the-paper-only (BitterDB). Cost of avoiding them: none beyond
   maintaining the current static-site + DOI + CC-BY posture.

Patterns deliberately **not** imported despite superficial similarity:
inline numbered references (GtoPdb) — measurement-id anchors already carry
strictly more information; per-year download directories (BitterDB) —
version DOI + manifest is the stronger form of the same idea.

## 6. Sources

All live URLs fetched 2026-11-03 (HTTP status 200 unless noted). Wayback
snapshots carry their capture dates.

### MAIC-DB (local repository)

- `docs/m3-website-spec.md` (§3 Q1–Q11, §4 data facts, §5 site structure)
- `site/templates/base.html`, `browse.html`, `card.html`, `parameters.html`,
  `downloads.html`
- Rendered pages, local preview `http://localhost:8000/`: `/`, `/downloads/`,
  `/channels/piezo1/`, `/parameters/conductance/`
- `site/_site/` and `site/_site/zh/` trees (64 HTML pages, structure listing)

### Channelpedia

- https://channelpedia.epfl.ch (homepage; self-reported 180 channels /
  50 HH models / ~180,000 abstracts)
- https://channelpedia.epfl.ch/wikipages/1 (Kv1.1 wiki page; sections,
  experiment entries, citation markers)
- https://channelpedia.epfl.ch/expdata (navigation tree)
- https://channelpedia.epfl.ch/faq (Datasharing answers: bulk data and HEKA
  files by email; wiki editing policy; cell ID definition)

### Guide to Pharmacology

- https://www.guidetopharmacology.org/ (homepage; registration banner,
  version 2026.3.1, CC BY-SA 4.0 footer, Zenodo report DOI
  10.5281/zenodo.23667960)
- Login wall pages (fetched 2026-11-03):
  https://www.guidetopharmacology.org/GRAC/LigandListForward?type=Approved ,
  https://www.guidetopharmacology.org/GRAC/AboutPageForward ,
  https://www.guidetopharmacology.org/download.jsp ,
  https://www.guidetopharmacology.org/GRAC/ReceptorFamiliesForward?type=IC
- https://blog.guidetopharmacology.org/2026/09/16/database-release-2026-3/
  (self-reported 3,147 human targets / 13,989 ligands / 50,429 references)
- https://blog.guidetopharmacology.org/2026/07/29/user-registration-is-coming-to-gtopdb/
  (registration announcement)
- Wayback snapshot (captured 2025-02-19), CaV1.2 target page:
  http://web.archive.org/web/20250219223557/https://www.guidetopharmacology.org/GRAC/ObjectDisplayForward?objectId=529

### BitterDB

- http://bitterdb.agri.huji.ac.il/dbbitter.php (homepage; self-reported
  >2,400 molecules, per-organism receptor counts, download CSV links,
  CC BY-NC-ND 4.0 footer)
- http://bitterdb.agri.huji.ac.il/Receptor.php?id=1 (hTAS2R1 receptor page)
- http://bitterdb.agri.huji.ac.il/compound.php?id=100 (strychnine compound
  page; reference-table citation model)

### Stanford HIVdb

- https://hivdb.stanford.edu/ and paths `/dr-summary/`, `/dr/`,
  `/page/release-notes/`, `/page/scoring-algorithms/`, `/dr/genotypes/`,
  `/page/genotype-treatment/`, `/pages/genotype-rx.html` (all: identical
  ~1.6 KB JS-app shell; SPA conclusion)
- Wayback snapshot (captured 2019-12-16), homepage:
  http://web.archive.org/web/20191216101612/https://hivdb.stanford.edu/
- Wayback snapshot (captured 2019-12-16), genotype-rx page:
  http://web.archive.org/web/20191216/https://hivdb.stanford.edu/pages/genotype-rx.html
- Wayback snapshot (captured 2019-12-16), by-mutations/CPR program page:
  http://web.archive.org/web/20191216101612/https://hivdb.stanford.edu/hivdb/by-mutations/
