"""Prepare reviewed Texas county reconciliation additions with shared PDF readers."""

import argparse
import copy
import gzip
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.compile_pdf_grids import compile_grids
from scripts.native_products import encoded, pin
from scripts.participation_intake.contract import observation_id
from scripts.pdf_measure_queries import queries
from scripts.verify_pdf_grids import verify


COUNT_RELEASE_TAG = "participation-texas-county-reconciliations-20261113-01"
COUNT_RELEASE_URL = (
    "https://github.com/hanshanley/margin_of_error/releases/download/"
    + COUNT_RELEASE_TAG
)
GEOMETRY = {
    "boundary_year": 2026,
    "counties": 254,
    "path": "data/county-results/20261105-house-02/geometry/TX.geojson.gz",
    "review_id": "provider-contextual-county-identities-20261109-01",
    "sha256": "6dec632a2eeb7ec21f9da35873e154636aa42be3681d6890e1ba23023061cad5",
    "uncompressed_sha256": "c068d086f11fcf9e91fed06581d521c0b3def8226cd4de182d27bd6d9425b25e",
    "url": (
        "https://raw.githubusercontent.com/hanshanley/margin_of_error/"
        "6b6b96caed4fa4f7c66fd206a64bd709310a69f2/"
        "data/county-results/20261105-house-02/geometry/TX.geojson.gz"
    ),
}


def grid(identifier, role, page, rows, fields, title_box, title, annotations=None):
    return {
        "id": identifier,
        "source_role": role,
        "page": page,
        "require": [{"reading_bbox": title_box, "decoded_text": title}],
        "rows": rows,
        "fields": fields,
        "source_annotations": annotations or {},
    }


def fields(label_band, measure, value_band, kind="count", allow_negative=False):
    return [
        {"id": "native_unit", "kind": "literal", "band": label_band},
        {
            "id": measure,
            "kind": kind,
            "band": value_band,
            **({"allow_negative": True} if allow_negative else {}),
        },
    ]


def source_recipe(name, source, role):
    if source.get("visual_only"):
        return {
            "id": source["source_id"],
            "filename": source["filename"],
            "url": source["url"],
            "pin": source["pin"],
            "state_code": "TX",
            "election_year": 2026,
            "retrieved_at_utc": source["retrieved_at_utc"],
            "native_updated_at": None,
            "expected_pages": 1,
            "redistribution": "factual_tables_only",
            "grids": [],
        }
    title_box, title = source["title"]
    common = {
        "source_role": role,
        "title_box": title_box,
        "title": title,
    }
    grids = [
        grid(
            name + "-status",
            role,
            1,
            [source["status"]["row"]],
            fields(
                source["status"]["label_band"],
                "status",
                source["status"]["value_band"],
                "literal",
            ),
            title_box,
            title,
        ),
        grid(
            name + "-county",
            role,
            1,
            [source["county_field"]["row"]],
            fields(
                source["county_field"]["label_band"],
                "county",
                source["county_field"]["value_band"],
                "literal",
            ),
            title_box,
            title,
        ),
        grid(
            name + "-registered",
            role,
            1,
            [source["registered"]["row"]],
            fields(
                source["registered"]["label_band"],
                "registered",
                source["registered"]["value_band"],
            ),
            title_box,
            title,
        ),
        grid(
            name + "-election-date",
            role,
            1,
            [source["election_date"]["row"]],
            fields(
                source["election_date"]["label_band"],
                "election_date",
                source["election_date"]["value_band"],
                "literal",
            ),
            title_box,
            title,
        ),
    ]
    for section in source["sections"]:
        annotations = copy.deepcopy(section.get("annotations", {}))
        grids.append(
            grid(
                name + "-" + section["id"],
                role,
                1,
                section["rows"],
                fields(
                    section["label_band"],
                    section["measure"],
                    section["value_band"],
                    section.get("kind", "count"),
                    section.get("allow_negative", False),
                ),
                title_box,
                title,
                annotations,
            )
        )
    return {
        "id": source["source_id"],
        "filename": source["filename"],
        "url": source["url"],
        "pin": source["pin"],
        "state_code": "TX",
        "election_year": 2026,
        "retrieved_at_utc": source["retrieved_at_utc"],
        "native_updated_at": None,
        "expected_pages": 1,
        "redistribution": "factual_tables_only",
        "grids": grids,
    }


