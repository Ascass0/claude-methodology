"""Minimal fake of `gitleaks git` for tests (no scanner needed).

$FAKE_GITLEAKS_MODE = clean | leak | error | badreport | noreport | hang; every call appends its arguments to
$FAKE_GITLEAKS_LOG and its report path to $FAKE_GITLEAKS_LOG.paths. The leak carries a value
('TOPSECRET') that the real tool would redact: mth must never print it.
"""
import json
import os
import sys
import time

argv = sys.argv[1:]
if argv[:1] == ["version"]:  # the tool version, not a scan: not logged
    print(os.environ.get("FAKE_GITLEAKS_VERSION", "8.30.1"))
    sys.exit(0)
mode = os.environ.get("FAKE_GITLEAKS_MODE", "clean")
report = argv[argv.index("--report-path") + 1] if "--report-path" in argv else ""
with open(os.environ["FAKE_GITLEAKS_LOG"], "a") as log:
    log.write(json.dumps(argv) + "\n")
with open(os.environ["FAKE_GITLEAKS_LOG"] + ".paths", "a") as paths:
    paths.write(report + "\n")
if mode == "error":
    print("fatal: leaked TOPSECRET in output", file=sys.stderr)
    sys.exit(1)
if mode == "hang":
    time.sleep(30)
if mode == "leak":
    finding = {"RuleID": "aws-access-token", "File": "src/cfg.py", "StartLine": 7,
               "Commit": "0123456789abcdef", "Secret": "TOPSECRET"}
    if "--staged" in argv:  # a staged finding has no commit yet
        finding["Commit"] = ""
    if "--baseline-path" in argv:  # like the real tool: accepted findings are not reported
        with open(argv[argv.index("--baseline-path") + 1]) as fh:
            if any(i.get("RuleID") == finding["RuleID"] and i.get("File") == finding["File"] for i in json.load(fh)):
                sys.exit(0)
    with open(report, "w") as fh:
        json.dump([finding], fh)
    sys.exit(2)
if mode == "badreport":
    with open(report, "w") as fh:
        fh.write("not json")
    sys.exit(2)
if mode == "noreport":
    sys.exit(2)
sys.exit(0)
