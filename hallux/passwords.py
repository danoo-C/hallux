"""The machine's passwords, checked where they were typed.

A password typed at a hidden prompt never goes to the AI. hallux keeps a salted hash per
name in /.hallux/passwords.json, which the fake OS can't see, and tells the AI only whether
what was typed is right. So a real password typed by habit stays on this computer.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path

SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1, "dklen": 32}


class Passwords:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.pending: tuple[str, dict[str, str]] | None = None   # a new password, typed once

    def check(self, name: str, typed: str) -> str:
        """Is `typed` the password stored under `name`? "yes", "no", or "unset" (none stored)."""
        self.cancel()
        entry = self._load().get(name)
        if entry is None:
            return "unset"
        return "yes" if _matches(entry, typed) else "no"

    def offer(self, name: str, typed: str) -> str:
        """A new password for `name`. It's saved once it has been typed the same twice in a row:
        "first" (held, waiting for the second time), "saved" or "mismatch"."""
        pending, self.pending = self.pending, None
        if pending is None or pending[0] != name:
            if typed:                                    # an empty password is never held
                self.pending = (name, _entry(typed))
            return "first"
        if not _matches(pending[1], typed):
            return "mismatch"
        self._save(self._load() | {name: pending[1]})
        return "saved"

    def cancel(self) -> None:
        """Something else happened between the two times: the new password is dropped."""
        self.pending = None

    def _load(self) -> dict[str, dict[str, str]]:
        try:
            stored = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return stored if isinstance(stored, dict) else {}

    def _save(self, entries: dict[str, dict[str, str]]) -> None:
        self.path.parent.mkdir(exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
        os.chmod(temp, 0o600)
        os.replace(temp, self.path)                      # atomic, like the memory


def _entry(password: str) -> dict[str, str]:
    salt = os.urandom(16)
    return {"salt": salt.hex(), "hash": _hash(password, salt).hex()}


def _matches(entry: dict[str, str], password: str) -> bool:
    try:
        salt, stored = bytes.fromhex(entry["salt"]), bytes.fromhex(entry["hash"])
    except (KeyError, TypeError, ValueError):            # a file someone edited by hand
        return False
    return hmac.compare_digest(_hash(password, salt), stored)


def _hash(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode("utf-8", "surrogatepass"), salt=salt, **SCRYPT)
