# Voter participation

Historical voter participation, not candidate preference. This is a local-only
research project; deployment requires the owner's explicit approval.

See [SOURCES.md](SOURCES.md) for the primary and secondary source ledger,
download/update rules, collection inventories and source-specific caveats, and
[REMAINING.md](REMAINING.md) for the active acquisition-to-estimation work queue.
It also tracks separately reviewed private survey inputs; recording a source
does not authorize publishing respondent data or change the public collectors' scope.

The analysis keeps three measures separate:

1. Census survey-reported turnout among all adult residents or adult citizens.
2. Administrative participation among registered voters, where election-time
   registration and participation counts are both available.
3. Precinct coverage and boundary availability. Election returns alone are not
   treated as ballots cast or demographic participation.

## Private survey reconstruction

The separate Civic 2026 estimator computes source-weighted participation,
prior/current-choice tables and exactly reconciled margin components:

```sh
.venv/bin/python -m scripts.civic_estimates \
  --csv "$CIVIC_CSV" --codebook "$CIVIC_CODEBOOK_ZIP" \
  --output "$PRIVATE_ANALYSIS_DIRECTORY"
```

Use the already supplied, hash-qualified files; do not download another copy.
The output directory must be new and outside any Git repository. The command
does not publish its fine-grained queries. Its modeled nonparticipation and
reported/intended choices are not administratively observed staying home or
certified population estimates. See `SOURCES.md` and `REMAINING.md` for the
weights, frame, geographic and remaining integration limitations.

The historical AP VoteCast reader uses the privately qualified four-wave contract:

```sh
.venv/bin/python -m scripts.ap_votecast_estimates \
  --contract "$AP_PRIVATE_CONTRACT" --output "$PRIVATE_AP_ANALYSIS_DIRECTORY"
```

It preserves all four poll-close/final state/national weight frames, nonvoters,
unknown demographics, native encodings and inference exclusions. Repeated
cross-sections are not a linked panel. `--years 2022 2024` can run selected waves
without repeating successful reductions. The full-frame weight total is named
`weight`; the distinct source weight variable is `weight_field`.

