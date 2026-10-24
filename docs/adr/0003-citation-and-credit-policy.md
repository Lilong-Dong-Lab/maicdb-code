# Citation and credit: named human creators, agents disclosed in prose

CITATION.cff and the Zenodo creators field name **humans only**. Dataset
v1.0.0 credits **Lilong Dong** (`hugolld`, ORCID 0000-0002-9519-3495) and
**Taiheng Li** (`xinfangowo`); **Yujie Chen** (`chiyun111`) is acknowledged
by name. All curation and code execution done by agents is disclosed in a
README "Contributorship & AI disclosure" section — tools named, the
gated-review discipline stated abstractly, **no links into the private
vault** (the gate digests stay there). The canonical, editable home of the
citation strings is CITATION.cff (and Zenodo, once published); this ADR
records the policy and the people as named at decision time (2026-10-10).

Rationale: Zenodo creator metadata is immutable after publication, so it
must not carry placeholders or agent entries that are hard to defend at
M6; journals expect human authors with AI use disclosed in prose; agent
entries in citation metadata create citation-index noise without adding
verifiable credit.

## Considered Options

- **Humans as creators, agents disclosed in prose (chosen)** — matches
  journal norms for the M6 manuscript; keeps the disclosure honest.
- **Lab org as placeholder creator** — risks the placeholder shipping
  permanently inside the DOI metadata.
- **Agents as contributors in CITATION.cff** — maximally transparent, but
  citation-index noise and venue friction.
