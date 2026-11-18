"""Reproduce the complete packaged geography outputs with external Python operations blocked."""

import argparse
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import runpy
import socket
import ssl
import subprocess
import sys
import unittest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--expected", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    os.environ["PROJ_NETWORK"] = "OFF"
    import pyproj
    import shapefile
    import shapely
    pyproj.network.set_network_enabled(False)
    calls = []

    def blocked(*args, **kwargs):
        calls.append("external_operation")
        raise RuntimeError("External operations are blocked during geography reproduction")

    for owner, name in ((socket.socket, "connect"), (socket.socket, "connect_ex"),
                        (socket, "create_connection"), (socket, "getaddrinfo"),
                        (subprocess, "Popen"), (os, "system")):
        setattr(owner, name, blocked)
    suite = unittest.defaultTestLoader.discover("tests", pattern="test_house_district_map.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful() or result.testsRun != 6:
        raise RuntimeError("Packaged geography tests failed or inventory differs")
    sys.argv = ["scripts.house_district_map", "--inputs", str(args.inputs), "--output", str(args.output)]
    with contextlib.redirect_stdout(io.StringIO()):
        runpy.run_module("scripts.house_district_map", run_name="__main__")
    outputs = {}
    for name in ("district-paths.json.gz", "district-geography.json.gz", "district-geography.csv", "manifest.json"):
        body = (args.output / name).read_bytes()
        if body != (args.expected / name).read_bytes():
            raise RuntimeError("Literal geography reproduction differs: "+name)
        outputs[name] = {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}
    if calls:
        raise RuntimeError("Reproduction attempted external operations")
    print(json.dumps({"passed": True, "outputs": outputs, "network_requests": 0,
                      "external_operations_blocked": True, "tests": result.testsRun,
                      "runtime": sys.version.split()[0], "dependencies": {
                          "pyproj": pyproj.__version__, "pyshp": shapefile.__version__,
                          "shapely": shapely.__version__}}), flush=True)


if __name__ == "__main__":
    main()