SOURCES = {
    "liberty": {
        "source_id": "liberty-official-reconciliation-20261106",
        "filename": "liberty-official-reconciliation.pdf",
        "url": (
            "https://newtools.cira.state.tx.us/upload/page/12682/"
            "Election%20Reconciliation%20Official%20Totals%20November%203%202026%20signed.pdf"
        ),
        "pin": {
            "bytes": 312207,
            "sha256": "32bf1986c7283e5e933c832e27113a0e6064a13603e37a72de82fe2971d952bd",
        },
        "retrieved_at_utc": "2026-11-13T18:51:59.863798+00:00",
        "clock": "11/06/2026",
        "source_time_kind": "attestation_date",
        "title": (
            [150, 22, 550, 38],
            "Election Reconciliation - Official Totals",
        ),
        "status": {
            "row": [22, 38],
            "label_band": [33, 150],
            "value_band": [150, 550],
        },
        "county_field": {
            "row": [44, 65],
            "label_band": [80, 145],
            "value_band": [145, 200],
        },
        "registered": {
            "row": [66, 87],
            "label_band": [80, 145],
            "value_band": [145, 180],
        },
        "election_date": {
            "row": [66, 87],
            "label_band": [308, 370],
            "value_band": [370, 440],
        },
        "sections": [
            {
                "id": "voters",
                "rows": [[132, 165], [170, 202], [206, 231], [244, 277], [281, 314]],
                "label_band": [82, 145],
                "value_band": [145, 180],
                "measure": "voters",
            },
            {
                "id": "rejected",
                "rows": [[206, 231], [244, 277], [281, 314]],
                "label_band": [242, 305],
                "value_band": [305, 330],
                "measure": "rejected",
            },
            {
                "id": "counted",
                "rows": [[132, 165], [170, 202], [206, 231], [244, 277], [281, 314]],
                "label_band": [400, 465],
                "value_band": [465, 500],
                "measure": "ballots",
                "annotations": {
                    "native_column_headers": {
                        "ballots": "M. Total ballots counted (I+J+K+L)"
                    }
                },
            },
            {
                "id": "difference",
                "rows": [[370, 391]],
                "label_band": [83, 225],
                "value_band": [225, 250],
                "measure": "difference",
                "allow_negative": True,
            },
            {
                "id": "mail",
                "rows": [[626, 650], [665, 698], [703, 726]],
                "label_band": [83, 145],
                "value_band": [145, 175],
                "measure": "mail",
            },
            {
                "id": "provisional",
                "rows": [[628, 659]],
                "label_band": [243, 305],
                "value_band": [305, 330],
                "measure": "provisional",
            },
            {
                "id": "clock",
                "rows": [[540, 560]],
                "label_band": [250, 440],
                "value_band": [450, 520],
                "measure": "source_time",
                "kind": "literal",
            },
        ],
        "county": "Liberty County",
        "native_county": "Liberty",
        "fips": "48291",
        "registered_value": 60591,
        "ballots": 25700,
        "total_voters": 25869,
        "total_rejected": 169,
        "difference": 0,
        "status_literal": "Election Reconciliation - Official Totals",
        "measure_literal": "M. Total ballots counted (I+J+K+L)",
        "stage": "official",
        "clock_table": "liberty-clock",
        "clock_unit": "ee Haidusek Chambers",
        "clock_value": "11/06/2026",
        "registered_unit": "Registered Voters",
        "voters_unit": "E. Total voters\n(A+B+C+D)",
        "rejected_unit": "H. Total ballots\nrejected\n(F+G)",
        "ballots_unit": "M. Total ballots\ncounted\n(l+J+K+L)",
        "difference_unit": "N. Difference between voters and ballots\n(E-H-M)",
        "status_unit": "Prescribed by the Texas Secretary of State\nSection 127. 131 (f)",
        "county_unit": "County",
        "election_date_unit": "Election Date",
        "native_election_date": "11/03/2026",
        "mode_vector_note": (
            "Native mail voters 503 split into 8 rejected and 495 counted ballots while "
            "the other reported mode vectors reconcile. These are source-defined "
            "administrative measures, not individual-level mode allocation."
        ),
    },
    "hemphill": {
        "source_id": "hemphill-official-reconciliation-20261109",
        "filename": "hemphill-official-reconciliation.pdf",
        "url": (
            "https://newtools.cira.state.tx.us/upload/page/7666/"
            "110326%20GE%20-%20Reconciliation%20-%20Official%20Totals.pdf"
        ),
        "pin": {
            "bytes": 104377,
            "sha256": "85b6772c939fcbe8f15e207e5fc797c93499b658a5b5158c4640b841ceda871f",
        },
        "retrieved_at_utc": "2026-11-13T18:52:28.121255+00:00",
        "clock": "11/9/2026 at 4:30 p.m",
        "source_time_kind": "publication_timestamp",
        "title": (
            [200, 41, 550, 57],
            "Election Reconciliation - Official Totals",
        ),
        "status": {
            "row": [41, 52],
            "label_band": [41, 200],
            "value_band": [200, 550],
        },
        "county_field": {
            "row": [62, 82],
            "label_band": [86, 145],
            "value_band": [145, 200],
        },
        "registered": {
            "row": [83, 104],
            "label_band": [86, 145],
            "value_band": [145, 180],
        },
        "election_date": {
            "row": [83, 104],
            "label_band": [327, 360],
            "value_band": [360, 430],
        },
        "sections": [
            {
                "id": "voters",
                "rows": [[149, 177], [185, 212], [220, 239], [255, 283], [291, 318]],
                "label_band": [88, 145],
                "value_band": [145, 180],
                "measure": "voters",
            },
            {
                "id": "rejected",
                "rows": [[220, 239], [255, 283], [291, 318]],
                "label_band": [239, 295],
                "value_band": [295, 320],
                "measure": "rejected",
            },
            {
                "id": "counted",
                "rows": [[149, 177], [185, 212], [220, 239], [255, 283], [291, 318]],
                "label_band": [400, 450],
                "value_band": [450, 490],
                "measure": "ballots",
                "annotations": {
                    "native_column_headers": {
                        "ballots": "M. Total ballots counted (I+J+K+L)"
                    }
                },
            },
            {
                "id": "difference",
                "rows": [[371, 390]],
                "label_band": [88, 220],
                "value_band": [220, 245],
                "measure": "difference",
                "allow_negative": True,
            },
            {
                "id": "mail-sent",
                "rows": [[617, 640]],
                "label_band": [87, 145],
                "value_band": [145, 175],
                "measure": "mail_sent",
            },
            {
                "id": "mail-not-returned",
                "rows": [[653, 666]],
                "label_band": [87, 145],
                "value_band": [145, 158],
                "measure": "mail_not_returned",
            },
            {
                "id": "mail-late",
                "rows": [[666, 682]],
                "label_band": [87, 145],
                "value_band": [145, 158],
                "measure": "mail_late",
            },
            {
                "id": "mail-surrendered",
                "rows": [[690, 705]],
                "label_band": [87, 145],
                "value_band": [145, 158],
                "measure": "mail_surrendered",
            },
            {
                "id": "provisional",
                "rows": [[615, 644]],
                "label_band": [239, 295],
                "value_band": [295, 320],
                "measure": "provisional",
            },
            {
                "id": "clock",
                "rows": [[735, 757]],
                "label_band": [56, 123],
                "value_band": [123, 260],
                "measure": "source_time",
                "kind": "literal",
            },
        ],
        "county": "Hemphill County",
        "native_county": "Hemphill",
        "fips": "48211",
        "registered_value": 2305,
        "ballots": 1262,
        "total_voters": 1265,
        "total_rejected": 3,
        "difference": 3,
        "status_literal": "Election Reconciliation - Official Totals",
        "measure_literal": "M. Total ballots counted (I+J+K+L)",
        "stage": "official",
        "clock_table": "hemphill-clock",
        "clock_unit": "Posted on",
        "clock_value": "11/9/2026 at 4:30 p.m",
        "registered_unit": "Registered Voters",
        "voters_unit": "E. Total voters\n(A+B+C+D)",
        "rejected_unit": "H. Total ballots\nrejected\n(F+G)",
        "ballots_unit": "Total ballots\ncounted\n(l+J+K+L)",
        "difference_unit": "N. Difference between voters and ballots\n(E-H-M)",
        "status_unit": (
            "Prescribed by the Texas Secretary of State\nSection 127.131(1)"
        ),
        "county_unit": "County",
        "election_date_unit": "Date",
        "native_election_date": "11/03/2026",
        "conflict": {
            "code": "native_reconciliation_difference_disagrees",
            "repaired": False,
            "actual_native": 3,
            "computed": 0,
            "expression": "E-H-M",
        },
        "mode_vector_note": (
            "Native provisional voters submitted and rejected are both 3 while counted "
            "provisional ballots are 0. These source-defined measures remain separate; "
            "no individual or causal inference is made."
        ),
    },
    "refugio": {
        "source_id": "refugio-preliminary-reconciliation-20261103",
        "filename": "refugio-preliminary-reconciliation.pdf",
        "url": (
            "https://newtools.cira.state.tx.us/upload/page/12428/docs/"
            "2026%20-%20NOVEMBER%203/RESULTS/UNOFFICIAL/"
            "2026%20-%20NOVEMBER%203%20-%20PRELIMINARY%20ELECTION%20"
            "RECONCILIATION%20-%20UNOFFICIAL%20TOTALS%20-%20SIGNED.pdf"
        ),
        "pin": {
            "bytes": 240717,
            "sha256": "85d8885f99199593a9f4daad9082a7712b8eb579322b8cd4c980db07c09518b5",
        },
        "retrieved_at_utc": "2026-11-13T18:53:22.772494+00:00",
        "clock": "11/03/2026",
        "source_time_kind": "attestation_date",
        "title": (
            [150, 42, 550, 56],
            "Preliminary Election Reconciliation -Unofficial Totals",
        ),
        "status": {
            "row": [42, 56],
            "label_band": [0, 150],
            "value_band": [150, 550],
        },
        "county_field": {
            "row": [98, 112],
            "label_band": [64, 130],
            "value_band": [130, 190],
        },
        "registered": {
            "row": [124, 135],
            "label_band": [64, 135],
            "value_band": [135, 165],
        },
        "election_date": {
            "row": [123, 134],
            "label_band": [301, 380],
            "value_band": [380, 430],
        },
        "sections": [
            {
                "id": "voters",
                "rows": [[197, 217], [236, 256], [276, 296]],
                "label_band": [67, 130],
                "value_band": [130, 165],
                "measure": "voters",
            },
            {
                "id": "rejected",
                "rows": [[197, 226], [235, 266], [274, 314]],
                "label_band": [234, 300],
                "value_band": [300, 312],
                "measure": "rejected",
            },
            {
                "id": "counted",
                "rows": [[195, 215], [234, 254], [273, 304]],
                "label_band": [401, 468],
                "value_band": [468, 500],
                "measure": "ballots",
                "annotations": {
                    "native_column_headers": {
                        "ballots": "I. Total ballots counted (G+H)"
                    }
                },
            },
            {
                "id": "percent",
                "rows": [[372, 392]],
                "label_band": [302, 440],
                "value_band": [440, 510],
                "measure": "native_fraction",
                "kind": "literal",
            },
        ],
        "county": "Refugio County",
        "native_county": "REFUGIO",
        "fips": "48391",
        "registered_value": 4915,
        "ballots": 2448,
        "total_voters": 2448,
        "total_rejected": 0,
        "difference": 0,
        "status_literal": "Preliminary Election Reconciliation -Unofficial Totals",
        "measure_literal": "I. Total ballots counted (G+H)",
        "stage": "preliminary",
        "clock_table": "refugio-visual-controls",
        "clock_unit": "Attestation date",
        "clock_value": "11/03/2026",
        "registered_unit": "Registeredvoters",
        "voters_unit": "C.   Total voters\n(A+B)",
        "rejected_unit": "F.   Total ballots\nrejected or\npending\n(D+E)",
        "ballots_unit": "I.    Total ballots\ncounted\n(G+H)",
        "difference_unit": "J. Difference between voters and ballots (C-F-I)",
        "status_unit": "",
        "county_unit": "County",
        "election_date_unit": "Election Date",
        "native_election_date": "11 /03/2026",
        "mode_vector_note": (
            "Native voter and counted-ballot mode vectors differ: in-person voters 2,364 "
            "versus 2,354 counted, and mail voters 84 versus 94 counted, while both totals "
            "are 2,448. These are distinct administrative measures, not interchangeable "
            "mode allocations; no causal, switching or individual-flow inference is made."
        ),
    },
    "archer": {
        "visual_only": True,
        "visual_table": "archer-visual-controls",
        "source_id": "archer-official-reconciliation-20261110",
        "filename": "archer-official-reconciliation.pdf",
        "url": "https://www.co.archer.tx.us/upload/page/1336/Election%20Reconciliation.pdf",
        "pin": {
            "bytes": 203694,
            "sha256": "64adeb170b2457d1764452b3e2d284944a40980ad79f3d4a573b8d27aea2393a",
        },
        "retrieved_at_utc": "2026-11-13T18:51:59.863798+00:00",
        "clock": "11/10/26",
        "source_time_kind": "attestation_date",
        "county": "Archer County",
        "native_county": "Archer",
        "fips": "48009",
        "registered_value": 7158,
        "ballots": 4035,
        "total_voters": 4035,
        "total_rejected": 0,
        "difference": None,
        "status_literal": "Election Reconciliation - Official Totals",
        "measure_literal": "M. Total ballots counted (I+J+K+L)",
        "stage": "official",
        "clock_table": "archer-visual-controls",
        "clock_unit": "Attestation date",
        "clock_value": "11/10/26",
        "registered_unit": "Registered Voters",
        "voters_unit": "E. Total voters (A+B+C+D)",
        "rejected_unit": "H. Total ballots rejected (F+G)",
        "ballots_unit": "M. Total ballots counted (I+J+K+L)",
        "difference_unit": "N. Difference between voters and ballots (E-H-M)",
        "difference_parse": "literal",
        "status_unit": "Source status",
        "county_unit": "County",
        "election_date_unit": "Election Date",
        "native_election_date": "11/3/26",
        "mode_vector_note": (
            "Native voter and counted-ballot mode vectors agree for the reported early, "
            "Election Day, mail and provisional rows; this agreement is an accounting "
            "control, not individual-level identification. The native difference and "
            "percentage fields are blank; computed zero is not substituted as a printed fact."
        ),
    },
    "cameron": {
        "visual_only": True,
        "visual_table": "cameron-visual-controls",
        "source_id": "cameron-official-reconciliation-20261110",
        "filename": "cameron-official-reconciliation.pdf",
        "url": (
            "https://www.cameroncountytx.gov/elections/wp-content/uploads/2026/11/"
            "GN26-Official-Reconciliation-Report.pdf"
        ),
        "pin": {
            "bytes": 970493,
            "sha256": "38477616b9ee0ab4cf5defcc9f85737baccfd375745a1832e39cf9c0cfe842ef",
        },
        "retrieved_at_utc": "2026-11-13T18:51:59.863798+00:00",
        "clock": "11-10-26",
        "source_time_kind": "attestation_date",
        "county": "Cameron County",
        "native_county": "Cameron",
        "fips": "48061",
        "registered_value": 103976,
        "ballots": 103976,
        "total_voters": 104206,
        "total_rejected": 238,
        "difference": "-8",
        "difference_parse": "literal",
        "status_literal": "Election Reconciliation - Official Totals",
        "measure_literal": "M. Total ballots counted (I+J+K+L)",
        "stage": "official",
        "clock_table": "cameron-visual-controls",
        "clock_unit": "Attestation date",
        "clock_value": "11-10-26",
        "registered_unit": "Registered Voters",
        "voters_unit": "E. Total voters (A+B+C+D)",
        "rejected_unit": "H. Total ballots rejected (F+G)",
        "ballots_unit": "M. Total ballots counted (I+J+K+L)",
        "difference_unit": "N. Difference between voters and ballots (E-H-M)",
        "status_unit": "Source status",
        "county_unit": "County",
        "election_date_unit": "Election Date",
        "native_election_date": "11-3-26",
        "mode_vector_note": (
            "Native voter and counted-ballot mode vectors differ and the form attributes "
            "the retained -8 reconciliation to clerical error, improper check-ins and "
            "fleeing voters. The candidate does not infer individual behavior or repair "
            "any component. Native Registered Voters 103,976 exactly equals M. Total "
            "ballots counted 103,976, while E. Total voters 104,206 exceeds that "
            "registration stock by 230. This is a retained native source anomaly, not a "
            "duplicated transcription; registration remains unqualified context and no "
            "100% turnout inference, analytical rate or repair is made."
        ),
    },
    "nolan": {
        "visual_only": True,
        "visual_table": "nolan-visual-controls",
        "source_id": "nolan-official-reconciliation-20261109",
        "filename": "nolan-official-reconciliation.pdf",
        "url": "https://newtools.cira.state.tx.us/upload/page/0503/Reconciliation%2011032026.pdf",
        "pin": {
            "bytes": 237107,
            "sha256": "b8a04016828d668260b62bc836eab6a5897a5c823594906c6bd8cd54dea93168",
        },
        "retrieved_at_utc": "2026-11-13T18:51:59.863798+00:00",
        "clock": "11.9.26",
        "source_time_kind": "attestation_date",
        "county": "Nolan County",
        "native_county": "Nolan",
        "fips": "48353",
        "registered_value": 9085,
        "ballots": 3781,
        "total_voters": 3788,
        "total_rejected": 5,
        "difference": 2,
        "status_literal": "Election Reconciliation - Official Totals",
        "measure_literal": "M. Total ballots counted (I+J+K+L)",
        "stage": "official",
        "clock_table": "nolan-visual-controls",
        "clock_unit": "Attestation date",
        "clock_value": "11.9.26",
        "registered_unit": "Registered Voters",
        "voters_unit": "E. Total voters (A+B+C+D)",
        "rejected_unit": "H. Total ballots rejected (F+G)",
        "ballots_unit": "M. Total ballots counted (I+J+K+L)",
        "difference_unit": "N. Difference between voters and ballots (E-H-M)",
        "status_unit": "Source status",
        "county_unit": "County",
        "election_date_unit": "Election Date",
        "native_election_date": "11.03.26",
        "mode_vector_note": (
            "The form retains one early-voting and one Election Day fleeing-voter "
            "difference. These source explanations and mode vectors are accounting "
            "context, not causal or individual-level identification."
        ),
    },
    "moore": {
        "visual_only": True,
        "visual_table": "moore-visual-controls",
        "source_id": "moore-preliminary-reconciliation-20261103",
        "filename": "moore-preliminary-reconciliation.pdf",
        "url": (
            "https://newtools.cira.state.tx.us/upload/page/4507/2026/"
            "preliminary_election_reconcillationunofficial_totals.pdf"
        ),
        "pin": {
            "bytes": 85503,
            "sha256": "c6a880809a58b051c314401463bcb61ea12375675945b2e140cefcb215c22e1b",
        },
        "retrieved_at_utc": "2026-11-13T18:52:50.743727+00:00",
        "clock": "11/03/2026",
        "source_time_kind": "attestation_date",
        "county": "Moore County",
        "native_county": "MOORE",
        "fips": "48341",
        "registered_value": 10254,
        "ballots": 4164,
        "total_voters": 4197,
        "total_rejected": 44,
        "difference": 11,
        "status_literal": "Preliminary Election Reconciliation – Unofficial Totals",
        "measure_literal": "I. Total ballots counted (G+H)",
        "stage": "preliminary",
        "clock_table": "moore-visual-controls",
        "clock_unit": "Attestation date",
        "clock_value": "11/03/2026",
        "registered_unit": "Registered Voters",
        "voters_unit": "C. Total voters (A+B)",
        "rejected_unit": "F. Total ballots rejected or pending (D+E)",
        "ballots_unit": "I. Total ballots counted (G+H)",
        "difference_unit": "J. Difference between voters and ballots (C-F-I)",
        "status_unit": "Source status",
        "county_unit": "County",
        "election_date_unit": "Election Date",
        "native_election_date": "11-03-2026",
        "conflict": {
            "code": "native_reconciliation_difference_disagrees",
            "repaired": False,
            "actual_native": 11,
            "computed": -11,
            "expression": "C-F-I",
        },
        "mode_vector_note": (
            "Native in-person voters 4,088 differ from 4,055 counted ballots while mail "
            "voters and counted mail both equal 109. Source notes retain accepted and "
            "limited-ballot context; no mode allocation or causal inference is made."
        ),
    },
    "wise": {
        "visual_only": True,
        "visual_table": "wise-visual-controls",
        "source_id": "wise-preliminary-reconciliation-20261104",
        "filename": "wise-preliminary-reconciliation.pdf",
        "url": (
            "https://www.co.wise.tx.us/DocumentCenter/View/8027/"
            "Preliminary-Election-Reconciliation--Unofficial-Totals?bidId="
        ),
        "pin": {
            "bytes": 324221,
            "sha256": "e3e2de27be0f03d8928c5faf846be152eea6ba1435bbe31b53c44e7b9f552a22",
        },
        "retrieved_at_utc": "2026-11-13T18:52:50.743727+00:00",
        "clock": "11/04/2026",
        "source_time_kind": "attestation_date",
        "county": "Wise County",
        "native_county": "Wise",
        "fips": "48497",
        "registered_value": 59881,
        "ballots": 31186,
        "total_voters": 31494,
        "total_rejected": 299,
        "difference": 9,
        "status_literal": "Preliminary Election Reconciliation – Unofficial Totals",
        "measure_literal": "I. Total ballots counted (G+H)",
        "stage": "preliminary",
        "clock_table": "wise-visual-controls",
        "clock_unit": "Attestation date",
        "clock_value": "11/04/2026",
        "registered_unit": "Registered Voters",
        "voters_unit": "C. Total voters (A+B)",
        "rejected_unit": "F. Total ballots rejected or pending (D+E)",
        "ballots_unit": "I. Total ballots counted (G+H)",
        "difference_unit": "J. Difference between voters and ballots (C-F-I)",
        "status_unit": "Source status",
        "county_unit": "County",
        "election_date_unit": "Election Date",
        "native_election_date": "Nov 3, 2026",
        "mode_vector_note": (
            "Native in-person voters 30,726 versus 30,445 counted and mail voters 768 "
            "versus 741 counted are distinct administrative vectors. Rejected/pending "
            "and final-board notes are retained; no causal or mode-allocation inference "
            "is made."
        ),
    },
}


