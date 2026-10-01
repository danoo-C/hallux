"""The machine's passwords: hashed on this computer, never handed to the AI."""
import json
import stat

from hallux.passwords import Passwords


def stored(tmp_path, name="user", password="correct horse"):
    passwords = Passwords(tmp_path / ".hallux" / "passwords.json")
    assert passwords.offer(name, password) == "first"
    assert passwords.offer(name, password) == "saved"
    return passwords


def test_nothing_stored_is_unset(tmp_path):
    passwords = Passwords(tmp_path / ".hallux" / "passwords.json")
    assert passwords.check("user", "anything") == "unset"
    assert not (tmp_path / ".hallux").exists()               # checking writes nothing


def test_a_password_typed_twice_is_saved_and_checked(tmp_path):
    passwords = stored(tmp_path)
    assert passwords.check("user", "correct horse") == "yes"
    assert passwords.check("user", "Correct horse") == "no"
    assert passwords.check("user", "") == "no"
    assert passwords.check("root", "correct horse") == "unset"   # one password per name


def test_passwords_survive_a_new_session(tmp_path):
    stored(tmp_path)
    assert Passwords(tmp_path / ".hallux" / "passwords.json").check("user", "correct horse") == "yes"


def test_the_file_holds_no_password_and_is_private(tmp_path):
    stored(tmp_path, password="tr0ub4dor&3")
    path = tmp_path / ".hallux" / "passwords.json"
    assert "tr0ub4dor" not in path.read_text()
    assert set(json.loads(path.read_text())["user"]) == {"salt", "hash"}
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_the_same_password_gets_a_different_salt(tmp_path):
    stored(tmp_path, "user", "same")
    stored(tmp_path, "root", "same")
    entries = json.loads((tmp_path / ".hallux" / "passwords.json").read_text())
    assert entries["user"] != entries["root"]


def test_a_retype_that_differs_changes_nothing(tmp_path):
    passwords = stored(tmp_path, password="old")
    assert passwords.offer("user", "new") == "first"
    assert passwords.offer("user", "nwe") == "mismatch"
    assert passwords.check("user", "old") == "yes"
    assert passwords.offer("user", "new") == "first"         # after a mismatch: from the start


def test_a_new_password_must_be_retyped_right_away(tmp_path):
    passwords = Passwords(tmp_path / ".hallux" / "passwords.json")
    assert passwords.offer("user", "new") == "first"
    passwords.cancel()                                       # Ctrl-C, or another command
    assert passwords.offer("user", "new") == "first"
    assert passwords.offer("root", "new") == "first"         # another account: not a retype
    assert passwords.check("user", "new") == "unset"
    assert passwords.offer("root", "new") == "first"         # a check came in between


def test_an_empty_password_is_never_saved(tmp_path):
    passwords = Passwords(tmp_path / ".hallux" / "passwords.json")
    assert passwords.offer("user", "") == "first"
    assert passwords.offer("user", "") == "first"            # Enter twice saves nothing
    assert passwords.check("user", "") == "unset"


def test_a_damaged_file_counts_as_no_passwords(tmp_path):
    path = tmp_path / ".hallux" / "passwords.json"
    path.parent.mkdir()
    path.write_text("not json")
    assert Passwords(path).check("user", "x") == "unset"
    path.write_text('{"user": {"salt": "zz"}}')              # edited by hand: never matches
    assert Passwords(path).check("user", "x") == "no"
