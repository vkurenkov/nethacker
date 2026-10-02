"""CHOKEPOINT (chokepoint lane; switches in jf_config): fight a pack from a square that only one or two of it can reach.

Why: multi-monster fights kill in every phase of the game -- grind packs at XL 5-6 (hill orcs, rothes, giant ants:
ledger F090/H028), the Gnomish Mines camp and the stairs dives (F092: soldier ants, killer bees, @ crowds). In NetHack
a monster melees only from one of the 8 squares around its target (mon.c monnear: dist2 < 3). Doorways restrict
movement, not attacks (hack.c domove attacks before test_move; mhitu.c has no door check), and monsters never swap
places with each other. So on a square that the pack can approach through at most two of its neighbours -- a straight
corridor, a Mines passage, the corridor square outside a door, the room square inside a door the pack comes through --
at most two of them attack at once, and the rest queue up. fight2's own move heatmap ('strike first') keeps us two
squares from every monster wherever we stand, so a pack in a room or an open cave surrounds us.

The measure: the neighbours of a square that some hostile reaches without passing through the square itself and without
a long detour (CHOKE_DETOUR squares over its straight-line distance): 'facing' squares. A chokepoint has at most
CHOKE_MAX_FACING of them (or at most two walkable neighbours at all).

What it does, inside fight2 (agent.fight2 calls adjust() on its action list):
- trigger: CHOKE_MIN_NEAR melee hostiles within CHOKE_NEAR_RADIUS, or CHOKE_MIN_VIEW within CHOKE_VIEW_RADIUS (sessile,
  passive and trivial kinds do not count; nothing is done while one of them walks through rock);
- in the open: a move toward the nearest chokepoint within CHOKE_STEPS BFS steps (CHOKE_RETREAT_STEPS, and only against
  2+ adjacent or 3+ near, when something is already next to us) that no hostile can reach before us, at CHOKE_PRIORITY
  (above melee: 16);
- on a chokepoint: no moves off it (fight2 would step into the open to strike first); melee, missiles, wands,
  Elbereth and pickups stay, and 'hold' (a search turn, CHOKE_HOLD_PRIORITY) waits for the pack to come. A hold with
  no contact for CHOKE_HOLD_TURNS ends and the trigger rests CHOKE_COOLDOWN turns (sleeping packs, monsters keeping
  their distance); so does being shot at with nothing next to us for CHOKE_SHOT_TURNS (archers keeping away).
Everything above fight2 keeps precedence: the Elbereth rest, the retreat upstairs, prayer, KNOWN_ITEMS, dig_first (a
digger finishes its hole), the minotaur guard. Not used in Sokoban and the other branches, on Medusa's level, the mazes
below it or the castle level, in a shop, in a pit, while levitating, blind, hallucinating or polymorphed; no approach
from the stairs (an exit) or from an Elbereth that scares the adjacent pack. A square counts only when all 8 squares
around it are known (a dark room's unseen floor must not pass for rock).
CHOKE_LOG (logging only) writes the same analysis as 'CHOKE census' lines without acting: the lane's census.
"""
import numpy as np

from . import jf_config, utils
from .glyph import G, MON, SS
from .level import Level
from .combat.monster_utils import ONLY_RANGED_SLOW_MONSTERS, WEAK_MONSTERS

NEIGH = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))
_CORR = frozenset((SS.S_corr, SS.S_litcorr))
_DOOR = frozenset((SS.S_ndoor,)) | G.DOOR_OPENED
_ROOM = frozenset((SS.S_room, SS.S_darkroom))
_STAIRS = G.STAIR_UP | G.STAIR_DOWN


def _cheb(a, b):
    return max(abs(int(a[0]) - int(b[0])), abs(int(a[1]) - int(b[1])))


def square_class(level, y, x):
    g = level.objects[y, x]
    if g in _CORR:
        return 'corr'
    if g in _DOOR:
        return 'door'
    if g in _STAIRS:
        return 'stairs'
    if g in _ROOM:
        return 'room'
    return 'other' if g != -1 else 'unknown'


def known_around(level, y, x):
    h, w = level.walkable.shape
    for dy, dx in NEIGH:
        yy, xx = y + dy, x + dx
        if 0 <= yy < h and 0 <= xx < w and not (level.walkable[yy, xx] or level.seen[yy, xx]):
            return False
    return True


