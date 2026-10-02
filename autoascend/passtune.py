"""The castle drawbridge's passtune as a Mastermind game (NetHack 3.6.6 music.c do_play_instrument, ~768-838).

The tune is 5 notes out of A..G (u_init: tune[i] = 'A' + rn2(7)). A wrong tune played on the castle level with the
drawbridge (05,08) or its portcullis (06,08) inside the hero's 3x3 gives feedback:
    gears    = notes right in the right place;
    tumblers = counted by ONE left-to-right pass over the guess with a shared matched[] array: a wrong note at x claims
               the first y whose tune note it equals, that is not matched yet and whose own guess note is not a gear
               (buf[y] != tune[y]) -- not textbook Mastermind scoring, so the exact loop is simulated here.
'You hear N tumblers click and M gears turn.' / 'You hear N tumblers click.' / 'You hear M gears turn.' / nothing at
all for 0 and 0. The right tune opens (or closes) the drawbridge instead and makes the tune known
(u.uevent.uheard_tune = 2: later plays ask 'Play the passtune?').

Solver: first guess AABBC, then a minimax guess over the consistent tunes (a fixed-seed sample of <= 300 when more
remain). Offline (dev check in __main__): mean ~5.3 plays, max 7-8 over random tunes.
"""

import itertools
import re

import numpy as np

NOTES = 'ABCDEFG'
FIRST_GUESS = 'AABBC'
POOL = 300

_CODES = None


def _codes():
    global _CODES
    if _CODES is None:
        _CODES = np.array(list(itertools.product(range(7), repeat=5)), dtype=np.int8)
    return _CODES


def feedback(guess, secrets):
    """guess: (5,) int array; secrets: (M, 5) -> (M,) gears * 6 + tumblers, exactly as music.c counts them."""
    m = secrets.shape[0]
    gears = np.zeros(m, np.int16)
    tumblers = np.zeros(m, np.int16)
    matched = np.zeros((m, 5), bool)
    gear_at = secrets == guess[None, :]          # buf[y] == tune[y], per position
    for x in range(5):
        g = guess[x]
        hit = gear_at[:, x]
        gears += hit
        matched[hit, x] = True
        miss = ~hit
        found = np.zeros(m, bool)
        for y in range(5):
            cand = miss & ~found & ~matched[:, y] & (secrets[:, y] == g) & ~gear_at[:, y]
            tumblers += cand
            matched[cand, y] = True
            found |= cand
    return gears * 6 + tumblers


def to_code(tune):
    return np.array([NOTES.index(c) for c in tune.upper()], dtype=np.int8)


def to_tune(code):
    return ''.join(NOTES[int(i)] for i in code)


_FB_RE = re.compile(r'You hear (\d+) tumblers? click(?: and (\d+) gears? turn)?|You hear (\d+) gears? turn')


def parse_feedback(message):
    """(gears, tumblers) from the play's messages, or None when there is no feedback line. music.c prints nothing at
    all for 0 and 0, so the caller decides whether a silent play was a real (0, 0)."""
    m = _FB_RE.search(message or '')
    if not m:
        return None
    if m.group(1) is not None:
        return int(m.group(2) or 0), int(m.group(1))
    return int(m.group(3)), 0


class Solver:
    """Mastermind state: the tunes still consistent with every (guess, gears, tumblers) heard so far."""

    def __init__(self, seed=20260930):
        self.rng = np.random.default_rng(seed)
        self.cands = _codes()
        self.history = []

    def next_guess(self):
        if not self.history:
            return FIRST_GUESS
        n = len(self.cands)
        if n == 0:
            return None
        if n <= 2:
            return to_tune(self.cands[0])
        pool = self.cands if n <= POOL else self.cands[self.rng.choice(n, POOL, replace=False)]
        best, best_v = None, None
        for g in pool:
            v = int(np.bincount(feedback(g, self.cands), minlength=36).max())
            if best_v is None or v < best_v:
                best, best_v = g, v
        return to_tune(best)

    def update(self, guess, gears, tumblers):
        """Keep the tunes that would have given this feedback. Returns the number left (0 = something was misread:
        the caller resets)."""
        self.history.append((guess, gears, tumblers))
        code = gears * 6 + tumblers
        self.cands = self.cands[feedback(to_code(guess), self.cands) == code]
        return len(self.cands)

    def exclude(self, guess):
        """The exact tune was played and nothing opened: it is not the tune (e.g. a play away from the bridge)."""
        c = to_code(guess)
        self.cands = self.cands[~(self.cands == c[None, :]).all(axis=1)]

    def reset(self, keep_last=False):
        """Recompute from the history minus its last entry (a misread) -- or from scratch."""
        hist = self.history[:-1] if keep_last else []
        self.cands = _codes()
        self.history = []
        for g, ge, tu in hist:
            self.update(g, ge, tu)
        return len(self.cands)


if __name__ == '__main__':   # dev check: python3 -m bot.autoascend.passtune (or run the file)
    import sys
    rng = np.random.default_rng(1)
    idx = rng.choice(len(_codes()), int(sys.argv[1]) if len(sys.argv) > 1 else 200, replace=False)
    plays = []
    for i in idx:
        secret = _codes()[i]
        s = Solver()
        for n in range(1, 20):
            g = s.next_guess()
            if (to_code(g) == secret).all():
                plays.append(n)
                break
            fb = int(feedback(to_code(g), secret[None, :])[0])
            s.update(g, fb // 6, fb % 6)
        else:
            plays.append(99)
    print('tunes', len(plays), 'mean plays', round(float(np.mean(plays)), 2), 'max', max(plays),
          {k: plays.count(k) for k in sorted(set(plays))})
