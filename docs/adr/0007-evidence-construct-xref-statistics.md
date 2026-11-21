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

Ticket #97 implements only the biophysics evidence spine. It may not claim
authority for bioactivity or unmapped measurements; ticket #98 performs the
all-fact-family parity and authority cutover. Public payloads and exports expose
the normalized Evidence item when available and an explicit legacy/unmigrated
disclosure otherwise. Detailed editorial history remains vault-only.
