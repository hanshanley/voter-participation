# Routine participation updates

`scripts.participation_batch` is the shared discovery, intake, cache, constrained
count-runtime compiler and publication command. It does not route through
state-specific importers or qualify a new measure merely because it parses.

## Reproduce the accepted example

Extract the complete workflow download listed in [DATA.md](DATA.md). From its
`code/` directory, run:

```sh
python -m scripts.participation_batch \
  --registry ../originals/registry.json \
  --baseline ../originals/baseline \
  --supplied-root ../originals/supplied \
  --work-dir ../replayed --offline
```

Compare `../replayed/batches/<recipe>/counts/` with the complete packaged
`../queries/counts/`, and compare `all-51-jurisdictions.json` and
`complete-source-dispositions.json`. Operational parse counters can differ
between a fresh replay and a cached run. The numerical queries must not.
Run the same command again: a verified cache hit reports `no_op: true` and
does not parse or compile again.

This example checks **4,963 already-connected reporting observations** in
Arkansas, Arizona and Wyoming: 113 county parents, 83 unknown counts and
22 observed zeros. All native observation fields and existing display bindings
are preserved. All 51 accepted jurisdiction shards remain, including the
48 jurisdictions without a newly registered source in this example. These are
previously reviewed canonical public snapshots, not fresh native acquisitions
or newly qualified nationwide native products.

The actual publisher check found the dataset unchanged; a subsequent actual
CLI invocation made zero requests, parses, compilations or publication attempts.
Its entire working directory retained identical bytes and modification times
while network, DNS and child commands were blocked and probed.

## Register and update a reviewed product

Use the maintained example registry
`data/participation-routine-batch/20261112-01/registry.json` as the contract
reference. A registry pins an accepted baseline and explicitly lists every
source's replacement scope, literal election/state, public-aggregate
classification and source/scope review evidence. Source and packet IDs must
be safe and distinct; replacement scopes cannot overlap.

Existing shared CSV, JSON and PDF adapters accept declared fields and explicit
display bindings. The reviewed `canonical_json` adapter reuses complete
canonical observations losslessly; it does not relabel an accepted derived
snapshot as an original native extraction. JSON may declare gzip compression
and exact root-field controls. Personal-record inputs are rejected, and
quarantined inputs are excluded from the complete public packet.

An optional discovery declaration may select exactly one HTML anchor matching
its pattern, within an explicitly approved URL list. Its index original needs
an approved redistribution policy and is retained for offline reproduction.
A newly declared or ambiguous product is held for review, not silently ingested.
Direct native-adapter/discovery changes have focused fixture tests; this
three-source demonstration does not claim their nationwide native deployment.

For ordinary refreshes, omit `--supplied-root` and use:

```sh
python -m scripts.participation_batch \
  --registry reviewed-registry.json --baseline accepted-counts \
  --work-dir routine-work --refresh
```

Without `--refresh`, held content-addressed originals are reused. With
`--refresh`, ordinary conditional source requests retain ETag/Last-Modified
validators where available. `--offline` forbids missing-original requests.
Explicit and persisted source-access holds are enforced before using a source,
including its cache; there is no blocked-route workaround.

The compiler requires the exact existing geography/measure-mode inventory and
unchanged election, geography, complete measure semantics and display identities.
Changing an inventory, geographic join, measure, voting mode or reference map
requires separately reviewed qualification. Unknowns remain unknown and zeros
remain zeros. Candidate votes do not become ballots; registration stocks do
not automatically become turnout denominators.

## Bind a same-measure refresh to reviewed native facts

The Cape May refresh in [DATA.md](DATA.md) is a real changed-source example,
not the earlier canonical no-op demonstration. It uses complete reviewed PDF
factual grids, the existing approved county context and the complete19-row
accepted replacement scope. Only one observation changes; all51jurisdiction
shards and other source/mode frames remain represented. The existing measure,
election and geographic identities are not requalified.

For `canonical_json`, optional `format.fact_bindings` compare individual
canonical fields with an independently supplied, pinned
`participation.reviewed_pdf_factual_grids.v1` input. For example:

```json
{
  "input": "facts",
  "compression": "gzip",
  "record": {"geography.id": "existing-reviewed-county"},
  "path": "count.value",
  "source_id": "reviewed-native-product",
  "table_id": "reviewed-summary",
  "native_unit": "Ballots Cast - Total",
  "measure": "total",
  "parse": "count"
}
```

Declare `facts` in `spec.inputs`, including its full byte/SHA pin and permitted
publication policy. Product, table, record and native-row selectors must each
be unambiguous. Supported native roles are reviewed
`unofficial_registration_ballot_reported_turnout_statistics` and neutral
`native_registration_ballot_reported_turnout_statistics`, not contest-choice
tables. The neutral role does not invent an official/unofficial or certified
status when the report supplies none.
Native numerator labels must match the accepted measure; missing cells cannot
become reported zeroes. `parse: "count"` accepts only a native scalar count,
not provenance metadata. Other conversions are rejected.

Bind dependent mirrors too: `count.literal`, `view.ballots`, denominator fields
and native printed percentages. `value_scope: "annotations"` plus `value_path`
can verify the native clock; `value_scope: "source"` can verify original source
URL/hash metadata. These use literal comparisons, not inferred dates or
retrieval clocks. The full published refresh registry contains all eleven
assertions and is included in its complete offline packet.