def append_visual_controls(facts, transcription):
    if transcription.get("contract") != "participation.reviewed_visual_pdf_transcriptions.v1":
        raise ValueError("Reviewed visual transcription inventory is required")
    method = "visually_reviewed_source_image_transcription"
    seen = set()
    for reviewed in transcription["sources"]:
        matches = [
            (name, source)
            for name, source in SOURCES.items()
            if source["source_id"] == reviewed["source_id"]
        ]
        products = [
            item for item in facts["products"] if item["source"]["id"] == reviewed["source_id"]
        ]
        if len(matches) != 1 or len(products) != 1 or reviewed["source_id"] in seen:
            raise ValueError("Visual source inventory differs")
        seen.add(reviewed["source_id"])
        name, configured = matches[0]
        source = products[0]["source"]
        if source["pin"] != reviewed["source_pin"]:
            raise ValueError("Visual transcription is bound to another original")
        rows = []
        for number, item in enumerate(reviewed["rows"], 1):
            value = item["value"]
            rows.append(
                {
                    "row": number,
                    "cells": {
                        "native_unit": {
                            "value": item["native_unit"],
                            "native_status": "literal",
                            "reviewed_text": item["native_unit"],
                            "reading_bbox": item.get("label_bbox", reviewed["page_bbox"]),
                            "source_method": method,
                        },
                        item["measure"]: {
                            "value": value,
                            "native_status": item.get(
                                "native_status",
                                "reported" if type(value) is int else "literal",
                            ),
                            "reviewed_text": item["literal"],
                            "reading_bbox": item.get("value_bbox", reviewed["page_bbox"]),
                            "source_method": method,
                        },
                    },
                }
            )
        products[0]["tables"].append(
            {
                "id": configured.get("visual_table", name + "-visual-controls"),
                "source_page": 1,
                "source_role": (
                    "unofficial_administrative_measures_not_candidate_returns"
                    if configured["stage"] == "preliminary"
                    else "native_registration_ballot_reported_turnout_statistics"
                ),
                "source_annotations": {
                    "source_method": method,
                    "reviewed_image_pin": source["pin"],
                    "visual_header_review_evidence": reviewed[
                        "visual_header_review_evidence"
                    ],
                },
                "rows": rows,
                "automatic_geographic_or_model_qualification": False,
            }
        )
    expected = {
        source["source_id"]
        for source in SOURCES.values()
        if source.get("visual_only") or source["source_id"] == SOURCES["refugio"]["source_id"]
    }
    if seen != expected:
        raise ValueError("Every image fact source needs one complete reviewed transcription")


