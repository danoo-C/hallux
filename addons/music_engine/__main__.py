"""The music addon's child: python -m music_engine, started in the addons folder.

It gets scores as text on its input, plays them, and answers on its output: one line of JSON
per message, as addons/window.py does it. A message with an id is a question, and its answer
has the same id. A line without one is an event.

    {"cmd": "play", "text": "...", "loop": false, "id": 1}
        {"ok": true, "seconds": 9.6, "peak": 98, "id": 1}
        {"error": "line 7: unknown name CUTOF\\nline 12: ...", "id": 1}
    {"cmd": "stop", "id": 2}
        {"ok": true, "id": 2}
    {"cmd": "quit"}
        {"event": "finished"}        when a song that plays once ends by itself

The child speaks first: {"id": 0, "ok": true} once numpy is loaded and the mixer is open, or
{"id": 0, "error": "no sound device: ..."}. Nothing of Hallux is in it, so it can be run and
tried by hand.

Started with the word check, python -m music_engine check, it plays nothing. It reads one
message, renders that score, gives the answer play would give, and ends:

    {"text": "..."}
        {"ok": true, "seconds": 9.6, "peak": 98}
        {"error": "line 7: unknown name CUTOF\\nline 12: ..."}

It opens no sound card for that and never loads pygame, so it works where no sound can get
out, and beside a child that is playing.
"""
import contextlib
import json
import os
import queue
import sys
import threading
import traceback

TICK_SECONDS = 0.05                           # how often the player is asked how it is doing


def main() -> int:
    line_out = os.fdopen(os.dup(1), "w")      # the line to Hallux
    os.dup2(2, 1)                             # what a library prints can't garble it

    def say(message: dict) -> None:
        line_out.write(json.dumps(message) + "\n")   # ASCII only, whatever the pipe's encoding
        line_out.flush()

    if sys.argv[1:] == ["check"]:
        return check(say)

    # Only now: numpy and pygame take a while, and pygame may print while it starts.
    from music_engine import player, render, score, song

    try:
        sound = player.Player()
    except player.PlayerError as problem:
        say({"id": 0, "error": str(problem)})
        return 1

    def tick() -> None:
        if sound.tick():
            say({"event": "finished"})        # no id: it answers no question

    def play(message: dict) -> dict:
        """Check a score, render it and start it. One that fails its check changes nothing:
        what was playing plays on."""
        text, loop = message.get("text"), message.get("loop", False)
        if not isinstance(text, str) or not isinstance(loop, bool):
            return {"error": "addon bug: play takes a text, and true or false for loop"}
        try:
            read = score.read(text)
            rendered = render.render(read, song.unfold(read), loop)
        except score.ScoreError as problems:
            return {"error": str(problems)}
        sound.play(rendered.first, rendered.again, loop)
        return {"ok": True} | rendered.report()

    def answer(message: dict) -> dict:
        if message.get("cmd") == "play":
            return play(message)
        if message.get("cmd") == "stop":
            sound.stop()
            return {"ok": True}
        return {"error": f"unknown message: {str(message.get('cmd'))[:30]}"}

    def carry_out(message: dict) -> dict:
        """The answer to one message. A render takes a while, so it has a thread of its own,
        and the song that is playing is looked after meanwhile."""
        result: list[dict] = []

        def work() -> None:
            try:
                result.append(answer(message))
            except Exception as bug:          # an answer, not a crash: the child lives on
                traceback.print_exc()
                result.append({"error": f"addon bug: {type(bug).__name__}: {bug}"[:200]})

        worker = threading.Thread(target=work, name="music play")
        worker.start()
        while worker.is_alive():
            worker.join(TICK_SECONDS)
            tick()
        return result[0]

    inbox: queue.Queue = queue.Queue()        # messages from Hallux; None: it has gone away

    def listen() -> None:
        # Read the descriptor itself: a thread stuck inside sys.stdin can crash Python's exit.
        waiting = b""
        while chunk := os.read(0, 65536):
            *lines, waiting = (waiting + chunk).split(b"\n")
            for line in lines:
                with contextlib.suppress(ValueError):
                    message = json.loads(line)
                    if isinstance(message, dict):
                        inbox.put(message)
        inbox.put(None)

    threading.Thread(target=listen, name="music messages", daemon=True).start()
    say({"id": 0, "ok": True})
    while True:
        try:
            message = inbox.get(timeout=TICK_SECONDS)
        except queue.Empty:
            tick()
            continue
        if message is None or message.get("cmd") == "quit":
            sound.close()
            return 0
        say(carry_out(message) | {"id": message.get("id")})


def check(say) -> int:
    """Started for a check: one score comes in, its answer goes out, and that is all. The
    player isn't loaded here. It loads pygame, and a check has to work without it."""
    from music_engine import render, score, song          # numpy takes a while; no pygame

    try:
        message = json.loads(sys.stdin.buffer.read())     # all of it: nothing follows a check
    except ValueError:
        message = None
    text = message.get("text") if isinstance(message, dict) else None
    if not isinstance(text, str):
        say({"error": "addon bug: check takes a text"})
        return 0
    try:
        read = score.read(text)
        say({"ok": True} | render.render(read, song.unfold(read)).report())
    except score.ScoreError as problems:
        say({"error": str(problems)})
    except Exception as bug:                  # an answer, as from the child that plays
        traceback.print_exc()
        say({"error": f"addon bug: {type(bug).__name__}: {bug}"[:200]})
    return 0


if __name__ == "__main__":
    sys.exit(main())
