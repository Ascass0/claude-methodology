"""Minimal fake of `gitleaks git` for tests (no scanner needed).

$FAKE_GITLEAKS_MODE = clean | leak | error | badreport | noreport; every call appends its arguments to
$FAKE_GITLEAKS_LOG and its report path to $FAKE_GITLEAKS_LOG.paths. The leak carries a value
('TOPSECRET') that the real tool would redact: mth must never print it.
"""
import json
import os
import sys

argv = sys.argv[1:]
mode = os.environ.get("FAKE_GITLEAKS_MODE", "clean")
report = argv[argv.index("--report-path") + 1] if "--report-path" in argv else ""
with open(os.environ["FAKE_GITLEAKS_LOG"], "a") as log:
    log.write(json.dumps(argv) + "\n")
with open(os.environ["FAKE_GITLEAKS_LOG"] + ".paths", "a") as paths:
    paths.write(report + "\n")
if mode == "error":
    print("fatal: bad revision 'x..HEAD'", file=sys.stderr)
    sys.exit(1)
if mode == "leak":
    with open(report, "w") as fh:
        json.dump([{"RuleID": "aws-access-token", "File": "src/cfg.py", "StartLine": 7,
                    "Commit": "0123456789abcdef", "Secret": "TOPSECRET"}], fh)
    sys.exit(2)
if mode == "badreport":
    with open(report, "w") as fh:
        fh.write("not json")
    sys.exit(2)
if mode == "noreport":
    sys.exit(2)
sys.exit(0)