def table_row(facts, source_id, table_id, native_unit, measure):
    products = [item for item in facts["products"] if item["source"]["id"] == source_id]
    if len(products) != 1:
        raise ValueError("Source identity is ambiguous")
    tables = [item for item in products[0]["tables"] if item["id"] == table_id]
    if len(tables) != 1:
        raise ValueError("Table identity is ambiguous")
    rows = [
        row
        for row in tables[0]["rows"]
        if " ".join(row["cells"]["native_unit"]["value"].split())
        == " ".join(native_unit.split())
    ]
    if len(rows) != 1 or measure not in rows[0]["cells"]:
        raise ValueError(f"Native row is absent: {source_id} {table_id} {native_unit}")
    return rows[0]["cells"][measure]["value"]


def fact_table(name, field):
    source = SOURCES[name]
    if source.get("visual_only"):
        return source["visual_table"]
    if field == "clock":
        return source["clock_table"]
    if field == "difference" and name == "refugio":
        return source["clock_table"]
    return name + "-" + field


def source_fields(name, facts):
    source = SOURCES[name]
    prefix = name + "-"
    values = {
        "ballots": table_row(
            facts, source["source_id"], fact_table(name, "counted"), source["ballots_unit"], "ballots"
        ),
        "registered": table_row(
            facts,
            source["source_id"],
            fact_table(name, "registered"),
            source["registered_unit"],
            "registered",
        ),
        "total_voters": table_row(
            facts, source["source_id"], fact_table(name, "voters"), source["voters_unit"], "voters"
        ),
        "total_rejected": table_row(
            facts,
            source["source_id"],
            fact_table(name, "rejected"),
            source["rejected_unit"],
            "rejected",
        ),
        "difference": table_row(
            facts,
            source["source_id"],
            fact_table(name, "difference"),
            source["difference_unit"],
            "difference",
        ),
        "source_time_literal": table_row(
            facts,
            source["source_id"],
            fact_table(name, "clock"),
            source["clock_unit"],
            "source_time",
        ),
        "source_time_kind": source["source_time_kind"],
        "native_status_literal": table_row(
            facts,
            source["source_id"],
            fact_table(name, "status"),
            source["status_unit"],
            "status",
        ),
        "source_county": table_row(
            facts, source["source_id"], fact_table(name, "county"), source["county_unit"], "county"
        ),
        "native_election_date": table_row(
            facts,
            source["source_id"],
            fact_table(name, "election-date"),
            source["election_date_unit"],
            "election_date",
        ),
        "source_method": (
            "decoded_PDF_characters_with_separately_reviewed_visual_controls"
            if name == "refugio"
            else "visually_reviewed_source_image_transcription"
            if source.get("visual_only")
            else "decoded_PDF_characters"
        ),
    }
    expected = {
        "ballots": source["ballots"],
        "registered": source["registered_value"],
        "total_voters": source["total_voters"],
        "total_rejected": source["total_rejected"],
        "difference": source["difference"],
        "source_time_literal": source["clock_value"],
        "native_status_literal": source["status_literal"],
        "source_county": source["native_county"],
        "native_election_date": source["native_election_date"],
    }
    if any(values[key] != value for key, value in expected.items()):
        raise ValueError(f"Reviewed Texas source control differs: {name}")
    return values


