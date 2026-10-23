"""For every test: the music addon's child, the package addons/music_engine, is found the
way it finds itself when Hallux starts it in the addons folder."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "addons"))


import os as _os
import tempfile as _tempfile

# hpm's store: never the real one in ~/.local/share/hallux/hpm. Each test that needs its own
# store passes one; this keeps any other from reaching yours.
_os.environ["HPM_HOME"] = _os.path.join(_tempfile.gettempdir(), "hpm-tests-store")

# hpm's AI costs money: no test may reach the real model (hallux/hpm/ai.py, real_client).
_os.environ["HALLUX_NO_REAL_MODEL"] = "1"
