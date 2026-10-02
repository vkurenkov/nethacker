"""MEDUSA_HOP (jf_config): cross a 1-wide moat channel by drowning and crawling out.

NetHack 3.6.6 trap.c drown(): a hero who walks into water (or whose hole floods) and cannot swim, fly or breathe
water 'tries to crawl out': the game picks a random square among the eight around the WATER square that
hack.c crawl_destination() accepts (goodpos: land, no monster, not rock; a diagonal one unless both orthogonal
neighbours are rock), at no cost in HP. The origin square is always such a square, so the step cannot drown us, and
when the water square touches a second stretch of land the crawl may put us there: a 1-wide channel is crossed with
probability n_far / (n_far + n_near) per try (the harness probe of Medusa-4's islets: 5 of 6 landed across). What it
costs is the soaking (water_damage_chain: scrolls blank, potions dilute, iron rusts) -- the same as every flood of
the dig lottery.

Why it matters: on Medusa-3/4 most fall squares have no dry floor (every neighbour-count k >= 1), and a pick-axe hole
beside k moat squares floods with probability 1 - 1/(k+1)^2 (dig.c dighole -> fillholetyp at the pit and again at the
hole). Medusa-4's islets are joined to stretches with dry floor (k = 0: no flood roll can come up wet) by one or two
1-wide channels. This module only analyses the fixed maps of medusa_maps.py (screen coordinates (y, x), as there);
dive_logic.DiveLogic._hop_action walks to a launch square and steps in.
"""

import collections
import heapq

from . import medusa_maps

# map characters that are rock for hack.c bad_rock (walls, secret doors, trees, solid stone)
_ROCK = frozenset('-|ST ')
_LAND = frozenset('.{')

_MODELS = {}


class Model:
    """Static analysis of one Medusa variant: land components (8-connected), moat-neighbour counts, channels."""

    def __init__(self, name):
        self.name = name
        yoff, rows = medusa_maps.MAPS[name]
        self._yoff = yoff
        h, w = len(rows), len(rows[0])
        self._h, self._w = h, w
        self._rows = rows
        land = [(y + yoff, x + medusa_maps.XOFF) for y in range(h) for x in range(w) if rows[y][x] in _LAND]
        self.land = frozenset(land)
        self.comp = {}
        self.comps = []
        for p in land:
            if p in self.comp:
                continue
            idx = len(self.comps)
            members = []
            todo = [p]
            self.comp[p] = idx
            while todo:
                cy, cx = todo.pop()
                members.append((cy, cx))
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        n = (cy + dy, cx + dx)
                        if n in self.land and n not in self.comp:
                            self.comp[n] = idx
                            todo.append(n)
            self.comps.append(members)
        self.k = {p: sum(1 for dy in (-1, 0, 1) for dx in (-1, 0, 1) if (dy or dx) and self.char(p[0] + dy, p[1] + dx) == '}')
                  for p in land}
        # comps with a square no moat touches: a hole there cannot flood (fillholetyp counts moat in the 3x3)
        self.dry = frozenset(i for i, m in enumerate(self.comps) if any(self.k[p] == 0 for p in m))
        # channels: water square -> {comp: [crawl destinations of that comp]}
        self.channels = {}
        for y in range(h):
            for x in range(w):
                if rows[y][x] != '}':
                    continue
                wy, wx = y + yoff, x + medusa_maps.XOFF
                dest = collections.defaultdict(list)
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        n = (wy + dy, wx + dx)
                        if n in self.comp and self._crawl_ok(wy, wx, dy, dx):
                            dest[self.comp[n]].append(n)
                if len(dest) >= 2:
                    self.channels[(wy, wx)] = dict(dest)

    def char(self, y, x):
        return medusa_maps.char_at(self.name, y, x)

    def _bad_rock(self, y, x):
        return self.char(y, x) in _ROCK

    def _crawl_ok(self, wy, wx, dy, dx):
        """hack.c crawl_destination for the square (wy + dy, wx + dx) from the water square (wy, wx)."""
        if not (dy or dx):
            return False
        if dy and dx:
            # a diagonal crawl squeezes between the two orthogonal neighbours: refused when both are rock
            return not (self._bad_rock(wy + dy, wx) and self._bad_rock(wy, wx + dx))
        return True

    def move_ok(self, ly, lx, wy, wx):
        """The step from land (ly, lx) into the water square (wy, wx) is not a diagonal squeeze between rocks."""
        dy, dx = wy - ly, wx - lx
        if dy and dx:
            return not (self._bad_rock(ly + dy, lx) and self._bad_rock(ly, lx + dx))
        return True

    def launches(self, wy, wx, comp_id):
        """Squares of `comp_id` from which a step into (wy, wx) is legal."""
        out = []
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                n = (wy + dy, wx + dx)
                if (dy or dx) and self.comp.get(n) == comp_id and self.move_ok(n[0], n[1], wy, wx):
                    out.append(n)
        return out


def model(name):
    m = _MODELS.get(name)
    if m is None:
        m = _MODELS[name] = Model(name)
    return m


def edge_options(m, src, dst):
    """[(p_cross, W, launches)] over the channel squares joining comp `src` to comp `dst`: p_cross is the chance
    one try ends on `dst` (destinations on dst over all valid destinations; the origin square counts for src)."""
    out = []
    for w, dest in m.channels.items():
        if src in dest and dst in dest:
            launches = m.launches(w[0], w[1], src)
            if not launches:
                continue
            n_near, n_far = len(dest[src]), len(dest[dst])
            others = sum(len(v) for c, v in dest.items() if c not in (src, dst))
            out.append((n_far / float(n_near + n_far + others), w, launches))
    return out


def plan(name, pos, max_cost=12.0):
    """The cheapest chain of hops from the land component of `pos` to a component with dry floor.
    Returns None (already on dry land / no chain / no land under pos), else a dict:
      comp (ours), path (comp ids), cost (expected tries over the chain), options (the first edge's options sorted
      best p_cross first: [(p_cross, W, launches)])."""
    m = model(name)
    src = m.comp.get(tuple(pos))
    if src is None or src in m.dry:
        return None
    best = {src: (0.0, None)}
    heap = [(0.0, src)]
    goal = None
    while heap:
        cost, u = heapq.heappop(heap)
        if cost > best[u][0] + 1e-9:
            continue
        if u in m.dry:
            goal = u
            break
        if cost > max_cost:
            break
        nxt = {c for w, dest in m.channels.items() if u in dest for c in dest if c != u}
        for v in nxt:
            opts = edge_options(m, u, v)
            if not opts:
                continue
            p = max(o[0] for o in opts)
            c2 = cost + 1.0 / p
            if v not in best or c2 < best[v][0]:
                best[v] = (c2, u)
                heapq.heappush(heap, (c2, v))
    if goal is None or best[goal][0] > max_cost:
        return None
    path = [goal]
    while path[-1] != src:
        path.append(best[path[-1]][1])
    path.reverse()
    opts = edge_options(m, path[0], path[1])
    opts.sort(key=lambda o: -o[0])
    return {'comp': src, 'path': path, 'cost': best[goal][0], 'options': opts}
