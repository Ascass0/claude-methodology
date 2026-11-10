"""GitHub operations through the ``gh`` CLI (pull requests, checks, releases)."""
from __future__ import annotations

import json
import os
import re
import tempfile
import time
from pathlib import Path

from .errors import MthError
from .log import say, warn
from .proc import run

# Checks can take a few seconds to register after a push (race window).
_POLL_SECONDS = float(os.environ.get("MTH_CI_POLL_SECONDS", "10"))
_POLL_ATTEMPTS = int(os.environ.get("MTH_CI_POLL_ATTEMPTS", "6"))
_NO_CHECKS = "no checks reported"


class GitHub:
    """Pull-request lifecycle used by integrate, release and hotfix.

    Args:
        root: Repository working tree (``gh`` resolves the repo from it).
    """

    def __init__(self, root: Path, repo: str | None = None) -> None:
        self.root = root
        self.repo = repo  # explicit target: never let gh guess between origin and upstream

    def _gh(self, *args: str, check: bool = True):
        return run(["gh", *args], cwd=self.root, check=check)

    def _gh_repo(self, *args: str, check: bool = True):
        """gh call scoped to the integration repository (appends --repo)."""
        return self._gh(*args, *(["--repo", self.repo] if self.repo else []), check=check)

    def ensure_ready(self) -> None:
        """Raises MthError when gh is missing or not authenticated."""
        if self._gh("auth", "status", check=False).returncode != 0:
            raise MthError("gh no está autenticado.", hint="Ejecuta `gh auth login`.")

    def find_pr(self, head: str, base: str, state: str = "open") -> dict | None:
        out = self._gh_repo("pr", "list", "--head", head, "--base", base, "--state", state,
                       "--json", "number,state,url", "--limit", "1").stdout
        items = json.loads(out or "[]")
        return items[0] if items else None

    def create_pr(self, head: str, base: str, title: str, body: str) -> int:
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as fh:
            fh.write(body)
            body_file = fh.name
        try:
            out = self._gh_repo("pr", "create", "--head", head, "--base", base,
                           "--title", title, "--body-file", body_file).stdout
        finally:
            os.unlink(body_file)
        m = re.search(r"/pull/(\d+)", out)
        if not m:
            raise MthError("No se pudo leer el número del PR creado.", hint=out.strip())
        return int(m.group(1))

    def ensure_pr(self, head: str, base: str, title: str, body: str) -> int:
        """Return the open PR ``head → base``, creating it if needed (idempotent).

        Whether the work is already merged is decided by git ancestry, never by
        PR metadata: a branch name reused later must not match an old PR.
        """
        if pr := self.find_pr(head, base, "open"):
            return pr["number"]
        number = self.create_pr(head, base, title, body)
        say(f"· PR #{number} creado: {head} → {base}")
        return number

    def wait_checks(self, number: int, required: bool) -> None:
        """Block until CI finishes; fail-safe on red or (when required) absent CI.

        Raises:
            MthError: Failing checks, or no checks while ``required``.
        """
        for attempt in range(_POLL_ATTEMPTS):
            proc = self._gh_repo("pr", "checks", str(number), "--watch", "--fail-fast", check=False)
            text = (proc.stdout + proc.stderr).lower()
            if _NO_CHECKS not in text:
                if proc.returncode != 0:
                    raise MthError(f"La CI del PR #{number} está en rojo.",
                                   hint=(proc.stdout or proc.stderr).strip()[-1500:])
                say(f"· CI en verde en el PR #{number}")
                return
            if attempt < _POLL_ATTEMPTS - 1:
                time.sleep(_POLL_SECONDS)
        if required:
            raise MthError(f"El PR #{number} no tiene checks de CI y ci.required = true.",
                           hint="Configura CI en el repo o pon ci.required = false de forma explícita.")
        warn(f"El PR #{number} no tiene CI; se continúa porque ci.required = false.")

    def merge(self, number: int, subject: str, body: str) -> None:
        """Merge with a merge commit (history of the branch is preserved)."""
        self._gh_repo("pr", "merge", str(number), "--merge", "--subject", subject, "--body", body)
        say(f"· PR #{number} mergeado con merge commit")

    def release(self, tag: str, notes: str) -> None:
        if self._gh_repo("release", "view", tag, check=False).returncode == 0:
            return
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as fh:
            fh.write(notes or tag)
            notes_file = fh.name
        try:
            self._gh_repo("release", "create", tag, "--title", tag, "--notes-file", notes_file, "--verify-tag")
        finally:
            os.unlink(notes_file)
        say(f"· Release de GitHub {tag} publicada")

    def api(self, method: str, path: str, payload: dict | None = None, check: bool = True):
        if self.repo:
            path = path.replace("{owner}/{repo}", self.repo)
        args = ["api", "-X", method, path, "-H", "Accept: application/vnd.github+json"]
        if payload is not None:
            args += ["--input", "-"]
        return run(["gh", *args], cwd=self.root, check=check,
                   input_text=json.dumps(payload) if payload is not None else None)