The [complete selected historical AP package](https://github.com/hanshanley/margin_of_error/releases/download/participation-ap-history-20261108-01/complete-analysis.zip)
now contains 602 broad participation rows and every one of the 710 requested
broad-query selection decisions. It includes all permitted selected inputs,
full CSVs, viewer JSON, source hashes, code and tests, not raw respondents or
state demographic cells. The four weight frames remain separate; 2018 state
inference qualifications, 2022 DE/WV holds and the absent 2022 race field remain
explicit. After unpacking, reproduce offline:

```sh
python3 -m unittest discover -s tests -p test_ap_public_aggregates.py
python3 -m scripts.ap_public_aggregates --inputs selected-aggregates.json --output reproduced
```

These are source-weighted modeled participation shares, not administrative
turnout or a linked panel. Source definitions differ across years, and joining
these rows to Civic does not identify a cross-study turnout change.
The [historical study view](https://www.themarginoferror.com/voter-participation/#participation-ap-history)
is live inside the existing folded research section. Its eight national fallback
rows work without JavaScript; selected state/national-group views use a
checksum-verified public snapshot rather than private fine cells.

## Exact House source-count comparison

The [complete versioned House analysis](https://github.com/hanshanley/margin_of_error/releases/download/participation-house-exact-panel-20261108-01/complete-analysis.zip)
contains all pinned aggregate inputs, complete county and county-district
queries, candidate controls, exclusions, code and tests. It includes 3,152 county
records, 2,639 positive-count pairs and 2,228 comparisons passing known-source
screens in 38 states. These are candidate contest votes, not ballots, turnout or
individual switching. Passing the screens does not certify complete coverage or
matched district boundaries.

After unpacking, reproduce without network access or additional packages:

```sh
python3 -m unittest discover -s tests -p test_house_panel.py
python3 -m scripts.house_panel --inputs . --output reproduced
```

For a new source snapshot, use `--website-root "$EXACT_WEBSITE_CHECKOUT"`
instead of `--inputs`. The reader verifies each input against that checkout's
actual Git commit and refuses to overwrite an existing analysis. Missing counts,
historical no-ballot races, withheld source rows, literal-party/fusion ambiguities
and differing current candidate-control scopes remain explicit.

## Senate county identifier joins

The [complete Senate identifier package](https://github.com/hanshanley/margin_of_error/releases/download/participation-senate-identifiers-20261108-01/complete-analysis.zip)
retains all 34,492 original candidate-unit rows and adds separately labeled
reference IDs for six counties. Native blank FIPS, counts, parties and clocks
remain unchanged. The joins use held Census-backed House namespace records and
CNN declared IDs, not names or vote equality alone. All 23 additional named
candidate identities match; 22 counts agree and one difference remains.
Same-round or independent outcome validation is not implied. The Maine write-in
gap and Alaska/Connecticut scope exceptions are not repaired by these joins.

The archive includes all sufficient aggregate inputs, complete outputs, code,
six tests and offline reproduction instructions. The derived `resolved_fips`
and `fips_resolution` columns do not overwrite original identifier/eligibility
fields.

## Conditional current-registration controls

The [complete expanded state/control comparison](https://github.com/hanshanley/margin_of_error/releases/download/participation-state-controls-20261108-02/complete-analysis.zip)
contains all 51 state/D.C. rows, 15 native control observations and six
conditional current-register scenarios for AL, CA, CO, HI, NC and OR.
`R*p` and `R*(1-p)` split each native registration denominator using its state's
source-weighted modeled participation share. **Exchangeability to that exact
registration frame is an unvalidated assumption**, not measured staying home,
independent model validation or an original-coalition population estimate.

Active, all-registered, eligible/pre-registered and source-undefined denominators
remain distinct. Only AL, HI, NC and OR have cast-ballot measure comparisons.
Colorado returned/processed ballots and California native `voterTurnout` are
not relabeled as cast-ballot observations; missing registration totals are not
filled with UF's estimated VEP. Native dates, unsupported states, the duplicate
NC source and all county-only observations remain in the full query.
Hawaii's declared statewide summary reports 365,897 ballots and 853,399
registrations. Its native unit ballot sum is six higher; that discrepancy and
precinct registration/rate holds remain visible. Wyoming's separate 191,688
ballots reconcile across all 23 counties, but its registration denominator stays
null. Minnesota's 4,105-row statistics file has only 2,490 units flagged reported
and 15 ballot-mode discrepancies: its sums are retained, never treated as
statewide controls or allocated statewide survey estimates.

The 17-member archive includes complete permitted sufficient inputs, original
aggregate sources, all queries, code, 12 tests and offline reproduction
instructions. Independent verification passed 5,530 checks and two byte-identical
offline reproductions. The original five scenarios, 49 unaffected state rows
and all 12 old controls remain unchanged; the
[initial version](https://github.com/hanshanley/margin_of_error/releases/tag/participation-state-controls-20261108-01)
is preserved immutably. These new control outputs are research downloads, not
an additional deployed website view.

## Reproduce

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m playwright install chromium
.venv/bin/python -m scripts.download
.venv/bin/python -m scripts.build
.venv/bin/python -m pytest
python3 -m http.server 8765 --bind 127.0.0.1 --directory public
```

Dependencies are declared in `pyproject.toml`. Source downloads are cached
atomically in `data/raw`, with SHA-256 checksums in `data/sources.json`.
Rerunning the downloader reuses verified files. Failed requests are recorded,
not silently replaced with fabricated data. Public aggregate source data only:
no individual voter records are collected.

Historical Census workbooks extend the national series as far back as their
published tables support. Both presidential and midterm elections are included.
North Carolina's historical aggregate voter-history and registration files
provide a first administrative precinct series. Other states are marked
unassessed until their numerator, denominator, and historical geometry have
actually been checked.

Current outputs include national demographic turnout from 1964–2024 and state
turnout from 1972–2024, with availability and population definitions varying by
series. Election-specific Census tables add citizen-denominator education and sex
rates for every election from 2000–2024; older education and sex series retain
their all-adult-resident denominator. Calculated rates retain their published
thousand-person numerator, citizen denominator, and source rows. Bachelor's and
advanced degrees are combined using counts, never an average of percentages.

The NC precinct series covers 2002–2024. Election-year boundary snapshots are
available for 2006, 2012, 2014, 2016, 2020, 2022, and 2024. Maps use those snapshots
only, not a modern boundary substituted for earlier elections. Joining an ID
does not certify election-day boundaries or create a constant-precinct panel.
Missing participation records, inconsistent counts, and zero denominators are
flagged and have no displayed rate. NC education is not available.

The 561-row nationwide coverage matrix explicitly marks the other 50
jurisdictions **not assessed**: this is an initial inventory, not a completed
nationwide precinct-source audit. Nationwide state estimates are not precinct
estimates. NC archive participation/registration totals are separately compared
with the official ballots/eligible-count table; source discrepancies and the
official 2010 percentage/count inconsistency are preserved, not silently fixed.

Raw ZIP files are retained locally and backed up as GitHub release assets;
normalized datasets, source manifests, analysis, and application code are
versioned in Git. These data backups are not a deployment.

To restore the exact archived NC and boundary sources after cloning, authenticate
the GitHub CLI and run `.venv/bin/python -m scripts.restore`. This downloads
missing originals from release `data-snapshot-2026-11-03` and verifies every
SHA-256 against `data/sources.json`, without overwriting existing files.
`data/backups.json` records the release-asset checksum verification. Census
workbooks, source catalogs, and layouts are versioned directly in Git. The
explorer's complete-analysis ZIP contains all observations and geometry, not
just metadata; raw originals are preserved separately.

## November 3, 2026 preliminary reporting

Refresh a separate, immutable NC snapshot, then rebuild the complete download:

```sh
.venv/bin/python -m scripts.current
.venv/bin/python -m scripts.build
```

For frequent election-night refreshes, use the lightweight command instead:

```sh
.venv/bin/python -m scripts.current --update-downloads
```

It updates the current pointer and complete download using the already saved
historical data; it does not download historical archives or recompute them.
The absentee URLs follow the official catalog's current daily files rather than
remaining hardcoded to November 3.

GitHub Actions runs `.github/workflows/election-night.yml` every 15 minutes
(minutes 7, 22, 37, 52) on November 4–5 UTC, 2026: November 3 at 7 p.m.
through November 5 at 7 p.m. Eastern. GitHub may delay scheduled starts.
Manual `workflow_dispatch` remains available afterward. Every valid refresh
commits the originals, checksums, complete observations and ZIPs to `main` as
`hanshanley`, without Copilot attribution. Failed captures retain their raw
sources and error manifest without replacing the last valid public snapshot;
the workflow fails visibly. This workflow does not deploy a website.

The same workflow now captures **nationwide** sources independently, not only NC.
It requests a refresh every 15 minutes on November 4–5 UTC and hourly on
November 6–19 UTC; those are requested schedules, not guaranteed collection times.
Every snapshot displays its actual retrieval time and each source's own data date.

The complete-analysis ZIP contains every saved normalized observation and the
latest complete-source snapshot ZIP. Superseded original-source ZIPs remain
individually downloadable in their immutable snapshot directories, rather than
being duplicated inside every new full-analysis ZIP.

The updater retrieves the official election-night county feed (`bct` ballots cast,
`rtl` registered voters, and precinct reporting counts), not candidate totals.
It separately retrieves aggregate absentee/early-voting demographic CSVs, sums out
party affiliation, and reconciles every statewide cell against county sums.
The source's unusual count-column header `0` is handled explicitly, not guessed.
No individual voter files are downloaded.

Every successful refresh keeps original bytes, source update/retrieval timestamps,
checksums, and a complete snapshot ZIP under `data/raw/current/<UTC snapshot>/`
and `public/data/current/<UTC snapshot>/`. Earlier snapshots are never overwritten.
Rejected snapshots retain an error manifest and cannot replace the last valid
`current/latest.json`. Commit and push new snapshots to preserve them.

Election-night ballots/registrations are a **partial reporting fraction**, not
final turnout. An unreported county is not assigned 0% turnout. Absentee group
counts use a different update time and do not include Election Day in-person
voting. These overlapping feeds must never be added together. No matched group
registration denominator, 2026 CPS estimates, education, age, or precinct-level
demographic turnout is inferred. The historical 1964–2024 series stays unchanged.

## Nationwide 2026 updates

```sh
.venv/bin/python -m scripts.nationwide --update-downloads
```

The collector checks all 50 states and DC against civicAPI's public early-vote
capability endpoint, then saves in-person early and returned-mail counts, all
available source-region observations, and reported race, ethnicity, gender and
age breakdowns. Party registration is summed out; requested ballots and candidate
votes are never substituted for votes cast. civicAPI permits public reuse with
attribution; its original responses and source dates are preserved, not described
as certified state-government turnout.

Separate verified administrative adapters currently cover Alabama, North Carolina,
North Dakota and Oregon. They read ballots, not candidate contest totals.
Registered voters (AL), active/inactive registrations (NC), active registrations
(OR), and estimated eligible voters (ND) are explicitly different denominators.
ND's rounded published percentage does not establish an exact eligible denominator.

`data/raw/nationwide/<UTC snapshot>/` preserves every attempted response, including
404/error responses, and URL/retrieval/header/checksum manifests.
`public/data/nationwide/<UTC snapshot>/` contains the full JSON, early-voting,
demographic, administrative and 51-jurisdiction coverage CSVs, plus a complete
original-source ZIP. If a previously valid source fails, its observations and
original source bytes remain in the next complete ZIP, marked retained/stale with
the original dates and the new failure. Other states continue updating.
The full-analysis ZIP retains all normalized snapshots and the latest complete
source ZIP from each collector; old source ZIPs remain separately downloadable.

Coverage is evidence about **assessed sources**, not a claim that missing states
have no data anywhere. Undated responses are rejected; observed zeros remain
counts, not zero turnout. A demographic total can differ from its corresponding
mode total/date and is flagged accordingly. State group definitions and age bins
are not pooled into a nationwide demographic percentage, and no matched group
denominator or 2026 education/precinct turnout is invented.

The requested NYT tracker is a methodological reference only. Its modeled
figures, supplied article tables and proprietary inputs are not ingested,
republished or used to train our work. The interactive analysis uses attributed,
independently acquired public inputs.

## Independent participation methodology

See [METHODOLOGY.md](METHODOLOGY.md) for the participation-only research protocol,
public primary references, proposed administrative/survey tracks, denominator
rules and publication gates. We do not recreate candidate-preference estimates.

```sh
.venv/bin/python -m scripts.model
.venv/bin/python -m pytest tests/test_model.py
```

The implemented first experiment uses archived Census citizen-denominator rates,
never NYT outcomes. It carries forward national turnout from the last election of
the same type and transfers the group's average log-odds turnout gap from the
preceding three same-type elections. Each historical target is withheld from
training and compared with simple group-rate carry-forward. Presidential and
midterm tests, native demographic bins, source rows and failed checks remain
visible. This is a retrospective year holdout using current archived tables,
not an as-of-release-vintage forecast or validation against individual records.

`public/data/model/` includes every prediction/error, per-year/type/dimension
scores, input hashes, full CSV/JSON downloads, the method and a ZIP containing all
observations and input tables. The complete-analysis ZIP includes these files.
The normal historical build regenerates the experiment; frequent current-data
refreshes preserve it without fitting to incomplete 2026 feeds.

The first candidate **does not pass** the prespecified historical screen.
Its 98 tests have 4.22 percentage-point mean absolute error, versus 4.17 for
carry-forward. It is not a validated 2026 estimator. Outputs explicitly withhold
2026 predictions: matched current inputs, uncertainty estimates and independent
confirmation after model selection are still required. Historical education/sex
and race/age bins are not relabeled to resemble the NYT bins. A proposed richer
public-microdata model is documented, not presented as already fitted.

### Joint-demographic survey inputs

The next step now has independently acquired **2022 and 2024 public Census CPS
survey files**, original technical documentation, source catalogs and checksums.
They are anonymized public survey responses, not commercial or administrative
individual voter records. No NYT estimates are used.

```sh
.venv/bin/python -m scripts.cps --download
.venv/bin/python -m scripts.cps
.venv/bin/python -m pytest -q tests/test_cps.py
```

The first command acquires/cache-verifies inputs; the second rebuilds offline.
Age-18+ civilian citizen records are weighted using the documented final weight.
Observed joint cells cross state, age, sex, education and an exclusive
race/Hispanic-origin partition; they are never synthesized from marginal shares.
Unknown participation responses and supplement noninterviews remain separate
from reported nonvoters. Most fine joint cells have small samples and are
research inputs, not precise subgroup turnout estimates.

`public/data/cps/` includes **every** observed cell and projected marginal,
all published-rate comparisons, audit JSON and a complete ZIP with original
public survey files, documentation, catalogs and comparison inputs.
No person/household identifiers are projected into website tables.
The published-table comparisons audit input handling, not predictive reliability.
The earlier failed model stays unchanged. Replicate-weight uncertainty,
compatible population inputs, more training years and a frozen confirmation
specification are still needed before the richer model can be fit and assessed.
No 2026 demographic turnout is estimated from these historical files.