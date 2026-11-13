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

For reviewed duplicate exports, optional `format.view_aliases` can rebind
consumer selections to an ordinary refresh's verified successor. This requires
`participation.reviewed_view_aliases.v1`, review evidence, an exact baseline
views pin, and each retained alias's whole-record pin, `refreshed_from`,
`selector_partitions`, and complete `{mode, partition, index}` occurrences.
The old records must match apart from their ID, source ID and project selector
partition; source counts, clocks, measures and qualifications cannot differ.
All occurrences are checked, cross-partition duplicate selections are refused,
and qualified denominators or rates cannot be introduced through aliases.
Original alias records remain available. Omit this declaration for ordinary
same-scope refreshes; no aliases are inferred from names or similar counts.

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

For a permitted native document viewer, direct callers can pass an optional
`response_trace={}` to `Store.acquire`. It records the actual final response URL,
status and content type, including a conditional304 response, so a declared
viewer document parameter can be resolved without guessed paths. The trace is
private operational context: redirected URLs can contain temporary signatures
and are never added to standard public receipts. Each acquisition clears stale
trace data before checking access holds; this adds no request path around a stop,
changes no public receipt or cache schema, and does not qualify viewer HTML as
election results.

The compiler requires the exact existing geography/measure-mode inventory and
unchanged election, geography, complete measure semantics and display identities.
Changing an inventory, geographic join, measure, voting mode or reference map
requires separately reviewed qualification. Unknowns remain unknown and zeros
remain zeros. Candidate votes do not become ballots; registration stocks do
not automatically become turnout denominators.

The distinct `counts_addition` target requires a
`participation.reviewed_count_addition.v1` declaration: the exact accepted
state-shard pin, full added-observation pins, source/scope review and every
mode/partition's existing IDs plus explicit appended IDs. It never replaces
old observations or selected display identities. Missing modes, changed
preimages, shadowed identities, count/clock discrepancies and rate promotion
are rejected. Ordinary same-inventory refresh guards remain unchanged.
Mapped county additions additionally require the complete accepted native
baseline and a pinned `participation.reviewed_county_reference_addition.v1`
review for every affected mode. Only explicit new identities can be appended
to existing complete contextual bindings; feature names, state, vintage,
reference hash, preserved binding preimages and withheld rates are checked.
Geometry files and prior bindings are never rewritten to fit new counts.

When the canonical observations themselves carry approved joins, the registered
reference asset may name an `input` from the source's pinned input inventory.
The routine forwards that exact body to the shared geometry verifier and
packages it for fresh offline replay. The declared input pin must equal the
reference asset pin; a checksum still needs explicit approval evidence and
cannot authorize a new join by itself.

Signer attestation dates and page-posting timestamps are typed provenance, not
count-as-of clocks. Retain them as directly fact-bound `source_time_kind` and
`source_time_literal` fields and explain them in source-reporting notes. Unless
the native product supplies an actual count-update field, canonical
`source_clock.literal` and `view.source_update_label` remain null.

The shared `native_statistics` adapter reads complete pinned factual
worksheets and their reviewed query/grouping roles directly. It preserves
every statistical unit, zero, mode vector and agreeing duplicate parent,
and derives count-only canonical rows rather than taking counts from
metadata. Explicitly reviewed disjoint report frames can supply a separately
labeled composite parent. Different report clocks remain separate, not a
common snapshot; decoded Excel clocks retain cache lexemes, number formats
and date systems. Registrations and printed fractions remain native context,
not inferred denominators. Source units gain no precinct geometry or rates.
Where templates are excluded, the public packet reproduces all factual
queries and transformations, not extraction of the private originals.

For an already accepted derived mode subtotal, a PDF fact binding can declare
`operation: "component_sum"` and distinct `components`, each naming its native
`measure`, literal `native_header` and `header_requirement` index. Exactly one
native parent row is selected. Every encoded component must occupy its own
declared physical header column; repeated parents or fields, missing counts,
metadata and changed headers are rejected. Image-only facts instead require
their pinned, explicitly reviewed image transcription and separate
`visual_header_review_evidence`; no encoded-text extraction is claimed.

Both `sum_review_evidence` and `same_measure_review_evidence` must justify the
specific nonoverlapping components and unchanged `accepted_measure_literal`.
Administrative tables additionally require `administrative_measure_review_evidence`.
An early-vote/Election-Day/tallied-mail subtotal remains that subtotal, not
all-mode ballots or unique voters. Issued, received, pending and provisional
counts cannot be silently added. Retain the selected parent scope, including
any explicitly included overseas component, rather than replacing it with a
different municipal aggregate. Compare dated native contexts before selection;
do not resolve same-clock conflicts by page order or impose monotonic counts.

### State-only native HTML statistics

The separate `state_reporting` target advances one existing same-source statewide
reference without replacing county records or an unselected dated historical
observation. It does not weaken the county/coherent-control or fixed-registration
operations. Supply one complete canonical state observation, its
`participation.selected_html_statistics.v1` factual projection and the exact
`participation.native_html_statistics_recipe.v1` recipe as pinned public inputs.