def observation(name, facts):
    source = SOURCES[name]
    fields_value = source_fields(name, facts)
    geography_id = "native:TX:" + source["fips"]
    election_id = "texas-2026-11-03-general"
    measure_id = "native-counted-ballots"
    identity = observation_id(
        source["source_id"], election_id, geography_id, measure_id, "source_defined"
    )
    county_id = "native:TX:" + source["fips"]
    status = source["status_literal"]
    notes = [
        "Native county election-reconciliation counted ballots, not candidate votes, unique people or observed staying home.",
        "Registered voters remain source context; analytical rates and demographic allocations are not qualified.",
        "The source's total voters, rejected or pending ballots and reconciliation difference remain separate controls and are not added to counted ballots.",
        "County identity uses the unchanged complete254-county Census context; the native form does not print a FIPS code.",
        "No precinct geometry, statewide total, switching, persuasion or individual behavior is inferred.",
    ]
    if source["stage"] == "preliminary":
        notes.append(
            "Preliminary unofficial status is retained; no finality, certification or completed-counting claim follows."
        )
    else:
        notes.append(
            "The form's Official Totals label is retained; it does not qualify a registration denominator or individual-level behavior."
        )
    notes.append(source["mode_vector_note"])
    time_note = (
        "Attested on " + source["clock_value"] + "; this signer date is provenance, not a count-as-of update."
        if source["source_time_kind"] == "attestation_date"
        else "Posted on " + source["clock_value"] + "; this publication timestamp is provenance, not a count-as-of update."
    )
    notes.append(time_note)
    conflicts = [copy.deepcopy(source["conflict"])] if source.get("conflict") else []
    if conflicts:
        conflict = conflicts[0]
        notes.append(
            "Native printed reconciliation difference "
            + str(conflict["actual_native"])
            + " disagrees with computed "
            + conflict["expression"]
            + "="
            + str(conflict["computed"])
            + "; retained unrepaired."
        )
    label = (
        "Native counted ballots (preliminary reconciliation)"
        if source["stage"] == "preliminary"
        else "Native counted ballots (official reconciliation)"
    )
    view = {
        "ballots": source["ballots"],
        "cast_ballot_count_qualified": False,
        "complete_download_url": COUNT_RELEASE_URL + "/complete-analysis.zip",
        "county": source["county"],
        "county_fips": source["fips"],
        "county_id": county_id,
        "denominator": None,
        "denominator_basis": "native_registered_voters_status_and_cutoff_unqualified",
        "geography_level": "county",
        "maps_approved": True,
        "native_printed_pct": None,
        "native_record": fields_value,
        "official": source["stage"] == "official",
        "participation_measure_kind": "native_counted_ballots",
        "participation_measure_label": label,
        "participation_measure_literal": source["measure_literal"],
        "quality": notes,
        "reference_geometry": GEOMETRY,
        "registered": source["registered_value"],
        "reported_pct": None,
        "reported_units": None,
        "review_id": COUNT_RELEASE_TAG,
        "source": (
            "County-published preliminary " + source["county"] + " election reconciliation"
            if source["stage"] == "preliminary"
            else "County-published official " + source["county"] + " election reconciliation"
        ),
        "source_mode": "source_defined_native_reconciliation",
        "source_reporting_label": "; ".join(notes),
        "source_status_literal": status,
        "source_time_kind": source["source_time_kind"],
        "source_time_literal": source["clock_value"],
        "source_update_label": None,
        "source_update_timezone": None,
        "source_url": source["url"],
        "state_code": "TX",
        "total_units": None,
        "unique_voter_count_qualified": False,
        "year": 2026,
    }
    return {
        "contract": "participation.observation.v1",
        "id": identity,
        "election": {
            "id": election_id,
            "year": 2026,
            "date": "2026-11-03",
            "type": "general",
            "qualification": "native",
        },
        "geography": {
            "id": geography_id,
            "state_code": "TX",
            "level": "county",
            "name": source["county"],
            "parent_id": None,
            "join": {
                "status": "approved",
                "reference_id": GEOMETRY["sha256"],
                "feature_key": source["fips"],
                "evidence": (
                    "Literal official county name matched to unchanged complete254-county "
                    "Census context; no native FIPS claim."
                ),
            },
        },
        "measure": {
            "id": measure_id,
            "kind": "participation_reported",
            "unit": "source_reported_counted_ballots",
            "mode": "source_defined",
            "literal": source["measure_literal"],
        },
        "count": {
            "status": "reported",
            "value": source["ballots"],
            "literal": source["ballots"],
        },
        "denominator": None,
        "source_clock": {"literal": None, "timezone": None},
        "reporting_status": {
            "literal": status,
            "complete": None,
            "reported_units": None,
            "total_units": None,
        },
        "source": {
            "id": source["source_id"],
            "url": source["url"],
            "input_sha256": source["pin"]["sha256"],
            "classification": "public_aggregate",
            "selector": {
                "table_id": name + "-counted",
                "native_unit": source["ballots_unit"],
                "measure": "ballots",
            },
            "fields": fields_value,
        },
        "quality": {"conflicts": conflicts, "notes": notes},
        "view": view,
    }


