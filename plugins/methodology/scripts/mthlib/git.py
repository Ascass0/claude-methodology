"""Thin git wrapper. Every call goes through :func:`proc.run` (no shell)."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .errors import MthError
from .proc import run


class Git:
    """Git operations rooted at a working tree.

    Args:
        root: Top-level directory of the working tree.
        remote: Name of the remote used for integration.
    """

    def __init__(self, root: Path, remote: str = "origin") -> None:
        self.root = root
        self.remote = remote

    @classmethod
    def discover(cls, start: Path) -> "Git":
        """Locate the repository containing ``start``.

        Raises:
            MthError: ``start`` is not inside a git working tree.
        """
        proc = run(["git", "rev-parse", "--show-toplevel"], cwd=start, check=False)
        if proc.returncode != 0:
            raise MthError("No estás dentro de un repositorio git.")
        return cls(Path(proc.stdout.strip()))

    # -- primitives ---------------------------------------------------------
    def out(self, *args: str) -> str:
        return run(["git", *args], cwd=self.root).stdout.strip()

    def ok(self, *args: str) -> bool:
        return run(["git", *args], cwd=self.root, check=False).returncode == 0

    def try_run(self, *args: str):
        return run(["git", *args], cwd=self.root, check=False)

    # -- queries ------------------------------------------------------------
    def git_dir(self) -> Path:
        return Path(self.out("rev-parse", "--absolute-git-dir"))

    def common_dir(self) -> Path:
        """Directory shared by every worktree of the repository (``--git-common-dir``)."""
        return Path(self.out("rev-parse", "--path-format=absolute", "--git-common-dir"))

    def hooks_dir(self) -> Path:
        path = Path(self.out("rev-parse", "--git-path", "hooks"))
        return path if path.is_absolute() else self.root / path

    def current_branch(self) -> str:
        proc = self.try_run("symbolic-ref", "--quiet", "--short", "HEAD")
        if proc.returncode != 0:
            raise MthError("HEAD está desacoplado (detached).", hint="Cambia a una rama.")
        return proc.stdout.strip()

    def is_clean(self) -> bool:
        return self.out("status", "--porcelain") == ""

    def require_clean(self) -> None:
        if not self.is_clean():
            raise MthError("El árbol de trabajo tiene cambios sin confirmar.",
                           hint="Haz commit (skill mth-commit) o descarta los cambios.")

    def has_staged(self) -> bool:
        return not self.ok("diff", "--cached", "--quiet")

    def has_remote(self) -> bool:
        return self.remote in self.out("remote").split()

    def remote_ref(self, branch: str) -> str:
        return f"refs/remotes/{self.remote}/{branch}"

    def remote_has(self, branch: str) -> bool:
        return self.ok("rev-parse", "--verify", "--quiet", self.remote_ref(branch))

    def local_has(self, branch: str) -> bool:
        return self.ok("rev-parse", "--verify", "--quiet", f"refs/heads/{branch}")

    def remote_branches(self) -> list[str]:
        refs = self.out("for-each-ref", "--format=%(refname)", f"refs/remotes/{self.remote}/")
        prefix = f"refs/remotes/{self.remote}/"
        return [r[len(prefix):] for r in refs.splitlines() if r and not r.endswith("/HEAD")]

    def sha(self, ref: str) -> str:
        return self.out("rev-parse", ref)

    def is_ancestor(self, ancestor: str, descendant: str) -> bool:
        return self.ok("merge-base", "--is-ancestor", ancestor, descendant)

    def commits(self, rev_range: str, exclude: list[str] | None = None) -> list[tuple[str, str]]:
        """Non-merge commits in ``rev_range`` as ``(sha, message)``, oldest first.

        Args:
            rev_range: Revision range (``base..head``).
            exclude: Refs whose history is left out (external code such as upstream).
        """
        raw = self.out("log", "--reverse", "--no-merges", "--format=%H%x00%B%x1e", rev_range,
                       *[f"^{ref}" for ref in exclude or []])
        result = []
        for chunk in raw.split("\x1e"):
            chunk = chunk.strip("\n")
            if chunk:
                sha, _, message = chunk.partition("\x00")
                result.append((sha.strip(), message.strip()))
        return result

    def latest_version(self, prefix: str = "v") -> tuple[int, int, int]:
        """Highest ``<prefix>X.Y.Z`` tag, or ``(0, 0, 0)`` when none exists.

        Tags with another prefix (for example, those fetched from upstream) are ignored.
        """
        tag_re = re.compile(rf"^{re.escape(prefix)}(\d+)\.(\d+)\.(\d+)$")
        versions = [tuple(int(x) for x in m.groups())
                    for t in self.out("tag", "--list", f"{prefix}*").split()
                    if (m := tag_re.match(t))]
        return max(versions, default=(0, 0, 0))

    def changed_files(self, base: str) -> list[str]:
        """Files changed on HEAD since its merge-base with ``base``."""
        return [f for f in self.out("diff", "--name-only", f"{base}...HEAD").splitlines() if f]

    def worktree_changes(self) -> set[str]:
        """Files that differ from HEAD: modified, deleted, renamed (both paths) and new not ignored."""
        raw = run(["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"], cwd=self.root).stdout
        entries = raw.split("\0")
        changed: set[str] = set()
        i = 0
        while i < len(entries):
            entry = entries[i]
            i += 1
            if len(entry) < 4:
                continue
            status, path = entry[:2], entry[3:]
            changed.add(path)
            if "R" in status or "C" in status:  # the next entry is the original path
                if i < len(entries) and entries[i]:
                    changed.add(entries[i])
                i += 1
        return changed

    def remote_url(self) -> str | None:
        """The URL configured for the remote, as written (no ``insteadOf`` rewriting); None without remote."""
        proc = self.try_run("config", "--get", f"remote.{self.remote}.url")
        return proc.stdout.strip() or None if proc.returncode == 0 else None

    def github_repo(self) -> str | None:
        """``owner/repo`` of the remote when it is hosted on GitHub, else None."""
        proc = self.try_run("remote", "get-url", self.remote)
        m = re.search(r"github\.com[:/]([\w.-]+)/([\w.-]+?)(?:\.git)?/?$", proc.stdout.strip())
        return f"{m.group(1)}/{m.group(2)}" if proc.returncode == 0 and m else None

    def count(self, rev_range: str) -> int:
        return int(self.out("rev-list", "--count", rev_range) or 0)

    def tag_exists(self, tag: str) -> bool:
        return self.ok("rev-parse", "--verify", "--quiet", f"refs/tags/{tag}")

    def unchanged_since(self, rev: str) -> set[str]:
        """Files of ``rev`` whose working-tree content is identical to that commit.

        Raises:
            MthError: ``rev`` is not a commit of this repository.
        """
        if not self.ok("cat-file", "-e", f"{rev}^{{commit}}"):
            raise MthError(f"No existe el commit {rev} de trace.legacy_base.",
                           hint="Trae la historia completa (git fetch --unshallow) o corrige trace.legacy_base.")
        in_base = set(self.out("ls-tree", "-r", "--name-only", "-z", rev).split("\0"))
        changed = set(self.out("diff", "--name-only", "-z", rev).split("\0"))
        return {f for f in in_base - changed if f}

    def files(self) -> list[str]:
        """Tracked and untracked-but-not-ignored files (POSIX relative paths)."""
        raw = run(["git", "ls-files", "-co", "--exclude-standard", "-z"], cwd=self.root).stdout
        return sorted({f for f in raw.split("\0") if f and (self.root / f).is_file()})

    def merge_base(self, ref: str) -> str:
        """Common ancestor of HEAD and ``ref``.

        Raises:
            MthError: ``ref`` does not exist or shares no history with HEAD.
        """
        proc = self.try_run("merge-base", "HEAD", ref)
        if proc.returncode != 0 or not proc.stdout.strip():
            raise MthError(f"No se puede calcular el punto de partida de la rama respecto a {ref}.",
                           hint=f"Trae la rama (`git fetch {self.remote}`) y vuelve a intentarlo.")
        return proc.stdout.strip()

    def blob_chunks(self, rev: str, path: str, size: int = 1 << 20):
        """Yield the bytes of ``path`` at ``rev`` in chunks (nothing if the file did not exist there).

        Raises:
            MthError: Git cannot list or read the object, so a missing file is never confused with an unreadable one.
        """
        listed = self.try_run("ls-tree", "--name-only", "-z", rev, "--", path)
        if listed.returncode != 0:
            raise MthError(f"No se puede leer {path} en {rev[:7]}.", hint=(listed.stderr or "").strip() or None)
        if not listed.stdout.strip("\0"):
            return
        with subprocess.Popen(["git", "cat-file", "blob", f"{rev}:{path}"], cwd=self.root,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE) as proc:
            while chunk := proc.stdout.read(size):
                yield chunk
            err = proc.stderr.read().decode("utf-8", "replace").strip()
            if proc.wait() != 0:
                raise MthError(f"No se puede leer {path} en {rev[:7]}.", hint=err or None)

    def renamed_from(self, base: str) -> dict[str, str]:
        """Renames and copies detected between ``base`` and the working tree, as ``{new: old}``."""
        tokens = self.out("diff", "-M", "--name-status", "-z", base).split("\0")
        out, i = {}, 0
        while i < len(tokens) and tokens[i]:
            status = tokens[i]
            if status[0] in "RC" and i + 2 < len(tokens):
                out[tokens[i + 2]] = tokens[i + 1]
                i += 3
            else:
                i += 2
        return out

    def binary_by_attributes(self, paths: list[str]) -> set[str]:
        """Paths that ``.gitattributes`` marks as binary for diffs (``-diff`` or ``binary``)."""
        if not paths:
            return set()
        raw = run(["git", "check-attr", "-z", "--stdin", "diff"], cwd=self.root,
                  input_text="\0".join(paths) + "\0").stdout.split("\0")
        return {raw[i] for i in range(0, len(raw) - 2, 3) if raw[i + 2] == "unset"}

    # -- mutations ----------------------------------------------------------
    def fetch(self) -> None:
        if not self.has_remote():
            raise MthError(f"El repositorio no tiene el remoto '{self.remote}'.")
        self.out("fetch", "--prune", "--tags", self.remote)

    def checkout_synced(self, branch: str) -> None:
        """Check out ``branch`` and fast-forward it to its remote counterpart."""
        if self.local_has(branch):
            self.out("checkout", branch)
            proc = self.try_run("merge", "--ff-only", self.remote_ref(branch))
            if proc.returncode != 0:
                raise MthError(f"La rama local '{branch}' ha divergido de {self.remote}/{branch}.",
                               hint="Revisa los commits locales: nunca se reescribe historia compartida.")
        else:
            self.out("checkout", "-b", branch, "--track", f"{self.remote}/{branch}")

    def push(self, branch: str) -> None:
        self.out("push", "-u", self.remote, branch)

    def delete_branch(self, branch: str) -> None:
        """Delete ``branch`` locally and on the remote. Its commits survive in merges."""
        if self.remote_has(branch):
            self.out("push", self.remote, "--delete", branch)
        if self.local_has(branch):
            self.out("branch", "-D", branch)
