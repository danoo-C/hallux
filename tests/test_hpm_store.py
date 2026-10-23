"""The store on your PC (hallux/hpm/store.py), and how hpm finds a world and its user
(hallux/hpm/world.py). Every store and world is a temporary folder."""
import os
from pathlib import Path

import pytest

from hallux.disk import Disk
from hallux.hpm.archive import pack
from hallux.hpm.manifest import Version
from hallux.hpm.store import Store, store_home
from hallux.hpm.world import HpmError, find_world, homes, world_user


def release(tmp_path, name="kittystory", version="1.4"):
    folder = tmp_path / "pkgs" / f"{name}-{version}"
    folder.mkdir(parents=True)
    (folder / "hpm.toml").write_text(f'name = "{name}"\nversion = "{version}"\n')
    return pack(folder, tmp_path / "pkgs" / f"{name}-{version}.hpm")


# ---------------------------------------------------------------- where the store is

def test_the_store_is_found_from_the_three_variables(tmp_path):
    assert store_home({"HPM_HOME": str(tmp_path / "h"), "XDG_DATA_HOME": "/x"}) == tmp_path / "h"
    assert store_home({"XDG_DATA_HOME": str(tmp_path)}) == tmp_path / "hallux" / "hpm"
    assert store_home({}) == Path.home() / ".local" / "share" / "hallux" / "hpm"
    assert store_home({"HPM_HOME": ""}) == Path.home() / ".local" / "share" / "hallux" / "hpm"


def test_the_tests_never_reach_the_real_store():
    assert os.environ.get("HPM_HOME"), "conftest sets HPM_HOME for every test"


# ---------------------------------------------------------------- releases

def test_releases_latest_and_add(tmp_path):
    store = Store(tmp_path / "store")
    assert store.releases("kittystory") == [] and store.latest("kittystory") is None
    store.add(release(tmp_path, version="1.3"))
    store.add(release(tmp_path, version="1.10"))
    with pytest.raises(HpmError):
        store.add(release(tmp_path, version="1.4"))                 # 1.4 < 1.10
    assert [str(r.version) for r in store.releases("kittystory")] == ["1.3", "1.10"]
    latest = store.latest("kittystory")
    assert latest.version == Version("1.10")
    assert latest.path == tmp_path / "store" / "local" / "kittystory" / "1.10.hpm"
    assert latest.manifest().name == "kittystory"
    assert store.find("kittystory") == latest
    assert store.names() == ["kittystory"]


def test_add_refuses_a_version_that_is_there_and_a_lower_one(tmp_path):
    store = Store(tmp_path / "store")
    store.add(release(tmp_path, version="1.4"))
    with pytest.raises(HpmError, match="is in the store already"):
        store.add(release(tmp_path / "again", version="1.4"))
    with pytest.raises(HpmError, match=r"1\.4\.0 is in the store already \(as 1\.4\)"):
        store.add(release(tmp_path / "zero", version="1.4.0"))
    with pytest.raises(HpmError, match="lower than the store's latest, 1.4"):
        store.add(release(tmp_path / "low", version="1.3"))
    assert [str(r.version) for r in store.releases("kittystory")] == ["1.4"]


def test_add_leaves_the_packed_file_where_it_was(tmp_path):
    store = Store(tmp_path / "store")
    file = release(tmp_path)
    store.add(file)
    assert file.exists()


def test_add_refuses_what_isnt_a_package(tmp_path):
    (tmp_path / "x.hpm").write_bytes(b"not a package")
    with pytest.raises(HpmError, match="not a package hpm can read"):
        Store(tmp_path / "store").add(tmp_path / "x.hpm")


def test_a_stranger_in_the_store_is_told(tmp_path):
    store = Store(tmp_path / "store")
    store.add(release(tmp_path))
    (store.local / "kittystory" / "notes.txt").write_text("mine")
    with pytest.raises(HpmError, match="notes.txt doesn't belong in the store"):
        store.releases("kittystory")
    (store.local / "kittystory" / "notes.txt").unlink()
    (store.local / "kittystory" / "new.hpm").write_text("x")
    with pytest.raises(HpmError, match="'new' is no version"):
        store.releases("kittystory")


