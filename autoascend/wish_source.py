"""wishes lane (lane 5, readiness program 2026-10-01): wishes from thrones and magic lamps, and what a SINGLE wish asks for.

A wand of wishing gives a route (tele_route.py); a throne or a lamp gives ONE wish, and a wish cannot be saved once it is
granted. Everything here is behind jf_config flags that are OFF unless measured (THRONE_SIT, THRONE_HUNT, LAMP_RUB,
WISH_SINGLE); with them off no code of this module runs (the hooks test the flags first), so games replay byte-identically.

THRONES -- NetHack 3.6.6 (verified in handoff/nethack-3.6.6/src):
* mklev.c makelevel: on a rooms-and-corridors level at depth > 4 the special-room chain makes a court when the shop roll
  fails (!rn2(6)): 5.75% of surveyed levels at Dlvl 5-12 and 11.75% at 13-20 (our survey of 1600 natural levels,
  runs/wish-survey-d*, dev/wscenario.py rooms_survey). mkroom.c fill_zoo: every floor square of the court holds a SLEEPING
  hostile court monster (courtmon(): kobolds, gnomes, hobgoblins/bugbears, orcs at shallow depth; centaurs, trolls,
  giants, dragons deeper) except the squares along the wall that carries the room's first door; the ruler
  (mk_zoo_thronemon: gnome king / dwarf king / Elvenking / ogre king by depth) sleeps ON the throne.
* A Valkyrie has intrinsic Stealth: monmove.c disturb() wakes a sleeper only when !Stealth, and hack.c check_special_room
  wakes the whole level's sleepers 1 time in 3 on entering a court only when !Stealth. So the court stays asleep until we
  hit a monster; each blow wakes just its target.
* sit.c: every #sit on a throne: rnd(6) > 4 (1/3) -> rnd(13): 6 = makewish() (Luck >= 0), 8 = genocide (do_genocide(5)),
  12 = identify, 7 = rnd(10) awake court monsters next to us, 3 = shock rnd(30), 1 = lose attribute + rnd(10) HP, 9 = curse
  items (Luck <= 0) or 250-349 turns of blindness (Luck > 0), 11 = teleport, 13 = confusion; then !rn2(3) the throne
  vanishes. P(wish per throne) = 1/13.
* sounds.c dosounds: has_court && !rn2(200) per turn, only while a sleeping or lord/prince court monster is in the room, so a
  20-turn visit hears a court on 10% of court levels; hack.c says 'You enter an opulent throne room!' on entering. The
  throne glyph is hidden under the ruler until he dies; the #terrain view (agent.check_terrain) shows it.

LAMP -- apply.c dorub: wields the lamp, a magic lamp with spe > 0 releases the djinni 1 time in 3 (potion.c
djinni_from_bottle: blessed 80% wish, uncursed 20% wish / 20% tame / 20% peaceful / 20% gone / 20% hostile, cursed 5% wish /
80% hostile); mkobj.c blesses/curses a random magic lamp 1 in 4 each, so 31% of random lamps grant a wish. 'You see a puff
of smoke' comes only from a magic lamp, 'Nothing happens' also from an oil lamp. The base price is 50 (objects.c; a shop
'lamp' quoted 50-100 is magic, ledger F304); lane 4 (supply) buys it, this module rubs it. An unpaid lamp is never rubbed.

SINGLE WISH (WISH_SINGLE) -- see single_wish(): the wish is chosen from the kit, measured in the harness on the real castle
kits (ledger result posts); power.wish_text calls it when agent.wish_purpose == 'single'.

Entry points:
  note_message(agent)       agent.update: court sounds, 'You enter an opulent throne room!', throne / lamp outcomes
  note_glyphs(agent)        agent.update_level: throne squares seen (also in the #terrain view)
  throne_strategy(dive)     preempt-chain strategy: walk to the throne, kill what sits in the way, #sit until it vanishes
  hunt_level(dive)          DiveLogic: explore this level for the court we heard (THRONE_HUNT, bounded)
  lamp_strategy(agent)      preempt-chain strategy: rub a carried magic-lamp candidate (LAMP_RUB_FIRST: also with a hostile in view)
  single_wish(agent)        the wish text for purpose 'single': single_wish_v1 (phase 1) or, WISH_SINGLE_V2, single_wish_v2
  horn_strategy(dive)       preempt-chain strategy (HORN_LANDING): blow a known tooled horn at the castle-likely landing before the
                            west maze's minotaur shows up
"""
import heapq
import re

import nle.nethack as nh
from nle.nethack import actions as A

from . import jf_config, utils
from .exceptions import AgentChangeStrategy, AgentFinished, AgentPanic
from .glyph import G, MON, SS, Hunger
from .item import Item, flatten_items
from .strategy import Strategy

THRONE_GLYPH = SS.S_throne
COURT_SOUNDS = re.compile(r"courtly conversation|sceptre pounded in judgment|Off with (?:her|his|their|its) head|"
                          r"Queen Beruthiel's cats")
ENTER_COURT = 'You enter an opulent throne room'
RULERS = frozenset(('gnome king', 'dwarf king', 'Elvenking', 'ogre king'))
# never meleed by this module (the fight2 lists: passive damage or paralysis); none lives in a court, but a wanderer may
# stand next to us
NO_MELEE = frozenset(('floating eye', 'gas spore', 'green mold', 'yellow mold', 'brown mold', 'red mold', 'blue jelly',
                      'spotted jelly', 'ochre jelly', 'acid blob', 'gelatinous cube', 'cockatrice', 'chickatrice'))
# 'The jackal bites!' / 'It misses.' -- a monster's attack on us (ours read 'You hit the jackal.')
_ATTACKED = re.compile(r"(?:^|[.!?] ?)(?:The |An? )?([A-Za-z' -]+?) (?:hits|bites|misses|just misses|stings|touches|kicks|"
                       r"claws|butts|thrusts|swings|bashes|slashes|punches|whips|spears|stabs|strikes|pummels|squeezes|"
                       r"gores|lashes|scratches|smites|clubs|pricks|impales)\b")
# ... and the other things only an awake monster does (a thrown dart, a wielded weapon): the court is up
_ACTING = re.compile(r"(?:^|[.!?] ?)(?:The |An? )?([A-Za-z' -]+?) (?:throws|wields|zaps|picks up|puts on|fires|shoots|casts|"
                     r"turns to flee)\b")