`scripts.html_statistics` extracts counts beside their own literal labels,
checks agreeing repeated percentages, retains the native clock and exact
election assertions, and keeps explicitly selected backend context opaque.
The recipe binds the complete original's hash, encoding and reviewed selectors.
Metadata, retrieval time, candidate votes and opaque counters cannot authorize
replacement statistical values. Use an independent parser to qualify a new
original before registering its selected factual projection.

Every count/register/percentage/clock mirror needs a direct fact binding.
`format.state_reporting` declares the statistics path, exact old reference
preimage, registration-basis review and source-status limitation. A changed
active-registration stock must be explicitly reviewed; it does not certify
eligibility, counting completion or the survey's population/cutoff transport.
All 51 jurisdiction shards and unrelated current modes remain unchanged.

Where publisher HTML/application redistribution is not qualified, retain the
full original privately and publish every permitted selected numerical fact,
literal, selector/provenance record, receipt, recipe, exact reader and complete
query. The public standalone packet replays selected facts and transformations,
**not extraction of excluded publisher HTML**. This boundary is explicit in the
model and source downloads, not disguised as complete-original reproduction.

The companion `scripts.state_reference_model` revises one existing selected
reported-count/registered scenario using the complete accepted model and count
batch. It checks its own older model preimage separately from the runtime's
preimage, preserves all study weights/probabilities, and recomputes only that
registered-frame partition. Separate monthly registers, held envelope contexts,
all other scenarios and full prior numerical downloads remain unchanged.
Native-minus-model differences are nominal source comparisons, not validated
error, administrative nonparticipation or observed staying home.

### Native workbook facts and coherent reporting targets

Fact bindings also accept `participation.native_factual_tables.v1` directly,
without disguising workbook facts as PDF grids. Supply the complete pinned
native query recipe as another input and declare `query_recipe_input`,
`native_query_id`, an exact `native_record` selector, the reviewed statistical
role and `native_header_row`. The native source/pin/election/jurisdiction must
match the complete recipe and the canonical scope. Header guards must name the
actual count column; label equivalence needs explicit review. Cached values are
read as facts, never calculated by executing workbook formulas.

Worksheet query fields may select `$table` and `$row` as provenance keys when
repeated statistical labels or identical values must retain distinct physical
rows. Neither selector may supply a count field. Blank cells remain blank.
The independent reader preserves every exact numeric cache lexeme and decoded
value; a separate binary64 reader's fractional values are compared in its own
numeric representation, without rounding or weakening integer-count checks.

`native_products.statistical_units` groups a separately reviewed statistical
worksheet query using explicit field, mode and parent roles. It requires each
unit's mode counts and repeated registration stock to reconcile, preserves
zeros and unknown native fractions, and checks repeated parent copies for
equality instead of adding them. Missing counts, ambiguous unit identities and
disagreeing controls are held. These are native statistical groups, not
automatic physical-ballot, geographic, population or turnout qualifications.

The same native binding may check source URL/hash and missing native clock via
`value_scope: "source"`. Metadata still cannot authorize a statistical count.
Candidate-choice columns, unknown cells and ambiguous rows are not ballot
refreshes. The full factual grids and recipe remain downloadable sufficient
inputs, even where redistribution of the original workbook template is held.

Direct delimited and `json_records` products use their actual column/field names
in the same complete native recipe. JSON records retain scalar types, unknowns
and zero-based source-record indices; they are not represented as worksheet
cells. Declare the expected full record inventory and native record guards
(for example an exact election-header pattern).
Optionally use `count_formats: {"field": "comma_grouped_integer"}` for explicitly
reviewed thousands-grouped textual counts. The default integer reader stays
strict. Malformed grouping, decimal values, whitespace repairs, unknown formats
and declarations for non-count fields are rejected; original factual strings
and true zeros remain intact. Duplicate JSON keys, changing
record schemas and undeclared nested fields are rejected. The independent
verifier checks every native field/type/index against the complete original.

For these record products, `native_measure_header` is the actual field name;
omit `native_header_row`. Existing measure-equivalence and statistical-role
reviews remain required. A per-record literal such as its own result clock
uses `value_scope: "row"`, `value_path` naming a declared query field, and
`parse: "literal"`. That literal cannot authorize a statistical count or turn
acquisition time into a native result clock. Workbook guards are unchanged.

When complete originals are permitted, `format.native_reproduction` binds a
`recipe_input`, every product ID to its `original` and `facts` input names
(optional `compression: "gzip"`), and a complete `queries_input` (optional
`queries_compression: "gzip"`). The same routine re-parses every full original,
compares every factual table and reproduces every declared numerical query
before accepting observations. Original source URLs, pins, election/state and
explicit original-redistribution declarations must agree. Metadata-only inputs,
altered cells or partial query sets cannot satisfy this option. Do not enable
it for workbook originals whose redistribution remains held.

