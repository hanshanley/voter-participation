"""Optional atomic all-state transition refresh from accepted public inputs."""

from contextlib import redirect_stdout
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import tempfile

from scripts import statewide_house_transitions as model
from scripts.verify_statewide_house_transitions import verify


REVIEW_PATH = "data/statewide-house-transitions/20261127-01/review.json"
REVIEW_CONTRACT = "participation.statewide_house_transition_review.v1"
PREFIX = "house/statewide-transitions/"


def encoded(value):
    return (json.dumps(value, separators=(",", ":"), sort_keys=True, allow_nan=False) + "\n").encode()


def pin(body):
    return dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())


def compressed(body):
    value = gzip.compress(body, compresslevel=9, mtime=0)
    return value[:9] + bytes([3]) + value[10:]


def validate_review(value):
    if (value.get("contract") != REVIEW_CONTRACT or value.get("states") != 50
            or value.get("categories") != list(model.CHOICES)
            or value.get("source_models_refitted") is not False
            or value.get("individual_histories_identified") is not False
            or value.get("legacy_behavioral_gates_changed") is not False):
        raise ValueError("Unqualified statewide House-transition review")
    source = value["benchmark_2024"]
    body = source["csv_utf8"].encode()
    if (source["url"] != "https://election.lab.ufl.edu/data-downloads/turnoutdata/Turnout_2024G_v0.4.csv"
            or pin(body) != {key:source[key] for key in ("bytes","sha256")}):
        raise ValueError("Changed 2024 turnout benchmark")
    model.parse_turnout(body, 2024)
    return value


def refresh(review, snapshot, congress_body, model_files, count_snapshot_body):
    validate_review(review)
    uf = snapshot.get("uf_turnout", {}).get("data")
    if uf is None:
        raise ValueError("No accepted UF 2026 ballot/population benchmark")
    csv26 = uf["originals"]["csv"].encode()
    if pin(csv26) != {key:uf["sources"]["csv"][key] for key in ("bytes","sha256")}:
        raise ValueError("UF 2026 original differs from its accepted pin")
    model.parse_turnout(csv26, 2026)
    files = {
        "UF-2024.csv":review["benchmark_2024"]["csv_utf8"].encode(),
        "UF-2026.csv":csv26, "congressional.json.gz":congress_body,
        "runtime.json":encoded(dict(version=hashlib.sha256(congress_body+csv26).hexdigest(),
            checked_at=snapshot.get("checked_at"), reference_kind="accepted_house_and_turnout_inputs")),
    }
    for profile in model.PROFILES:
        files[f"source-{profile}.json.gz"] = model_files["house/statewide-source/"+profile+".json.gz"]
    with tempfile.TemporaryDirectory(prefix="statewide-house-transitions-") as temporary:
        root = Path(temporary); inputs = root / "inputs"; inputs.mkdir()
        for name, body in files.items():
            (inputs/name).write_bytes(body)
        output = root / "product"
        with redirect_stdout(io.StringIO()):
            model.build(inputs, output)
        verification = verify(inputs, output)
        viewer_body = (output/"viewer-data.json").read_bytes()
        viewer = json.loads(viewer_body)
        artifacts = {
            PREFIX+"viewer.json.gz":compressed(viewer_body),
            PREFIX+"summary.json":(output/"summary.json").read_bytes(),
            PREFIX+"complete-state-comparisons.csv":(output/"complete-state-comparisons.csv").read_bytes(),
            PREFIX+"verification.json":encoded(verification),
        }
        with gzip.open(output/"complete-sensitivity.csv.gz", "rt", newline="") as source:
            reader=csv.DictReader(source);current=None;stream=None;writer=None
            for row in reader:
                if row["state_code"] != current:
                    if stream is not None:
                        artifacts[PREFIX+"cases/"+current+".csv.gz"] = compressed(stream.getvalue().encode())
                    current=row["state_code"];stream=io.StringIO(newline="")
                    writer=csv.DictWriter(stream,fieldnames=reader.fieldnames,lineterminator="\n");writer.writeheader()
                writer.writerow(row)
            if stream is not None:
                artifacts[PREFIX+"cases/"+current+".csv.gz"] = compressed(stream.getvalue().encode())
    body = artifacts[PREFIX+"viewer.json.gz"]
    descriptor = dict(contract=model.CONTRACT, version=viewer["version"], states=50,
        path=PREFIX+"viewer.json.gz", compression="gzip",media_type="application/json",
        **pin(body),decoded_bytes=len(viewer_body),decoded_sha256=hashlib.sha256(viewer_body).hexdigest(),
        house_results_sha256=hashlib.sha256(congress_body).hexdigest(),
        count_snapshot_sha256=hashlib.sha256(count_snapshot_body).hexdigest(),
        source_models_refitted=False, legacy_behavioral_gates_changed=False,
        population_or_individual_histories_validated=False)
    return artifacts, descriptor
