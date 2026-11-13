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
be unambiguous. The current supported native role is the reviewed unofficial
registration/ballot/turnout-statistics grid, not a contest-choice table.
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

## Complete outputs, publication and resume

Every batch includes all 51 jurisdiction dispositions, complete selected-source
queries, every compiled count file, permitted original inputs, source-specific
intake packets, registry, exact processing code and workflow tests. The original
three-source packet has14tests; the native-fact refresh packet has17.
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
