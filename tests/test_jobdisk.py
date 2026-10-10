"""The fenced disk of a job, hallux/jobdisk.py, on a test world. No model, no session, no
table: a Disk, a folder, a list of files and a number."""
import errno
import os
import stat
import threading

import pytest

import hallux.jobdisk
from hallux import addons
from hallux.disk import Disk
from hallux.importing import carry_out
from hallux.jobdisk import BYTES_MAX, FILES_MAX, FolderGone, JobDisk, sweep

BEAT, NEON = "BPM = 120\nSONG:\n", "BPM = 90\n# neon\nSONG:\n"


@pytest.fixture
def root(tmp_path):
    root = tmp_path / "world"
    music = root / "home" / "user" / "Music"
    (music / "old").mkdir(parents=True)
    (music / "beat.score").write_text(BEAT)
    (music / "neon.score").write_text(NEON)
    (music / "My Song.score").write_text("the user's own name\n")
    (music / "old" / "first.score").write_text("an early one\n")
    for folder in ("etc", "usr/local/bin", "root", "tmp/work", ".hallux"):
        (root / folder).mkdir(parents=True)
    (root / "etc" / "passwd").write_text("user:x:1000\n")
    (root / ".hallux" / "memory.md").write_text("# memory\n")
    return root


@pytest.fixture
def disk(root):
    return Disk(root)


@pytest.fixture
def music(root):
    return root / "home" / "user" / "Music"


@pytest.fixture
def job(disk):
    """A job in the user's Music folder that was given one score to change."""
    return JobDisk(disk, "/home/user/Music", ["/home/user/Music/neon.score"], 30001)


def refused(code, fn, *args, path=None, **more):
    """The call is refused with this errno. Returns the path the refusal names."""
    with pytest.raises(OSError) as info:
        fn(*args, **more)
    assert info.value.errno == code, errno.errorcode.get(info.value.errno)
    if path is not None:
        assert info.value.filename == path
    return info.value.filename


def tree(folder):
    """Every file of a folder with what it holds, byte for byte."""
    return {str(path.relative_to(folder)): path.read_bytes() if path.is_file() else None
            for path in sorted(folder.rglob("*"))}


def copies(root, pid=30001):
    return tree(root / ".hallux" / "jobs" / str(pid))


# ---------------------------------------------------------------- the folder

@pytest.mark.parametrize("folder, code", [
    ("/", errno.EACCES), ("/home", errno.EACCES), ("/home/user", errno.EACCES),
    ("/root", errno.EACCES), ("/etc", errno.EACCES), ("/usr/local/bin", errno.EACCES),
    ("/usr", errno.EACCES),
    ("/home/user/Music/beat.score", errno.ENOTDIR),          # a file
    ("/home/user/Videos", errno.ENOENT),                     # not there
    ("/.hallux", errno.ENOENT),                              # hidden, as always
])
def test_a_folder_no_job_may_work_in_is_refused(disk, folder, code):
    assert refused(code, JobDisk, disk, folder) == folder    # and the refusal names it


def test_the_folder_is_checked_as_it_really_is(disk, root, tmp_path):
    (root / "home" / "user" / "Settings").symlink_to(root / "etc")
    (root / "home" / "user" / "Mine").symlink_to(root / "home" / "user")
    (root / "home" / "user" / "Out").symlink_to(tmp_path)
    refused(errno.EACCES, JobDisk, disk, "/home/user/Settings", path="/home/user/Settings")
    refused(errno.EACCES, JobDisk, disk, "/home/user/Mine")          # a home folder, by a link
    refused(errno.EACCES, JobDisk, disk, "/home/user/Out")           # out of the machine: the jail
    (root / "home" / "user" / "Songs").symlink_to(root / "home" / "user" / "Music")
    by_link = JobDisk(disk, "/home/user/Songs")                      # a link to a good folder
    assert by_link.read_text("beat.score") == BEAT


@pytest.mark.parametrize("folder", ["/home/user/Music", "/tmp/work", "/root/Music", "/tmp",
                                    "/home/user/.etc"])
def test_folders_a_job_may_work_in(disk, root, folder):
    disk.real(folder).mkdir(exist_ok=True)
    assert JobDisk(disk, folder).folder == folder


