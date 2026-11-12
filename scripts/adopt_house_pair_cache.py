"""Carry forward successful fits after a verified score-reduction-only correction."""

import argparse
import ast
import copy
import gzip
import hashlib
import json
from pathlib import Path
import subprocess


def digest(body):
    return hashlib.sha256(body).hexdigest()


def main():
    import numpy as np
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("old-policy", "new-policy", "old-private", "new-private", "proof"):
        parser.add_argument("--" + key, type=Path, required=True)
    parser.add_argument("--old-commit", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    original = subprocess.check_output(["git", "-C", str(root), "show",
                                       args.old_commit + ":scripts/house_pair_oof.py"])
    current = (root / "scripts/house_pair_oof.py").read_bytes()
    before = json.loads(args.old_policy.read_bytes())
    after = json.loads(args.new_policy.read_bytes())
    old_binding, new_binding = digest(args.old_policy.read_bytes()), digest(args.new_policy.read_bytes())
    assert digest(original) == before["fitter_sha256"]
    assert digest(current) == after["fitter_sha256"]
    allowed = {"fitter_sha256", "score_backend_correction", "original_policy_sha256",
               "frozen_before_first_new_paired_source_fit"}
    assert {k: v for k, v in before.items() if k not in allowed} == {
        k: v for k, v in after.items() if k not in allowed}
    old_tree, new_tree = ast.parse(original), ast.parse(current)
    old_functions = {node.name: node for node in old_tree.body if isinstance(node, ast.FunctionDef)}
    new_functions = {node.name: node for node in new_tree.body if isinstance(node, ast.FunctionDef)}
    assert old_functions.keys() == new_functions.keys()
    for name in old_functions:
        if name == "metrics":
            continue
        left, right = copy.deepcopy(old_functions[name]), copy.deepcopy(new_functions[name])
        if name == "run":
            for tree in (left, right):
                assignments = [node for node in ast.walk(tree) if isinstance(node, ast.Assign)
                               and any(isinstance(target, ast.Name) and target.id == "expected" for target in node.targets)]
                assert len(assignments) == 1
                assignments[0].value = ast.Constant(value=None)
        assert ast.dump(left) == ast.dump(right), "Fitting or feature semantics changed"
    assert not args.new_private.exists() and not args.proof.exists()
    args.new_private.mkdir(mode=0o700, parents=True)
    (args.new_private / "heads").mkdir(mode=0o700)
    prepared = json.loads(gzip.decompress((args.old_private / "prepared.json.gz").read_bytes()))
    assert prepared["policy_sha256"] == old_binding
    prepared["policy_sha256"] = new_binding
    destination = args.new_private / "prepared.json.gz"
    destination.write_bytes(gzip.compress(json.dumps(prepared, sort_keys=True).encode(), mtime=0))
    destination.chmod(0o600)
    names = []
    for path in sorted((args.old_private / "heads").glob("*.npz")):
        with np.load(path, allow_pickle=False) as archive:
            metadata = json.loads(str(archive["metadata"]))
            probabilities = archive["probabilities"].copy()
        assert metadata["policy_sha256"] == old_binding
        assert np.isfinite(probabilities).all() and (probabilities > 0).all()
        assert np.max(abs(probabilities.sum(axis=1) - 1)) < 1e-12
        metadata["policy_sha256"] = new_binding
        output = args.new_private / "heads" / path.name
        np.savez_compressed(output, probabilities=probabilities,
                            metadata=np.asarray(json.dumps(metadata, sort_keys=True)))
        output.chmod(0o600)
        with np.load(output, allow_pickle=False) as check:
            assert np.array_equal(probabilities, check["probabilities"])
        names.append(path.name)
    assert len(names) == 72
    report = dict(status="pass_score_only_cache_adoption", completed_fits_reused=len(names),
        old_policy_sha256=old_binding, new_policy_sha256=new_binding,
        original_fitter_commit=args.old_commit, original_fitter_sha256=digest(original),
        corrected_fitter_sha256=digest(current), fitting_and_feature_function_ASTs_unchanged=True,
        run_AST_unchanged_except_expected_weighted_sum=True,
        all_successful_probability_arrays_byte_identical=True,
        statistical_design_models_weights_splits_and_regularization_unchanged=True,
        private_cache_names_sha256=digest("\n".join(names).encode()), successful_fits_repeated=0)
    args.proof.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