def binding(name, record, table, native_unit, measure, path, parse="count", **extra):
    source = SOURCES[name]
    result = {
        "input": "facts",
        "compression": "gzip",
        "source_id": source["source_id"],
        "table_id": table,
        "record": {"id": record["id"]},
        "native_unit": native_unit,
        "measure": measure,
        "path": path,
        "parse": parse,
        "reading_whitespace_normalized": True,
        **extra,
    }
    if source["stage"] == "preliminary":
        result["administrative_measure_review_evidence"] = (
            "The official county reconciliation reports administrative voter, rejected or "
            "pending and counted-ballot measures, not candidate returns."
        )
    return result


def bindings(name, record):
    source = SOURCES[name]
    prefix = name + "-"
    measure_evidence = (
        "The official county form directly labels the selected total as counted ballots; "
        "no candidate totals or registration counts are substituted."
    )
    rows = []
    for path in (
        "count.value",
        "count.literal",
        "view.ballots",
        "source.fields.ballots",
        "view.native_record.ballots",
    ):
        extra = (
            {}
            if source.get("visual_only")
            else {
                "accepted_measure_literal": source["measure_literal"],
                "native_measure_header": source["measure_literal"],
                "same_measure_review_evidence": measure_evidence,
            }
        )
        rows.append(
            binding(
                name,
                record,
                fact_table(name, "counted"),
                source["ballots_unit"],
                "ballots",
                path,
                **extra,
            )
        )
    direct = [
        (
            fact_table(name, "registered"),
            source["registered_unit"],
            "registered",
            ["view.registered", "source.fields.registered", "view.native_record.registered"],
            "count",
        ),
        (
            fact_table(name, "voters"),
            source["voters_unit"],
            "voters",
            ["source.fields.total_voters", "view.native_record.total_voters"],
            "count",
        ),
        (
            fact_table(name, "rejected"),
            source["rejected_unit"],
            "rejected",
            ["source.fields.total_rejected", "view.native_record.total_rejected"],
            "count",
        ),
        (
            fact_table(name, "difference"),
            source["difference_unit"],
            "difference",
            ["source.fields.difference", "view.native_record.difference"],
            source.get("difference_parse", "count"),
        ),
        (
            fact_table(name, "clock"),
            source["clock_unit"],
            "source_time",
            [
                "source.fields.source_time_literal",
                "view.native_record.source_time_literal",
                "view.source_time_literal",
            ],
            "literal",
        ),
        (
            fact_table(name, "status"),
            source["status_unit"],
            "status",
            [
                "reporting_status.literal",
                "view.source_status_literal",
                "source.fields.native_status_literal",
                "view.native_record.native_status_literal",
            ],
            "literal",
        ),
        (
            fact_table(name, "county"),
            source["county_unit"],
            "county",
            ["source.fields.source_county", "view.native_record.source_county"],
            "literal",
        ),
        (
            fact_table(name, "election-date"),
            source["election_date_unit"],
            "election_date",
            [
                "source.fields.native_election_date",
                "view.native_record.native_election_date",
            ],
            "literal",
        ),
    ]
    for table, unit, measure, paths, parse in direct:
        for path in paths:
            rows.append(binding(name, record, table, unit, measure, path, parse=parse))
    for path in ("source.url", "view.source_url"):
        source_binding = {
                "input": "facts",
                "compression": "gzip",
                "source_id": source["source_id"],
                "table_id": fact_table(name, "status"),
                "record": {"id": record["id"]},
                "value_scope": "source",
                "value_path": "url",
                "path": path,
                "parse": "literal",
            }
        if source["stage"] == "preliminary":
            source_binding["administrative_measure_review_evidence"] = (
                "The official county reconciliation reports administrative counted-ballot "
                "measures, not candidate returns."
            )
        rows.append(source_binding)
    sha_binding = {
            "input": "facts",
            "compression": "gzip",
            "source_id": source["source_id"],
            "table_id": fact_table(name, "status"),
            "record": {"id": record["id"]},
            "value_scope": "source",
            "value_path": "pin.sha256",
            "path": "source.input_sha256",
            "parse": "literal",
        }
    if source["stage"] == "preliminary":
        sha_binding["administrative_measure_review_evidence"] = (
            "The official county reconciliation reports administrative counted-ballot "
            "measures, not candidate returns."
        )
    rows.append(sha_binding)
    return rows


