"""Refresh an existing state-only native reference with an explicitly reviewed register."""

import copy
from decimal import Decimal

from scripts.html_statistics import validate
from scripts.participation_intake.adapters import field
from scripts.participation_intake.contract import IntakeError, encoded, pin


ROLE_PATHS = {
    "count": ("count.value", "view.ballots"),
    "denominator": ("denominator.value", "view.denominator"),
    "percentage": ("view.native_published_pct",),
    "clock": ("source_clock.literal", "view.source_update_label"),
}


def facts(row, spec):
    binding = spec.get("format", {}).get("state_reporting")
    if (not isinstance(binding, dict)
            or set(binding) != {"statistics_path", "previous_reference", "registered_frame_review",
                               "source_status_literal"}
            or not binding["registered_frame_review"].strip()
            or not binding["source_status_literal"].strip()
            or not spec["format"].get("html_statistics_recipe_input")):
        raise IntakeError("state_reporting_scope", "An explicit state-only registration/reference review is required")
    selected = field(row, binding["statistics_path"])
    try:
        validate(selected)
        source, roles = selected["source"], selected["recipe"]["roles"]
        values = {role: selected["fields"][name]["value"] for role, name in roles.items()}
        if (source["state_code"] != spec["geography"]["state_code"]
                or source["election_year"] != spec["election"]["year"]
                or row["geography"]["level"] != "state"
                or row["geography"]["state_code"] != source["state_code"]
                or row["election"] != spec["election"]
                or row["source"]["url"] != source["url"]
                or row["source"]["input_sha256"] != source["pin"]["sha256"]
                or row["count"]["status"] != "reported"):
            raise ValueError("State statistic source, native pin or canonical scope changed")
        for role, paths in ROLE_PATHS.items():
            for path in paths:
                matches = [item for item in spec["format"].get("fact_bindings", [])
                    if item.get("record") == {"id": row["id"]} and item.get("path") == path
                    and item.get("source_id") == source["id"]
                    and item.get("measure") == roles[role]
                    and item.get("value_scope", "cell") == "cell"
                    and item.get("parse") == ("count" if role in ("count", "denominator") else "literal")
                    and item.get("operation", "unique") == "unique"]
                actual = field(row, path)
                if len(matches) != 1 or type(actual) is not type(values[role]) or actual != values[role]:
                    raise ValueError("Metadata cannot replace a directly bound statewide count, register or clock")
        if (row["source_clock"]["timezone"] != row["view"].get("source_update_timezone")
                or row["denominator"]["basis"] != binding["previous_reference"]["denominator_basis"]):
            raise ValueError("Native registration basis or clock-zone binding changed")
    except (KeyError, TypeError, ValueError) as error:
        raise IntakeError("state_reporting_scope", str(error)) from error
    return selected, values, binding


def append_count_only(data, row, spec):
    binding = spec.get("format", {}).get("state_reporting", {})
    if (set(binding) != {"contract", "statistics_path", "previous_reference",
                        "registered_frame_review", "source_status_literal", "baseline_state_references"}
            or binding["contract"] != "participation.state_reporting_addition.v1"
            or binding["previous_reference"] is not None
            or not binding["registered_frame_review"].strip()
            or not binding["source_status_literal"].strip()
            or not spec["format"].get("html_statistics_recipe_input")):
        raise IntakeError("state_reporting_scope", "A new count-only state reference needs an explicit addition review")
    try:
        selected = field(row, binding["statistics_path"])
        validate(selected)
        source, roles = selected["source"], selected["recipe"]["roles"]
        code = spec["geography"]["state_code"]
        if (selected["contract"] != "participation.selected_html_statistics.v2"
                or roles["denominator"] is not None or roles["clock"] is not None
                or row["geography"]["level"] != "state" or row["geography"]["state_code"] != code
                or source["state_code"] != code or source["election_year"] != spec["election"]["year"]
                or row["election"] != spec["election"]
                or row["source"]["url"] != source["url"]
                or row["source"]["input_sha256"] != source["pin"]["sha256"]
                or source["native_updated_at"] is not None
                or row["measure"]["kind"] != "participation_reported"
                or row["measure"]["mode"] != "source_defined"
                or row["count"]["status"] != "reported"
                or row["denominator"] is not None
                or row["view"].get("denominator") is not None
                or any(row["view"].get(key) is not None for key in ("reported_pct", "validated_pct"))
                or row["view"].get("maps_approved") is not False
                or row["source_clock"] != dict(literal=None, timezone=None)
                or row["view"].get("source_update_label") is not None
                or row["view"].get("source_date") is not None
                or row["view"].get("source_update_timezone") is not None):
            raise ValueError("Count-only state additions cannot infer a denominator, rate, count clock or map")
        for path in ("count.value", "view.ballots"):
            matches = [item for item in spec["format"].get("fact_bindings", [])
                if item.get("record") == {"id": row["id"]} and item.get("path") == path
                and item.get("source_id") == source["id"]
                and item.get("measure") == roles["count"]
                and item.get("value_scope", "cell") == "cell"
                and item.get("parse") == "count"
                and item.get("operation", "unique") == "unique"]
            actual = field(row, path)
            value = selected["fields"][roles["count"]]["value"]
            if len(matches) != 1 or type(actual) is not type(value) or actual != value:
                raise ValueError("The new state total needs its own directly bound native count")
        percentage = (selected["fields"][roles["percentage"]]["value"]
                      if roles["percentage"] is not None else None)
        if row["view"].get("native_printed_pct") != percentage:
            raise ValueError("A printed native percentage is context, not an inferred analytical fraction")
        before = dict(reporting=[item for item in data["snapshot"]["reporting"] if item["state_code"] == code],
                      reviewed_states=[item for item in data["reviewed_states"] if item["state_code"] == code])
        if (binding["baseline_state_references"] != {key: pin(encoded(value)) for key, value in before.items()}
                or any(before.values())):
            raise ValueError("A state addition cannot replace or shadow an existing administrative reference")
        view = copy.deepcopy(row["view"])
        if (view["state_code"] != code or view["year"] != spec["election"]["year"]
                or view["source_url"] != source["url"] or view["source_sha256"] != source["pin"]["sha256"]
                or view["participation_measure_literal"] != row["measure"]["literal"]
                or view["source_status_literal"] != binding["source_status_literal"]):
            raise ValueError("State reference display mirrors differ from the qualified observation")
        data["snapshot"]["reporting"].append(view)
        coverage = [item for item in data["snapshot"]["coverage"] if item["state_code"] == code]
        if len(coverage) != 1:
            raise ValueError("The complete state coverage inventory changed")
        coverage[0].update(official_status="reported_native_state_count_only",
                           status="native_state_count_and_separate_early_activity")
        data["snapshot"].setdefault("native_reporting_successors", []).append(dict(
            state_code=code, source_url=source["url"], source_sha256=source["pin"]["sha256"],
            operation="reviewed_state_only_count_addition", previous_state_reference=None,
            native_count_label=selected["fields"][roles["count"]]["native_label"],
            registered_frame_review=binding["registered_frame_review"],
            count_clock_unknown=True, base_snapshot_not_a_common_asof=True))
    except (KeyError, TypeError, ValueError) as error:
        raise IntakeError("state_reporting_scope", str(error)) from error
    return data