If existing observations already have approved joins, register the unchanged
reference under `entry.references.assets` and supply its exact original as a
pinned `spec.inputs` product. The shared runner forwards those references to
the existing strict intake validator and includes them in the complete source
packet. A missing original, changed checksum, absent feature key or missing
approval evidence holds the source. This does not grant a new join or permit
an inventory change.

### Reviewed reporting-part sums and wide statistical tables

The VT refresh uses the same runner, not a per-state importer. An explicit
`table_ids` list can span source pages; all declared tables must be present
exactly once. `reading_whitespace_normalized: true` allows layout whitespace
only, not place-name aliases. `where_nonempty` declares source row selectors
that distinguish reporting parts from blank county headings.

`operation: "sum"` requires `parse: "count"` and nonempty
`sum_review_evidence`. Every selected factual row needs a unique table/row
identity and every selected count must be known. Missing values are not
silently skipped or converted to zero. A default unique-cell binding still
rejects multiple matches. Percentages and provenance metadata are not approved
summable count fields; registration stocks need an explicitly reviewed additive
partition, not repeated whole-population values.

In wide tables, the row label names a locality rather than a measure.
Numerator bindings may declare an exact `native_measure_header`, the unchanged
`accepted_measure_literal` and explicit `same_measure_review_evidence`. Every
selected table's native column-header annotation must match. This records a
reviewed same-quantity label equivalence; it does not change accepted measure,
election or geographic identity, approve candidate-choice substitution, or
grant physical-ballot/unique-voter qualification.

`pdf_group_queries.py` and the optional `--group-recipe` argument to
`reproduce_pdf_measures.py` reproduce complete reporting-part, grouped-unit,
parent and state queries. Recipes name source tables, count fields, literal
parent headings/control suffixes, expected inventories and percentage pairs.
Unknown counts, missing controls and duplicate reporting-part identities fail
closed. Native percentages retain their own denominators and display precision;
zero-denominator rates remain unqualified. Grouped percentages are not added
or averaged. Complete cell JSON/CSV and numerical control outputs remain
included, not replaced by a reconciliation summary.

The VT complete batch additionally declares the full native-source analysis
ZIP as a pinned public input, so it remains nested in the offline packet with
its own complete facts, queries, code and tests. Both fresh archive extractions
pass37 affected tests and reproduce57 batch files plus all three full native
outputs. Six older rate holds are explicitly reviewed against the new native
turnout/registration frame; this is not a general permission to lift old masks.

## Complete outputs, publication and resume

### Native workbook and stock-query maintenance

`native_products.py` supports pinned direct `xlsx` inputs with an exact `sheets`
inventory, alongside existing `xlsx_zip` inputs. Both retain native formula
text, raw stored values, cached decoded values and blank cells without executing
formulas. The independent verifier checks XML attributes/cache/formula literals
as well as decoded values; a changed decoded count cannot hide behind an
unchanged cached literal.

`reproduce_pdf_measures.py --wide-recipe` accepts reviewed table selections,
expected row inventories, source-field filters and optional literal-label carry.
Carried labels have explicit review evidence and source-row provenance; original
blank labels stay blank. Derived fields cannot overwrite native fields or
provenance. Count/parent equations remain declarative. Optional signed stock
percent-change checks use the printed precision and preserve unqualified zero
denominators; none of this identifies voter entry/exit or party choice.

Direct/grouped/wide control recipes are mutually exclusive. Existing NJ/VT
complete outputs remain byte-identical. All52 affected reader, independent
verification, PDF and routine tests pass. The AL/ORdirectory products used for
compatibility are already integrated, exact-source no-ops; use their existing
complete downloads, not a duplicate model/data release.

### Publication and resume

Every batch includes all 51 jurisdiction dispositions, complete selected-source
queries, every compiled count file, permitted original inputs, source-specific
intake packets, registry, exact processing code and workflow tests. The original
three-source packet has14tests; the Cape May native-fact packet has17 and the
complete VT native-group/batch packet has37 across its included test suites.
`complete-analysis.zip` includes member checksums and offline instructions,
not merely metadata or a sampled row export.

Adding `--website-repo PATH` invokes the existing atomic batch publisher.
An unchanged candidate preserves accepted compressed bytes and needs no build.
A changed candidate first requires a verified public complete download:
`--complete-download descriptor.json` must bind that exact batch ZIP's byte
count and SHA-256. Publication uses separate staging, so descriptor injection
does not mutate the immutable compilation cache.

The publisher stages and verifies immutable data before switching the catalog,
checks the expected accepted version and refuses concurrent catalog advancement.
Publication journals resume interrupted work without blindly replaying accepted
activation. A cached verified compilation can be published later; changing
resume inputs is rejected. Corrupt cached members fail verification instead of
being trusted as unchanged. A source hold retains the baseline and produces
explicit dispositions with exit status 2; it does not activate a partial batch.

The original no-op milestone adds no turnout rate, boundary match, precinct
polygon, group allocation or model fit. The subsequent Cape May refresh updates
the numerator and percentage within its existing reported-registration frame,
not an eligible-population turnout rate. Newly qualified native-binding
products and broader
within-state/office/mode completeness remain separate work; see
[REMAINING.md](../REMAINING.md).
