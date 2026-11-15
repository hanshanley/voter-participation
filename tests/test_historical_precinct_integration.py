import json
from pathlib import Path
import zipfile

from scripts.historical_native_counts import compile_dataset
from scripts.historical_precinct_qualification import (
    build,
    integration_descriptor,
    iter_integrated_observations,
    pin_file,
)
from test_historical_precinct_qualification import (
    OFFICIAL_FIELDS,
    csv_gzip,
    fixture,
    official_row,
    official_sources,
    packet,
)


def historical_component(path):
    rows = [
        official_row(2, "A", "ballots_cast", "5"),
        official_row(3, "A", "registration_stock", "10"),
    ]
    packet(path, {
        "queries/complete-source-cell-query.csv.gz":
            csv_gzip(OFFICIAL_FIELDS, rows),
        "originals/product-provenance.json":
            json.dumps(list(official_sources().values())).encode(),
    })
    return path


def test_default_is_unchanged_and_configured_sidecar_is_queryable(tmp_path):
    qualification_inputs = fixture(tmp_path / "qualification-inputs")
    qualification_output = tmp_path / "qualification-output"
    build(qualification_inputs, qualification_output)
    component = historical_component(tmp_path / "official.zip")
    base = {
        "inputs": [{
            "collection": "official-state", "file": str(component),
            **pin_file(component),
        }]
    }
    default_spec = tmp_path / "default.json"
    default_spec.write_text(json.dumps(base, sort_keys=True))
    default_output = tmp_path / "default-output"
    default_result = compile_dataset(default_spec, default_output)
    default_index = json.loads((default_output / "index.json").read_text())
    assert "historical_precinct_qualification" not in default_index
    assert "qualified_precinct_observations" not in default_result

    descriptor = integration_descriptor(qualification_output)
    configured = {
        **base,
        "historical_precinct_qualification": {
            "directory": str(qualification_output),
            **descriptor,
        },
    }
    configured_spec = tmp_path / "configured.json"
    configured_spec.write_text(json.dumps(configured, sort_keys=True))
    configured_output = tmp_path / "configured-output"
    configured_result = compile_dataset(configured_spec, configured_output)
    assert configured_result["records"] == default_result["records"] == 2
    assert configured_result["qualified_precinct_observations"] == 1
    assert (configured_output / "states/AL.json.gz").read_bytes() == \
        (default_output / "states/AL.json.gz").read_bytes()
    observations = list(iter_integrated_observations(configured_output))
    assert len(observations) == 1
    assert observations[0]["rate_numerator"] == 0
    assert observations[0]["rate_denominator"] == 10