def test_a_relative_folder_starts_at_the_machines_working_directory(disk):
    refused(errno.ENOENT, JobDisk, disk, "Music", path="/Music")
    disk.chdir("/home/user")
    job = JobDisk(disk, "Music")
    assert job.folder == "/home/user/Music" and job.read_text("beat.score") == BEAT
    refused(errno.EACCES, JobDisk, disk, ".", path="/home/user")


# ---------------------------------------------------------------- the files it is given

def test_each_file_in_the_list_is_checked(disk, root):
    here = "/home/user/Music"
    for edit, code, named in [
            ([f"{here}/nope.score"], errno.ENOENT, f"{here}/nope.score"),
            ([f"{here}/old"], errno.EISDIR, f"{here}/old"),
            (["/etc/passwd"], errno.EACCES, "/etc/passwd"),              # outside the folder
            ([f"{here}/../../../etc/passwd"], errno.EACCES, "/etc/passwd"),
            ([f"{here}/beat.score", f"{here}/neon.score", f"{here}/beat.score"], errno.EINVAL,
             f"{here}/beat.score"),                                      # twice
            (["/.hallux/memory.md"], errno.ENOENT, "/.hallux/memory.md")]:
        assert refused(code, JobDisk, disk, here, edit) == named, edit
    for n in range(9):
        (root / "home" / "user" / "Music" / f"s{n}.score").write_text("x")
    refused(errno.E2BIG, JobDisk, disk, here, [f"{here}/s{n}.score" for n in range(9)])
    eight = JobDisk(disk, here, [f"{here}/s{n}.score" for n in range(8)])
    assert eight.edit == [f"{here}/s{n}.score" for n in range(8)]
    assert not (root / ".hallux" / "jobs").exists()          # a refusal leaves nothing behind


def test_given_files_are_paths_of_the_machine(disk):
    disk.chdir("/home/user")
    job = JobDisk(disk, "Music", ["Music/neon.score", "Music/old/first.score"])
    assert job.edit == ["/home/user/Music/neon.score", "/home/user/Music/old/first.score"]
    assert job.write_file("old/first.score", "changed\n") == {"ok": True, "size": 8}


def test_a_name_the_user_chose_is_fine_as_a_given_file(disk, music):
    (music / ".hidden score").write_text("with a dot in front\n")
    job = JobDisk(disk, "/home/user/Music", ["/home/user/Music/My Song.score",
                                             "/home/user/Music/.hidden score"])
    job.write_file("My Song.score", "the job's version\n")
    job.edit_file(".hidden score", "dot", "DOT")
    assert job.read_text("My Song.score") == "the job's version\n"
    assert job.read_text(".hidden score") == "with a DOT in front\n"


def test_a_given_file_too_big_to_write_back_is_refused_at_once(disk, music):
    (music / "huge.score").write_bytes(b"#" * (BYTES_MAX + 1))
    (music / "big.score").write_bytes(b"#" * BYTES_MAX)
    refused(errno.EFBIG, JobDisk, disk, "/home/user/Music", ["/home/user/Music/huge.score"],
            path="/home/user/Music/huge.score")
    JobDisk(disk, "/home/user/Music", ["/home/user/Music/big.score"])       # just fits


def test_two_names_for_one_file_are_one_file(disk, music):
    (music / "also-neon.score").symlink_to("neon.score")
    refused(errno.EINVAL, JobDisk, disk, "/home/user/Music",
            ["/home/user/Music/neon.score", "/home/user/Music/also-neon.score"])
    job = JobDisk(disk, "/home/user/Music", ["/home/user/Music/also-neon.score"], 30001)
    job.write_file("neon.score", "changed\n")                # given under its second name
    assert job.read_text("also-neon.score") == job.read_text("neon.score") == "changed\n"
    job.write_file("also-neon.score", "again\n", append=True)
    assert job.read_text("neon.score") == "changed\nagain\n"
    assert copies(music.parent.parent.parent) == {"neon.score": b"changed\nagain\n"}    # one copy


# ---------------------------------------------------------------- reading, and the fence

