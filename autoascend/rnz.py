"""The exact distribution of NetHack 3.6.6's rnz(350) (rnd.c rnz / rne with u.ulevel < 15), the prayer timeout that pray.c pleased() sets after
a good prayer (u.ublesscnt = rnz(350)); allmain.c lowers it by one a turn. A prayer in MAJOR trouble is heard when ublesscnt <= 200 (pray.c
can_pray: p_type 0 'too soon' above that), so after a good prayer `gap` turns ago

    P(heard) = P(rnz(350) <= gap + 200).

Derived from the source, not measured (lane 21's survival/rnzlib.py is the same table: gap 0 .222, 100 .439, 200 .555, 300 .662, 400 .769,
500 .875, 800 .915, 1000 .946, 1200 .977). The caller must handle 'never prayed' (the start timeout is 300: heard from turn 100 on).
"""
from functools import lru_cache

RNE = [(1, 3 / 4), (2, 3 / 16), (3, 3 / 64), (4, 3 / 256), (5, 1 / 256)]   # rne(4) with utmp = 5 (u.ulevel < 15)


@lru_cache(maxsize=None)
def _cdf():
    pm = {}
    for k, pk in RNE:
        for j in range(1000):
            tmp = (1000 + j) * k
            p = pk / 1000.0
            x = 350 * tmp // 1000          # rn2(2) != 0: x *= tmp; x /= 1000
            pm[x] = pm.get(x, 0.0) + 0.5 * p
            x = 350 * 1000 // tmp          # else: x *= 1000; x /= tmp
            pm[x] = pm.get(x, 0.0) + 0.5 * p
    acc = 0.0
    out = []
    for x in sorted(pm):
        acc += pm[x]
        out.append((x, acc))
    return out


def p_timeout_le(s):
    """P(rnz(350) <= s)."""
    cdf = _cdf()
    if s < cdf[0][0]:
        return 0.0
    if s >= cdf[-1][0]:
        return 1.0
    lo, hi = 0, len(cdf) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if cdf[mid][0] <= s:
            lo = mid
        else:
            hi = mid - 1
    return cdf[lo][1]


def p_heard(gap, major=True):
    """P(a prayer is heard) `gap` turns after the last good prayer (major trouble: timeout <= 200; minor: <= 100)."""
    return p_timeout_le(gap + (200 if major else 100))
