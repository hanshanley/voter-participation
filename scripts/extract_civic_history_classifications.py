"""Coarsen already-verified private joints in memory; never export their fine cells."""

from collections import defaultdict
import csv
from fractions import Fraction
import hashlib
import json


PRIOR = ("recalled_candidate_choice", "other_unresolved_prior_response")
CURRENT = ("modeled_participant", "modeled_nonparticipant")


def prior_block(value):
    if value not in ("D", "R", "O", "N", "U"):
        raise ValueError("Unknown native prior response")
    return PRIOR[0] if value in ("D", "R", "O") else PRIOR[1]


def current_block(value):
    if value not in ("D", "R", "O", "N", "U"):
        raise ValueError("Unknown native modeled destination")
    return CURRENT[1] if value == "N" else CURRENT[0]


def private_tables(folder):
    summary = json.loads((folder / "summary.json").read_bytes())
    source = folder / "choice-transitions.csv"
    if hashlib.sha256(source.read_bytes()).hexdigest() != summary["outputs"][source.name]["sha256"]:
        raise ValueError("Changed independently reviewed private reduction")
    tables = defaultdict(lambda: {(p, c): [0, Fraction(0)] for p in PRIOR for c in CURRENT})
    for row in csv.DictReader(source.open()):
        if row["dimension"] != "overall" or row["scope"] == "POOLED_SOURCE":
            continue
        if row["prior_election"] not in ("2022", "2024"):
            raise ValueError("Changed native prior contest")
        n, weight = int(row["n"]), Fraction(row["weight"])
        if n < 0 or weight < 0 or (n == 0) != (weight == 0):
            raise ValueError("Native case/weight disagreement")
        cell = tables[int(row["prior_election"]), row["scope"]][
            prior_block(row["prior_choice"]), current_block(row["modeled_current_destination"])]
        cell[0] += n
        cell[1] += weight
    return tables, summary