def test_a_copy_under_way_is_not_a_release(tmp_path):
    store = Store(tmp_path / "store")
    store.add(release(tmp_path))
    (store.local / "kittystory" / ".1.5.hpm.hallux-1234abcd").write_text("half")
    assert [str(r.version) for r in store.releases("kittystory")] == ["1.4"]


# ---------------------------------------------------------------- finding the world

@pytest.fixture
def world(tmp_path):
    root = tmp_path / "worlds" / "test-hallux"
    (root / ".hallux").mkdir(parents=True)
    (root / "home" / "danika-hous" / ".kittystory" / "chars" / "Emma").mkdir(parents=True)
    return root


def test_the_world_from_a_folder_deep_inside_it(world):
    deep = world / "home" / "danika-hous" / ".kittystory" / "chars" / "Emma"
    assert find_world(start=deep) == world
    assert find_world(start=world) == world


def test_no_world_without_a_hallux_folder(tmp_path):
    (tmp_path / "plain").mkdir()
    with pytest.raises(HpmError, match="is in no Hallux world"):
        find_world(start=tmp_path / "plain")
    with pytest.raises(HpmError, match="is no Hallux world: it has no .hallux folder"):
        find_world(given=tmp_path / "plain")


def test_world_given_by_flag(world, tmp_path):
    assert find_world(start=tmp_path, given=world) == world


def test_your_home_is_never_a_world(monkeypatch, tmp_path):
    (tmp_path / ".hallux").mkdir()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    with pytest.raises(HpmError, match="it is your home"):
        find_world(given=tmp_path)
    (tmp_path / "w").mkdir()
    with pytest.raises(HpmError, match="is in no Hallux world"):
        find_world(start=tmp_path / "w")                 # home's .hallux doesn't count


# ---------------------------------------------------------------- the world's user

def test_the_user_from_passwd(world):
    (world / "etc").mkdir()
    (world / "etc" / "passwd").write_text(
        "root:x:0:0:root:/root:/bin/bash\n"
        "nobody:x:65534:65534:nobody:/nonexistent:/usr/sbin/nologin\n"
        "danika-hous:x:1000:1000:Danika:/home/danika-hous:/bin/bash\n")
    assert homes(Disk(world)) == ["/home/danika-hous"]
    assert world_user(Disk(world)) == "/home/danika-hous"


def test_several_users_must_be_named(world):
    (world / "etc").mkdir()
    (world / "etc" / "passwd").write_text("a:x:1000:1000::/home/a:/bin/sh\n"
                                          "b:x:1001:1001::/home/b:/bin/sh\n")
    with pytest.raises(HpmError, match=r"several users \(a, b\); say which with --user"):
        world_user(Disk(world))
    assert world_user(Disk(world), "b") == "/home/b"
    with pytest.raises(HpmError, match="no user 'c'; its users: a, b"):
        world_user(Disk(world), "c")


def test_a_short_passwd_line_still_gives_a_home(world):
    (world / "etc").mkdir()
    (world / "etc" / "passwd").write_text("user:x:1000\n")          # as the AI may write it
    assert homes(Disk(world)) == ["/home/user"]


def test_without_passwd_the_homes_that_arent_empty(world):
    (world / "home" / "user").mkdir()                    # the skeleton's, empty
    assert homes(Disk(world)) == ["/home/danika-hous"]
    os.rmdir(world / "home" / "user")
    (world / "home" / "other").mkdir()
    (world / "home" / "other" / "x").write_text("x")
    assert homes(Disk(world)) == ["/home/danika-hous", "/home/other"]


def test_only_empty_homes_are_still_homes(tmp_path):
    root = tmp_path / "w"
    (root / ".hallux").mkdir(parents=True)
    (root / "home" / "user").mkdir(parents=True)
    assert world_user(Disk(root)) == "/home/user"


def test_no_home_at_all(tmp_path):
    root = tmp_path / "w"
    (root / ".hallux").mkdir(parents=True)
    assert homes(Disk(root)) == [] and world_user(Disk(root)) is None


def test_a_home_that_links_out_of_the_world_is_not_one(world, tmp_path):
    (world / "home" / "away").symlink_to(tmp_path)
    assert homes(Disk(world)) == ["/home/danika-hous"]