For an existing same-source county record frame, the maintained
`scripts.native_count_refresh` preparation operation accepts reviewed identity
and field roles, the complete accepted baseline, and a source-input directory
containing the registered `recipe`, gzipped `controls`, permitted originals and
`facts-<product-id>` tables. It requires exact native IDs/names, separate
state/county controls, unchanged registration stocks, matching printed fractions
and each record's own literal clock. It preserves observation/geographic IDs,
existing rate holds and all unselected modes; no metadata supplies counts.
The prepared registry and supplied inputs then use the same routine command.
Fresh preparation refuses an existing output directory. Preparation code and
review are included in the complete download, alongside every native original
and query. Native source packets also include their shared query-reader modules
so their own isolated `reproduce.py` does not depend on a surrounding checkout.

When the same source also has an existing state record in the current snapshot,
the reviewed preparation sets `refresh_current_reporting: true`. Its separate
native state reference is fact-bound in the accepted county observations.
The common compiler updates that one same-source state record together with
its counties, checks all county/state count and registration controls, and
preserves the other reporting records, early/mail and demographic partitions.
The base snapshot remains historical provenance, not a fabricated common clock;
the successor retains its own source hash and result/retrieval labels.

For existing reporting-unit tables served by the native-binding dataset, use
the **same routine command** with an additional complete baseline:

```sh
python3 -m scripts.participation_batch \
  --registry reviewed-registry.json --baseline accepted-counts \
  --native-baseline accepted-native-bindings \
  --supplied-root reviewed-inputs --work-dir routine-work --offline
```

Pin `native_baseline_version` in the registry. Ordinary sources retain the
default `target: "counts"`; a complete existing reporting table declares
`target: "native_reporting"` and reviewed `reporting_source` metadata. Every
original observation identity, geographic/display key, registration definition,
rate hold and source-unit type must survive. New inventories or qualified
geography require separate review. Metadata binds the entire current compressed
properties export; it cannot substitute a number for source facts.

Both complete datasets and baselines are packaged together. Unchanged state
shards, geometry and native tables remain byte-identical. The existing resumable
publisher verifies both expected versions, stages all immutable bodies and
activates the coherent changes in one catalog commit; it does not publish an
updated parent against stale child counts. Cached execution validates both
baselines and performs no acquisition, parsing or compilation.

## Revise an existing scientific control without inventing a model

Use the complete current packet in [DATA.md](DATA.md) as the pinned input and
recipe reference. From a full extraction, the native-context operation is:

```sh
python3 -S -m scripts.native_context_successor --inputs inputs --output /new/replay
```

The operation rereads complete source records through explicitly reviewed column
roles, checks their literal identities/counts against every accepted source-query
row and parent, and checks a separate printed registration control. Headerless
column roles are a reviewed schema, never relabelled as printed headers.
Missing/unreported/duplicate units, changed source/election, incomplete packets
and metadata-supplied replacement counts are rejected. Full prior analysis and
native source packets remain sufficient inputs; all before/after controls and
unit/parent queries are downloadable.

This operation can replace only an existing **non-selected context** that is
not referenced by a current state estimate or conditional scenario. State and
scenario CSV bytes, the selected registration stock, source weights/means and
all other controls remain unchanged. Complete native reporting-unit coverage
does not qualify physical ballots, unique people, a population denominator or
observed staying home. Component discrepancies, source zeros and null rates
are preserved, not repaired. Duplicate numerical/coverage updates are refused.

An actual change to an existing registered-frame scenario instead uses the
separate `scripts.registered_control_successor` operation and its reviewed
native group-fact recipe. It derives new registration counts from native count
columns, reuses accepted study probabilities/weights unchanged and retains
all frame/behavior qualifications. Neither operation creates another model
family or fits a propensity to an unqualified native outcome counter.

An existing selected **ballot-only** reference with no registered denominator or
conditional scenario uses `scripts.ballot_control_successor`. Its complete
count/reporting batch must agree with the separate native unit/county/state
controls, and its old runtime must reproduce the old model reference. This
updates the counter and explicitly scoped valid-choice context only. The latter
may include source-unassigned write-ins and exclude over/undervotes; a scope
change is not participation or switching. No study probability, weight,
registered source mean or geographic hold is changed.

An existing **reported-ballot reference with an unchanged registered scenario**
instead uses `scripts.reported_registered_reference`. It verifies the complete
new batch against original record products, the separate native state control,
every county identity and both refreshed runtimes. The accepted registered
stock, study weights and all conditional voter/nonvoter means must remain
unchanged. Only the source reference/time, registered reporting fraction and
nominal reported-minus-modeled comparison change. That comparison is not an
independently validated prediction error or observed staying home.

The operation retains earlier same-source evidence with its old count/date,
but does not continue describing it as a duplicate of the latest reference.
Paired public aggregate state/county group tables must reconcile every joint
cell, including recorded zeros. Complete source-mode group observations and
queries are exported separately; overlapping feeds and different clocks are
not added, deduplicated or promoted to full demographic turnout. No new model
family, scenario, geographic allocation or propensity fit is created.

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
