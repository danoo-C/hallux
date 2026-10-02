"""How long a whole render takes: run by hand, with  .venv/bin/python tests/music_timing.py

Not a test. It is what the limits in addons/music_engine/limits.py are set by: each of the two
stress scores has to render in under 4 seconds on the computer the limits were chosen on,
half of what the addon allows a play, so that a computer half as fast still fits.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "addons"))

from music_engine import limits, render, score, song  # noqa: E402

SCORES = Path(__file__).parent / "scores"
BUDGET = 4.0                                  # seconds a stress score may take


def longest_song() -> str:
    """The longest song allowed, with 8 voices that sound all the time, each a saw with two
    gliding variables: the sample maths, and the memory."""
    steps = limits.SONG_SECONDS * 16          # at 120 BPM a step is a 16th of a second
    return (f"BPM = 120\nA = 0\nB = 255\n\nINSTRUMENT voice:\n"
            f"    saw(p) * A * B * vel >> 24\n\nSONG:\n"
            f"    (0, {steps}, 255, A)\n    (0, {steps}, 0, B)\n"
            f"    (0, {steps}, C3 E3 G3 B3 D4 F4 A4 C5, voice, 30)\n")


def most_events() -> str:
    """The most events allowed, all of them short drum notes: what every single note costs
    before its first sample."""
    drums = (SCORES / "drum-beat.score").read_text().partition("# one bar")[0]
    hits = "".join(f"    ({step}, 2, {note}, {drum}, 100)\n"
                   for step in range(32)
                   for note, drum in (("A1", "kick"), ("C6", "hat"), ("G3", "snare"),
                                      ("C6", "hat")))
    bars = limits.EVENTS // (32 * 4)
    return f"{drums}PATTERN bar 32:\n{hits}\nSONG:\n    (0, bar, 0, {bars})\n"


def timed(text: str, loop: bool = False) -> dict:
    stamps = [time.perf_counter()]
    read = score.read(text)
    stamps.append(time.perf_counter())
    unfolded = song.unfold(read)
    stamps.append(time.perf_counter())
    render._to_16_bits, to_16_bits = lambda mix, largest: mix, render._to_16_bits
    try:
        rendered = render.render(read, unfolded, loop)
    finally:
        render._to_16_bits = to_16_bits
    stamps.append(time.perf_counter())
    largest = max(render._largest(rendered.first),
                  0 if rendered.again is None else render._largest(rendered.again))
    to_16_bits(rendered.first, largest)
    stamps.append(time.perf_counter())
    reading, unfolding, rendering, turning = (b - a for a, b in zip(stamps, stamps[1:]))
    return {"notes": len(unfolded.notes), "seconds": rendered.seconds, "peak": rendered.peak,
            "reading": reading, "unfolding": unfolding, "rendering": rendering,
            "to 16 bits": turning, "total": stamps[-1] - stamps[0]}


def main() -> int:
    scores = [("the longest song, 8 voices", longest_song(), True),
              ("the most events, drums", most_events(), True)]
    scores += [(path.stem, path.read_text(), False) for path in sorted(SCORES.glob("*.score"))]
    print(f"{'score':28} {'notes':>6} {'length':>7} {'reading':>8} {'unfolding':>9} "
          f"{'rendering':>9} {'to 16 bits':>10} {'total':>7}")
    slow = []
    for name, text, stress in scores:
        best = min((timed(text) for _ in range(3)), key=lambda found: found["total"])
        print(f"{name:28} {best['notes']:6} {best['seconds']:6.1f}s {best['reading']:8.3f} "
              f"{best['unfolding']:9.3f} {best['rendering']:9.3f} {best['to 16 bits']:10.3f} "
              f"{best['total']:6.3f}s")
        if stress and best["total"] > BUDGET:
            slow.append(name)
    for name in slow:
        print(f"TOO SLOW: {name} takes more than {BUDGET:g} s")
    return 1 if slow else 0


if __name__ == "__main__":
    raise SystemExit(main())
