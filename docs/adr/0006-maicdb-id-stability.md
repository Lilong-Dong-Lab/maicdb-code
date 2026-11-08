# maicdb_id stability: per-release row keys now; freeze at public release

The loader assigns the formal `maicdb_id` (the `MAIC:BX:*` accession) by
sorted-key insert order over the vault's extraction rows. Every freeze
retarget therefore shifts visible ids whenever new rows sort before old
ones: the data-v1.1 sync moved the biophysics block +1 below the Duru
insertion and +12 above it (MAIC:BX:00397→00409 for the same row), and the
next sync will move them again. The ids are not internal: the site renders
them, query tests pin them, and the dataset is headed for a public release
(ADR-0002 mints the DOI). Citing an id across releases is currently
undefined behavior. Decided 2026-11-08.

## Considered Options

- **Two-stage: per-release keys now, frozen assignment at public release
  (chosen)** — honest about what the ids already are, at zero loader cost
  today, with a concrete trigger and mechanism for the day external
  citations arrive.
- **Content-derived stable ids (hash of measurement_id + kind + value)** —
  stable across releases by construction. Rejected for now: meaningless
  accessions, migration rewrites every pin and site surface, and the cost
  lands before any external user exists.
- **Freeze assignment immediately (pre-release)** — prevents one final
  normalization but forces the loader to carry an id-assignment ledger
  (read the previous release's manifest, reuse ids, append) *now*. Deferred
  to stage 2: the machinery is only worth its maintenance once someone can
  actually cite.
- **Drop surrogate ids, cite the vault `measurement_id`** (e.g.
  `OSCA-EX-00097`) — the natural key IS stable across releases (vault
  extraction ids are additive by convention). Rejected as a replacement:
  the formal DB needs dense per-table accessions for display and joins,
  but adopted as the *cross-release identity* half of the contract.

## Consequences

**Contract (normative).**

1. **Within a tagged release**: `maicdb_id` is the row address. Cite it
   with the tag (`data-v1.1`, `MAIC:BX:00409`) — never a bare id.
2. **Across releases**: identity is the vault `measurement_id` (+ channel
   prefix it already carries). A `maicdb_id` may map to different rows in
   different releases; that is specified behavior, not corruption.
3. **Trigger**: the first *public* release (site deploy or DOI mint,
   whichever first) freezes assignment from that release onward. Its
   publication process MAY run one final id normalization beforehand.
4. **After the freeze**: existing rows keep ids for life; new rows append
   `max+1` in the loader's sorted-key order at append time; deleted rows
   leave permanent gaps (no reuse). The loader gains the
   previous-manifest lookup at that point — implementation deferred until
   the trigger fires, and it is the *first* loader change this ADR licenses.

**Ripple sites (what legitimately moves per release, and what must not
silently).** Test pins on accessions (`MAIC:BX:00409` in query tests, site
payload tests, and the analysis-artifact tests) move with each renumber — a
moved pin
carries a derivation note per the pin discipline; an unexplained moved
accession pin is a gate finding. Count-only pins (corpus-stats and friends)
do not move on a renumber. `db/load-manifest.json` remains the
identity document of a release (vault_head + counts + content keys);
`db/README.md` states the per-release semantics alongside this ADR.

**No code changes in this ADR.** Documentation-only decision; this PR adds
the db/README.md pointer, and the loader, site, and citation policy
(ADR-0003) will gain pointers in follow-up PRs as their surfaces are
touched; the stage-2
mechanism is specified here so the future PR is transcription, not design.
