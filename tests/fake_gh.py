"""Minimal fake of the `gh` CLI for end-to-end tests (no network).

State lives in $FAKE_GH_STATE; merges are performed against the bare repo in
$FAKE_GH_REMOTE with real merge commits. $FAKE_GH_CHECKS = pass | fail | none.
"""
import json
import os
import subprocess
import sys
import tempfile

STATE = os.environ["FAKE_GH_STATE"]
REMOTE = os.environ["FAKE_GH_REMOTE"]


def load():
    if os.path.exists(STATE):
        with open(STATE) as fh:
            return json.load(fh)
    return {"prs": [], "releases": []}


def save(state):
    with open(STATE, "w") as fh:
        json.dump(state, fh)


def opt(args, name, default=None):
    return args[args.index(name) + 1] if name in args else default


def git(*args, cwd=None):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def main(argv):
    state = load()
    if argv[:2] == ["auth", "status"]:
        return 0
    if argv[:2] == ["pr", "list"]:
        head, base, st = opt(argv, "--head"), opt(argv, "--base"), opt(argv, "--state", "open")
        found = [{"number": p["number"], "state": p["state"].upper(), "url": ""}
                 for p in state["prs"] if p["head"] == head and p["base"] == base and p["state"] == st]
        print(json.dumps(found[:1]))
        return 0
    if argv[:2] == ["pr", "create"]:
        number = len(state["prs"]) + 1
        state["prs"].append({"number": number, "head": opt(argv, "--head"), "base": opt(argv, "--base"),
                             "title": opt(argv, "--title"), "state": "open",
                             "body": open(opt(argv, "--body-file")).read()})
        save(state)
        print(f"https://github.com/o/r/pull/{number}")
        return 0
    if argv[:2] == ["pr", "checks"]:
        mode = os.environ.get("FAKE_GH_CHECKS", "pass")
        if mode == "none":
            print("no checks reported on the 'x' branch", file=sys.stderr)
            return 1
        print("ci\t" + ("pass" if mode == "pass" else "fail"))
        return 0 if mode == "pass" else 1
    if argv[:2] == ["pr", "merge"]:
        number = int(argv[2])
        pr = next(p for p in state["prs"] if p["number"] == number)
        with tempfile.TemporaryDirectory() as tmp:
            git("clone", "-q", REMOTE, tmp)
            git("checkout", "-q", pr["base"], cwd=tmp)
            git("-c", "core.hooksPath=/dev/null", "merge", "--no-ff", f"origin/{pr['head']}",
                "-m", opt(argv, "--subject"), "-m", opt(argv, "--body"), cwd=tmp)
            git("push", "-q", "origin", pr["base"], cwd=tmp)
        pr["state"] = "merged"
        save(state)
        return 0
    if argv[:2] == ["release", "view"]:
        return 0 if argv[2] in state["releases"] else 1
    if argv[:2] == ["release", "create"]:
        state["releases"].append(argv[2])
        save(state)
        return 0
    if argv[0] == "api":
        print(json.dumps({"full_name": "o/r"}) if "GET" in argv else "{}")
        return 0
    print(f"fake gh: unsupported {argv}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
