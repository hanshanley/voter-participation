# Voter participation

Historical voter participation, not candidate preference. This is a local-only
research project; deployment requires the owner's explicit approval.

The analysis keeps three measures separate:

1. Census survey-reported turnout among all adult residents or adult citizens.
2. Administrative participation among registered voters, where election-time
   registration and participation counts are both available.
3. Precinct coverage and boundary availability. Election returns alone are not
   treated as ballots cast or demographic participation.

## Reproduce

```sh
python3 -m scripts.download
python3 -m scripts.build
python3 -m pytest
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

Raw ZIP files are retained locally and backed up as GitHub release assets;
normalized datasets, source manifests, analysis, and application code are
versioned in Git. These data backups are not a deployment.