def threats(monsters, xl):
    """The hostiles that come at us in melee: not the sessile/passive kinds fight2 leaves alone, not the trivial ones
    (level-0 kinds -- jackals, sewer rats, kobolds, goblins -- from XL CHOKE_TRIVIAL_XL on)."""
    out = []
    for m in monsters:
        mon = m[3]
        name = getattr(mon, 'mname', '')
        if name in ONLY_RANGED_SLOW_MONSTERS or name in WEAK_MONSTERS:
            continue
        if getattr(mon, 'mmove', 12) <= 0:
            continue
        if xl >= jf_config.CHOKE_TRIVIAL_XL and getattr(mon, 'mlevel', 1) <= 0:
            continue
        out.append(m)
    return out


def _wallwalker(mon):
    return bool(getattr(mon, 'mflags1', 0) & MON.M1_WALLWALK)


def _excluded(agent):
    """Where the tactic stays out: other branches, special levels and states with plans of their own."""
    level = agent.current_level()
    dive = agent.global_logic.dive
    if level.dungeon_number not in (Level.DUNGEONS_OF_DOOM, Level.GNOMISH_MINES):
        return 'branch'
    if dive.on_medusa_level() or dive.below_medusa():
        return 'medusa'   # (the mazes below: every square is a corridor, and their minotaurs are MINO_GUARD's)
    castle_key = getattr(dive.castle, 'castle_key', None)
    if castle_key is not None and castle_key == level.key():
        return 'castle'
    if dive.levitating():
        return 'levitating'
    prop = agent.character.prop
    if prop.blind or prop.hallu or prop.polymorph:
        return 'state'
    if level.shop[agent.blstats.y, agent.blstats.x]:
        return 'shop'
    if agent.in_pit():
        return 'pit'
    return None


class Geometry:
    """The ground as the pack sees it: squares a monster can stand on (known walkable, no boulder) and the diagonal
    rule (no diagonal step into or out of a door, as the bot's own BFS)."""

    def __init__(self, agent, level, thr):
        self.level = level
        self.walk = level.walkable & ~utils.isin(agent.glyphs, G.BOULDER)
        self.diag = self.walk & ~utils.isin(level.objects, G.DOORS) & (level.objects != -1)
        self.thr = sorted(thr, key=lambda m: m[0] if m[0] >= 0 else 99)[:jf_config.CHOKE_MAX_THREATS]
        self._facing = {}

    def open_count(self, y, x):
        n = 0
        h, w = self.walk.shape
        for dy, dx in NEIGH:
            yy, xx = y + dy, x + dx
            if 0 <= yy < h and 0 <= xx < w and self.walk[yy, xx]:
                n += 1
        return n

    def facing(self, y, x):
        """How many neighbours of (y, x) the pack can come at it through: reached by some threat with (y, x) itself
        blocked, within CHOKE_DETOUR squares over that threat's straight-line distance."""
        key = (y, x)
        if key in self._facing:
            return self._facing[key]
        h, w = self.walk.shape
        nbrs = [(y + dy, x + dx) for dy, dx in NEIGH
                if 0 <= y + dy < h and 0 <= x + dx < w and self.walk[y + dy, x + dx]]
        walk = self.walk.copy()
        diag = self.diag.copy()
        walk[y, x] = False
        diag[y, x] = False
        face = set()
        for m in self.thr:
            my, mx = int(m[1]), int(m[2])
            if (my, mx) == (y, x):
                continue
            if len(face) == len(nbrs):
                break
            dm = utils.bfs(my, mx, walkable=walk, walkable_diagonally=diag, can_squeeze=True)
            lim = _cheb((my, mx), (y, x)) + jf_config.CHOKE_DETOUR
            for n in nbrs:
                if 0 <= dm[n] <= lim:
                    face.add(n)
        self._facing[key] = len(face)
        return len(face)

    def is_choke(self, y, x):
        """(ok, facing, open) for (y, x)."""
        n_open = self.open_count(y, x)
        if n_open <= 2:
            return True, n_open, n_open
        f = self.facing(y, x)
        return f <= jf_config.CHOKE_MAX_FACING, f, n_open


class ChokeState:
    """Per-agent memory: the square we hold, since when, the last contact, the cooldown, the log throttle."""

    def __init__(self):
        self.hold = None          # (dungeon, level, y, x)
        self.since = 0
        self.last_contact = 0
        self.last_call = -10 ** 9
        self.cool_until = -1
        self.last_log = (None, -10 ** 9)


def _state(agent):
    st = getattr(agent, '_choke_state', None)
    if st is None:
        st = agent._choke_state = ChokeState()
    return st


