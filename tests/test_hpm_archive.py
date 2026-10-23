""".hpm files, hallux/hpm/archive.py: packing a package's folder, unpacking it safely,
reading only its manifest, fingerprints. Every archive here is made in a temporary folder."""
import gzip
import io
import os
import tarfile

import pytest

from hallux.hpm import archive
from hallux.hpm.archive import (
    ArchiveError, pack, package_files, read_manifest, sha256, to_machine, to_member, unpack,
)

MANIFEST = '''name = "kittystory"
version = "1.4"
memory_line = "kittystory: split-screen chat with characters"
[files]
app  = ["/usr/local/bin/kittystory", "/usr/local/share/apps/kittystory/**"]
seed = ["/usr/local/share/apps/kittystory/data/state.json"]
'''

FILES = {
    "files/root/usr/local/bin/kittystory": "# kittystory\nthe card\n",
    "files/root/usr/local/share/apps/kittystory/index.html": "<html></html>\n",
    "files/root/usr/local/share/apps/kittystory/sprites/emma.svg": "<svg/>\n",
    "files/root/usr/local/share/apps/kittystory/data/state.json": "{}\n",
    "files/home/.kittystory/packs/tsundere.pack": "a pack\n",
    "migrations/1-to-2.md": "# kittystory data format 1 → 2\n",
    "CHANGELOG.md": "## 1.4\n- the web app\n",
}


@pytest.fixture
def folder(tmp_path):
    return make(tmp_path / "kittystory-1.4")


def make(folder, files=FILES, manifest=MANIFEST):
    folder.mkdir(parents=True)
    (folder / "hpm.toml").write_text(manifest)
    for name, text in files.items():
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_text(text)
    return folder


def contents(folder):
    return {p.relative_to(folder).as_posix(): p.read_bytes()
            for p in sorted(folder.rglob("*")) if p.is_file()}


def tar_of(tmp_path, entries, name="bad.hpm"):
    """An archive made by hand: (TarInfo, bytes or None) for each entry."""
    out = tmp_path / name
    with tarfile.open(out, "w:gz") as tar:
        for info, data in entries:
            if data is not None:
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
            else:
                tar.addfile(info)
    return out


def regular(name, data=b"x"):
    return tarfile.TarInfo(name), data


def good_manifest():
    return regular("hpm.toml", MANIFEST.encode())


# ---------------------------------------------------------------- names

def test_names_and_machine_paths():
    assert to_machine("files/root/usr/local/bin/x") == "/usr/local/bin/x"
    assert to_machine("files/home/.kittystory/x") == "~/.kittystory/x"
    assert to_member("/usr/local/bin/x") == "files/root/usr/local/bin/x"
    assert to_member("~/.kittystory/x") == "files/home/.kittystory/x"
    for name in ("files/x", "files/root", "migrations/x.md", "files/other/x",
                 "files/root/proc/cpuinfo", "files/root/.hallux/memory.md"):
        with pytest.raises(ValueError):
            to_machine(name)


# ---------------------------------------------------------------- pack and unpack

def test_pack_then_unpack_gives_the_same_files(folder, tmp_path):
    out = pack(folder, tmp_path / "store" / "1.4.hpm")
    manifest = unpack(out, tmp_path / "unpacked")
    assert manifest.name == "kittystory" and str(manifest.version) == "1.4"
    assert contents(tmp_path / "unpacked") == contents(folder)


def test_the_times_are_kept(folder, tmp_path):
    card = folder / "files/root/usr/local/bin/kittystory"
    os.utime(card, (1_700_000_000, 1_700_000_000))
    unpack(pack(folder, tmp_path / "a.hpm"), tmp_path / "u")
    assert (tmp_path / "u/files/root/usr/local/bin/kittystory").stat().st_mtime == 1_700_000_000


def test_the_same_folder_packs_to_the_same_bytes(folder, tmp_path):
    first = pack(folder, tmp_path / "first.hpm").read_bytes()
    os.chmod(folder / "CHANGELOG.md", 0o600)                 # modes aren't kept
    assert pack(folder, tmp_path / "second.hpm").read_bytes() == first
    copy = make(tmp_path / "elsewhere" / "other-name")       # another folder, the same files
    for name in FILES:
        stamp = (folder / name).stat().st_mtime
        os.utime(copy / name, (stamp, stamp))
    os.utime(copy / "hpm.toml", ((folder / "hpm.toml").stat().st_mtime,) * 2)
    assert pack(copy, tmp_path / "third.hpm").read_bytes() == first


