# Current participation-release audit

Reviewed November 8, 2026. [Overview](../README.md) |
[Methods](../METHODOLOGY.md) | [Complete data](DATA.md) |
[Remaining evidence](../REMAINING.md).

**The current publication passes its numerical, disclosure, download and
interface checks. It does not establish observed nationwide demographic turnout.**

| Area | Verified result |
|---|---|
| 2026 models | All 1,530 state/group decisions and 671 selected fractions match the qualified full-weight inputs. All 50 source states have overall estimates; D.C. lacks a sample. |
| Definitions and missingness | Native model classes remain separate from administrative ballots. Unknowns stay in the full state denominator; held rates and statistics are null, never zero. |
| Disclosure screens | No positive singly withheld complement is exposed within or across states. Ten single-held partitions are zero-case source absences. Gender and native race-disclosure restrictions remain. These screens are not anonymity or precision guarantees. |
| Complete data | Every member and checksum in the nine-member 2026 and thirteen-member historical ZIPs passes. All 436 existing complete-download routes remain. |
| Live interface | All 36 production configurations pass, including every 2026 decision and all 1,734 historical state/group values on desktop/mobile, no-JavaScript tables, failed/changed sources, tab races, maps and deep links. |

The additional audit made **9,092 checks**, reusing completed native verification
and offline reproductions rather than reopening respondents or private joint
cells. No new source or runtime defect was found in this increment. A legacy
landing checker assumed no new IDs; its baseline was corrected after independent
verification that every old link and ID survived. Runtime code did not change.
Methods remains a 106-word overview.

## Evidence limits that remain

Civic's field period, calibration, state representativeness and demographic
population denominators remain unqualified. Native income is not independently
verified household income; county context is not individual residence; race and
sex/gender categories are not silently harmonized with CPS.

The models do not identify observed staying home, original-cohort change,
eligible-group counts or survey-design confidence intervals. State rates are
not allocated to counties or precincts. Nationwide observed demographic turnout
and election-year precinct participation are still incomplete.

## Publication identity

Source/data revision `e5adde3`; live website
`5005b2eaa4e2afb3224e8870125ff03cebdc49fc`.
Native Pages run `42534719520`, artifact `13638962850`, deployment `7643472553`.
The downloaded artifact's actual content is 981,327,119 bytes and tar is
983,838,720 bytes, both below the strict one-billion-byte cap.