def _before_us(m, steps, c):
    """m (not next to us) can't get onto square c before we stand on it (faster kinds cover more squares a turn)."""
    mmove = getattr(m[3], 'mmove', 12) or 12
    return _cheb((m[1], m[2]), c) > steps * max(mmove, 12) / 12.0


def find_chokepoint(agent, geo, dis, view, max_steps):
    """The nearest chokepoint within max_steps BFS steps: (steps, facing, -margin, y, x, open) or None."""
    level = geo.level
    here = (agent.blstats.y, agent.blstats.x)
    mt = agent.monster_tracker
    far = [m for m in view if _cheb((m[1], m[2]), here) > 1]
    by_steps = {}
    ys, xs = np.nonzero((dis >= 1) & (dis <= max_steps))
    for y, x in zip(ys, xs):
        y, x = int(y), int(x)
        if not geo.walk[y, x] or mt.monster_mask[y, x] or mt.peaceful_monster_mask[y, x]:
            continue
        if level.shop[y, x] or level.objects[y, x] in G.TRAPS:
            continue
        if not known_around(level, y, x):
            continue
        steps = int(dis[y, x])
        if not all(_before_us(m, steps, (y, x)) for m in far):
            continue
        by_steps.setdefault(steps, []).append((y, x))
    evaluated = 0
    for steps in sorted(by_steps):
        best = None
        for y, x in by_steps[steps]:
            if evaluated >= jf_config.CHOKE_MAX_CANDIDATES:
                break
            evaluated += 1
            ok, f, n_open = geo.is_choke(y, x)
            if not ok:
                continue
            margin = min((_cheb((m[1], m[2]), (y, x)) for m in view), default=99)
            cand = (steps, f, -margin, y, x, n_open)
            if best is None or cand < best:
                best = cand
        if best is not None:
            return best
    return None


def _first_step(agent, dis, target):
    """A legal step (dy, dx) from us one BFS step closer to target. Deterministic: agent.path shuffles with the
    bot's RNG, and CHOKE_LOG must not change any later choice."""
    y0, x0 = agent.blstats.y, agent.blstats.x
    dis_c = agent.bfs(*target)
    here = dis_c[y0, x0]
    if here <= 0:
        return None
    mt = agent.monster_tracker
    for dy, dx in NEIGH:
        y, x = y0 + dy, x0 + dx
        if not (0 <= y < dis.shape[0] and 0 <= x < dis.shape[1]):
            continue
        if dis[y, x] != 1 or dis_c[y, x] != here - 1:
            continue
        if mt.monster_mask[y, x] or mt.peaceful_monster_mask[y, x]:
            continue
        return dy, dx
    return None