_DIRS8 = [(dy, dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx]


# ---------------------------------------------------------------------------------------------------------------- state

class LevelNote:
    def __init__(self, key):
        self.key = key
        self.heard = None          # turn a court sound was heard here
        self.entered = None        # turn 'You enter an opulent throne room!' appeared here
        self.cells = set()         # throne squares (y, x) seen in the map or the #terrain view
        self.gone = set()          # ... that vanished ('puff of logic')
        self.terrain_tries = 0
        self.started = None        # turn the approach began
        self.hunt_started = None
        self.giveup = None         # reason, once abandoned
        self.done = False          # the throne is gone
        self.sits = 0
        self.actions = 0
        self.rest_turns = 0
        self.door_tries = 0
        self.nopath = 0
        self.panics = 0
        self.mobile = []           # (turn, y, x): a monster that appeared on a square that showed floor an observation ago
        self.terrain_turn = -10 ** 9
        self.mobile_logged = 0
        self.last_sit_turn = None
        self.alert_until = None    # turn until which every neighbour counts as awake (after a summons)
        self.corpse_since = None   # turn we began waiting for a corpse on the throne to rot away
        self.bad_edges = set()     # ((y, x), (y, x)) steps the game refused (a squeeze, a doorway diagonal): the planner avoids them
        self.pending_edge = None
        self.cleared = False       # nothing lies on the throne square (sit.c dosit sits on an object first)
        self.rot_wait = 0          # turns spent waiting for a corpse on the throne to rot away


class WishState:
    def __init__(self):
        self.levels = {}
        self.sat = 0                # #sit actions in all
        self.thrones = 0            # thrones that vanished under us
        self.wishes = 0
        self.effects = {}
        self.rubs = {}              # lamp inventory letter -> rubs so far
        self.smoke = set()          # lamp letters that gave 'a puff of smoke' (magic)
        self.oil = set()            # lamp letters that never did in LAMP_RUBS rubs, or that released the djinni
        self.djinni = 0
        self.lamp_errors = 0
        self.last_msg_step = -1
        self.rewield = False        # LAMP_RUB_FIX: a rub was cut short with the lamp in the hand
        self.rewield_tries = 0


def state(agent):
    st = getattr(agent, '_ws', None)
    if st is None:
        st = agent._ws = WishState()
    return st


def note(agent, key=None):
    st = state(agent)
    if key is None:
        key = agent.current_level().key()
    ln = st.levels.get(key)
    if ln is None:
        ln = st.levels[key] = LevelNote(key)
    return ln


def _obs(agent):
    """(level key, depth, turn, y, x, dungeon number) of the observation being processed: agent.blstats still holds the previous
    one when agent.update calls note_message, and 'You fall through...' + 'You enter an opulent throne room!' can arrive in the
    same observation as the new level."""
    b = agent._observation['blstats']
    return (int(b[23]), int(b[24])), int(b[12]), int(b[20]), int(b[1]), int(b[0]), int(b[23])


_SHADOW = [False]   # WISH_V2_SHADOW: True while a policy is evaluated only to be logged


def _log(agent, msg):
    agent.log(f'WISHSRC {"[shadow] " if _SHADOW[0] else ""}{msg}')


def _cheb(a, b):
    return max(abs(int(a[0]) - int(b[0])), abs(int(a[1]) - int(b[1])))


# ---------------------------------------------------------------------------------------------------------------- hooks

def note_message(agent):
    """agent.update, every observation (flags on only): court sounds, the court entry message, throne and wish results."""
    msg = agent.single_message or ''
    if not msg:
        return
    st = state(agent)
    if st.last_msg_step == agent.step_count:
        return
    st.last_msg_step = agent.step_count
    try:
        if getattr(agent, '_observation', None) is None:
            return
        key, depth, turn, y, x, dnum = _obs(agent)
        if dnum == 0 and not agent.character.prop.hallu:
            if COURT_SOUNDS.search(msg):
                ln = note(agent, key)
                if ln.heard is None:
                    _log(agent, f'court heard on {key} at depth {depth}: {msg[:80]!r}')
                ln.heard = turn
            if ENTER_COURT in msg:
                ln = note(agent, key)
                if ln.entered is None:
                    _log(agent, f'entered the throne room on {key} at depth {depth}')
                ln.entered = turn
        if 'The throne vanishes in a puff of logic' in msg:
            ln = note(agent, key)
            ln.gone.add((y, x))
            ln.done = not (ln.cells - ln.gone)
            st.thrones += 1
            _log(agent, f'the throne vanished after {ln.sits} sits at {(y, x)}')
        if 'You may wish for an object' in msg:
            st.wishes += 1
            _log(agent, f'a wish prompt (purpose {getattr(agent, "wish_purpose", None)!r})')
    except Exception as e:   # learning must never break the step loop
        agent.log(f'WISHSRC note_message failed: {e!r}')


def _track_mobile(agent, ln, now):
    """Who is awake? A sleeping monster never changes square, so a monster glyph that shows up on a square which displayed
    plain floor in the previous observation arrived there on its own legs (the court's sleepers are seen all at once, from
    squares that showed stone or nothing before). Kept for 3 turns in ln.mobile as (turn, y, x)."""
    prev = getattr(agent, '_previous_glyphs', None)
    if prev is None:
        return
    mons = agent.monster_tracker.monster_mask & ~agent.monster_tracker.peaceful_monster_mask
    cur = agent.glyphs
    for y, x in zip(*mons.nonzero()):
        if not MON.is_monster(cur[y, x]):
            continue
        pg = prev[y, x]
        if pg in G.FLOOR and (y, x) != (agent.blstats.y, agent.blstats.x):
            ln.mobile.append((now, int(y), int(x)))
            if jf_config.THRONE_DEBUG and ln.mobile_logged < 25:
                ln.mobile_logged += 1
                _log(agent, f'mover? {MON.permonst(cur[y, x]).mname} at {(int(y), int(x))} (was glyph {int(pg)}) hero at '
                            f'{(int(agent.blstats.y), int(agent.blstats.x))}')
    ln.mobile = [m for m in ln.mobile if now - m[0] <= 3][-40:]


def awake_monsters(agent, ln):
    """get_visible_monsters() restricted to the squares of recent movers (see _track_mobile)."""
    if not ln.mobile:
        return []
    squares = {(m[1], m[2]) for m in ln.mobile}
    return [m for m in agent.get_visible_monsters() if (int(m[1]), int(m[2])) in squares]


def note_glyphs(agent):
    """agent.update_level (flags on only): remember the throne squares and track who moves. The map shows a throne only when
    nothing stands or lies on it; the #terrain view (agent.check_terrain) shows it under the ruler and his sleepers."""
    try:
        bl = agent.blstats
        if bl.dungeon_number != 0 or agent.character.prop.hallu:
            return
        ln = agent.__dict__.get('_ws') and state(agent).levels.get(agent.current_level().key())
        if getattr(agent, '_terrain_view', False):
            state(agent).after_terrain = True   # this picture has no monsters in it: the next real one must not be compared
        elif ln is not None and (ln.heard is not None or ln.entered is not None or ln.cells):
            if getattr(state(agent), 'after_terrain', False):
                state(agent).after_terrain = False
            else:
                _track_mobile(agent, ln, bl.time)
        mask = agent.glyphs == THRONE_GLYPH
        if not mask.any():
            return
        ln = note(agent)
        level = agent.current_level()
        for y, x in zip(*mask.nonzero()):
            c = (int(y), int(x))
            if c in ln.gone:
                continue
            if c not in ln.cells:
                ln.cells.add(c)
                _log(agent, f'throne seen at {c} on {ln.key} (terrain view: {bool(getattr(agent, "_terrain_view", False))})')
            # walkable and known, so our planner may use it (update_level does not know thrones)
            level.walkable[c] = True
            level.objects[c] = THRONE_GLYPH
    except Exception as e:
        agent.log(f'WISHSRC note_glyphs failed: {e!r}')


# ---------------------------------------------------------------------------------------------------------------- planning

def _masks(agent):
    level = agent.current_level()
    walk = level.walkable & ~utils.isin(agent.glyphs, G.BOULDER) & \
        ~agent.monster_tracker.peaceful_monster_mask & ~level.forbidden
    walk = walk & ~utils.isin(level.objects, G.TRAPS)
    walk = walk | (utils.isin(level.objects, G.DOOR_CLOSED) & ~level.forbidden)   # ours to open (or kick) on the way
    diag = walk & ~utils.isin(level.objects, G.DOORS) & (level.objects != -1) & ~level.intact_doors
    can_squeeze = agent.inventory.items.total_weight <= 600
    if can_squeeze and jf_config.ROBUST_FIXES2 and agent._squeeze_blocked():
        can_squeeze = False   # the game refused a squeeze ('You are carrying too much to get through')
    return walk, diag, can_squeeze


def _hostiles(agent):
    """Visible hostile monsters: {(y, x): (dist, permonst)}."""
    return {(int(m[1]), int(m[2])): (m[0], m[3]) for m in agent.get_visible_monsters()}


def _ruler_ok(agent, started):
    bl = agent.blstats
    bar = 0.6 if started else 0.8
    return bl.hitpoints >= max(jf_config.THRONE_RULER_HP, bar * bl.max_hitpoints) and bl.experience_level >= 6


def _dangerous(agent, mon, ruler_ok):
    """A monster this module leaves asleep (its square is closed to the path): well above our level, or a ruler we are
    not fit for."""
    name = getattr(mon, 'mname', '')
    if name in NO_MELEE or name in jf_config.THRONE_AVOID:
        return True
    if name in RULERS:
        # an Elvenking (two 2d4+weapon attacks at speed 12) or an ogre king (3d5+club at 14) takes ~17 HP a turn from an AC-0
        # Valkyrie and ~40-60 HP to kill: jf81 s3 (cand-k replay) lost 37 of 63 HP in 8 turns and died two levels of
        # trouble later. Only a gnome king (difficulty 6) or a dwarf king (8) is fought, by XL + THRONE_RULER_DIFF
        return not ruler_ok or getattr(mon, 'difficulty', 99) > agent.blstats.experience_level + jf_config.THRONE_RULER_DIFF
    return getattr(mon, 'difficulty', 99) > agent.blstats.experience_level + jf_config.THRONE_DIFF


def _dijkstra(agent, start, goal, mons, ruler_ok, bad_edges=()):
    """A cheapest path start -> goal over known walkable squares: 1 per step, THRONE_MON_COST more through a hostile
    monster's square (it must be killed first), dangerous monsters' squares closed. [(y, x), ...] or None."""
    walk, diag, can_squeeze = _masks(agent)
    H, W = walk.shape
    inf = 10 ** 9
    dist = {start: 0}
    prev = {}
    heap = [(0, start)]
    while heap:
        d, cur = heapq.heappop(heap)
        if cur == goal:
            break
        if d > dist.get(cur, inf):
            continue
        y, x = cur
        for dy, dx in _DIRS8:
            ny, nx = y + dy, x + dx
            if not (0 <= ny < H and 0 <= nx < W) or not walk[ny, nx] or (cur, (ny, nx)) in bad_edges:
                continue
            if dy and dx and not (diag[ny, nx] and (diag[y, x] or cur == start) and
                                  (can_squeeze or walk[ny, x] or walk[y, nx])):
                continue
            cost = 1
            m = mons.get((ny, nx))
            if m is not None:
                if _dangerous(agent, m[1], ruler_ok):
                    continue
                cost += jf_config.THRONE_MON_COST
            nd = d + cost
            if nd < dist.get((ny, nx), inf):
                dist[(ny, nx)] = nd
                prev[(ny, nx)] = cur
                heapq.heappush(heap, (nd, (ny, nx)))
    if goal not in dist:
        return None
    path = [goal]
    while path[-1] != start:
        path.append(prev[path[-1]])
    return path[::-1]


def _attackers(agent):
    """Names (lower case) of monsters that attacked us in the last action's messages."""
    names = []
    for m in _ATTACKED.finditer(agent.message or ''):
        n = m.group(1).strip().lower()
        if n and n not in ('you', 'it'):
            names.append(n)
    return names


def _awake_names(agent):
    """Names (lower case) of monsters that attacked us or did something only an awake monster does in the last action's messages."""
    names = set(_attackers(agent))
    for m in _ACTING.finditer(agent.message or ''):
        n = m.group(1).strip().lower()
        if n and n not in ('you', 'it'):
            names.add(n)
    return names


def _throne_cells(ln):
    return sorted(ln.cells - ln.gone)


def _wield_ok(agent):
    """The best melee weapon in hand (the dive keeps the pick-axe wielded to dig)."""
    try:
        best = agent.inventory.get_best_melee_weapon()
        return best is None or best == agent.inventory.items.main_hand or agent.hands_welded()
    except Exception:
        return True


# ---------------------------------------------------------------------------------------------------------------- throne

def _plan(agent, dive):
    """The next throne action, or None. No env steps here (this runs as a preempt condition after every observation)."""
    bl = agent.blstats
    if bl.dungeon_number != 0 or not (jf_config.THRONE_MIN_DEPTH <= bl.depth <= jf_config.THRONE_MAX_DEPTH):
        return None
    st = state(agent)
    key = agent.current_level().key()
    ln = st.levels.get(key)
    if ln is None or ln.giveup or ln.done:
        return None
    cells = _throne_cells(ln)
    if not cells and not ((ln.entered is not None or ln.heard is not None) and
                          ln.terrain_tries < jf_config.THRONE_TERRAIN_TRIES):
        return None
    prop = agent.character.prop
    if prop.hallu or prop.blind or prop.polymorph or dive.levitating() or getattr(dive, 'rescue', False):
        return None
    if bl.hunger_state >= Hunger.WEAK:
        return None
    if ln.actions >= jf_config.THRONE_MAX_ACTIONS:
        ln.giveup = 'action budget'
        _log(agent, f'giving up {key}: action budget ({ln.actions})')
        return None
    if not cells:
        # entered: look at once; only heard: look when a crowd of monsters is in view (the court seen from its door or
        # a window) and now and then as exploration reveals more of the room (the look takes no game time)
        if ln.entered is not None and ln.terrain_tries == 0:
            return ('terrain',)
        if bl.time - ln.terrain_turn >= 15 and len(agent.get_visible_monsters()) >= jf_config.THRONE_CROWD:
            return ('terrain',)
        return None
    me = (int(bl.y), int(bl.x))
    hp, hpmax = bl.hitpoints, bl.max_hitpoints
    started = ln.started is not None
    if started and hp < jf_config.THRONE_ABORT_HP * hpmax:
        ln.giveup = 'low hp'
        _log(agent, f'giving up {key}: HP {hp}/{hpmax} after {ln.actions} actions, {ln.sits} sits')
        return None
    if started and bl.time - ln.started > jf_config.THRONE_TURNS:
        ln.giveup = 'turn budget'
        _log(agent, f'giving up {key}: turn budget ({bl.time - ln.started} turns)')
        return None
    mons = _hostiles(agent)
    adj = [(c, m) for c, m in mons.items() if _cheb(c, me) == 1]
    # (the HP a sit costs -- shock, 'lose attribute' -- is the throne's, not an attacker's)
    hurt = agent._hurt_recently(2) and not (ln.last_sit_turn is not None and bl.time - ln.last_sit_turn <= 2)
    attackers = _attackers(agent)
    mobile_sq = {(m[1], m[2]) for m in ln.mobile}
    if ln.alert_until is not None and bl.time <= ln.alert_until:
        # the throne summoned its court (sit.c case 7: rnd(10) awake courtmon() next to us): the sit ran inside an atom
        # operation, so the mover tracker never saw them arrive -- everything next to us is awake for a while
        mobile_sq |= {c for c, _ in adj}
    # a court that is up (a kicked door wakes everything within sqrt(20 XL) squares, dokick.c wake_nearby; a fall into the room next to
    # a woken ruler): a crowd is a fight we do not need -- jf81 s3 lost 37 of 63 HP in 8 turns to ten kobolds and gnomes at the door
    awake_names = _awake_names(agent)
    awake_sq = {c for c, m in mons.items() if c in mobile_sq or getattr(m[1], 'mname', '').lower() in awake_names}
    if len(awake_sq) >= jf_config.THRONE_AWAKE_MAX:
        ln.giveup = f'court awake ({len(awake_sq)})'
        _log(agent, f'giving up {key}: {len(awake_sq)} awake monsters in view (HP {hp}/{hpmax})')
        return None
    # an awake monster next to us (it hit us, or it walked up: a woken blow's target, the summoned court): fight it first,
    # wherever we are
    if adj and (hurt or attackers or any(c in mobile_sq for c, _ in adj)):
        ruler_now = _ruler_ok(agent, started)
        awake_bad = [m[1].mname for c, m in adj if (c in mobile_sq or getattr(m[1], 'mname', '').lower() in attackers) and
                     _dangerous(agent, m[1], ruler_now)]
        if awake_bad:
            ln.giveup = f'awake {awake_bad[0]}'
            _log(agent, f'giving up {key}: an awake {awake_bad[0]} next to us (HP {hp}/{hpmax})')
            return None   # the dive's own escape (dig_first, prayer) from here
        return ('fight', adj, attackers, mobile_sq)
    if (prop.confusion or prop.stun) and ln.rest_turns < jf_config.THRONE_REST_TURNS:
        return ('wait',)   # sit.c case 13 confuses for 16-22 turns: a confused step lands on a random neighbour (a sleeper)
    if me in cells:
        if hp < max(jf_config.THRONE_SIT_HP, 0.6 * hpmax):
            if hurt:
                return None
            if ln.rest_turns >= jf_config.THRONE_REST_TURNS:
                ln.giveup = 'rest budget'
                return None
            return ('rest',)
        if not ln.cleared:
            return ('clear',)
        return ('sit',)
    ln.cleared = False
    if started and hp < jf_config.THRONE_MID_REST_HP * hpmax and not hurt and ln.rest_turns < jf_config.THRONE_REST_TURNS and \
            not any(_cheb((m[1], m[2]), me) <= 6 for m in ln.mobile):
        return ('rest',)   # the court sleeps (Stealth): nothing near is awake, so heal in the middle of it
    if not started:
        if hp < jf_config.THRONE_HP_FRAC * hpmax or hp < jf_config.THRONE_MIN_HP:
            if hurt:
                return None
            if ln.rest_turns >= jf_config.THRONE_REST_TURNS:
                ln.giveup = 'rest budget'
                return None
            return ('rest',)
        if bl.experience_level < jf_config.THRONE_MIN_XL:
            ln.giveup = 'XL'
            return None
        if not _wield_ok(agent):
            return ('wield',)
    ruler_ok = _ruler_ok(agent, started)
    best = None
    for c in cells:
        path = _dijkstra(agent, me, c, mons, ruler_ok, ln.bad_edges)
        if path is not None and len(path) >= 2 and (best is None or len(path) < len(best)):
            best = path
    if best is None:
        ln.nopath += 1
        if ln.nopath > jf_config.THRONE_NOPATH:
            ln.giveup = 'no path'
            _log(agent, f'giving up {key}: no path to {cells}')
        return None
    return ('go', best)


def _throne_act(agent, dive, plan):
    bl = agent.blstats
    ln = note(agent)
    kind = plan[0]
    ln.actions += 1
    if ln.started is None and kind in ('go', 'fight', 'sit', 'wield'):
        ln.started = bl.time
        _log(agent, f'throne approach starts on {ln.key} depth {bl.depth}: cells {_throne_cells(ln)} HP {bl.hitpoints}/'
                    f'{bl.max_hitpoints} XL {bl.experience_level}')
    try:
        if kind == 'terrain':
            ln.terrain_tries += 1
            ln.terrain_turn = bl.time
            agent.check_terrain(force=True)
            _log(agent, f'terrain look {ln.terrain_tries}: cells {_throne_cells(ln)}')
        elif kind == 'wield':
            agent.wield_best_melee_weapon()
        elif kind == 'rest':
            ln.rest_turns += 10
            agent.search(10)
        elif kind == 'wait':
            ln.rest_turns += 1
            agent.search()
        elif kind == 'fight':
            _, adj, attackers, mobile_sq = plan
            target = None
            for c, m in adj:
                if getattr(m[1], 'mname', '').lower() in attackers or c in mobile_sq:
                    if getattr(m[1], 'mname', '') not in NO_MELEE:
                        target = c
                        break
            if target is None:
                cands = [(getattr(m[1], 'difficulty', 99), c) for c, m in adj
                         if getattr(m[1], 'mname', '') not in NO_MELEE]
                if cands:
                    target = min(cands)[1]
            if target is None:
                agent.search()
            else:
                agent.melee_attack(*target)
        elif kind == 'clear':
            _clear_square(agent, ln)
        elif kind == 'sit':
            _sit(agent, ln)
        elif kind == 'go':
            ny, nx = plan[1][1]
            glyph = agent.glyphs[ny, nx]
            if MON.is_monster(glyph) or glyph in G.INVISIBLE_MON:
                agent.melee_attack(ny, nx)
            elif glyph in G.DOOR_CLOSED:
                ln.door_tries += 1
                if ln.door_tries > 14:
                    ln.giveup = 'door'
                    agent.search()
                elif not agent.open_door(ny, nx) and 'locked' in (agent.message or ''):
                    # a kick calls wake_nearby() (dokick.c:902): the whole court within sqrt(20 XL) squares wakes up and Stealth is
                    # wasted; a pick-axe breaks the door in a few turns without a sound (dig.c). No digging tool: leave the court.
                    tool = dive.digging_tool() if jf_config.THRONE_QUIET_DOORS else None
                    if tool is not None:
                        dive.dig_toward(tool, ny, nx)
                    elif jf_config.THRONE_QUIET_DOORS:
                        ln.giveup = 'locked door'
                        _log(agent, f'giving up {ln.key}: a locked door and no digging tool (a kick would wake the court)')
                        agent.search()
                    else:
                        agent.kick(ny, nx)
            else:
                ln.pending_edge = ((int(bl.y), int(bl.x)), (int(ny), int(nx)))
                agent.move(ny, nx)
                ln.pending_edge = None
    finally:
        pass


def _clear_square(agent, ln):
    """sit.c dosit: with ANY object on the square, #sit sits on the object ('You sit on the corpse.  It's not very
    comfortable...') and never reaches the throne. The ruler dies on his throne and drops his mace (and a dwarf king his whole
    kit), so take what we can lift; a corpse we cannot lift is eaten when the bot's rules allow it (agent.eat_corpses_from_ground:
    not a dwarf's, we are one), else waited out (a corpse rots away after ~250 turns, mkobj.c start_corpse_timeout)."""
    items = agent.inventory.get_items_below_me()
    if not items:
        ln.cleared = True
        _log(agent, 'the throne square is clear')
        return
    movable = [i for i in items if not i.is_corpse() and i.weight() <= jf_config.THRONE_PICKUP_WT]
    if movable:
        _log(agent, f'taking {[i.text for i in movable][:6]} off the throne square')
        agent.inventory.pickup(movable)
        return
    before = agent.step_count
    if any(i.is_corpse() for i in items):
        agent.eat_corpses_from_ground(only_below_me=True).run()
        if agent.step_count != before:
            return
        if ln.corpse_since is None:
            ln.corpse_since = agent.blstats.time
            _log(agent, f'waiting for {[i.text for i in items if i.is_corpse()][:2]} on the throne to rot away')
        if agent.blstats.time - ln.corpse_since > jf_config.THRONE_ROT_WAIT:
            ln.giveup = 'corpse'
            _log(agent, f'giving up {ln.key}: a corpse stays on the throne ({[i.text for i in items][:3]})')
        agent.search(10)
        return
    ln.giveup = 'heavy object'
    _log(agent, f'giving up {ln.key}: {[i.text for i in items][:3]} on the throne square')
    agent.search()


def _sit(agent, ln):
    """One #sit on the throne we stand on. Prompts: the wish (agent.update, purpose 'single'), the genocide species (opp_items:
    a throne's genocide is real, never cursed -> 'uncursed throne' tells genocide_answer), the identify menu (power_route)."""
    from . import opp_items, power_route
    st = state(agent)
    bl = agent.blstats
    ln.sits += 1
    st.sat += 1
    ln.last_sit_turn = bl.time
    prev_purpose = getattr(agent, 'wish_purpose', None)
    agent.wish_purpose = 'single'
    if jf_config.GENOCIDE_POLICY:
        opp_items.state(agent).reading = dict(letter=None, glyph=None, text='uncursed throne', count=1,
                                              step=agent.step_count, turn=bl.time, why='throne')
    menu_pages = {}
    sit_cmd = getattr(A.Command, 'SIT', None)

    def gen():
        for _ in range(60):
            msg = agent.single_message or ''
            head = msg + ' ' + ' '.join(agent.single_popup[:3])
            if power_route.in_identify_menu(agent, head, menu_pages):
                keys = power_route._identify_step(agent, menu_pages)
                if keys is None:
                    yield A.Command.ESC
                    continue
                if keys.endswith('\r'):
                    menu_pages.clear()
                for k in keys:
                    yield k
                continue
            misc = agent._observation['misc']
            if misc[2] and not misc[1]:
                yield ' '   # a --More-- (before the identify menu, between the throne's messages)
                continue
            return

    hp0 = bl.hitpoints
    try:
        with agent.atom_operation():
            if sit_cmd is not None:
                agent.step(sit_cmd, gen())
            else:
                agent.type_text('#sit')
                agent.step(A.MiscAction.MORE, gen())
    finally:
        agent.wish_purpose = prev_purpose
    msg = (agent.message or '').replace('\n', ' ')
    kind = _classify(msg)
    st.effects[kind] = st.effects.get(kind, 0) + 1
    if 'puff of logic' in msg:
        kind += '+vanish'
    if 'Thy audience hath been summoned' in msg:
        ln.alert_until = agent.blstats.time + 40
    if re.search(r'You sit on (?!the opulent throne)', msg):
        ln.cleared = False
        kind = 'object'
    _log(agent, f'sit {ln.sits} (HP {hp0}->{agent.blstats.hitpoints}) {kind}: {msg[:140]!r}')
    if ln.sits >= jf_config.THRONE_MAX_SITS:
        ln.giveup = 'sit budget'


_EFFECTS = (
    ('wish', 'You may wish for an object'), ('genocide', 'By thine Imperious order'), ('identify', 'granted an insight'),
    ('summon', 'Thy audience hath been summoned'), ('shock', 'electric shock'), ('curse', 'A curse upon thee'),
    ('teleport', 'wrenching sensation'), ('confusion', 'pretzel'), ('heal', 'much, much better'),
    ('gold', 'Your purse feels lighter'), ('vision', 'vision becomes clear'), ('map', 'image forms in your mind'),
    ('aggravate', 'You feel threatened'), ('nothing', 'out of place'), ('nothing', 'very comfortable'),
    ('attr', 'You feel'),
)


def _classify(msg):
    for kind, needle in _EFFECTS:
        if needle in msg:
            return kind
    return 'nothing'


def scenario_hint(agent):
    """Dev harness only (jf_scenario.STATE keys court_heard / court_entered): the setup knew a court was on the start level."""
    try:
        from . import jf_scenario
        s = jf_scenario.STATE
        if not s or not (s.get('court_heard') or s.get('court_entered')):
            return
        st = state(agent)
        if getattr(st, 'hint_used', False):
            return
        st.hint_used = True
        ln = note(agent)
        t = agent.blstats.time
        if s.get('court_heard'):
            ln.heard = t
        if s.get('court_entered'):
            ln.entered = t
        _log(agent, f'scenario hint on {ln.key}: heard={ln.heard} entered={ln.entered}')
    except Exception as e:
        agent.log(f'WISHSRC scenario_hint failed: {e!r}')


def throne_strategy(dive):
    agent = dive.agent

    def f():
        if not jf_config.THRONE_SIT:
            yield False
            return
        scenario_hint(agent)
        plan = _plan(agent, dive)
        if plan is None:
            yield False
            return
        yield True
        # Keep acting while the plan holds: returning after one action lets the strategy underneath (dig_first: Elbereth,
        # a pit, a hole) take a turn before this hook is checked again (the same lesson as dig_first's own loop). Higher
        # layers' hooks (prayer, known items, minotaur guard) still interrupt any step.
        for _ in range(jf_config.THRONE_LOOP):
            before = agent.step_count
            try:
                _throne_act(agent, dive, plan)
            except AgentPanic:
                ln = note(agent)
                if ln.pending_edge is not None:
                    ln.bad_edges.add(ln.pending_edge)   # (a refused step takes no time: it would repeat for ever)
                    ln.pending_edge = None
                ln.panics += 1
                if ln.panics > jf_config.THRONE_PANICS:
                    ln.giveup = 'panics'
                    _log(agent, f'giving up {ln.key}: {ln.panics} panics in {plan[0]}')
                raise
            except (AgentFinished, AgentChangeStrategy):
                raise
            except Exception as e:
                # any other error (an assertion in the inventory look, say): counted like a panic, so a plan that keeps failing is
                # dropped; the agent's main loop recovers from the exception itself
                ln = note(agent)
                ln.panics += 1
                if ln.panics > jf_config.THRONE_PANICS:
                    ln.giveup = 'errors'
                    _log(agent, f'giving up {ln.key}: {ln.panics} errors, last {type(e).__name__}: {str(e)[:100]}')
                raise
            if agent.step_count == before:
                agent.search()   # a body must step (agent.preempt asserts against cyclic preempts)
            plan = _plan(agent, dive)
            if plan is None:
                break

    return Strategy(f)


# ---------------------------------------------------------------------------------------------------------------- hunt

def hunt_level(dive):
    """THRONE_HUNT: this level has a court we heard (or entered) and no throne is known yet -> explore it (DiveLogic.plan_step
    runs its exploration with a budget, as PREP_MID does). Ends at a danger, the turn budget, hunger, or once a throne
    square is known (throne_strategy takes over)."""
    if not jf_config.THRONE_HUNT:
        return False
    agent = dive.agent
    bl = agent.blstats
    level = agent.current_level()
    if level.dungeon_number != 0 or not (jf_config.HUNT_MIN_DEPTH <= bl.depth <= jf_config.HUNT_MAX_DEPTH):
        return False
    scenario_hint(agent)
    ln = state(agent).levels.get(level.key())
    if ln is None or ln.giveup or ln.done or (ln.heard is None and ln.entered is None) or (ln.cells - ln.gone):
        return False
    if dive.rescue or not dive.diving or dive.digging_tool() is None or level.key() in dive.fully_explored:
        return False
    if bl.hunger_state >= Hunger.WEAK or \
            (ln.hunt_started is not None and bl.time - ln.hunt_started > jf_config.HUNT_TURNS):
        return False
    if bl.hitpoints < jf_config.HUNT_HP * bl.max_hitpoints or bl.experience_level < jf_config.THRONE_MIN_XL:
        return False
    awake = awake_monsters(agent, ln)
    if awake and not dive._prep_calm(awake):
        ln.giveup = 'hunt danger'
        _log(agent, f'hunt on {level.key()} ends: danger '
                    f'{[(m[3].mname, getattr(m[3], "difficulty", -1)) for m in awake[:4]]}')
        return False
    if ln.hunt_started is None:
        ln.hunt_started = bl.time
        _log(agent, f'hunt starts on {level.key()} depth {bl.depth} (heard {ln.heard}, entered {ln.entered})')
    return True


def hunt_calm(dive, monsters):
    """DiveLogic.dig_first while hunting: the ordinary-fight test counts only monsters that moved (the court's sleepers are not
    a crowd to dig away from)."""
    agent = dive.agent
    ln = state(agent).levels.get(agent.current_level().key())
    if ln is None:
        return dive._prep_calm(monsters)
    squares = {(m[1], m[2]) for m in awake_monsters(agent, ln)}
    awake = [m for m in monsters if (m[1], m[2]) in squares]
    return not awake or dive._prep_calm(awake)


# ---------------------------------------------------------------------------------------------------------------- lamp

def lamp_candidates(agent):
    """Carried items that are or may be a magic lamp and are ours to rub: [Item]."""
    try:
        from . import supply   # lane 4's helper when it exists
        helper = getattr(supply, 'magic_lamps', None)
    except Exception:
        helper = None
    items = helper(agent) if helper is not None else [
        i for i in flatten_items(agent.inventory.items)
        if i.category == nh.TOOL_CLASS and any(getattr(o, 'name', '') == 'magic lamp' for o in i.objs)]
    st = state(agent)
    out = []
    for it in items:
        if 'unpaid' in (it.text or '') or it.shop_status == Item.UNPAID:
            continue
        if it.status == Item.CURSED:   # a lamp KNOWN cursed (the display says so): 5% wish, 80% hostile djinni (djinni_from_bottle)
            continue
        try:
            letter = agent.inventory.items.get_letter(it)
            if letter in st.oil:   # (keyed by letter: a released lamp changes its glyph)
                continue
            if jf_config.LAMP_RUB_FIX and st.rubs.get(letter, 0) >= jf_config.LAMP_RUBS_MAX:
                continue   # spent: (2/3)^LAMP_RUBS_MAX for a magic lamp (the 1,969-rub loop of an emptied lamp, routes lane)
        except Exception:
            pass
        out.append(it)
    return out


def _lamp_in_hand(agent):
    """LAMP_RUB_FIX: a lamp is the wielded item (apply.c dorub wields what it rubs; the inventory model keeps main_hand for
    weapons only, so the hand then reads as empty)."""
    try:
        for it in flatten_items(agent.inventory.items):
            if it.equipped and it.category == nh.TOOL_CLASS and \
                    any(getattr(o, 'name', '') in ('oil lamp', 'magic lamp') for o in it.objs):
                return True
    except Exception:
        pass
    return False


def _rewield(agent):
    """Take the lamp out of the hand: the best melee weapon, else the fists."""
    before = agent.step_count
    if not agent.wield_best_melee_weapon() and _lamp_in_hand(agent):
        agent.inventory.wield(None)
    if agent.step_count == before:
        agent.search()    # (a body must step: agent.preempt asserts against cyclic preempts)


def _certainly_magic(agent, item):
    """The lamp is known to be magic: its type says so (supply's shop-price knowledge narrows the glyph), supply published its
    letter, or a rub of it showed 'a puff of smoke'."""
    st = state(agent)
    try:
        letter = agent.inventory.items.get_letter(item)
    except Exception:
        letter = None
    if letter is not None and (letter in st.smoke or letter in getattr(agent, '_magic_lamp_letters', ())):
        return True
    if item.is_unambiguous() and getattr(item.object, 'name', '') == 'magic lamp':
        return True
    try:
        from . import supply
        f = getattr(supply, 'certainly_magic_lamp', None)
        return bool(f is not None and f(item))
    except Exception:
        return False


def _lamp_ok_now(agent, item):
    """A lamp known to be magic waits for the castle (LAMP_RUB_AT 'castle': the wish is then chosen with the final kit, and
    the castle depth is known); a lamp that may be an oil lamp is tested at the first quiet moment, anywhere: 6 rubs show it
    (each rub: djinni 1/3, 'a puff of smoke' 1/3, nothing 1/3 for a magic lamp; always nothing for an oil lamp), and a puff of
    smoke ends the test with the djinni still inside."""
    if not _certainly_magic(agent, item):
        if jf_config.LAMP_CASTLE_TEST and not jf_config.LAMP_TEST_UNKNOWN:
            # LAMP_CASTLE_TEST: a lamp that may be an oil lamp is tested at the castle landing like a known magic one (the test
            # rub frees the djinni half the time: apply.c dorub, 1/3 djinni against 1/3 smoke), where the wish is worth most
            from . import power_route
            return agent.blstats.depth >= 25 and power_route.on_castle_level(agent)
        return jf_config.LAMP_TEST_UNKNOWN
    if jf_config.LAMP_RUB_AT == 'now':
        return True
    from . import power_route
    if jf_config.LAMP_RUB_AT == 'dive':
        # once the dive has started: the pack is the dive-start kit (the dig-dive collects almost nothing), the levels are still
        # easy and quiet moments are many; the castle is not known yet (single_wish then uses its priors)
        dive = power_route._dive(agent)
        return dive is not None and bool(dive.diving)
    return agent.blstats.depth >= 25 and power_route.on_castle_level(agent)


def _rub_blocked(agent):
    """A hostile in view keeps us from rubbing (phase 1: any). LAMP_RUB_FIRST, on a castle-depth level of the Dungeons: only one
    within LAMP_RUB_NEAR squares (Chebyshev: a shark in the moat is next to us although the BFS cannot reach it)."""
    mons = agent.get_visible_monsters()
    if not mons:
        return False
    bl = agent.blstats
    if jf_config.LAMP_RUB_FIRST and bl.dungeon_number == 0 and bl.depth >= 25:
        return any(max(abs(int(m[1]) - int(bl.y)), abs(int(m[2]) - int(bl.x))) <= jf_config.LAMP_RUB_NEAR for m in mons)
    return True


def lamp_strategy(agent):
    def f():
        if jf_config.WISH_V2_SHADOW:
            _shadow(agent)
        if jf_config.AC_PROBE:
            _acprobe(agent)
        if not jf_config.LAMP_RUB:
            yield False
            return
        if jf_config.LAMP_RUB_FIX and state(agent).rewield:
            # a rub cut short (a preempting strategy, e.g. the wish route once the wished ring is in the pack) left the lamp in
            # the hand: the sword goes back first (the castle landing is no place for a lamp in the hand)
            st0 = state(agent)
            if st0.rewield_tries >= 4 or not _lamp_in_hand(agent):
                st0.rewield = False
            elif not agent.hands_welded() and not agent.character.prop.polymorph:
                yield True
                st0.rewield_tries += 1
                try:
                    _rewield(agent)
                except (AgentFinished, AgentChangeStrategy):
                    raise
                except Exception as e:
                    agent.log(f'WISHSRC re-wield failed: {e!r}')
                if not _lamp_in_hand(agent):
                    st0.rewield = False
                return
            else:
                st0.rewield = False
        if jf_config.LANDING_FOCUS:
            # landing lane: a crusher-armed kit rubs its lamp (6-7 turns) on the crusher square under Elbereth, not in the
            # west maze where the minotaur and the lich close in (lnd-a3 jf89-s11: seven rubs at T+7..T+12 among wargs)
            from . import power_route
            dive = power_route._dive(agent)
            if dive is not None and dive.landing_pending():
                yield False
                return
        bl = agent.blstats
        prop = agent.character.prop
        # (a hostile djinni -- 31% of random magic lamps -- is a 7-HD fighter: not at XL 1-5 in the grind, LAMP_MIN_MAXHP)
        if prop.hallu or prop.confusion or prop.stun or prop.polymorph or bl.hitpoints < 0.6 * bl.max_hitpoints or \
                bl.max_hitpoints < jf_config.LAMP_MIN_MAXHP or state(agent).lamp_errors >= 5:
            yield False
            return
        cands = [it for it in lamp_candidates(agent) if _lamp_ok_now(agent, it)]
        if not cands:
            yield False
            return
        if agent.current_level().shop[bl.y, bl.x] or _rub_blocked(agent) or agent.hands_welded():
            yield False
            return
        yield True
        # rub until the djinni comes, or a puff of smoke shows an untested lamp is magic (keep it for the castle), or the lamp is
        # judged an oil lamp: one body, so the strategies underneath get no turn between rubs
        st = state(agent)
        try:
            for _ in range(jf_config.LAMP_RUBS + 2):
                item = cands[0]
                was_certain = _certainly_magic(agent, item)
                djinni_before = st.djinni
                _rub(agent, item)
                if st.djinni != djinni_before or _rub_blocked(agent) or \
                        agent.blstats.hitpoints < 0.5 * agent.blstats.max_hitpoints:
                    break
                cands = [it for it in lamp_candidates(agent) if _lamp_ok_now(agent, it)]
                if not cands or (not was_certain and _certainly_magic(agent, item) and not _lamp_ok_now(agent, item)):
                    break
        except (AgentFinished, AgentChangeStrategy):
            raise
        except Exception as e:
            st.lamp_errors += 1   # (a rub that keeps failing is dropped after a few tries)
            agent.log(f'WISHSRC lamp rub failed ({st.lamp_errors}): {type(e).__name__}: {str(e)[:100]}')
            raise

    return Strategy(f)


def _book_interrupted_rub(agent, st, g, n, wishes_before, exc):
    """LAMP_RUB_FIX: what _rub would have booked after a RUB step that an exception cut short."""
    try:
        msg = ((agent.message or '') + ' ' + (agent.single_message or '')).replace('\n', ' ')
        djinni = 'djinni' in msg or 'In a cloud of smoke' in msg or st.wishes > wishes_before
        if 'puff of smoke' in msg or 'smell smoke' in msg:
            st.smoke.add(g)
        if djinni:
            st.djinni += 1
            st.oil.add(g)    # the lamp is an oil lamp now (apply.c dorub)
        st.rewield = True
        st.rewield_tries = 0
        _log(agent, f'rub {n} of lamp {g!r} cut short by {type(exc).__name__}: djinni={djinni} wishes {wishes_before}->{st.wishes} '
                    f'msg={msg[:120]!r}')
    except Exception as e2:    # (bookkeeping must never mask the exception that is going up)
        agent.log(f'WISHSRC interrupted-rub bookkeeping failed: {e2!r}')


def _rub(agent, item):
    st = state(agent)
    letter = agent.inventory.items.get_letter(item)
    g = letter   # (a released magic lamp becomes an oil lamp: another glyph, same letter)
    n = st.rubs[g] = st.rubs.get(g, 0) + 1
    prev_purpose = getattr(agent, 'wish_purpose', None)
    agent.wish_purpose = 'single'

    def gen():
        if 'What do you want to rub?' not in agent.single_message:
            return
        yield letter

    before = agent.step_count
    wishes_before = st.wishes
    try:
        with agent.atom_operation():
            agent.step(A.Command.RUB, gen())
    except BaseException as e:
        if jf_config.LAMP_RUB_FIX:
            # AgentChangeStrategy (a preempting strategy fired right after the wish: T_ROUTE_TOP puts the wished ring on),
            # AgentPanic or AgentFinished left the step AFTER the game had run the rub: book what it showed, or the emptied lamp
            # (an oil lamp now) is rubbed for the rest of the game
            _book_interrupted_rub(agent, st, g, n, wishes_before, e)
        raise
    finally:
        agent.wish_purpose = prev_purpose
    msg = (agent.message or '').replace('\n', ' ')
    # (the wish prompt is answered inside the step, so the last message may be about the wished item: a counted prompt is
    # a djinni too -- k-lamp-old, WISH_SINGLE off, kept rubbing an oil lamp 9 times after its wish)
    djinni = 'djinni' in msg or 'In a cloud of smoke' in msg or st.wishes > wishes_before
    if 'puff of smoke' in msg or 'smell smoke' in msg:
        st.smoke.add(g)
    _log(agent, f'rub {n} of {item.text!r}: {msg[:160]!r}')
    done = djinni or (n >= jf_config.LAMP_RUBS and g not in st.smoke)
    if djinni:
        st.djinni += 1
        st.oil.add(g)   # the lamp is an oil lamp now (apply.c dorub)
    elif done:
        st.oil.add(g)
        _log(agent, f'{item.text!r} is no magic lamp ({n} rubs, no smoke)')
    if agent.step_count == before:
        agent.search()
    if done or (g in st.smoke and not _lamp_ok_now(agent, item)):
        try:
            agent.wield_best_melee_weapon()   # the rub wielded the lamp
        except AgentFinished:
            raise
        except Exception as e:
            agent.log(f'WISHSRC re-wield failed: {e!r}')


# ---------------------------------------------------------------------------------------------------------------- single wish

WISH_POLYCTL = 'blessed ring of polymorph control'
WISH_MB = 'blessed amulet of magical breathing'

# Harness values P(max depth >= 30 | real current-bot castle kit + this one wish) the policy compares (castle-k-real-x4, n 448,
# base f414e9e, ledger result post; k/n in the comments):
VAL_POLY_SOURCE = 0.29      # polymorph control, kits that hold a polymorph source (potion / wand / ring): 16/56
VAL_POLY_KNOWN = 0.50       # ... with the source KNOWN (R170: control + wand of polymorph on the castle: 14/30, 15/30)
VAL_TELE2_TC_RING = 0.62    # '2 cursed scrolls of teleportation', kits that hold a TC ring (it need not be identified: the
                            # cursed scrolls' prompts name it): 10/16
VAL_TC_KNOWN = 0.90         # TC known + 2 cursed scrolls (R151: 24/24)
VAL_LEV_CASTLE29 = 0.09     # a levitation ring on a castle at Dlvl 29: 8/88
VAL_LEV_OTHER = 0.003       # ... castles 25-28 (the Valley is not Dlvl 30): 1/360
PRIOR_POLY_SOURCE = 0.125   # kits holding a polymorph source (potion 4, wand 9, ring 3 of 112; 14 distinct kits)
PRIOR_TC_RING = 0.036       # kits holding a TC ring (4 of 112)


def _objs(cls, *names):
    from . import objects as O
    return frozenset(O.from_name(n, cls) for n in names)


def _p_any(items, kinds):
    """1 - P(none of these unidentified stacks is one of `kinds`) -- kinds: [(item class, targets)]."""
    from . import power
    p_none = 1.0
    for it in items:
        if it.is_unambiguous():
            continue
        for cls, targets in kinds:
            if it.category == cls:
                p_none *= 1.0 - power.p_of(it, targets)
    return 1.0 - p_none


def single_wish(agent):
    """The text for a single wish (a throne, a lamp, a water demon): WISH_SINGLE_V2 = the cand-l5 table (single_wish_v2),
    else the phase-1 policy (single_wish_v1)."""
    if jf_config.WISH_SINGLE_V2:
        return single_wish_v2(agent)
    return single_wish_v1(agent)


def single_wish_v1(agent):
    """The text for a single wish (a throne, a lamp), by expected P(pass): each candidate's harness value (VAL_*) times how
    likely the pack makes it work. The two that work are kit-dependent: polymorph control needs a polymorph source (12% of the
    current-bot kits hold one; the castle plan quaffs unknown potions and tries rings, and the wand is zapped) and '2 cursed
    scrolls of teleportation' needs a TC ring (3.6% of the kits; with TC known it is the 0.9 route). A levitation ring only
    passes on a castle at Dlvl 29 (the Valley is then Dlvl 30)."""
    from . import power, power_route, tele_route
    why = ''
    try:
        items = list(flatten_items(agent.inventory.items))
        bl = agent.blstats
        tc = power_route.tc_known(agent)
        cursed = power_route.cursed_tele_scrolls(agent)
        ncursed = sum(i.count for i in cursed)
        poly_ctl = any(i.category == nh.RING_CLASS and i.is_unambiguous() and i.object.name == 'polymorph control'
                       for i in items)
        poly_known = _poly_source(agent, items)
        poly_objs = [(nh.POTION_CLASS, _objs(nh.POTION_CLASS, 'polymorph')),
                     (nh.WAND_CLASS, _objs(nh.WAND_CLASS, 'polymorph')),
                     (nh.RING_CLASS, _objs(nh.RING_CLASS, 'polymorph'))]
        p_src = 1.0 if poly_known else _p_any(items, poly_objs)
        p_tc = 1.0 if tc else _p_any(items, [(nh.RING_CLASS, frozenset([tele_route.TC_RING]))])
        # (WISH_SINGLE_EARLY, dev: choose as an early wish would -- priors, castle depth unknown -- on the castle landing)
        early = jf_config.WISH_SINGLE_EARLY or not (bl.dungeon_number == 0 and bl.depth >= 25)   # the castle is still ahead: the pack will grow before it matters
        if early:
            # a throne's wish comes at Dlvl 5-20 with most of the dive's pickups still to come: the pack then lacks what
            # the castle's will hold (12.5% of the current-bot kits have a polymorph source, 3.6% a TC ring)
            p_src = max(p_src, PRIOR_POLY_SOURCE)
            p_tc = max(p_tc, PRIOR_TC_RING)
        castle29 = bl.dungeon_number == 0 and bl.depth == 29 and not jf_config.WISH_SINGLE_EARLY
        cand = []   # (value, text, why)
        if not poly_ctl:
            cand.append(((VAL_POLY_KNOWN if poly_known else VAL_POLY_SOURCE) * p_src, WISH_POLYCTL,
                         f'polymorph source P={p_src:.2f}' + (f' ({poly_known})' if poly_known else '')))
        if tc and ncursed < 2:
            cand.append((VAL_TC_KNOWN, tele_route.WISH_TELE_SCROLLS, 'TC known'))
        elif not tc:
            cand.append((VAL_TELE2_TC_RING * p_tc, tele_route.WISH_TELE_SCROLLS, f'TC ring P={p_tc:.2f}'))
            if ncursed:
                cand.append((VAL_TC_KNOWN if ncursed >= 2 else 0.35, tele_route.WISH_TC_RING,
                             f'{ncursed} known cursed scroll(s)'))
        if not power.has_object(agent, power.LEV_RING):
            if castle29:
                v_lev, w = VAL_LEV_CASTLE29, 'castle on Dlvl 29'
            elif early:
                v_lev, w = 0.2 * VAL_LEV_CASTLE29 + 0.8 * VAL_LEV_OTHER, 'castle depth unknown (1 in 5 is Dlvl 29)'
            else:
                v_lev, w = VAL_LEV_OTHER, 'castle above Dlvl 29'
            cand.append((v_lev, power.WISH_LEV_RING, w))
        tv = getattr(tele_route, 'single_wish_value', None)   # lane 9's own estimate for the teleport route, when it exists
        route = tv(agent) if tv is not None else None
        if route is not None:
            cand.append((float(route[1]), route[0], 'tele_route.single_wish_value'))
        cand.sort(key=lambda c: -c[0])
        value, text, why = cand[0]
        why = f'{why}, value {value:.3f}; others ' + ', '.join(f'{c[1]!r} {c[0]:.3f}' for c in cand[1:4])
        if value < 0.005:
            text = {'polyctl': WISH_POLYCTL, 'lev': power.WISH_LEV_RING, 'tc': tele_route.WISH_TC_RING,
                    'ls': power.WISH_LS}.get(jf_config.WISH_SINGLE_DEFAULT, WISH_POLYCTL)
            why += f'; all ~0: default {jf_config.WISH_SINGLE_DEFAULT}'
    except Exception as e:
        agent.log(f'WISHSRC single_wish failed: {e!r}')
        text, why = WISH_POLYCTL, 'error fallback'
    _log(agent, f'single wish: {text!r} ({why})')
    return text


def _poly_source(agent, items):
    """A polymorph source in the pack that the bot knows: a wand with charges or a potion of polymorph."""
    for i in items:
        if not i.is_unambiguous():
            continue
        if i.category == nh.WAND_CLASS and i.object.name == 'polymorph' and not agent.inventory.is_known_empty(i):
            return 'wand of polymorph'
        if i.category == nh.POTION_CLASS and i.object.name == 'polymorph':
            return 'potion of polymorph'
    return None


# ---------------------------------------------------------------------------------------------------------------- single wish v2
# WISH_SINGLE_V2 (wishes lane phase 2, ledger I323 / A335 / R398+): the same idea as single_wish_v1 -- each candidate's harness value
# times how likely the pack makes it work -- with the table re-measured on the cand-l5 tree (008ef20), and with the candidate that
# needs no partner item: a TOOLED HORN. The castle's drawbridge crusher (castle_crusher.py: Mastermind passtune, crush the garrison,
# walk in to the tower chest's wand of wishing and the tele_route wishes) is the one route that works for a kit with nothing, and
# only a horn also gets HORN_SCARE (mino_guard: the landing's minotaurs flee it) and PASSTUNE_HORN_XORN/PRESS (crusher and inner
# castle: xorns, soldiers, trolls flee it) -- a flute or harp kit passes a third as often.
# Harness (castle-k-real-x4: 112 real castle arrivals x 4 level-generation salts = 448 games, the hero lands where the real game
# landed, ONE wished item in the pack, --max-turns 5000, bot 008ef20 unchanged; no item: 3/448 = 0.7%; runs wishes worktree
# runs/w10-<item>; ledger R398, R411):
#   tooled horn, named by the wish (WISH_LEARN)  21/448 = 4.7% [3.1, 7.1]   ('a horn', unnamed: 18/448 = 4.0%; magic flute 6/448)
#   ring of polymorph control                    19/448 = 4.2% [2.7, 6.5]   by what the bot KNOWS at the landing: polymorph source
#                                                known (p >= 0.9) 7/13 = 54%, source unknown 12/435 = 2.8% (kits that really hold one
#                                                9/43, kits without 3/392) -- the bot's belief p_src does not rank the unknown ones
#                                                (buckets 0-0.30: 2.1, 1.7, 4.3, 3.1, 3.1%), so only a KNOWN source (identified wand or
#                                                potion) makes polymorph control the better wish
#   2 cursed scrolls of teleportation            TC ring KNOWN 4/4; p_tc 0.05-0.15 and unknown 3/53 = 5.7%; p_tc < 0.05 0/32
#   ring of levitation, castle 29                4/84 = 4.8% on cand-l5 (8/88 on f414e9e; castle_inner hijacks a lift crossing at the
#                                                east trap door, routes lane B308: its fix brings the old number back); 25-28: ~0
#   ring of teleport control                     3/92 = 3.3% (R323: 6/448 on f414e9e) -- the pick of kits the others did not want
# The horn and polymorph-control pass sets are disjoint (0 of 448 games pass in both). Composition of the rules on the same 448
# games (dev/wish10/emul.py): phase-1 policy 28/448 = 6.2%, 'known source -> polyctl, known TC -> tele2, else horn' 31/448 = 6.9%,
# horn always 21/448, oracle over the arms 50/448 = 11.2%.
V2_INSTR_TEXT = 'tooled horn'
V2_VAL_HORN = 0.047           # a horn in a kit with no tonal instrument: hornid 21/448 (5.0% in the 421 kits without an instrument)
V2_VAL_HORN_UPGRADE = 0.030   # the kit carries only a flute / harp / bugle: a horn adds the scare logic (landing census F360: horn kits reach
                              # the crusher square 46% vs flute 28% / harp 36%; flute kits end to end 1.3-2.9%) -- mechanism, not an arm
V2_VAL_POLY_UNKNOWN = 0.028   # ring of polymorph control, no polymorph source known to the bot: 12/435
V2_VAL_POLY_KNOWN = 0.50      # ... a source the bot KNOWS (a wand of polymorph with charges, a potion): 7/13; R170 14/30, 15/30
V2_VAL_TELE2_NOTC = 0.002     # '2 cursed scrolls of teleportation' with no teleport control ring in the pack (R323: 1/432)
V2_VAL_TELE2_TC = 0.62        # ... with a TC ring in the pack (it need not be identified): 10/16 (R323); known: 4/4
V2_VAL_TC_ALONE = 0.025       # a ring of teleport control, no known cursed scroll (the TC route reads unknown scrolls: T_BLIND_READ)
V2_VAL_LEV29 = 0.060          # a levitation ring on a castle at Dlvl 29: 4/84 now, 8/88 before B308; lamp arm 6/55
V2_VAL_LEV_OTHER = 0.003      # ... castles 25-28 (the Valley is not Dlvl 30): 1/360 (R323)
# ARMOR II: a gray dragon scale mail for a kit that already holds a horn (the crusher route is there; armour class multiplies a route).
# MEASURED (ledger R453, castle-kf-instr-x4, 448 instrument kits, ARMOR_UP on in every arm, paired by kit and salt): control 18/448 = 4.0%,
# worn mail (AC -5.5 at +100 turns) 27/448 = 6.0% (+18/-9, sign p 0.12) -- but on the kits that already hold a horn-like instrument (n=136)
# 13 -> 12 (+5/-6) and on the other instrument kits (n=312) 5 -> 15 (+13/-3, p 0.021). So for the kits this candidate is offered to the
# wish is worth about nothing (the placeholder 0.083 came from the observational AC gradient, which the arm did not confirm); speed boots
# (-1.2 AC) do as well as the mail on the other kits and 13 -> 17 on horn kits. On REAL kits (no instrument) neither makes a route:
# speed boots 2/448 = 0.4%, GDSM 0/112. The mail is only worn at all with ARMOR_UP on (jf79-s1 AC 1 and jf79-s3 AC 10 unchanged after 400
# turns without it). The candidate stays behind WISH_V2_GDSM (off) with a value below the others so that it never wins.
V2_GDSM_TEXT = 'blessed greased +3 gray dragon scale mail'
V2_VAL_GDSM = 0.0


def _horn_state(agent, items):
    """(has a horn-like tonal instrument, has some other tonal instrument): a horn = a tooled horn, an unknown 'horn', a frost/fire
    horn (opp_items.instrument_kind 'scare' or 'horn' on a tonal tool; a drum is no tonal instrument)."""
    from . import opp_items
    horn = other = False
    for i in items:
        if not opp_items.is_tonal(i):
            continue
        if opp_items.instrument_kind(agent, i) in ('scare', 'horn') or \
                (i.is_unambiguous() and i.object.name in ('frost horn', 'fire horn')):
            horn = True
        else:
            other = True
    return horn, other


def single_wish_v2(agent):
    """WISH_SINGLE_V2: the wish text with the best expected P(pass) for the pack, from the cand-l5 harness table above."""
    from . import power, power_route, tele_route
    why = ''
    try:
        items = list(flatten_items(agent.inventory.items))
        bl = agent.blstats
        tc = power_route.tc_known(agent)
        ncursed = sum(i.count for i in power_route.cursed_tele_scrolls(agent))
        poly_ctl = any(i.category == nh.RING_CLASS and i.is_unambiguous() and i.object.name == 'polymorph control'
                       for i in items)
        poly_known = _poly_source(agent, items)
        poly_objs = [(nh.POTION_CLASS, _objs(nh.POTION_CLASS, 'polymorph')),
                     (nh.WAND_CLASS, _objs(nh.WAND_CLASS, 'polymorph')),
                     (nh.RING_CLASS, _objs(nh.RING_CLASS, 'polymorph'))]
        p_src = 1.0 if poly_known else _p_any(items, poly_objs)
        p_tc = 1.0 if tc else _p_any(items, [(nh.RING_CLASS, frozenset([tele_route.TC_RING]))])
        early = jf_config.WISH_SINGLE_EARLY or not (bl.dungeon_number == 0 and bl.depth >= 25)
        if early:
            # the castle is still ahead (a throne, a lamp tested early): the pack will grow, and its depth is not known
            p_tc = max(p_tc, PRIOR_TC_RING)
        castle29 = bl.dungeon_number == 0 and bl.depth == 29 and not jf_config.WISH_SINGLE_EARLY
        horn, other_tonal = _horn_state(agent, items)
        cand = []   # (value, text, why)
        if not poly_ctl:
            cand.append((V2_VAL_POLY_KNOWN if poly_known else V2_VAL_POLY_UNKNOWN, WISH_POLYCTL,
                         f'polymorph source known: {poly_known}' if poly_known else 'no polymorph source known'))
        if tc and ncursed < 2:
            cand.append((VAL_TC_KNOWN, tele_route.WISH_TELE_SCROLLS, 'TC known'))
        elif not tc:
            cand.append((V2_VAL_TELE2_NOTC + (V2_VAL_TELE2_TC - V2_VAL_TELE2_NOTC) * p_tc, tele_route.WISH_TELE_SCROLLS,
                         f'TC ring P={p_tc:.2f}'))
            if ncursed:
                cand.append((VAL_TC_KNOWN if ncursed >= 2 else 0.35, tele_route.WISH_TC_RING,
                             f'{ncursed} known cursed scroll(s)'))
            else:
                cand.append((V2_VAL_TC_ALONE, tele_route.WISH_TC_RING, 'no known cursed scroll'))
        if not power.has_object(agent, power.LEV_RING):
            if castle29:
                v_lev, w = V2_VAL_LEV29, 'castle on Dlvl 29'
            elif early:
                v_lev, w = 0.2 * V2_VAL_LEV29 + 0.8 * V2_VAL_LEV_OTHER, 'castle depth unknown (1 in 5 is Dlvl 29)'
            else:
                v_lev, w = V2_VAL_LEV_OTHER, 'castle above Dlvl 29'
            cand.append((v_lev, power.WISH_LEV_RING, w))
        if not horn:
            cand.append((V2_VAL_HORN_UPGRADE if other_tonal else V2_VAL_HORN, V2_INSTR_TEXT,
                         'only a flute/harp/bugle in the pack' if other_tonal else 'no tonal instrument in the pack'))
        elif jf_config.WISH_V2_GDSM and jf_config.ARMOR_UP and \
                not any(i.is_armor() and i.is_unambiguous() and 'dragon scale' in i.object.name for i in items):
            cand.append((V2_VAL_GDSM, V2_GDSM_TEXT, f'a horn in the pack, ARMOR_UP wears the mail: AC {int(bl.armor_class)} now'))
        cand.sort(key=lambda c: -c[0])
        value, text, why = cand[0]
        why = f'{why}, value {value:.3f}; p_src {p_src:.3f} p_tc {p_tc:.3f} tonal {horn or other_tonal} depth {bl.depth}; others ' + \
            ', '.join(f'{c[1]!r} {c[0]:.3f}' for c in cand[1:4])
        if value < 0.005:
            text = WISH_POLYCTL
            why += '; all ~0: polymorph control'
    except Exception as e:
        agent.log(f'WISHSRC single_wish_v2 failed: {e!r}')
        text, why = WISH_POLYCTL, 'error fallback'
    _log(agent, f'single wish v2: {text!r} ({why})')
    return text


def _acprobe(agent):
    """AC_PROBE (dev, log only): the armour class and HP at +0, 25, 50, 100, 200 game turns after the first observation of the
    run, one WISHSRC line each -- the arrival AC after the bot's own wear pass (armor II measurements)."""
    try:
        bl = agent.blstats
        st = state(agent)
        done = getattr(st, 'acprobe', None)
        if done is None:
            done = st.acprobe = {}
            st.acprobe_t0 = int(bl.time)
        for mark in (0, 25, 50, 100, 200):
            if mark not in done and int(bl.time) - st.acprobe_t0 >= mark:
                done[mark] = True
                _log(agent, f'acprobe +{mark} AC {int(bl.armor_class)} HP {int(bl.hitpoints)}/{int(bl.max_hitpoints)} depth {int(bl.depth)}')
    except Exception as e:
        agent.log(f'WISHSRC acprobe failed: {type(e).__name__}: {str(e)[:80]}')


def _shadow(agent):
    """WISH_V2_SHADOW (dev, log only): once per game, a few steps in, what the phase-1 policy and v2 would wish for the pack as
    it is -- the per-kit decision of both on the same harness game."""
    st = state(agent)
    if getattr(st, 'shadowed', False) or agent.step_count < 3:
        return
    st.shadowed = True
    _SHADOW[0] = True
    try:
        t1 = single_wish_v1(agent)
        t2 = single_wish_v2(agent)
        _log(agent, f'v1 {t1!r} | v2 {t2!r} at depth {agent.blstats.depth} turn {agent.blstats.time}')
    except Exception as e:
        agent.log(f'WISHSRC shadow failed: {type(e).__name__}: {str(e)[:100]}')
    finally:
        _SHADOW[0] = False


# ---------------------------------------------------------------------------------------------------------------- horn at the landing
# HORN_LANDING (wishes lane phase 2): a tooled horn in the pack is blown at the castle-likely landing BEFORE the minotaur shows up.
# Why (harness castle-k-real-x4 + an identified tooled horn, 448 kits; dev/wish10/minoseen.py): the bot first SEES the west maze's
# minotaur at distance 1 in 76 of 176 games (the maze is dark), blows the horn at once in 63 of them and 37 die anyway (49%); the
# landing census (F360) puts an awake west minotaur at turn 0 in 56% of castles, median distance 4. music.c awaken_monsters: every
# monster within dist2 < 10*XL that fails resist() (a minotaur: MR 0, never) flees with no timer -- before it is adjacent, not after
# its first round (3d10 + 3d10 + 2d8). A flee ends 1 time in 25 per move at full HP (monmove.c), so the blow is repeated every
# HORN_LANDING_GAP turns while we are still in the west maze (bot x <= 9) in the first HORN_LANDING_TURNS turns of the visit.
# Only a KNOWN scare horn (tooled horn / a horn glyph that scared): an unknown horn may fire a frost/fire ray, a drum deafens
# (landing_ear needs the castle's door sounds).

def _horn_landing_item(agent, dive):
    from . import opp_items
    bl = agent.blstats
    if bl.dungeon_number != 0 or bl.depth < 25 or int(bl.x) > 9:
        return None
    key = agent.current_level().key()
    vkey, t0 = dive._visit_start
    if vkey != key or bl.time - t0 > jf_config.HORN_LANDING_TURNS:
        return None
    prop = agent.character.prop
    if prop.confusion or prop.stun or prop.hallu or prop.blind or prop.polymorph or getattr(dive, 'rescue', False):
        return None
    rec = getattr(state(agent), 'horn_land', None) or {}
    last, n = rec.get(key, (None, 0))
    if n >= jf_config.HORN_LANDING_MAX or (last is not None and bl.time - last < jf_config.HORN_LANDING_GAP):
        return None
    for it in agent.inventory.items:
        if opp_items.instrument_kind(agent, it) == 'scare' and set(it.objs) <= opp_items.HORNS:
            return it
    return None


def horn_strategy(dive):
    agent = dive.agent

    def f():
        if not jf_config.HORN_LANDING:
            yield False
            return
        try:
            item = _horn_landing_item(agent, dive)
        except Exception as e:   # (a condition must never break the step loop)
            agent.log(f'WISHSRC horn_landing check failed: {type(e).__name__}: {str(e)[:100]}')
            item = None
        if item is None:
            yield False
            return
        yield True
        from . import opp_items
        st = state(agent)
        bl = agent.blstats
        key = agent.current_level().key()
        rec = getattr(st, 'horn_land', None)
        if rec is None:
            rec = st.horn_land = {}
        rec[key] = (bl.time, rec.get(key, (None, 0))[1] + 1)
        _log(agent, f'landing horn blow {rec[key][1]} at +{bl.time - dive._visit_start[1]}: {item.text!r} (bot x {int(bl.x)})')
        before = agent.step_count
        opp_items.play(agent, item, 'n')
        if agent.step_count == before:
            agent.search()

    return Strategy(f)
