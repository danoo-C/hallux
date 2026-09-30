"""The machine's disk: a real folder, seen through the eyes of the fake OS.

Every path the AI uses is a path inside the fake machine ("/home/user/notes.md").
Disk maps it into the root folder and refuses anything that would leave it. The folder
/.hallux (the machine's memory and hardware config) is invisible to the fake OS: only
the memory methods reach it.

Methods return plain JSON-able data. They fail by raising OSError (always with an
errno) or ValueError; hallux.tools turns those into tool results for the AI.
"""
from __future__ import annotations

import errno
import fnmatch
import os
import posixpath
import shutil
import stat
from datetime import datetime
from pathlib import Path

HIDDEN_NAME = ".hallux"
READ_LIMIT = 64 * 1024        # bytes returned per read_file call
FIND_LIMIT = 1000             # entries returned per find call


def _fail(code: int) -> OSError:
    return OSError(code, os.strerror(code))


def _replace_once(text: str, old: str, new: str) -> str:
    count = text.count(old)
    if count != 1:
        raise ValueError(f"`old` matches {count} times, it must match exactly once")
    return text.replace(old, new, 1)


def _utf8_cut(data: bytes) -> int:
    """Length of `data` without a trailing, incomplete UTF-8 character."""
    for back in range(1, min(4, len(data)) + 1):
        byte = data[-back]
        if byte & 0xC0 != 0x80:                   # the lead byte of the last character
            needed = 1 if byte < 0xC0 else 2 if byte < 0xE0 else 3 if byte < 0xF0 else 4
            return len(data) if back >= needed else len(data) - back
    return len(data)


