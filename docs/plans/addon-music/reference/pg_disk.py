# Does pygame's mixer hand the samples on unchanged, and is a queued sound gapless?
# SDL's "disk" driver writes what would go to the sound card into a file.
import os, sys, time
out = sys.argv[1]
os.environ.update(SDL_AUDIODRIVER="disk", SDL_DISKAUDIOFILE=out, PYGAME_HIDE_SUPPORT_PROMPT="1")
import numpy as np, pygame
pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=1024, allowedchanges=0)
print("mixer:", pygame.mixer.get_init(), "driver:", pygame.mixer.get_sdl_mixer_version())
rng = np.random.default_rng(1)
A = rng.integers(-32768, 32767, 30000, dtype=np.int16)      # lengths that are no multiple of 1024
B = rng.integers(-32768, 32767, 20011, dtype=np.int16)
a, b = pygame.mixer.Sound(buffer=A.tobytes()), pygame.mixer.Sound(buffer=B.tobytes())
ch = a.play(); ch.queue(b); rounds = 1
while ch.get_busy():
    if ch.get_queue() is None and rounds < 3: ch.queue(b); rounds += 1
    time.sleep(0.005)
time.sleep(0.2); pygame.mixer.quit()
got = np.fromfile(out, dtype=np.int16); want = np.concatenate([A, B, B, B])
start = next((i for i in range(len(got) - len(A)) if got[i] == A[0] and np.array_equal(got[i:i + 50], A[:50])), -1)
seg = got[start:start + len(want)]
print("rounds queued:", rounds, " output starts at sample", start)
print("A + B + B + B bit-exact and gapless:", len(seg) == len(want) and np.array_equal(seg, want))
if len(seg) == len(want) and not np.array_equal(seg, want):
    bad = np.nonzero(seg != want)[0]; print("first difference at", bad[0], "of", len(want), "count", len(bad))