def refresh(data, sources):
    result, changed, seen = copy.deepcopy(data), 0, set()
    for source in sources:
        spec, rows = source["spec"], source["rows"]
        if len(rows) != 1:
            raise IntakeError("state_reporting_scope", "A state-only refresh is not a partial county aggregate")
        row = rows[0]
        if spec.get("format", {}).get("state_reporting", {}).get("contract") == "participation.state_reporting_addition.v1":
            code = spec["geography"]["state_code"]
            if code in seen:
                raise IntakeError("state_reporting_scope", "Duplicate state-only native reference")
            seen.add(code)
            result = append_count_only(result, row, spec)
            changed += 1
            continue
        selected, values, binding = facts(row, spec)
        code, url = selected["source"]["state_code"], selected["source"]["url"]
        if code in seen:
            raise IntakeError("state_reporting_scope", "Duplicate state-only native reference")
        seen.add(code)
        matches = [item for item in result["snapshot"]["reporting"]
                   if item["state_code"] == code and item["source_url"] == url]
        previous = binding["previous_reference"]
        if (set(previous) != {"ballots", "denominator", "source_update_label", "denominator_basis"}
                or len(matches) != 1
                or any(type(matches[0].get(key)) is not type(previous[key])
                       or matches[0].get(key) != previous[key] for key in
                       ("ballots", "denominator", "source_update_label", "denominator_basis"))):
            raise IntakeError("state_reporting_scope", "Accepted state reference advanced or differs from its reviewed preimage")
        target, before = matches[0], copy.deepcopy(matches[0])
        target.update(
            ballots=values["count"], denominator=values["denominator"],
            published_pct=float(Decimal(values["percentage"][:-1])),
            validated_pct=(round(100 * values["count"] / values["denominator"], 3)
                           if target["validated_pct"] is not None else None),
            source_update_label=values["clock"],
            source_update_timezone=row["source_clock"]["timezone"],
            source_retrieved_at=row["view"]["source_retrieved_at"],
            source_snapshot="native-sha256:" + selected["source"]["pin"]["sha256"],
            source_sha256=selected["source"]["pin"]["sha256"],
            complete_download_url=row["view"]["complete_download_url"])
        if target != before:
            changed += 1
            lineage = result["snapshot"].setdefault("native_reporting_successors", [])
            lineage[:] = [item for item in lineage if item["state_code"] != code]
            lineage.append(dict(
                state_code=code, source_url=url, source_sha256=target["source_sha256"],
                operation="reviewed_state_only_registered_reference",
                previous_ballots=before["ballots"], previous_registered=before["denominator"],
                registered_frame_review=binding["registered_frame_review"],
                native_count_label=selected["fields"][selected["recipe"]["roles"]["count"]]["native_label"],
                native_registration_label=selected["fields"][selected["recipe"]["roles"]["denominator"]]["native_label"],
                native_completeness_context_is_opaque=True, base_snapshot_not_a_common_asof=True))
            note = "Native reporting successors retain their own result/retrieval clocks; the base snapshot date is not a common as-of time."
            limitations = result["snapshot"].setdefault("limitations", [])
            if note not in limitations:
                limitations.append(note)
    return result, changed
