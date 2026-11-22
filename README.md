<div align="center">
  <h1>Voter participation</h1>
  <p>
    <a href="https://www.themarginoferror.com/voter-participation/">Live explorer</a> &middot;
    <a href="METHODOLOGY.md">Methods</a> &middot;
    <a href="docs/DATA.md">Data &amp; downloads</a> &middot;
    <a href="docs/REPRODUCING.md">Reproduce</a>
  </p>
</div>

---

Voter participation across US presidential and midterm elections: historical
demographic rates, administrative counts, supported local maps, and automatically
updated House and Senate results.

Recorded results and assumption-dependent modeled explanations are kept separate.
Local coverage is partial; candidate votes are not turnout, and modeled mechanisms
are not observed individual behavior.

## Documentation

- [Coverage and limitations](docs/AUDIT.md)
- [Automatic results intake](docs/RESULTS_INTAKE.md)
- [Source ledger](SOURCES.md) and [research gaps](REMAINING.md)

Complete downloads include all permitted inputs, code, queries, and results.
The [website repository](https://github.com/hanshanley/margin_of_error) hosts the explorer.

### New Mexico historical precinct identifier audit

The weekly research audit reads the five official 2016–2024 turnout editions
from an immutable accepted checkpoint and checks their identifiers against
three dated GIS references. It preserves turnout-only and reference-only
records, including source denominator holds. A matching identifier, even
with a valid polygon, does not establish an election-day boundary.

The audit artifact contains every turnout row, all match decisions, the source
receipts, and the inputs and code needed to reproduce the tables offline.
From the extracted artifact, run:

```sh
python3.12 -m scripts.new_mexico_precinct_reference_audit \
  --turnout-facts inputs/turnout-facts.json \
  --reference-rows inputs/reference-rows.json --output reproduced
```

The source receipts also identify the original archives and hashes for
independently re-extracting the GIS inputs with `pyshp==3.1.8` and
`shapely==2.2.0`.
