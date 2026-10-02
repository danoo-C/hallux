import time, numpy as np
SR = 44100
SIN = np.round(np.sin(np.arange(65536) * 2 * np.pi / 65536) * 32767).astype(np.int64)

def step_of(f): return round(f * 2**32 / SR)
def best(fn, n=3):
    r = []
    for _ in range(n):
        a = time.perf_counter(); fn(); r.append(time.perf_counter() - a)
    return min(r)

def tdiv(a, b):                      # C-style: toward zero, x/0 = 0
    b0 = np.where(b == 0, 1, b)
    q = np.abs(a) // np.abs(b0)
    q = np.where((a < 0) != (b0 < 0), -q, q)
    return np.where(b == 0, 0, q)
def fdiv(a, b):                      # floor, x/0 = 0, scalar divisor fast path
    if np.isscalar(b): return a // b if b else a * 0
    return np.where(b == 0, 0, a // np.where(b == 0, 1, b))

# the "lead" of the second score, section 5
def lead(t, step, vel, VOL, BRIGHT):
    p = t * step >> 16
    return (((p & 65535) - 32768) * BRIGHT + SIN[p & 65535] * (255 - BRIGHT)) * vel * VOL >> 24
def fade(t, step, dur, div):
    p = t * step >> 16
    return div(SIN[p & 65535] * (dur - t), dur)

N = 60 * SR                          # one voice, one minute
st = step_of(440.0)
t_all = np.arange(N, dtype=np.int64)
vol_arr = np.linspace(0, 255, N).astype(np.int64); br_arr = vol_arr[::-1].copy()

def whole(): lead(t_all, st, 130, vol_arr, br_arr)
def blocks(B):
    def f():
        for a in range(0, N, B):
            lead(t_all[a:a+B], st, 130, vol_arr[a:a+B], br_arr[a:a+B])
    return f
def blocks_scalar(B):
    def f():
        for a in range(0, N, B):
            lead(t_all[a:a+B], st, 130, 200, 90)
    return f
print("lead, 1 voice-minute (%d samples)" % N)
print("  whole array, variables as arrays : %.3f s" % best(whole))
for B in (4096, 16384, 65536, 262144):
    print("  blocks of %6d, vars as arrays  : %.3f s" % (B, best(blocks(B))))
print("  blocks of  16384, vars as scalars: %.3f s" % best(blocks_scalar(16384)))

def fb(div):
    def f():
        for a in range(0, N, 16384):
            fade(t_all[a:a+16384], st, N, div)
    return f
print("sin fade, 1 voice-minute, blocks of 16384")
print("  '/' toward zero : %.3f s" % best(fb(tdiv)))
print("  '/' floor       : %.3f s" % best(fb(fdiv)))
x = t_all[:16384] * st >> 16
print("  per sample: sin lookup %.1f ns, mul %.1f ns, floor-div by scalar %.1f ns" % (
    best(lambda: [SIN[x & 65535] for _ in range(200)]) / 200 / 16384 * 1e9,
    best(lambda: [x * 130 for _ in range(200)]) / 200 / 16384 * 1e9,
    best(lambda: [x // 2646000 for _ in range(200)]) / 200 / 16384 * 1e9))

# ---- aliasing: naive saw vs polyBLEP saw, one second, energy off the harmonics
def naive_saw(p): return ((p & 65535) - 32768).astype(np.float64)
def blep_saw(p, step):
    ph = (p & 65535) / 65536.0; dt = step / 2**32
    y = 2 * ph - 1
    a = ph < dt; x1 = ph[a] / dt; y[a] -= x1 + x1 - x1 * x1 - 1
    b = ph > 1 - dt; x2 = (ph[b] - 1) / dt; y[b] -= x2 * x2 + x2 + x2 + 1
    return y * 32767
def alias_db(y, f):
    n = len(y); w = np.blackman(n); S = np.abs(np.fft.rfft(y * w)) ** 2
    fr = np.fft.rfftfreq(n, 1 / SR); k = np.round(fr / f)
    harm = (np.abs(fr - k * f) < 6) & (k >= 1)
    return 10 * np.log10(S[~harm & (fr > 20)].sum() / S[harm].sum())
t1 = np.arange(SR, dtype=np.int64)
print("aliasing: energy that is not on a harmonic, relative to the harmonics")
for name, f in (("A2", 110.0), ("A4", 440.0), ("C6", 1046.5), ("C7", 2093.0)):
    s = step_of(f); p = t1 * s >> 16
    print("  %s  naive saw %6.1f dB   band-limited (polyBLEP) %6.1f dB" % (name, alias_db(naive_saw(p), f), alias_db(blep_saw(p, s), f)))
pp = t_all[:16384] * st >> 16
print("  cost per sample: naive %.1f ns, polyBLEP %.1f ns" % (
    best(lambda: [(pp & 65535) - 32768 for _ in range(200)]) / 200 / 16384 * 1e9,
    best(lambda: [blep_saw(pp, st) for _ in range(200)]) / 200 / 16384 * 1e9))