def test_a_job_reads_everything_in_its_folder(job):
    assert job.read_text("beat.score") == BEAT
    assert job.read_file("/home/user/Music/old/first.score") == {
        "text": "an early one\n", "size": 13, "truncated": False}
    assert job.read_file("old/../beat.score", offset=6)["text"] == "120\nSONG:\n"
    assert [entry["name"] for entry in job.list_dir()] == [
        "My Song.score", "beat.score", "neon.score", "old"]
    assert [entry["name"] for entry in job.list_dir("old")] == ["first.score"]
    assert job.list_dir(".")[1].keys() == {"name", "mode", "size", "mtime"}     # as Disk's


def test_nothing_outside_the_folder_can_be_reached(job, root, music, tmp_path):
    (music / "passwords").symlink_to(root / "etc" / "passwd")
    (music / "out").symlink_to(tmp_path)
    for path in ("..", "../.bashrc", "/etc/passwd", "/home/user", "old/../../notes.md",
                 "passwords", "/home/user/Music/passwords", "out", "out/x"):
        for call in (job.read_text, job.read_file, job.list_dir):
            refused(errno.EACCES, call, path)
        refused(errno.EACCES, job.write_file, path, "x")
        refused(errno.EACCES, job.edit_file, path, "a", "b")
    for call in (job.read_text, job.list_dir):
        refused(errno.ENOENT, call, "/.hallux/memory.md")    # hidden, as always
    assert job.read_text("/home/user/Music/beat.score") == BEAT     # the folder's own full path
    assert not (root / ".hallux" / "jobs").exists()


def test_a_relative_path_starts_at_the_folder_whatever_the_shell_does(job, disk):
    disk.chdir("/etc")                                       # the machine's own cd
    assert job.read_text("beat.score") == BEAT
    job.write_file("new.score", "x")
    disk.chdir("/home/user/Music/old")
    assert job.read_text("new.score") == "x" and job.read_text("old/first.score")


# ---------------------------------------------------------------- writing

def test_a_new_file_is_the_jobs_own_until_it_lands(job, root, music):
    before = tree(music)
    assert job.write_file("midnight-cello.score", BEAT) == {"ok": True, "size": len(BEAT)}
    assert job.read_text("midnight-cello.score") == BEAT
    assert job.read_file("midnight-cello.score")["size"] == len(BEAT)
    listed = {entry["name"]: entry["size"] for entry in job.list_dir()}
    assert listed["midnight-cello.score"] == len(BEAT)       # the job sees it in its listing
    assert tree(music) == before                             # and nobody else does
    assert copies(root) == {"midnight-cello.score": BEAT.encode()}
    job.write_file("old/second_take.score", "y")             # into a subfolder that exists
    assert [entry["name"] for entry in job.list_dir("old")] == ["first.score", "second_take.score"]
    assert copies(root)["old/second_take.score"] == b"y" and tree(music) == before


def test_a_given_file_is_changed_in_a_copy(job, root, music):
    job.write_file("neon.score", "the job's neon\n")
    assert job.read_text("neon.score") == "the job's neon\n"
    assert job.read_file("/home/user/Music/neon.score")["text"] == "the job's neon\n"
    assert (music / "neon.score").read_text() == NEON        # the real one is as it was
    listed = {entry["name"]: entry["size"] for entry in job.list_dir()}
    assert listed["neon.score"] == len("the job's neon\n") and listed["beat.score"] == len(BEAT)
    assert copies(root) == {"neon.score": b"the job's neon\n"}


def test_an_edit_and_an_append_start_from_the_real_text(disk, root, music):
    job = JobDisk(disk, "/home/user/Music", ["/home/user/Music/neon.score",
                                             "/home/user/Music/beat.score"], 30001)
    assert job.edit_file("neon.score", "# neon", "# midnight") == {"ok": True}
    assert job.read_text("neon.score") == NEON.replace("neon", "midnight")
    assert job.write_file("beat.score", "    (0, 4, A4, b)\n", append=True)["size"] == len(BEAT) + 18
    assert job.read_text("beat.score") == BEAT + "    (0, 4, A4, b)\n"
    job.edit_file("beat.score", "A4", "C5")                  # and then from the job's own
    assert job.read_text("beat.score") == BEAT + "    (0, 4, C5, b)\n"
    with pytest.raises(ValueError, match="0 times"):         # as Disk says it
        job.edit_file("neon.score", "nothing like this", "x")
    assert (music / "neon.score").read_text() == NEON and (music / "beat.score").read_text() == BEAT
    job.write_file("draft.score", "one\n", append=True)      # an append can create, as on Disk
    job.write_file("draft.score", "two\n", append=True)
    assert job.read_text("draft.score") == "one\ntwo\n"