class Disk:
    def __init__(self, root: Path | str, cwd: str = "/"):
        self.root = Path(root).resolve()
        self.hidden = self.root / HIDDEN_NAME
        self.memory_file = self.hidden / "memory.md"
        self.cwd = cwd

    # ------------------------------------------------------------------ paths

    def virtual(self, path: str) -> str:
        """The absolute, normalized path inside the fake machine: "../x" from /home -> "/x"."""
        return "/" + posixpath.normpath(posixpath.join(self.cwd, path)).lstrip("/")

    def real(self, path: str, follow: bool = True) -> Path:
        """Map a path inside the fake machine to a real path inside the root, or refuse.

        follow=False leaves the last component unresolved, for operations on a symlink
        itself (rm, mv, stat) rather than on what it points to.
        """
        rel = self.virtual(path).lstrip("/")
        if follow or not rel:
            return self._check((self.root / rel).resolve())
        parent, name = posixpath.split(rel)
        return self._check((self.root / parent).resolve() / name)

    def _check(self, real: Path) -> Path:
        if real != self.root and self.root not in real.parents:
            raise _fail(errno.EACCES)             # a symlink pointing out of the machine
        if real == self.hidden or self.hidden in real.parents:
            raise _fail(errno.ENOENT)             # doesn't exist, as far as the OS knows
        return real

    def _virtual_of(self, real: Path) -> str:
        rel = real.relative_to(self.root).as_posix()
        return "/" if rel == "." else "/" + rel

    def _entry(self, real: Path, name: str) -> dict:
        st = real.lstat()
        entry = {
            "name": name,
            "mode": stat.filemode(st.st_mode),
            "size": st.st_size,
            "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
        }
        if stat.S_ISLNK(st.st_mode):
            target = os.readlink(real)
            inside = Path(target).is_absolute() and (Path(target) == self.root
                                                     or self.root in Path(target).parents)
            entry["target"] = self._virtual_of(Path(target)) if inside else target
        return entry

    # ------------------------------------------------------------------ reading

    def list_dir(self, path: str = ".") -> list[dict]:
        real = self.real(path)
        with os.scandir(real) as it:
            names = sorted(e.name for e in it if Path(e.path) != self.hidden)
        return [self._entry(real / name, name) for name in names]

    def stat(self, path: str) -> dict:
        real = self.real(path, follow=False)
        return self._entry(real, posixpath.basename(self.virtual(path)) or "/")

    def read_file(self, path: str, offset: int = 0) -> dict:
        real = self.real(path)
        size = real.stat().st_size
        with real.open("rb") as f:
            f.seek(offset)
            data = f.read(READ_LIMIT)
        if b"\0" in data:
            return {"binary": True, "size": size}
        truncated = offset + len(data) < size
        if truncated:
            data = data[:_utf8_cut(data)]
        result = {"text": data.decode("utf-8", "replace"), "size": size, "truncated": truncated}
        if truncated:
            result["next_offset"] = offset + len(data)
        return result

    def find(self, path: str = ".", pattern: str = "*") -> dict:
        base = self.real(path)
        entries = []
        for dirpath, dirnames, filenames in os.walk(base):    # never descends into symlinks
            here = Path(dirpath)
            if here == self.root:
                dirnames[:] = [d for d in dirnames if d != HIDDEN_NAME]
            dirnames.sort()
            for name in sorted(dirnames + filenames):
                if not fnmatch.fnmatchcase(name, pattern):
                    continue
                real = here / name
                kind = "l" if real.is_symlink() else "d" if real.is_dir() else "f"
                entries.append({"path": self._virtual_of(real), "type": kind})
                if len(entries) >= FIND_LIMIT:
                    return {"entries": entries, "truncated": True}
        return {"entries": entries, "truncated": False}

    # ------------------------------------------------------------------ writing

    def write_file(self, path: str, content: str, append: bool = False) -> dict:
        real = self.real(path)
        with real.open("a" if append else "w", encoding="utf-8", newline="") as f:
            f.write(content)
        return {"ok": True, "size": real.stat().st_size}

    def edit_file(self, path: str, old: str, new: str) -> dict:
        real = self.real(path)
        with real.open(encoding="utf-8", newline="") as f:
            text = _replace_once(f.read(), old, new)
        with real.open("w", encoding="utf-8", newline="") as f:
            f.write(text)
        return {"ok": True}

    def make_dir(self, path: str, parents: bool = False) -> dict:
        self.real(path).mkdir(parents=parents, exist_ok=parents)
        return {"ok": True}

    def chdir(self, path: str) -> dict:
        real = self.real(path)
        if not real.exists():
            raise _fail(errno.ENOENT)
        if not real.is_dir():
            raise _fail(errno.ENOTDIR)
        self.cwd = self.virtual(path)
        return {"cwd": self.cwd}

    def remove(self, path: str, recursive: bool = False) -> dict:
        real = self.real(path, follow=False)
        if real == self.root:                     # rm -rf /: empty the machine, keep its memory
            if not recursive:
                raise _fail(errno.EISDIR)
            for child in self.root.iterdir():
                if child != self.hidden:
                    self._delete(child)
            return {"ok": True}
        if real.is_dir() and not real.is_symlink() and not recursive:
            raise _fail(errno.EISDIR)
        if not real.exists() and not real.is_symlink():
            raise _fail(errno.ENOENT)
        self._delete(real)
        return {"ok": True}

    @staticmethod
    def _delete(real: Path) -> None:
        if real.is_dir() and not real.is_symlink():
            shutil.rmtree(real)
        else:
            real.unlink()                         # a symlink goes, never what it points to

    def move(self, src: str, dst: str) -> dict:
        source = self.real(src, follow=False)
        if source == self.root:
            raise _fail(errno.EBUSY)
        if not source.exists() and not source.is_symlink():
            raise _fail(errno.ENOENT)
        target = self._destination(source, dst)
        if source.is_dir() and not source.is_symlink() and (
                target == source or source in target.parents):
            raise _fail(errno.EINVAL)             # a directory into itself
        shutil.move(source, target)
        return {"ok": True, "path": self._virtual_of(target)}

    def copy(self, src: str, dst: str, recursive: bool = False) -> dict:
        source = self.real(src)                   # cp follows symlinks
        target = self._destination(source, dst)
        if source.is_dir():
            if not recursive:
                raise _fail(errno.EISDIR)
            if target == source or source in target.parents:
                raise _fail(errno.EINVAL)
            shutil.copytree(source, target, symlinks=True)   # links stay links: nothing
        else:                                                # outside the root gets copied in
            try:
                shutil.copy2(source, target)
            except shutil.SameFileError:
                raise _fail(errno.EINVAL) from None
        return {"ok": True, "path": self._virtual_of(target)}

    def _destination(self, source: Path, dst: str) -> Path:
        """Like mv and cp: an existing directory as the destination means "into it"."""
        target = self.real(dst, follow=False)
        if target.is_dir():
            target = self._check(target.resolve() / source.name)
        return target

    # ------------------------------------------------------------------ memory

    def memory_read(self) -> dict:
        exists = self.memory_file.exists()
        return {"text": self.memory_file.read_text(encoding="utf-8") if exists else ""}

    def memory_edit(self, old: str, new: str) -> dict:
        text = self.memory_read()["text"]
        text = _replace_once(text, old, new) if old else text + new
        self.hidden.mkdir(exist_ok=True)
        temp = self.memory_file.with_suffix(".tmp")
        temp.write_text(text, encoding="utf-8", newline="")
        os.replace(temp, self.memory_file)        # atomic: a crash never leaves half a memory
        return {"ok": True, "size": len(text)}
