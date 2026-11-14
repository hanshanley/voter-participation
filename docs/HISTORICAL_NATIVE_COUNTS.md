# Historical native administrative cells

This projection connects explicit **Ballots Cast** and **Registered Voters**
fields from already-held 2018 and 2020 general-election source queries.
It is separate from candidate returns, CPS estimates and the 2026 intake.
It does not create population turnout rates, demographic estimates, mapped
precincts or matched precinct histories.

The published projection contains 121,661 source cells in 39 separate
snapshots across 18 jurisdictions, including DC. All 51 jurisdiction decisions
are recorded for each of the two projection years. The 12,837 reported zero
cells remain zero; 115 unknown and 484 withheld cells retain their source
literals rather than becoming zero. These are counts of source cells, not
unique reporting units, people or ballots. Official and compiled versions can
overlap.

The complete package is immutable445000489, dataset88d51667 is separately
published and the existing-site reader is verified on desktop and mobile.
See the [complete download](DATA.md#historical-native-source-cells-and-marion-iowa)
and [source qualifications](../SOURCES.md#historical-native-administrative-cells-2018-and-2020).

## Source and election boundaries

The three complete, previously verified input components are:

| Component | Role |
|---|---|
| Official-state factual queries | Explicit Alabama statistical cells; the other preserved KS/PA products are not promoted from candidate returns |
| OpenElections statewide queries | Only explicitly labeled administrative rows, preserving every native field |
| OpenElections supplemental queries | Separate county/native-unit files, never silently merged with statewide alternatives |

General-election filename/year checks reject primary, special and mismatched
elections. A native office label and its actual native value must agree with
the compiled administrative field. Candidate votes are never substituted.
Administrative ballot styles, total rows, pooled units and voting-mode fields
remain source-defined; totals are not added to components or alternative files.

Registration is a separate stock. No stock, including a nonzero stock, becomes
a qualified denominator here. Native zero registration remains a source zero,
not an approved rate. Source clocks are not inferred from acquisition dates.
The source county/unit fields are not FIPS or election-boundary joins. Equal
labels across sources or years do not establish stable precinct identities.

The projection covers only 2018 and 2020. Its absence of selected administrative
cells in a state/year does not establish zero participation or missingness in
all other sources. It makes no missing-data classification for 2016, 2022,
2024 or the separate North Carolina registered-voter history.

## Reproduce

The full packet retains the three complete permitted component ZIPs,
their immutable hashes, processing code, tests, all state files and all 102
selection/withholding decisions. Original publisher document/application
templates and private respondents are not required or redistributed.
This replays a projection of already-verified factual queries, not a fresh
decoding of the excluded official workbook templates.

From the extracted download root, with Python3.9 or newer:

```bash
sh -eu REPRODUCE.txt
```

The producer checks each entire input component's exact bytes/hash before
streaming its complete factual query. It writes deterministic, source-separated
state shards and an all-jurisdiction index. A changed input or output directory
requires a new version; no source is requested by this projection. The exact
documented command selects `python3`, sets the startup-guard path, probes six
network/DNS/child denials, runs eight tests and regenerates all20 output files.
Both clean extracted-download executions match every output byte.
`dataset.json` contains the data identity. Its complete-download pointer is
publication metadata supplied only after immutable full-body verification,
not a self-authenticating claim inside an unpublished candidate.

## Viewer

`npm run test:historical-native` checks the shared browser reader.
`npm run test:count-contract` also retains the existing 2026 count contracts.
From the website checkout, with the already-built local site and the packet's dataset, run the real
dropdown/map pending-load regression using the existing Playwright Python
environment:

```bash
python3 scripts/verify-historical-native-navigation.py --base http://127.0.0.1:4399 \
  --dataset DATASET --download VERIFIED_PREDECESSOR_POINTER --output NEW_RECEIPT
```

This prepublication browser test explicitly routes the private candidate data;
it is not production certification. Final live acceptance uses the real
published catalog and complete package without candidate-route overrides.
The historical panel loads only when opened for a supported year, validates
immutable file hashes, limits displayed rows and cached state bodies, and
keeps source snapshot, native county field, measure and category explicit.
The complete state JSON and full numerical packet remain downloadable.
Unsupported scopes, source failures and withheld values never acquire
substitute values or new rates.