def test_a_file_that_exists_and_wasnt_given_cant_be_changed(job, root, music):
    refused(errno.EACCES, job.write_file, "beat.score", "x", path="/home/user/Music/beat.score")
    refused(errno.EACCES, job.write_file, "beat.score", "x", append=True)
    refused(errno.EACCES, job.edit_file, "beat.score", "120", "90")
    refused(errno.EACCES, job.write_file, "old/first.score", "x")
    refused(errno.EISDIR, job.write_file, "old", "x")
    refused(errno.EISDIR, job.write_file, ".", "x")
    refused(errno.ENOENT, job.edit_file, "nope.score", "a", "b")
    assert (music / "beat.score").read_text() == BEAT and not (root / ".hallux" / "jobs").exists()


@pytest.mark.parametrize("name, code", [
    ("my song.score", errno.EACCES),                         # a space
    (".bashrc", errno.EACCES),                               # a dot in front
    (".hidden.score", errno.EACCES),
    ("old/.profile", errno.EACCES),
    ("new/song.score", errno.ENOENT),                        # a folder that isn't there
    ("a;b.score", errno.EACCES), ("naïve.score", errno.EACCES), ("tab\there", errno.EACCES),
])
def test_a_name_the_job_may_not_make(job, root, name, code):
    refused(code, job.write_file, name, "x")
    assert not (root / ".hallux" / "jobs").exists()


@pytest.mark.parametrize("name", ["midnight-cello.score", "take_2.score", "A.b.c", "9", "-x"])
def test_names_the_job_may_make(job, name):
    job.write_file(name, "x")
    assert job.read_text(name) == "x"


def test_files_are_bytes(disk, root, music):
    (music / "odd.score").write_bytes(b"caf\xe9 \xff\xfe\r\nline\n")       # no valid UTF-8
    job = JobDisk(disk, "/home/user/Music", ["/home/user/Music/odd.score"], 30001)
    job.write_file("odd.score", "added\n", append=True)
    assert copies(root) == {"odd.score": b"caf\xe9 \xff\xfe\r\nline\nadded\n"}     # untouched
    with pytest.raises(ValueError):                          # an edit needs text, as on Disk
        job.edit_file("odd.score", "line", "LINE")
    assert copies(root) == {"odd.score": b"caf\xe9 \xff\xfe\r\nline\nadded\n"}
    job.write_file("crlf.score", "a\r\nb\r\n")
    assert copies(root)["crlf.score"] == b"a\r\nb\r\n"       # no line ending is changed


def test_a_given_file_that_is_gone_can_still_be_written(job, music):
    (music / "neon.score").unlink()                          # the user deleted it meanwhile
    job.write_file("neon.score", "more\n", append=True)
    assert job.read_text("neon.score") == "more\n"           # the landing will find the conflict


# ---------------------------------------------------------------- the limits

def test_the_seventeenth_file_is_over_the_limit(job, root):
    job.write_file("neon.score", "changed")                  # a given file counts too
    for n in range(FILES_MAX - 1):
        job.write_file(f"take-{n}.score", "x")
    before = copies(root)
    refused(errno.EDQUOT, job.write_file, "one-more.score", "x",
            path="/home/user/Music/one-more.score")
    assert copies(root) == before and len(before) == FILES_MAX
    job.write_file("take-0.score", "written again")          # one it has already is fine


