# Play the drum beat of section 5 through pygame's mixer, as the music addon's child would.
import os, sys, time, runpy, io, contextlib
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ["SDL_AUDIODRIVER"] = sys.argv[1] if len(sys.argv) > 1 else "pulseaudio"
with contextlib.redirect_stdout(io.StringIO()):
    ns = runpy.run_path(os.path.join(os.path.dirname(__file__), "scores.py"))
import numpy as np, pygame
beat = (ns["s3"] // 2).astype("<i2")                       # half volume: the speakers aren't mine
t0 = time.perf_counter()
pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=1024, allowedchanges=0)
print("driver %s, mixer %s, opened in %.2f s" % (os.environ["SDL_AUDIODRIVER"], pygame.mixer.get_init(), time.perf_counter() - t0))
snd = pygame.mixer.Sound(buffer=beat.tobytes())
t0 = time.perf_counter(); ch = snd.play()
while ch.get_busy(): time.sleep(0.02)
print("played %.1f s of sound in %.2f s" % (len(beat) / 44100, time.perf_counter() - t0))
pygame.mixer.quit()
