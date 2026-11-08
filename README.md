# Voter participation

**Who participates in elections, how participation changes over time, and where
the evidence supports a local map.** The project covers presidential and midterm
elections, with historical demographic series and separately labeled 2026 results
and survey estimates.

[Open the explorer](https://www.themarginoferror.com/voter-participation/) |
[Estimation methods](METHODOLOGY.md) |
[Complete downloads](docs/DATA.md) |
[Reproduce an analysis](docs/REPRODUCING.md)

## How the estimates work

We calculate demographic participation rates using each survey's own weights,
population and participation definitions. We retain unknown responses rather
than assuming everyone without a recorded vote stayed home.

Official election records provide a separate check on counts, reporting coverage
and denominators. A survey rate becomes a count estimate only when a suitable
population or registration frame exists, with its assumptions stated explicitly.
Candidate votes are contest results, not ballots or demographic turnout.

Historical comparisons keep presidential and midterm elections separate.
Projections are tested against simple historical baselines; precinct maps require
supported election-year counts and geography, not state rates spread across a map.

## What the explorer shows

| View | What it means |
|---|---|
| Historical demographic and state rates | Survey-reported participation; population definitions and available years vary. |
| Current survey studies | Source-weighted modeled or reported participation, not certified turnout. |
| Administrative participation | Source-defined counts and rates, with reporting status and denominator identified. |
| Precinct maps | Participation where supported; candidate results are a separate layer. Coverage is partial. |

**Limits:** These sources do not form one linked electorate. Missing data are not
zero, modeled nonparticipation is not observed staying home, and repeated survey
waves do not identify individual switching. Broad 2026 group denominators and
some historical/local coverage remain unresolved.

## Documentation

The website keeps Methods short; details live here.

| Read | Purpose |
|---|---|
| [Methods](METHODOLOGY.md) | Estimands, weighted rates, conditional counts, historical tests and uncertainty. |
| [Data catalog](docs/DATA.md) | Choose a complete, versioned analysis download. |
| [Reproduction guide](docs/REPRODUCING.md) | Run a saved analysis without reacquiring its inputs. |
| [Source ledger](SOURCES.md) | Technical provenance, native definitions, access holds and verification records. |
| [Remaining work](REMAINING.md) | Current research gaps and execution queue. |

## Repository layout

| Path | Contents |
|---|---|
| `scripts/`, `tests/` | Maintained readers, estimators and focused tests. |
| `data/` | Versioned source manifests and qualified analysis inputs. |
| `public/` | Historical explorer export, observations and complete downloads. |
| `docs/` | Reproduction, package references and the original research protocol. |

The website uses a reviewed, pinned export; a research update does not
automatically change its displayed estimates. Public packages contain complete
permitted inputs, queries, results and code, never metadata-only substitutes.
Privately supplied respondent records and private fine cells are not published.
