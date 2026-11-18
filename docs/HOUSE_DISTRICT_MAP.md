# National House district display

The district view joins all 435 voting House districts to the existing automatic
congressional results contract. It does not allocate statewide models, historical
votes or turnout onto districts. A new accepted hourly results snapshot changes
the counts and qualified changes without rebuilding or reacquiring the geography.

The dated display uses all 50 native Census 2026 CD120 archives. All 50 Census
2025 CD119 archives are retained for inspection. Three `ZZ` unassigned areas are
preserved in the downloads but are not voting seats. Native NAD83 coordinates,
leading-zero identifiers, attributes, rings and original archive hashes survive.
The screen projection and simplification are display-only.

Electoral eligibility remains the separate comparison-specific
block-equivalency/split-block, candidate, party and election-stage decision.
The accepted input has 259 qualified district comparisons and 176 holds; native
outline equality grants no additional comparisons. Both years' raw candidate
counts, Other/write-ins, source clocks and exact hold reasons remain inspectable.
Margin change is twice Democratic two-party-share change.

Missouri's retained archive metadata describes a plan reversion. The separate
Census correction page returned HTTP 403 and was not recovered. These literal
dated outlines do not certify the effective legal plan or override any hold.
Native geometry inequality alone does not establish a changed legal plan.

The complete geography packet, not just metadata, is published at the
`participation-house-district-geography-20261118-01` release in
`hanshanley/margin_of_error`. It contains all 100 complete originals, individual
acquisition receipts, catalogue evidence, complete queries, CSV, code and tests.
The website's receipt supplies the full immutable download URL and checksums.
Frontend source publication is not Pages deployment; deployment is not requested.

After extracting the packet, use Python 3.9+ with its pinned `requirements.txt`
already installed:

```bash
python -m scripts.replay_house_district_map --inputs inputs --expected expected --output reproduced
python -m scripts.verify_house_district_map --inputs inputs --output reproduced
```

The replay runs six focused tests and literally recompiles all four outputs.
Repeat the replay command for an unchanged byte-and-mtime no-op. The independent
standard-library SHP/DBF verifier checks every native record and vertex without
the compiler's polygon decoder. Selected Python network/process APIs are blocked
during replay; this is not a universal operating-system sandbox.
