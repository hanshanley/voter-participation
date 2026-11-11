"""Coarsen a held private reduction; never export its fine response cells."""

from collections import defaultdict
from fractions import Fraction


AGE_MAP = {"1": "18_29", "2": "18_29", "3": "30_49", "4": "30_49",
           "5": "50_64", "6": "65_plus", "99": "unknown", "MISSING": "unknown"}
STAGES = ("already_voted", "other_or_unresolved")
LABELS = {"1": "Definitely will vote", "2": "Probably will vote",
          "3": "Probably will not vote", "4": "Definitely will not vote",
          "5": "Already voted", "99": "DON'T KNOW/SKIPPED/REFUSED"}


def aggregate(rows):
    result = defaultdict(lambda: {stage: dict(n=0, weight=Fraction(0)) for stage in STAGES})
    seen = set()
    for row in rows:
        identity = tuple(row[key] for key in ("scope", "dimension", "group", "prior_choice", "LVB"))
        if identity in seen:
            raise ValueError("Duplicate held reduction cell")
        seen.add(identity)
        if row["scope"] == "POOLED_SOURCE" or row["dimension"] not in ("overall", "AGE6"):
            continue
        if row["LVB"] not in LABELS or row["LVB_label"] != LABELS[row["LVB"]]:
            raise ValueError("Unreviewed native response code/label; never impute a stage")
        if row["prior_choice"] not in ("D", "R", "O", "N", "U"):
            raise ValueError("Unreviewed prior-response class; no prior-response filtering")
        n, weight = int(row["n"]), Fraction(row["weight"])
        if n <= 0 or weight <= 0:
            raise ValueError("Changed positive-cell private reduction")
        group = AGE_MAP[row["group"]] if row["dimension"] == "AGE6" else "all"
        stage = "already_voted" if row["LVB"] == "5" else "other_or_unresolved"
        cell = result[row["scope"], row["dimension"], group][stage]
        cell["n"] += n
        cell["weight"] += weight
    return dict(result)


def supported(parent, cells):
    if parent["disposition"] != "selected_broad_source_model":
        return False
    if parent["n"] < 100:
        return False
    if sum(value["n"] for value in cells.values()) != parent["n"] or sum(
            (value["weight"] for value in cells.values()), Fraction(0)) != Fraction(parent["weight"]):
        raise ValueError("Complete LVB group does not match the published parent")
    if any(0 < value["n"] < 30 for value in cells.values()):
        return False
    already = cells["already_voted"]["n"]
    if any(0 < abs(parent[key] - already) < 30 for key in
           ("native_model_voter_cases", "native_model_nonvoter_cases")):
        return False
    return True


def close_age_masks(selected, private, parents):
    selected = set(selected)
    held = []
    for state in sorted({key[0] for key in parents}):
        overall = state, "overall", "all"
        while overall in selected:
            children = [key for key in parents if key[0] == state and key[1] == "AGE6"]
            hidden = [key for key in children if key not in selected and
                      sum(cell["n"] for cell in private.get(key, {}).values()) > 0]
            remaining = {stage: private[overall][stage]["n"] - sum(
                private[key][stage]["n"] for key in children if key in selected) for stage in STAGES}
            total = sum(remaining.values())
            if not (len(hidden) == 1 or 0 < total < 100 or any(0 < value < 30 for value in remaining.values())):
                break
            candidates = sorted((key for key in children if key in selected),
                                key=lambda key: (parents[key]["n"], key))
            key = candidates[0] if candidates else overall
            selected.remove(key)
            held.append(key)
    return selected, held


def select_profiles(snapshot, private):
    parents = {(row["state_code"], row["dimension"], row["group"]): row for row in snapshot["groups"]
               if row["dimension"] in ("overall", "AGE6")}
    if len(parents) != 306:
        raise ValueError("Incomplete 51-jurisdiction overall/age parent query")
    selected = set()
    for key, parent in parents.items():
        if parent["disposition"] == "selected_broad_source_model":
            if key not in private:
                raise ValueError("Missing complete LVB source group")
            if supported(parent, private[key]):
                selected.add(key)
    selected, held = close_age_masks(selected, private, parents)
    profiles = []
    for key, parent in parents.items():
        allowed = key in selected
        profiles.append(dict(state_code=key[0], dimension=key[1], group=key[2],
            disposition="selected_coarse_reported_stage" if allowed else
                        "no_dc_source_sample" if key[0] == "DC" else "held_source_support_or_complementary_disclosure",
            stages={stage: dict(n=private[key][stage]["n"] if allowed else None,
                                weight=str(private[key][stage]["weight"]) if allowed else None)
                    for stage in STAGES}))
    return profiles, held