def test_the_manifest_comes_first(folder, tmp_path):
    with tarfile.open(pack(folder, tmp_path / "a.hpm")) as tar:
        names = tar.getnames()
    assert names[0] == "hpm.toml" and names[1:] == sorted(names[1:])


def test_read_manifest_reads_only_the_manifest(folder, tmp_path):
    out = pack(folder, tmp_path / "a.hpm")
    assert read_manifest(out).memory_line == "kittystory: split-screen chat with characters"


def test_sha256(folder, tmp_path):
    out = pack(folder, tmp_path / "a.hpm")
    assert sha256(out) == sha256(pack(folder, tmp_path / "b.hpm"))
    assert sha256(out).startswith("sha256:") and len(sha256(out)) == 7 + 64


def test_package_files_by_machine_path(folder, tmp_path):
    unpack(pack(folder, tmp_path / "a.hpm"), tmp_path / "u")
    found = package_files(tmp_path / "u")
    assert sorted(found) == [
        "/usr/local/bin/kittystory",
        "/usr/local/share/apps/kittystory/data/state.json",
        "/usr/local/share/apps/kittystory/index.html",
        "/usr/local/share/apps/kittystory/sprites/emma.svg",
        "~/.kittystory/packs/tsundere.pack",
    ]
    assert found["~/.kittystory/packs/tsundere.pack"].read_text() == "a pack\n"


def test_unpack_into_an_empty_folder_and_never_over_anything(folder, tmp_path):
    out = pack(folder, tmp_path / "a.hpm")
    (tmp_path / "empty").mkdir()
    unpack(out, tmp_path / "empty")
    (tmp_path / "full").mkdir()
    (tmp_path / "full" / "mine.txt").write_text("mine")
    with pytest.raises(ArchiveError, match="must be a new or empty folder"):
        unpack(out, tmp_path / "full")
    assert contents(tmp_path / "full") == {"mine.txt": b"mine"}


# ---------------------------------------------------------------- what pack refuses

def test_pack_refuses_a_folder_without_a_manifest(tmp_path):
    (tmp_path / "p").mkdir()
    with pytest.raises(ArchiveError, match="has no hpm.toml"):
        pack(tmp_path / "p", tmp_path / "a.hpm")


def test_pack_refuses_a_bad_manifest(tmp_path):
    folder = make(tmp_path / "p", files={}, manifest='name = "x"\n')
    with pytest.raises(ArchiveError, match="version is missing"):
        pack(folder, tmp_path / "a.hpm")
    assert not (tmp_path / "a.hpm").exists()


def test_pack_tells_every_problem_and_writes_nothing(folder, tmp_path):
    os.symlink("/etc/passwd", folder / "files/root/usr/local/bin/link")
    (folder / "notes.txt").write_text("not part of a package")
    (folder / "files/root/proc").mkdir()
    (folder / "files/root/proc/cpuinfo").write_text("imagined")
    (folder / "migrations/sub").mkdir()
    with pytest.raises(ArchiveError) as caught:
        pack(folder, tmp_path / "a.hpm")
    text = str(caught.value)
    for words in ("4 problems", "'files/root/usr/local/bin/link' is a link", "'notes.txt' is no part",
                  "under /proc", "migrations/ holds no folders"):
        assert words in text, words
    assert not list(tmp_path.glob("*.hpm*"))                 # no file, and no half of one


def test_pack_refuses_too_many_files(folder, tmp_path, monkeypatch):
    monkeypatch.setattr(archive, "FILES_MAX", 3)
    with pytest.raises(ArchiveError, match="more than 3"):
        pack(folder, tmp_path / "a.hpm")


# ---------------------------------------------------------------- what unpack refuses

def symlink(name, target):
    info = tarfile.TarInfo(name)
    info.type, info.linkname = tarfile.SYMTYPE, target
    return info, None


def hardlink(name, target):
    info = tarfile.TarInfo(name)
    info.type, info.linkname = tarfile.LNKTYPE, target
    return info, None


def device(name):
    info = tarfile.TarInfo(name)
    info.type = tarfile.CHRTYPE
    return info, None