def prepare_baseline(source, destination, descriptor):
    if destination.exists():
        raise ValueError("Use a fresh baseline output directory")
    shutil.copytree(source, destination)
    (destination / "dataset.json").write_bytes(encoded(descriptor))


def prepare(args):
    output = args.output.resolve()
    if output.exists():
        raise ValueError("Use a fresh Texas preparation output directory")
    output.mkdir(parents=True)
    geometry_body = args.geometry.read_bytes()
    if pin(geometry_body) != {
        "bytes": args.geometry.stat().st_size,
        "sha256": GEOMETRY["sha256"],
    }:
        raise ValueError("Approved Texas county geometry pin changed")
    recipe = {
        "contract": "participation.reviewed_pdf_grids.v1",
        "sources": [
            source_recipe(
                name,
                source,
                (
                    "unofficial_administrative_measures_not_candidate_returns"
                    if source["stage"] == "preliminary"
                    else "native_registration_ballot_reported_turnout_statistics"
                ),
            )
            for name, source in SOURCES.items()
        ],
    }
    facts = compile_grids(recipe, args.originals)
    verification = verify(recipe, facts, args.originals)
    if not verification["passed"]:
        raise ValueError("Independent PDF decoder disagrees")
    transcription = json.loads(args.visual_transcription.read_bytes())
    append_visual_controls(facts, transcription)
    records = [observation(name, facts) for name in SOURCES]
    if len({record["id"] for record in records}) != len(records):
        raise ValueError("Repeated Texas observation identity")
    complete_queries = queries(facts)
    summary = {
        "contract": "participation.texas_county_reconciliation_summary.v1",
        "passed": True,
        "whole_state_product_qualified": False,
        "selected_counties": len(records),
        "selected_county_fips": [SOURCES[name]["fips"] for name in SOURCES],
        "explicit_remaining_county_gaps": 254 - 1 - len(records),
        "existing_harris_preserved": True,
        "candidate_votes_not_used_as_participation": True,
        "complete_selected_count_and_control_facts": True,
        "not_a_claim_of_all_form_fields": True,
        "blank_percent_and_explanation_fields_outside_selected_query_remain_unpromoted": True,
        "factual_only_replay_does_not_claim_original_pdf_reextraction": True,
        "analytical_rates_qualified": 0,
        "new_precinct_geometries": 0,
        "behavioral_model_changes": 0,
        "independent_pdf_verification": verification,
        "source_access_dispositions": pin(args.source_dispositions.read_bytes()),
        "approved_reference_geometry": pin(geometry_body),
    }
    supplied = output / "supplied" / "texas-reconciliations"
    supplied.mkdir(parents=True)
    fact_body = gzip.compress(encoded(facts), mtime=0)
    inputs = {
        "facts": fact_body,
        "snapshot": encoded(records),
        "complete_queries": encoded(complete_queries),
        "source_summary": encoded(summary),
        "visual_review": encoded(transcription),
        "geometry": geometry_body,
    }
    for name, body in inputs.items():
        (supplied / name).write_bytes(body)
    counts_descriptor = json.loads(args.counts_descriptor.read_bytes())
    native_descriptor = json.loads(args.native_descriptor.read_bytes())
    prepare_baseline(args.counts_baseline, output / "baseline", counts_descriptor)
    prepare_baseline(args.native_baseline, output / "native-baseline", native_descriptor)
    tx_state_file = counts_descriptor["files"]["states/TX.json.gz"]
    tx_state = json.loads(
        gzip.decompress((output / "baseline" / "states/TX.json.gz").read_bytes())
    )
    native_index = json.loads((output / "native-baseline" / "index.json").read_bytes())
    new_ids = [record["id"] for record in records]
    views = {}
    append_modes = {"available", "official", "uf_vap", "uf_vep"}
    for mode, frame in tx_state["views"].items():
        views[mode] = {}
        for partition in ("counties", "precincts", "nongeographic"):
            views[mode][partition] = {
                "before": frame[partition],
                "append": new_ids if mode in append_modes and partition == "counties" else [],
            }
    county_modes = {}
    for mode in sorted(append_modes):
        current = native_index["county_bindings"]["TX"][mode]
        county_modes[mode] = {
            "before": pin(encoded(current)),
            "append": new_ids,
        }
    fact_bindings = []
    for name, record in zip(SOURCES, records):
        fact_bindings.extend(bindings(name, record))
    registry = {
        "contract": "participation.routine_batch.v1",
        "baseline_version": counts_descriptor["version"],
        "native_baseline_version": native_descriptor["version"],
        "sources": [
            {
                "id": "texas-reconciliations",
                "target": "counts_addition",
                "baseline_source_ids": [],
                "references": {
                    "assets": {
                        GEOMETRY["sha256"]: {
                            "bytes": len(geometry_body),
                            "sha256": GEOMETRY["sha256"],
                            "key_path": "properties.key",
                            "input": "geometry",
                            "approval_evidence": (
                                "Unchanged complete254-county 2026 Census contextual reference; "
                                "literal county names and feature keys were separately reviewed."
                            ),
                        }
                    }
                },
                "addition": {
                    "contract": "participation.reviewed_count_addition.v1",
                    "baseline_shard": tx_state_file,
                    "records": {record["id"]: pin(encoded(record)) for record in records},
                    "source_scope_review_evidence": COUNT_RELEASE_URL,
                    "views": views,
                    "county_reference": {
                        "contract": "participation.reviewed_county_reference_addition.v1",
                        "review_evidence": (
                            "Literal official county names are explicitly matched to unchanged "
                            "2026 Census county feature keys; no geometry or native-FIPS claim."
                        ),
                        "baseline_index": pin(
                            (output / "native-baseline" / "index.json").read_bytes()
                        ),
                        "modes": county_modes,
                    },
                },
                "spec": {
                    "id": "reviewed-texas-county-reconciliations",
                    "adapter": "canonical_json",
                    "classification": "public_aggregate",
                    "primary_input": "snapshot",
                    "inputs": {
                        name: {
                            "url": COUNT_RELEASE_URL + "/" + name,
                            "publication": "original",
                            "pin": pin(body),
                        }
                        for name, body in inputs.items()
                    },
                    "election": {
                        "id": "texas-2026-11-03-general",
                        "year": 2026,
                        "date": "2026-11-03",
                        "type": "general",
                        "qualification": "native",
                    },
                    "geography": {"state_code": "TX"},
                    "expected_rows": len(records),
                    "format": {
                        "source_ids": [source["source_id"] for source in SOURCES.values()],
                        "fact_bindings": fact_bindings,
                    },
                    "review_evidence": COUNT_RELEASE_URL,
                },
            }
        ],
    }
    (output / "registry.json").write_bytes(encoded(registry))
    (output / "expected-observations.json").write_bytes(encoded(records))
    (output / "recipe.json").write_bytes(encoded(recipe))
    (output / "facts.json.gz").write_bytes(fact_body)
    (output / "complete-queries.json").write_bytes(encoded(complete_queries))
    (output / "independent-verification.json").write_bytes(encoded(verification))
    (output / "source-summary.json").write_bytes(encoded(summary))
    reference = output / "reference-geometry"
    reference.mkdir()
    (reference / "TX.geojson.gz").write_bytes(geometry_body)
    print(
        json.dumps(
            {
                "records": len(records),
                "factual_query_rows": len(complete_queries["rows"]),
                "fact_bindings": len(fact_bindings),
                "output": str(output),
            },
            sort_keys=True,
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--originals", type=Path, required=True)
    parser.add_argument("--visual-transcription", type=Path, required=True)
    parser.add_argument("--source-dispositions", type=Path, required=True)
    parser.add_argument("--geometry", type=Path, required=True)
    parser.add_argument("--counts-baseline", type=Path, required=True)
    parser.add_argument("--counts-descriptor", type=Path, required=True)
    parser.add_argument("--native-baseline", type=Path, required=True)
    parser.add_argument("--native-descriptor", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    prepare(parser.parse_args())


if __name__ == "__main__":
    main()
