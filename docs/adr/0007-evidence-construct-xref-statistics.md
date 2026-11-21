# Evidence, construct, cross-reference semantics, and coverage statistics

MAIC-DB's next data-model phase gives evidence, constructs, cross-reference
semantics, and coverage statistics first-class structure. The chosen model keeps
MAIC-DB's publication-citation trace while normalizing reusable evidence items
through subject links rather than locking evidence to one fact table.

## Decision

Evidence becomes a first-class published object. `evidence_item` records the
published claim, source, publication, quote, location, controlled evidence
type, confidence, curator note, lightweight review state, and review timestamp.
`evidence_subject` provides a many-to-many subject link, so one item can
support multiple subjects and one subject can cite multiple items. Existing
evidence columns remain a compatibility bridge until parity is proven.

Constructs become the experimental object that connects variants, structures,
and experimental-design metadata to measurement occasions. They are not
experiment conditions and do not replace the experiment row. External references
gain relationship and version semantics, and the website gains a four-part
coverage statistics surface. A standard Web API and finer-grained conditional
downloads remain intentionally deferred.

## Consequences

Ticket #97 implemented the biophysics evidence spine. Ticket #98 extends parity
to bioactivity and unmapped measurements and makes the normalized Evidence model
the shared authority for all three fact families. Public payloads and exports
resolve Evidence through the same subject-link path; any uncovered fact row is
counted and disclosed explicitly. Detailed editorial history remains vault-only.
Ticket #99 adds Construct as the measured genetic object between variants and
experiments. Ticket #100 records UniProt residue coordinates, title-derived
construction mutations, variant-structure locations, and explicit mapping
support; PDB residue coordinates remain nullable until SIFTS-derived mappings
are curated, rather than being inferred from sequence identity.
