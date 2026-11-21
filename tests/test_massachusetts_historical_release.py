import csv
import io
import json
import subprocess

import pytest

from scripts import massachusetts_historical_release as atlas
from scripts.participation_intake.contract import pin


def test_staged_failure_keeps_active_atlas_and_resume_reuses_verified_bytes(tmp_path, monkeypatch):
    repo, remote = tmp_path / "repo", tmp_path / "remote"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    publisher = atlas.GitPublisher(repo, ref=atlas.REF, github_repository=atlas.REPOSITORY)
    publisher.git("remote", "add", "origin", str(remote))

    def verify(commit, files):
        for path, expected in files.items():
            contents = subprocess.check_output(["git", "-C", str(repo), "show", f"{commit}:{path}"])
            assert pin(contents) == expected

    monkeypatch.setattr(publisher, "verify_files", verify)
    package = tmp_path / "complete-analysis.zip"
    package.write_bytes(b"first checked archive")
    assert atlas.publish(publisher, None, None, atlas.EMPTY_STOPS, package, "a" * 64) == "published"
    first = publisher.remote_head()
    initial = json.loads(publisher.git("show", first + ":latest.json"))
    assert initial["complete_download"]["sha256"] == pin(package.read_bytes())["sha256"]
    assert atlas.publish(publisher, first, initial, atlas.EMPTY_STOPS, package, "a" * 64) == "unchanged"
    assert publisher.remote_head() == first

    def unavailable(*_):
        raise OSError("Temporary public verification failure")

    for revised, version in ((b"upward revision", "b" * 64), (b"downward revision", "c" * 64)):
        package.write_bytes(revised)
        monkeypatch.setattr(publisher, "verify_files", unavailable)
        with pytest.raises(OSError, match="Temporary"):
            atlas.publish(publisher, first, initial, atlas.EMPTY_STOPS, package, version)
        staged = publisher.remote_head()
        assert json.loads(publisher.git("show", staged + ":latest.json")) == initial
        receipt = json.loads(publisher.git("show", staged + ":pending.json"))
        monkeypatch.setattr(publisher, "verify_files", verify)
        atlas.activate_staged(publisher, staged, receipt)
        first = publisher.remote_head()
        initial = json.loads(publisher.git("show", first + ":latest.json"))
        assert initial["numerical_version"] == version
        assert initial["complete_download"]["sha256"] == pin(revised)["sha256"]


def test_semantic_version_ignores_only_html_wrapper_bytes(tmp_path):
    history = tmp_path / atlas.canvass.HISTORY_CSV

    def write(count, page, original):
        value = io.StringIO(newline="")
        writer = csv.writer(value)
        writer.writerow(["ballots_including_blanks", "source_1_page_sha256", "source_1_csv_sha256"])
        writer.writerow([count, page, original])
        history.write_text(value.getvalue())
        return atlas.semantic_version(tmp_path)

    first = write(100, "initial", "original")
    assert write(100, "new html shell", "original") == first
    assert write(100, "initial", "new csv") != first
    assert write(101, "initial", "original") != first
    assert write(99, "initial", "original") != first