def test_a_megabyte_in_all_is_the_limit(job, root):
    job.write_file("half.score", "#" * (BYTES_MAX // 2))
    job.write_file("other.score", "#" * (BYTES_MAX // 2))    # exactly the megabyte
    before = copies(root)
    refused(errno.EDQUOT, job.write_file, "one-byte.score", "x")
    refused(errno.EDQUOT, job.write_file, "half.score", "x", append=True)
    refused(errno.EDQUOT, job.write_file, "neon.score", "x")
    assert copies(root) == before                            # nothing was written
    job.write_file("half.score", "small now")                # a file made smaller makes room
    job.write_file("one-byte.score", "x")


# ---------------------------------------------------------------- two threads

def test_a_call_from_a_second_thread_waits_for_the_first(job, monkeypatch):
    """The job's tools run in the event loop, an addon function's handle in its own thread."""
    in_the_middle, let_go, write_whole = threading.Event(), threading.Event(), hallux.jobdisk.write_whole

    def slow(target, data):
        in_the_middle.set()
        assert let_go.wait(5)
        write_whole(target, data)

    monkeypatch.setattr(hallux.jobdisk, "write_whole", slow)
    first = threading.Thread(target=job.write_file, args=("new.score", "x"))
    first.start()
    assert in_the_middle.wait(5)
    read = []
    second = threading.Thread(target=lambda: read.append(job.read_text("new.score")))
    second.start()
    second.join(0.3)
    assert second.is_alive() and read == []                  # it waits
    let_go.set()
    first.join(5), second.join(5)
    assert read == ["x"]                                     # and then reads what was written


# ---------------------------------------------------------------- an addon's disk handle

def test_the_addons_disk_handle_works_on_a_jobs_disk(job, root, music):
    handle = addons.DiskHandle(job)
    job.write_file("neon.score", "the job's neon\n")
    assert handle.read_text("neon.score") == "the job's neon\n"      # the job's own version
    assert handle.read_text("/home/user/Music/beat.score") == BEAT
    handle.write_text("from-check.score", "written through the handle\n")
    assert job.read_text("from-check.score") == "written through the handle\n"
    assert not (music / "from-check.score").exists()
    with pytest.raises(OSError) as outside:                  # the fence holds for an addon too
        handle.read_text("/etc/passwd")
    assert handle.refusal(outside.value) == "EACCES"         # and the AI is told it that way


# ---------------------------------------------------------------- when the job is over

def test_a_closed_disk_is_dead(job, root):
    handle = addons.DiskHandle(job)
    job.write_file("new.score", "x")
    job.close()
    for call, args in [(job.list_dir, ()), (job.read_text, ("new.score",)),
                       (job.read_file, ("beat.score",)), (job.write_file, ("new.score", "y")),
                       (job.edit_file, ("new.score", "x", "y"))]:
        refused(errno.ESTALE, call, *args)
    with pytest.raises(OSError) as stale:                    # also through a handle that an addon
        handle.read_text("new.score")                        # function still holds
    assert handle.refusal(stale.value) == "ESTALE"
    refused(errno.ESTALE, handle.write_text, "late.score", "written after the job ended")
    assert copies(root) == {"new.score": b"x"}               # and nothing changed
    job.close()                                              # twice is fine


def test_drop_deletes_the_copies_and_sweep_finds_what_a_crash_left(disk, job, root, music):
    before = tree(music)
    job.write_file("new.score", "x")
    job.write_file("old/deep.score", "y")
    other = JobDisk(disk, "/tmp/work", pid=30002)
    other.write_file("notes.txt", "z")
    assert sorted(os.listdir(root / ".hallux" / "jobs")) == ["30001", "30002"]
    job.close(), job.drop()
    assert os.listdir(root / ".hallux" / "jobs") == ["30002"]
    job.drop()                                               # with nothing to delete, too
    (root / ".hallux" / "jobs" / "stray").write_text("not a job's folder")
    assert sweep(disk) == ["30002", "stray"]                 # their names, for the log
    assert os.listdir(root / ".hallux" / "jobs") == [] and sweep(disk) == []
    assert tree(music) == before and (root / ".hallux" / "memory.md").read_text() == "# memory\n"
    assert sweep(Disk(root / "tmp")) == []                   # a world that never had a job


def test_done_when_a_job_writes_and_the_users_folder_is_what_it_was(disk, root, music):
    before = tree(music)
    times = {path: path.stat().st_mtime_ns for path in music.rglob("*")}
    job = JobDisk(disk, "/home/user/Music", ["/home/user/Music/neon.score"], 30007)
    job.write_file("midnight-cello.score", "BPM = 60\nSONG:\n")
    job.edit_file("neon.score", "BPM = 90", "BPM = 140")
    assert job.read_text("midnight-cello.score") == "BPM = 60\nSONG:\n"
    assert job.read_text("neon.score") == NEON.replace("90", "140")
    assert tree(music) == before                             # byte for byte
    assert {path: path.stat().st_mtime_ns for path in music.rglob("*")} == times
    assert copies(root, 30007) == {"midnight-cello.score": b"BPM = 60\nSONG:\n",
                                   "neon.score": NEON.replace("90", "140").encode()}


# ---------------------------------------------------------------- the landing

HERE = "/home/user/Music"


def times(folder):
    return {str(path.relative_to(folder)): path.stat().st_mtime_ns for path in folder.rglob("*")}


def test_a_new_file_and_a_changed_one_land(job, root, music):
    job.write_file("neon.score", "the job's neon\n")
    job.write_file("midnight-cello.score", BEAT)
    job.write_file("old/second.score", "in a subfolder\n")
    untouched = (music / "beat.score").stat().st_mtime_ns
    assert job.land() == {"files": [f"{HERE}/midnight-cello.score", f"{HERE}/neon.score",
                                    f"{HERE}/old/second.score"]}      # in the order of the names
    assert (music / "neon.score").read_text() == "the job's neon\n"
    assert (music / "midnight-cello.score").read_text() == BEAT
    assert (music / "old" / "second.score").read_text() == "in a subfolder\n"
    assert (music / "beat.score").stat().st_mtime_ns == untouched
    assert os.listdir(root / ".hallux" / "jobs") == []       # the copies are deleted
    assert not [path for path in music.rglob("*") if ".hallux-" in path.name or ".new" in path.name]


def test_a_given_file_the_job_never_wrote_isnt_touched(disk, root, music):
    job = JobDisk(disk, HERE, [f"{HERE}/neon.score", f"{HERE}/beat.score"], 30001)
    job.write_file("beat.score", "changed\n")
    before = (music / "neon.score").stat()
    assert job.land() == {"files": [f"{HERE}/beat.score"]}   # and it isn't in the list
    after = (music / "neon.score").stat()
    assert (after.st_mtime_ns, after.st_ino) == (before.st_mtime_ns, before.st_ino)
    assert (music / "neon.score").read_text() == NEON


def test_a_job_that_wrote_nothing_lands_nothing(job, root, music):
    before, when = tree(music), times(music)
    assert job.written() == 0 and job.land() == {"files": []}
    assert tree(music) == before and times(music) == when
    assert not (root / ".hallux" / "jobs").exists()


def test_a_file_that_was_changed_meanwhile_is_never_replaced(job, music):
    job.write_file("neon.score", "the job's neon\n")
    (music / "neon.score").write_text("the user's edit\n")   # saved in nano while the job ran
    assert job.land() == {"files": [f"{HERE}/neon.score.new"], "conflict": [f"{HERE}/neon.score"]}
    assert (music / "neon.score").read_text() == "the user's edit\n"
    assert (music / "neon.score.new").read_text() == "the job's neon\n"


def test_a_file_that_was_deleted_meanwhile_isnt_put_back(job, music):
    job.write_file("neon.score", "the job's neon\n")
    (music / "neon.score").unlink()
    assert job.land() == {"files": [f"{HERE}/neon.score.new"], "conflict": [f"{HERE}/neon.score"]}
    assert not (music / "neon.score").exists()
    assert (music / "neon.score.new").read_text() == "the job's neon\n"


def test_a_new_name_that_was_taken_meanwhile(job, music):
    job.write_file("midnight.score", "the job's song\n")
    (music / "midnight.score").write_text("the user had the same idea\n")
    assert job.land() == {"files": [f"{HERE}/midnight.score.new"],
                          "conflict": [f"{HERE}/midnight.score"]}
    assert (music / "midnight.score").read_text() == "the user had the same idea\n"
    assert (music / "midnight.score.new").read_text() == "the job's song\n"


def test_an_import_that_takes_a_jobs_name_keeps_it_and_the_job_lands_beside(job, disk, music,
                                                                           tmp_path):
    """What the user drops into the folder is someone else's change like any other."""
    job.write_file("a.score", "the job's\n")
    (tmp_path / "a.score").write_text("dropped by the user\n")
    assert carry_out(disk, [tmp_path / "a.score"], HERE, None).files == 1
    assert job.land() == {"files": [f"{HERE}/a.score.new"], "conflict": [f"{HERE}/a.score"]}
    assert (music / "a.score").read_text() == "dropped by the user\n"
    assert (music / "a.score.new").read_text() == "the job's\n"


def test_one_conflict_and_no_file_takes_its_place(disk, music):
    """The job wrote its files as a set, from the versions it read."""
    job = JobDisk(disk, HERE, [f"{HERE}/neon.score", f"{HERE}/beat.score"], 30001)
    job.write_file("neon.score", "neon 2\n")
    job.write_file("beat.score", "beat 2\n")
    job.write_file("new.score", "new\n")
    (music / "beat.score").write_text("changed by someone else\n")
    assert job.land() == {
        "files": [f"{HERE}/beat.score.new", f"{HERE}/neon.score.new", f"{HERE}/new.score.new"],
        "conflict": [f"{HERE}/beat.score"]}
    assert (music / "neon.score").read_text() == NEON        # it had no conflict, and still
    assert (music / "beat.score").read_text() == "changed by someone else\n"
    assert not (music / "new.score").exists()
    assert [(music / f"{name}.score.new").read_text() for name in ("beat", "neon", "new")] == [
        "beat 2\n", "neon 2\n", "new\n"]


def test_the_first_free_name_is_taken(job, music):
    job.write_file("neon.score", "the job's neon\n")
    (music / "neon.score").write_text("the user's edit\n")
    (music / "neon.score.new").write_text("from an earlier conflict\n")
    (music / "neon.score.new.2").symlink_to("nowhere")       # a name that is taken, too
    assert job.land() == {"files": [f"{HERE}/neon.score.new.3"], "conflict": [f"{HERE}/neon.score"]}
    assert (music / "neon.score.new.3").read_text() == "the job's neon\n"
    assert (music / "neon.score.new").read_text() == "from an earlier conflict\n"
    assert os.readlink(music / "neon.score.new.2") == "nowhere"


@pytest.mark.parametrize("what", ["deleted", "moved", "a link to another folder", "made again"])
def test_nothing_lands_when_the_folder_isnt_the_place_it_was(job, root, music, what):
    job.write_file("neon.score", "the job's neon\n")
    job.write_file("new.score", "new\n")
    elsewhere = root / "home" / "user" / "Elsewhere"
    if what == "deleted":
        for path in sorted(music.rglob("*"), reverse=True):
            path.rmdir() if path.is_dir() else path.unlink()
        music.rmdir()
    else:
        music.rename(elsewhere)
        if what == "a link to another folder":
            music.symlink_to(elsewhere)
        elif what == "made again":
            music.mkdir()
    before = tree(root / "home")
    with pytest.raises(FolderGone, match="^/home/user/Music$"):
        job.land()
    assert tree(root / "home") == before                     # nothing was written anywhere
    assert os.listdir(root / ".hallux" / "jobs") == []       # and the copies are gone


@pytest.mark.parametrize("what", ["a link that leads out", "a link inside", "deleted"])
def test_nothing_lands_when_a_place_in_the_folder_isnt_what_it_was(job, root, music, tmp_path, what):
    job.write_file("a-first.score", "would land first\n")
    job.write_file("old/second.score", "into the subfolder\n")
    (music / "old" / "first.score").unlink()
    (music / "old").rmdir()
    (tmp_path / "outside").mkdir()                           # not in the machine at all
    if what == "a link that leads out":
        (music / "old").symlink_to(tmp_path / "outside")
    elif what == "a link inside":
        (music / "takes").mkdir()
        (music / "old").symlink_to("takes")
    before = tree(music)
    with pytest.raises(FolderGone, match="^/home/user/Music/old/second.score$"):
        job.land()
    assert tree(music) == before and tree(tmp_path / "outside") == {}        # neither landed
    assert not (music / "a-first.score").exists()            # every place is checked first


def test_a_given_file_that_became_a_link_is_a_conflict(job, root, music):
    job.write_file("neon.score", "the job's neon\n")
    (music / "neon.score").unlink()
    (music / "neon.score").symlink_to(root / "etc" / "passwd")
    assert job.land() == {"files": [f"{HERE}/neon.score.new"], "conflict": [f"{HERE}/neon.score"]}
    assert (root / "etc" / "passwd").read_text() == "user:x:1000\n"     # nothing went through it
    assert (music / "neon.score").is_symlink()


def test_a_file_given_under_a_links_name_lands_in_the_file(disk, music):
    (music / "latest").symlink_to("neon.score")
    job = JobDisk(disk, HERE, [f"{HERE}/latest"], 30001)
    job.edit_file("latest", "# neon", "# midnight")
    assert job.land() == {"files": [f"{HERE}/neon.score"]}
    assert (music / "neon.score").read_text() == NEON.replace("neon", "midnight")
    assert os.readlink(music / "latest") == "neon.score"     # the link stays a link


def test_bytes_that_arent_text_land_as_they_are(disk, music):
    (music / "odd.score").write_bytes(b"caf\xe9 \xff\xfe\r\n")
    job = JobDisk(disk, HERE, [f"{HERE}/odd.score"], 30001)
    job.write_file("odd.score", "added\n", append=True)
    job.land()
    assert (music / "odd.score").read_bytes() == b"caf\xe9 \xff\xfe\r\nadded\n"


def test_a_landed_file_has_the_mode_the_real_file_had(job, music):
    (music / "neon.score").chmod(0o640)
    job.write_file("neon.score", "the job's neon\n")
    job.write_file("new.score", "new\n")
    (music / "plain.score").write_text("x")                  # what a new file gets here
    job.land()
    assert stat.S_IMODE((music / "neon.score").stat().st_mode) == 0o640
    assert (music / "new.score").stat().st_mode == (music / "plain.score").stat().st_mode


def test_written_counts_each_file_the_job_wrote_once(job):
    assert job.written() == 0
    job.write_file("new.score", "x")
    job.write_file("new.score", "y")                         # twice: one file
    job.write_file("neon.score", "z", append=True)           # a given one it changed
    with pytest.raises(OSError):
        job.write_file("beat.score", "refused")
    job.read_text("beat.score")
    assert job.written() == 2
    job.close(), job.drop()
    assert job.written() == 2                                # for the event of a job that was killed


def test_a_job_that_was_killed_never_lands(job, root, music):
    before = tree(music)
    job.write_file("new.score", "x")
    job.drop()                                               # what a kill does
    refused(errno.ESTALE, job.land)
    refused(errno.ESTALE, job.read_text, "beat.score")       # a dropped disk is dead
    assert tree(music) == before


def test_after_the_landing_the_disk_is_dead(job, root, music):
    handle = addons.DiskHandle(job)
    job.write_file("new.score", "x")
    assert job.land() == {"files": [f"{HERE}/new.score"]}
    refused(errno.ESTALE, job.write_file, "late.score", "after the landing")
    refused(errno.ESTALE, handle.write_text, "late.score", "through a handle")
    refused(errno.ESTALE, job.land)                          # and it lands once
    assert (music / "new.score").read_text() == "x" and not (music / "late.score").exists()
    assert os.listdir(root / ".hallux" / "jobs") == []


def test_a_landing_that_fails_halfway_leaves_what_had_landed(job, root, music, monkeypatch):
    """Each file lands in one step, the set doesn't. The order is the order of the names."""
    write_whole, landed = hallux.jobdisk.write_whole, []

    def gives_up_at_the_second(target, data):
        if landed:
            raise OSError(errno.ENOSPC, "No space left on device")
        landed.append(target.name)
        write_whole(target, data)

    job.write_file("b.score", "second\n")
    job.write_file("a.score", "first\n")
    monkeypatch.setattr(hallux.jobdisk, "write_whole", gives_up_at_the_second)
    refused(errno.ENOSPC, job.land)
    assert landed == ["a.score"] and (music / "a.score").read_text() == "first\n"
    assert not (music / "b.score").exists()
    assert os.listdir(root / ".hallux" / "jobs") == []       # the rest is gone with the copies


def test_done_when_the_users_change_stays_and_the_jobs_lands_beside_it(job, music):
    job.edit_file("neon.score", "BPM = 90", "BPM = 140")     # the job changes a score
    (music / "neon.score").write_text(NEON + "    (0, 4, A4, lead)\n")     # and so does the test
    landed = job.land()
    assert landed == {"files": [f"{HERE}/neon.score.new"], "conflict": [f"{HERE}/neon.score"]}
    assert (music / "neon.score").read_text() == NEON + "    (0, 4, A4, lead)\n"
    assert (music / "neon.score.new").read_text() == NEON.replace("90", "140")

