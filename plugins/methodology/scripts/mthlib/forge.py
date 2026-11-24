"""Hosting platform of the remote (SPEC-0016, ADR-0012): deduced from its URL, never from its credentials."""
from __future__ import annotations

import re

GITHUB, GITLAB, NONE = "github", "gitlab", "none"
FORGES = (GITHUB, GITLAB, NONE)

_URL = re.compile(r"^[a-z][a-z0-9+.-]*://(?:[^@/]*@)?(?P<host>[^/:]+)")
_SCP = re.compile(r"^(?:[^@/:]+@)?(?P<host>[^/:@]+):(?!//)")


def host_of(url: str) -> str | None:
    """Host of a remote URL (``https://``, ``ssh://`` or ``user@host:path``), lowercase; None if unreadable.

    The user and password of the URL are never part of the result.
    """
    text = url.strip()
    m = _URL.match(text) or _SCP.match(text)
    return m.group("host").lower() if m else None


def forge_of(url: str | None) -> str:
    """``github`` for github.com; ``gitlab`` for gitlab.com or a host whose first label is ``gitlab``; else ``none``."""
    host = host_of(url or "")
    if host == "github.com":
        return GITHUB
    if host and (host == "gitlab.com" or host.split(".")[0] == "gitlab"):
        return GITLAB
    return NONE
