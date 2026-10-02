"""Play a score file through the music addon's child, on the real sound card: run by hand.

    .venv/bin/python tests/music_play.py tests/scores/drum-beat.score
    .venv/bin/python tests/music_play.py --loop tests/scores/drum-beat.score

Not a test: no test makes a sound. It starts the child the way the addon does, sends it the
score, and prints what the child answers. Enter stops the sound and ends it.
"""
import json
import subprocess
import sys
import threading
from pathlib import Path

ADDONS = Path(__file__).resolve().parent.parent / "addons"


def main() -> int:
    paths = [arg for arg in sys.argv[1:] if arg != "--loop"]
    if len(paths) != 1:
        print(__doc__)
        return 2
    child = subprocess.Popen([sys.executable, "-m", "music_engine"], cwd=ADDONS, text=True,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    def say(message: dict) -> None:
        child.stdin.write(json.dumps(message) + "\n")
        child.stdin.flush()

    def show() -> None:
        for line in child.stdout:
            print("child:", line.rstrip())
            if json.loads(line) == {"event": "finished"}:
                print("the song is over: press Enter")

    hello = json.loads(child.stdout.readline() or '{"error": "the child said nothing"}')
    print("child:", json.dumps(hello))
    if "error" in hello:
        return 1
    threading.Thread(target=show, daemon=True).start()
    say({"cmd": "play", "text": Path(paths[0]).read_text(encoding="utf-8"),
         "loop": "--loop" in sys.argv, "id": 1})
    try:
        input("Enter stops the sound\n")
    except (EOFError, KeyboardInterrupt):
        pass
    say({"cmd": "quit"})
    return child.wait(5)


if __name__ == "__main__":
    raise SystemExit(main())