@pytest.mark.parametrize("entry, words", [
    (symlink("files/root/usr/bin/x", "/etc/passwd"), "is a link or a special file"),
    (hardlink("files/root/usr/bin/x", "hpm.toml"), "is a link or a special file"),
    (device("files/root/usr/bin/x"), "is a link or a special file"),
    (regular("/etc/passwd"), "is an absolute name"),
    (regular("files/root/../../etc/passwd"), "has an empty name, . or .."),
    (regular("files/root/usr//x"), "has an empty name, . or .."),
    (regular("C:/x"), "is an absolute name"),
    (regular("files\\root\\x"), "is an absolute name"),
    (regular("files/root/.hallux/memory.md"), "under /.hallux"),
    (regular("files/other/x"), "files/ holds only root/ and home/"),
    (regular("setup.py"), "is no part of a package"),
    (regular("migrations/run.sh"), "migrations/ holds only .md notes"),
    (regular("files/root/a\nb"), "control character"),
])
def test_unpack_refuses_and_writes_nothing(tmp_path, entry, words):
    bad = tar_of(tmp_path, [good_manifest(), regular("files/root/usr/bin/ok"), entry])
    with pytest.raises(ArchiveError, match=words.replace(".", r"\.").replace("/", "/")):
        unpack(bad, tmp_path / "into")
    assert not (tmp_path / "into").exists()


def test_unpack_refuses_a_name_twice(tmp_path):
    bad = tar_of(tmp_path, [good_manifest(), regular("CHANGELOG.md"), regular("CHANGELOG.md")])
    with pytest.raises(ArchiveError, match="is in it twice"):
        unpack(bad, tmp_path / "into")


def test_unpack_refuses_too_many_files(tmp_path, monkeypatch):
    monkeypatch.setattr(archive, "FILES_MAX", 3)
    bad = tar_of(tmp_path, [good_manifest()] + [regular(f"files/root/x/{n}") for n in range(5)])
    with pytest.raises(ArchiveError, match="more than 3 files"):
        unpack(bad, tmp_path / "into")
    assert not (tmp_path / "into").exists()


def test_unpack_refuses_too_big(tmp_path, monkeypatch):
    monkeypatch.setattr(archive, "BYTES_MAX", 1000)
    bad = tar_of(tmp_path, [good_manifest(), regular("files/root/big", b"x" * 2000)])
    with pytest.raises(ArchiveError, match="MB unpacked"):
        unpack(bad, tmp_path / "into")


def test_unpack_refuses_without_a_manifest_or_with_a_bad_one(tmp_path):
    with pytest.raises(ArchiveError, match="no hpm.toml in it"):
        unpack(tar_of(tmp_path, [regular("CHANGELOG.md")]), tmp_path / "a")
    with pytest.raises(ArchiveError, match="version is missing"):
        unpack(tar_of(tmp_path, [regular("hpm.toml", b'name = "x"')], "b.hpm"), tmp_path / "b")
    with pytest.raises(ArchiveError, match="bigger than 64 KB"):
        unpack(tar_of(tmp_path, [regular("hpm.toml", b"#" * 70_000)], "c.hpm"), tmp_path / "c")


def test_unpack_tells_every_problem_at_once(tmp_path):
    bad = tar_of(tmp_path, [regular("/abs"), symlink("files/root/l", "/"), regular("junk")])
    with pytest.raises(ArchiveError) as caught:
        unpack(bad, tmp_path / "into")
    assert "4 problems" in str(caught.value)                 # and no hpm.toml


@pytest.mark.parametrize("data", [b"not an archive at all", b"", gzip.compress(b"not a tar")])
def test_unpack_refuses_what_isnt_an_archive(tmp_path, data):
    (tmp_path / "x.hpm").write_bytes(data)
    with pytest.raises(ArchiveError, match="not a package hpm can read"):
        unpack(tmp_path / "x.hpm", tmp_path / "into")
    with pytest.raises(ArchiveError):
        read_manifest(tmp_path / "x.hpm")


def test_a_failure_while_writing_leaves_nothing(folder, tmp_path, monkeypatch):
    out = pack(folder, tmp_path / "a.hpm")
    real_utime, calls = os.utime, []

    def failing(*args, **kwargs):
        calls.append(args)
        if len(calls) == 3:
            raise OSError(28, "No space left on device")
        return real_utime(*args, **kwargs)

    monkeypatch.setattr(archive.os, "utime", failing)
    with pytest.raises(OSError, match="No space left"):
        unpack(out, tmp_path / "into")
    assert not (tmp_path / "into").exists()
    (tmp_path / "empty").mkdir()
    calls.clear()
    with pytest.raises(OSError):
        unpack(out, tmp_path / "empty")
    assert list((tmp_path / "empty").iterdir()) == []        # empty again, and still there


def test_read_manifest_of_an_archive_without_one(tmp_path):
    with pytest.raises(ArchiveError, match="no hpm.toml in it"):
        read_manifest(tar_of(tmp_path, [regular("CHANGELOG.md")]))
