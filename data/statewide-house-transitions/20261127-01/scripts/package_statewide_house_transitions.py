"""Package the complete all-state transition model and replayable public inputs."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def package(inputs, product, review, output):
    if output.exists():
        raise ValueError("Do not overwrite a published scientific version")
    viewer=json.loads((product/'viewer-data.json').read_text())
    if viewer['quick_development_preview'] or viewer['states']!=50 or len(viewer['rows'])!=50:
        raise ValueError("Package a complete production model")
    engine=viewer['numerical_runtime']
    if engine['implementation']!=sys.implementation.name or engine['python_major_minor']!=list(sys.version_info[:2]):
        raise ValueError("Package with the same numerical Python version as the producer")
    root=Path(__file__).parents[1]
    names=['viewer-data.json','summary.json','complete-state-comparisons.csv','complete-sensitivity.csv.gz']
    files={name:(product/name).read_bytes() for name in names}
    body=gzip.compress(files['viewer-data.json'],compresslevel=9,mtime=0)
    files['viewer-data.json.gz']=body[:9]+bytes([3])+body[10:]
    files['review.json']=review.read_bytes()
    files.update({'inputs/'+path.name:path.read_bytes() for path in inputs.iterdir() if path.is_file()})
    for name in ['scripts/statewide_house_transitions.py','scripts/verify_statewide_house_transitions.py',
                 'scripts/automatic_house_transitions.py','scripts/package_statewide_house_transitions.py',
                 'tests/test_statewide_house_transitions.py','tests/test_automatic_house_transitions.py']:
        files[name]=(root/name).read_bytes()
    version='.'.join(map(str,engine['python_major_minor']))
    files['README.txt']=(
        'Whole-state 2024-to-2026 House switching/no-counted-ballot transition estimates for all 50 states.\n'
        'These are conditional modeled flows, not linked voter histories or causal evidence of persuasion.\n'
        'Both years retain their reported House categories and UF ballot/VEP benchmarks.\n'
        'H includes ballots without a reported House choice, including unreported uncontested choices; H is not staying home.\n'
        'N means no counted ballot in the assumed eligible accounting frame, not proof someone physically stayed home.\n'
        'E separates eligibility/frame change. State model counts are not additive unique people.\n'
        'Percentages use all 2024 recorded House D/R/Other-unassigned votes; contributions use Democratic D/(D+R) points.\n'
        'The complete case file contains all 109350 decisions and every feasible 6-by-6 matrix, including rejected hypothetical ballot cases.\n'
        'Ranges are assumption sensitivity, not confidence intervals or complete source/population uncertainty.\n'
        'UF benchmarks: Michael McDonald, University of Florida Election Lab, 2024 v0.4 and 2026 v0.3; CC-BY-4.0.\n'
        'No private respondents or private fine source cells are redistributed.\n'
        'For byte-identical replay use CPython '+version+':\n'
        'python -m scripts.statewide_house_transitions --inputs inputs --output reproduced\n'
        'python -m scripts.verify_statewide_house_transitions --inputs inputs --product reproduced\n'
        'python -m unittest discover -s tests -p test_statewide_house_transitions.py\n'
    ).encode()
    files['checksums.json']=encoded({name:dict(bytes=len(body),sha256=hashlib.sha256(body).hexdigest()) for name,body in sorted(files.items())})
    output.mkdir(parents=True)
    for name,body in files.items():
        path=output/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(body)
    with zipfile.ZipFile(output/'complete-analysis.zip','w') as archive:
        for name,body in sorted(files.items()):
            item=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));item.compress_type=zipfile.ZIP_DEFLATED;item.external_attr=0o644<<16
            archive.writestr(item,body)
    print(json.dumps(dict(states=50,model_version=viewer['version'],files=len(files),archive_bytes=(output/'complete-analysis.zip').stat().st_size)))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inputs',type=Path,required=True);p.add_argument('--product',type=Path,required=True)
    p.add_argument('--review',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();package(a.inputs,a.product,a.review,a.output)
