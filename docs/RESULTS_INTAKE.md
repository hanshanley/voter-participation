# Automatic 2026 results intake

The **Update election results** GitHub Actions workflow refreshes registered
sources hourly, at minute 23, through January 31, 2027 UTC. It can also be run
manually from Actions, including outside that election window:

```sh
gh workflow run election-night.yml --repo hanshanley/voter-participation --ref main
```

The tool publishes data to the separate `results-data` branch. It does not
rebuild the website, overwrite its reviewed participation catalog, or refit
switching/nonparticipation models.

## Get the complete results

Read `latest.json` on `results-data`. Its `results_commit`, `base_url` and `files`
inventory identify immutable result bodies, their byte lengths and SHA-256
checksums. Download `complete-results.zip` using that inventory. Branch history
retains previous snapshots; 30-day Actions artifacts are an additional convenience,
not the only copy.

The download contains all 14 complete numerical queries, selected source facts,
all 51 accepted jurisdiction shards and their complete baseline, source
qualifications, processing code, tests and checksums. It excludes respondent/voter
records, private fine cells, and publisher HTML/application templates.

| Query | Meaning |
|---|---|
| `snapshot.json.gz` | All current source channels and jurisdiction decisions. |
| `coverage.csv` | All 50 states plus D.C.; available, retained and missing sources. |
| `participation-observations.csv.gz` | Complete accepted observations plus separate refreshed source frames. |
| `house-candidates.csv` | Literal candidate counts, district, source clock and freshness status. |
| `house-state-results.csv` | Party sums only when every declared district snapshot is available. |
| `source-status.csv` | Each collected/retained feed, failure status and source URL. |
| `declared-products.json` | Official-directory discoveries awaiting scope/parser review. |
| `granular-source-queries.json.gz` | Complete registered county/reporting-unit statistical queries and source dispositions. |
| `declared-numerical-queries.json.gz` | Complete permitted tabular facts from newly declared products, with unqualified measures held. |
| `canonical-local-changes.csv` | Every qualified same-identity count update; appearances are not unique people or geographies. |
| Four `accepted-*.json` queries | Complete accepted House candidates, controls, native scope and state qualification flags. |

After extracting the ZIP into a fresh directory, run its literal command:

```sh
python3 code/reproduce.py replay --package . --output reproduced
```

Python 3.9+ and the project's existing `requests` dependency are required. Replay
verifies every pinned member and reproduces all query bytes without acquiring
sources or rerunning private survey fits. Optional packaged tests use `pytest`:

```sh
cd code
python3 -m pytest -q tests/test_results_intake.py tests/test_results_granular.py tests/test_nationwide.py tests/test_current.py
```

## What updates automatically

The registry covers every jurisdiction's supplied official-directory disposition.
Existing parsers refresh provider early/mail and supported demographic feeds,
the four registered statewide administrative feeds (AL, NC, ND, OR), and House
district returns explicitly declared by the national source.

Registered local adapters also parse North Carolina county statistics, Minnesota
county/reporting-unit statistics, accepted Alabama general-election workbook
columns, and Connecticut town statistics. Changed identities/layouts remain held;
these adapters do not approve new boundaries or guarantee complete precinct coverage.
Alabama's registered workbook URL is distinct from newly declared ZIP products:
discovery alone does not alias a new release to that accepted source.

House collection is independent of county geometry/reconciliation. A county-map
failure cannot abort otherwise usable district returns. Full House baseline
counts remain available when the live declaration or a district is unavailable;
those rows are explicitly retained, not newly checked returns. D.C. has no voting
House seat. Distinct district clocks and accepted official HI/WY source scopes
remain visible; raw provider updates do not replace reviewed model endpoints.

This is not a universal parser for every state portal, PDF or newly posted
spreadsheet. Newly declared products with unfamiliar layouts remain review items
until an election/measure-specific parser and tests are registered. No guessed
endpoint, inferred missing count, or unreviewed precinct join is promoted.

## Failure handling and interpretation

Each source is independent. A failed request or changed schema retains its last
valid data and original source clock. HTTP 401/403, security challenges and
product stops persist on `results-data`, even if the operational HTTP cache is
lost. HTTP 429 also stops its host. The next run does not retry those routes or
switch clients/aliases. Removing a stop requires a separately reviewed access
change; a newer calendar date alone does not clear it.

Publication stages the complete result bodies and durable operational state,
verifies their anonymous immutable downloads, then activates `latest.json`.
An interrupted/failed run cannot replace the last valid pointer with empty
results. Identical content/provenance/code leaves the data branch unchanged;
checking again does not itself become a new native count clock.

Candidate votes are not ballots. Early/mail activity, registration stocks and
all-method participation are separate, nonadditive channels. Complete reporting
is not certification. Aggregate counts do not identify individual switching or
staying home. Existing behavioral qualification holds remain unchanged.

## Local operation

```sh
python3 -m scripts.results_intake collect \
  --registry data/results-intake/registry.json --work-dir /tmp/election-intake
python3 -m scripts.results_intake publish --work-dir /tmp/election-intake
```

`collect --offline` may reuse permitted, checksum-verified cached source bodies;
it makes no election-source requests and still honors durable access stops.
The initial source state and accepted numerical baseline are pinned in
`data/results-intake/registry.json`. Add or change sources there only with the
corresponding native scope review and focused parser tests.

## Automatic website and estimate consumer

The separate `scripts.automatic_runtime` consumer is enabled in the website's
own GitHub workflow and uses its token, not a shared cross-repository secret.
It pins reviewed producer `4d73fd2`; the initial live reader `4b08650` passed
actual Pages and no-override desktop/mobile acceptance. Collection runs hourly
at minute23 UTC and consumption at minute31. The assistant continuation is not
required for these numerical updates. Source-only publication by itself would
not establish live delivery; [the complete acceptance record](../data/participation-access/20261114-automatic-runtime-01/acceptance.json)
records both hosted jobs, public replay and actual website propagation.

```sh
PYTHONPATH=/path/to/research-source python3 -m scripts.automatic_runtime \
  --repository /path/to/website --work-dir /tmp/participation-runtime
```

It reads the pinned `results-data` snapshot once, advances compatible counts,
existing native bindings and all affected nine House family/profile cases, and
retains unsupported comparisons. Compatible registered-frame revisions reuse
the accepted probabilities; unchanged sources do not trigger private fits.
After the first run, a verified rolling seed is mandatory. Source failure never
resets estimates to the bootstrap seed or applies older retained local facts
over the website's last-good counts.

Each runtime packet includes the complete source-results ZIP, before/after
counts and native bodies, safe aggregate priors, every model query, code, tests
and checksums. Its fresh extracted command is:

```sh
python3 code/reproduce.py --replay-package . --output reproduced
```

Publication requires successful zero-network, complete-output replay, a
server-immutable full archive verified both authenticated and anonymously,
staged-body verification, and one atomic `catalog.json` plus
`automatic/latest.json` activation on the website's `participation-data` branch.
Count/native descriptors and models share the same immutable staged commit.
Interrupted staging is resumable; concurrent branch changes are not overwritten.
Subsequent numerical activations do not start a Pages build.

These are delivery guarantees, not observed individual switching/nonparticipation,
new geographic qualifications or final/certified nationwide results. The actual
GitHub-job, public full-packet replay and no-override production gates passed for
this increment; future parser/reader changes must satisfy the same gates.