def adjust(agent, monsters, actions, dis):
    """fight2's hook: returns (actions, note); note (or None) is the log line's text. With CHOKEPOINT off (CHOKE_LOG
    only) the actions come back unchanged and the note is the census line."""
    st = _state(agent)
    bl = agent.blstats
    t = bl.time
    # CHOKE_FROM_TURN (dev replays only): log-only before that turn, so a pinned game replays the base game up to the
    # fight under study (CHOKE_LOG is byte-identical to the flag off)
    act = bool(jf_config.CHOKEPOINT) and t >= jf_config.CHOKE_FROM_TURN
    if t - st.last_call > 3:
        st.hold = None            # a new fight
    st.last_call = t
    if _excluded(agent) is not None:
        st.hold = None
        return actions, None
    thr = threats(monsters, bl.experience_level)
    if not thr or any(_wallwalker(m[3]) for m in thr):
        st.hold = None
        return actions, None
    level = agent.current_level()
    key = level.key()
    here = (bl.y, bl.x)
    adj = [m for m in thr if _cheb((m[1], m[2]), here) <= 1]
    near = [m for m in thr if _cheb((m[1], m[2]), here) <= jf_config.CHOKE_NEAR_RADIUS]
    view = [m for m in thr if _cheb((m[1], m[2]), here) <= jf_config.CHOKE_VIEW_RADIUS]
    if adj:
        st.last_contact = t
    triggered = len(near) >= jf_config.CHOKE_MIN_NEAR or len(view) >= jf_config.CHOKE_MIN_VIEW
    holding = st.hold == (*key, *here)
    if not holding:
        st.hold = None
    if not triggered and not holding and len(adj) < 2:
        return actions, None
    geo = Geometry(agent, level, view or near or adj)
    ok_here, f_here, n_here = geo.is_choke(*here)
    names = sorted(m[3].mname for m in view)[:6]
    info = f'adj={len(adj)} near={len(near)} view={len(view)} here={square_class(level, *here)}/{n_here}/{f_here}'
    # a hold that sees nothing come at us ends (sleeping packs, monsters that keep their distance)
    if holding and not adj and t - max(st.last_contact, st.since) > jf_config.CHOKE_HOLD_TURNS:
        st.hold = None
        st.cool_until = t + jf_config.CHOKE_COOLDOWN
        return actions, f'release (no contact for {jf_config.CHOKE_HOLD_TURNS} turns) {info} {names}'
    if t < st.cool_until and not adj:
        return actions, None
    if not triggered and not holding:
        return actions, f'census {info} (no trigger) {names}'
    dive = agent.global_logic.dive
    # on a chokepoint already: hold it -- unless we are only being shot at from afar (waiting just takes the volleys; a
    # thrown dagger with the pack at the door is no reason to walk out into it: jf80 s5's grind stepped from the
    # doorway into a room of hill orcs after one, 33 -> 11 HP)
    if ok_here:
        if dive.shot_recently() and t - st.last_contact > jf_config.CHOKE_SHOT_TURNS:
            st.hold = None
            return actions, f'census {info} shot at: no hold {names}'
        if not holding:
            st.hold = (*key, *here)
            st.since = t
        if not act:
            return actions, f'census {info} would hold {names}'
        kept = [a for a in actions if a[1][0] not in ('move', 'go_to')]
        kept.append((jf_config.CHOKE_HOLD_PRIORITY, ('hold',)))
        return kept, f'hold {info} {names}'
    st.hold = None
    # in the open: walk to a chokepoint, unless something better holds us here
    if level.objects[here] in _STAIRS:
        return actions, f'census {info} on stairs {names}'
    if (agent.inventory.engraving_below_me or '').lower() == 'elbereth' and \
            not any(dive._melee_ignores_elbereth(m[3]) for m in adj):
        return actions, f'census {info} on Elbereth {names}'
    if adj and not (len(adj) >= 2 or len(near) >= 3):
        return actions, f'census {info} one adjacent: fight {names}'
    max_steps = jf_config.CHOKE_RETREAT_STEPS if adj else jf_config.CHOKE_STEPS
    best = find_chokepoint(agent, geo, dis, view, max_steps)
    if best is None:
        return actions, f'census {info} no chokepoint within {max_steps} {names}'
    steps, f_c, _, cy, cx, n_c = best
    step = _first_step(agent, dis, (cy, cx))
    where = f'{square_class(level, cy, cx)}/{n_c}/{f_c} at {(cy, cx)} {steps} steps'
    if step is None:
        return actions, f'census {info} {where}: no first step {names}'
    if not act:
        return actions, f'census {info} would go {where} {names}'
    return actions + [(jf_config.CHOKE_PRIORITY, ('move', step[0], step[1]))], f'approach {info} -> {where} {names}'


def would_choose(actions, attack_only):
    """fight2's choice from its own actions (before adjust), with its stall breaker's attack-only filter."""
    if attack_only:
        attacks = [a for a in actions if a[1][0] in ('melee', 'kick', 'ranged', 'zap')]
        if attacks:
            actions = attacks
    return max(actions, key=lambda a: a[0])[1] if actions else None


def _act_str(a):
    """An action tuple, e.g. ('move', dy, dx) or ('zap', dy, dx, wand, targets), as 'move 1 0'."""
    if a is None:
        return 'None'
    return ' '.join([str(a[0])] + [str(int(v)) for v in a[1:3] if isinstance(v, (int, np.integer))])


def log_choice(agent, note, best_action, would):
    """One line per decision change (and at most every CHOKE_LOG_EVERY turns while it repeats). 'changed' marks a
    choice that differs from fight2's own (the first one in a game is where CHOKEPOINT first acted)."""
    st = _state(agent)
    t = agent.blstats.time
    kind = note.split(' ', 1)[0]
    chosen = _act_str(best_action)
    changed = would is not None and _act_str(would) != chosen
    sig = (kind, best_action[0] if best_action else None, changed)
    if st.last_log[0] == sig and t - st.last_log[1] < jf_config.CHOKE_LOG_EVERY:
        return
    st.last_log = (sig, t)
    agent.log(f'CHOKE {note} -> {chosen}{" changed from " + _act_str(would) if changed else ""}')
