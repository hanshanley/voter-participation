"""Resume one verified multi-dataset stage and atomic catalog promotion."""

import copy
import json
from pathlib import Path


def publish_datasets(website_repo, roots, expected_versions, complete_download, journal_path):
    from scripts.participation_intake.contract import encoded, pin
    from scripts.participation_intake.publisher import GitPublisher, validate_dataset

    journal_path = Path(journal_path)
    if (not complete_download.get("verified_anonymously") or not complete_download.get("immutable")
            or not complete_download.get("sha256") or complete_download.get("bytes", 0) <= 0):
        raise ValueError("A full anonymously verified immutable package is required")
    publisher = GitPublisher(website_repo)

    def save():
        temporary = journal_path.with_suffix(".tmp")
        temporary.write_bytes(encoded(journal))
        temporary.replace(journal_path)

    if journal_path.exists():
        journal = json.loads(journal_path.read_bytes())
        if (journal["expected_versions"] != expected_versions
                or journal["complete_download"] != complete_download):
            raise ValueError("Resume inputs differ from the original publication")
        publisher.fetch_parent(publisher.remote_head())
        before, parent = journal["before"], journal["parent"]
        if publisher.remote_head() not in (parent, journal.get("staged"), journal.get("promoted")):
            raise ValueError("Catalog advanced since this journal; rebase rather than overwrite")
    else:
        parent = publisher.remote_head()
        publisher.fetch_parent(parent)
        before = publisher.catalog(parent)
        for identity, version in expected_versions.items():
            if before["datasets"].get(identity, {}).get("version") != version:
                raise ValueError("Published dataset advanced; rebase the batch, do not overwrite: "+identity)
        journal = dict(parent=parent, before=before, expected_versions=expected_versions,
                       complete_download=complete_download)
        journal_path.parent.mkdir(parents=True, exist_ok=True)
        save()
    descriptions, bodies, seen = {}, {}, set()
    for supplied_root in roots:
        root = Path(supplied_root)
        description = json.loads((root/"dataset.json").read_bytes())
        identity = description["id"]
        if identity in seen:
            raise ValueError("Duplicate dataset in one batch")
        seen.add(identity)
        current = before["datasets"].get(identity)
        if current and current["version"] == description["version"]:
            description = validate_dataset(root)
            if (current["files"] != description["files"]
                    or current["complete_download"] != description.get("complete_download")):
                raise ValueError("An existing immutable version cannot change")
            continue
        if identity not in expected_versions or identity in descriptions:
            raise ValueError("Missing baseline pin or duplicate dataset")
        description["complete_download"] = complete_download
        (root/"dataset.json").write_bytes(encoded(description))
        description = validate_dataset(root)
        descriptions[identity] = description
        prefix = f"datasets/{identity}/{description['version']}/"
        bodies.update({prefix+name: (root/name).read_bytes() for name in description["files"]})
        bodies[prefix+"dataset.json"] = encoded(description)
    if not descriptions:
        if publisher.remote_head() != parent:
            raise ValueError("Catalog advanced during no-op validation; rebase this batch")
        result = dict(status="unchanged", catalog_commit=parent,
                      datasets_changed=0, website_builds_started=0)
        journal["result"] = result
        save()
        return result
    body_pins = {name: pin(body) for name, body in bodies.items()}
    if "file_pins" in journal and journal["file_pins"] != body_pins:
        raise ValueError("Compiled files changed during publication resume")
    journal["file_pins"] = body_pins
    if "staged" not in journal:
        journal["staged"] = publisher.commit(publisher.tree(parent, bodies), parent,
            "Stage verified participation batch datasets")
        save()
    staged = journal["staged"]
    remote = publisher.remote_head()
    if remote == parent:
        publisher.promote(staged, parent)
    elif remote not in (staged, journal.get("promoted")):
        raise ValueError("Catalog advanced while staging; preserve the new head")
    if not journal.get("immutable_files_verified"):
        verified = publisher.verify_files(staged, body_pins)
        journal["immutable_files_verified"] = len(verified)
        save()
    candidate = copy.deepcopy(before)
    for identity, description in descriptions.items():
        prefix = f"datasets/{identity}/{description['version']}/"
        candidate["datasets"][identity] = dict(description, status="loaded", staged_commit=staged,
            base_url=f"https://raw.githubusercontent.com/{publisher.github_repository}/{staged}/{prefix}")
    if "promoted" not in journal:
        journal["promoted"] = publisher.commit(publisher.tree(staged, {"catalog.json": encoded(candidate)}),
            staged, "Atomically activate verified participation batch")
        save()
    promoted = journal["promoted"]
    if publisher.remote_head() == staged:
        publisher.promote(promoted, staged)
    elif publisher.remote_head() != promoted:
        raise ValueError("Catalog advanced before activation; no overwrite")
    publisher.verify_files(promoted, {"catalog.json": pin(encoded(candidate))})
    if publisher.catalog(staged) != before or publisher.catalog(promoted) != candidate:
        raise ValueError("Staging or atomic catalog verification differs")
    result = dict(status="published", staged_commit=staged, catalog_commit=promoted,
        datasets_changed=len(descriptions), changed_ids=sorted(descriptions),
        anonymous_verified_files=journal["immutable_files_verified"],
        intermediate_catalog_unchanged=True, single_catalog_commit_for_all_changes=True,
        unchanged_dataset_entries_preserved=True, website_builds_started=0,
        worktree_head_or_index_changed=False)
    journal["result"] = result
    save()
    return result
