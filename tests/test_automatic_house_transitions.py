import copy
import csv
import gzip
import hashlib
import io
import json

import pytest

from scripts import automatic_house_transitions as automatic
from scripts import statewide_house_transitions as model


def review_fixture():
    stream=io.StringIO(newline="")
    writer=csv.DictWriter(stream,fieldnames=["STATE","STATE_ABV","TOTAL_BALLOTS_COUNTED","VEP"])
    writer.writeheader()
    for code in sorted(model.STATES):writer.writerow(dict(STATE=code,STATE_ABV=code,TOTAL_BALLOTS_COUNTED=100,VEP=200))
    body=stream.getvalue().encode()
    return dict(contract=automatic.REVIEW_CONTRACT,states=50,categories=list(model.CHOICES),
        source_models_refitted=False,individual_histories_identified=False,legacy_behavioral_gates_changed=False,
        benchmark_2024=dict(csv_utf8=body.decode(),url="https://election.lab.ufl.edu/data-downloads/turnoutdata/Turnout_2024G_v0.4.csv",**automatic.pin(body)))


def test_review_does_not_remove_legacy_gates_or_promote_source_units_to_histories():
    good=review_fixture();automatic.validate_review(good)
    for key in ['source_models_refitted','individual_histories_identified','legacy_behavioral_gates_changed']:
        changed=copy.deepcopy(good);changed[key]=True
        with pytest.raises(ValueError):automatic.validate_review(changed)
    changed=copy.deepcopy(good);changed['benchmark_2024']['csv_utf8']+='changed'
    with pytest.raises(ValueError,match='benchmark'):automatic.validate_review(changed)


def test_atomic_binding_and_complete_per_state_queries(monkeypatch):
    review=review_fixture();csv26=review['benchmark_2024']['csv_utf8'].encode()
    snapshot=dict(checked_at='2026-11-27T23:00:00Z',uf_turnout=dict(data=dict(
        originals=dict(csv=csv26.decode()),sources=dict(csv=automatic.pin(csv26)))))
    congress=b'complete synthetic test snapshot';counts=b'same accepted synthetic count frame'
    files={'house/statewide-source/'+p+'.json.gz':b'synthetic source prior' for p in model.PROFILES}

    def fake_build(inputs,output):
        assert (inputs/'UF-2024.csv').read_bytes()==csv26
        assert (inputs/'congressional.json.gz').read_bytes()==congress
        output.mkdir()
        (output/'viewer-data.json').write_text(json.dumps(dict(version='a'*64,states=50)))
        (output/'summary.json').write_text('{}')
        (output/'complete-state-comparisons.csv').write_text('all fifty fixture states')
        with gzip.open(output/'complete-sensitivity.csv.gz','wt',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=['state_code','fixture']);writer.writeheader()
            for code in sorted(model.STATES):writer.writerow(dict(state_code=code,fixture='owned-'+code))

    monkeypatch.setattr(automatic.model,'build',fake_build)
    monkeypatch.setattr(automatic,'verify',lambda *args:dict(status='passed',synthetic_binding_test=True))
    artifacts,descriptor=automatic.refresh(review,snapshot,congress,files,counts)
    assert len(artifacts)==54
    assert descriptor['house_results_sha256']==hashlib.sha256(congress).hexdigest()
    assert descriptor['count_snapshot_sha256']==hashlib.sha256(counts).hexdigest()
    assert descriptor['legacy_behavioral_gates_changed'] is False
    for code in model.STATES:
        rows=list(csv.DictReader(io.StringIO(gzip.decompress(artifacts[automatic.PREFIX+'cases/'+code+'.csv.gz']).decode())))
        assert rows==[dict(state_code=code,fixture='owned-'+code)]


def test_missing_or_changed_turnout_source_cannot_refresh_a_model():
    with pytest.raises(ValueError,match='No accepted'):
        automatic.refresh(review_fixture(),{},b'counts',{},b'frame')
    with pytest.raises(ValueError,match='original differs'):
        automatic.refresh(review_fixture(),dict(uf_turnout=dict(data=dict(originals=dict(csv='changed'),
            sources=dict(csv=dict(bytes=1,sha256='a'*64))))),b'counts',{},b'frame')
