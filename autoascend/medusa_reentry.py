"""MEDUSA_REENTRY (jf_config): leave a wet Medusa island by the '<' and fall in again through the hole we dug above.

NetHack 3.6.6, the facts this rests on (ledger I322):
  * dig.c digactualhole(HOLE) at the hero: goto_level(dlevel + 1) -- the FIRST fall through a hole we dig is exactly one level
    (ledger F306). But the hole stays on the level as a trap (HOLE, seen).
  * trap.c dotrap() -> fall_through(): every later entry -- walking onto the known hole, or '>' on it after 'You escape a
    hole' (do.c dodown: uescaped_shaft -> dotrap(TOOKPLUNGE)) -- picks the destination with
        newlevel = dunlev; do { newlevel++ } while (!rn2(4) && newlevel < bottom);
    so one entry in four skips the level below: from the level above Medusa it lands on the maze (or the castle) under her.
  * Medusa-3's '<' lies in medusa.des STAIR:(32,01,39,07) -- on the raven island that every fall from above lands on -- and a
    raven (monst.c: M2_WANDER | M2_HOSTILE, no M2_STALK) never follows up the stairs.
So a landing that finds no dry square (Medusa-3: all 18 island squares have a moat neighbour, a pick-axe hole floods with
1 - 1/(k+1)^2 and the ravens gather meanwhile) walks to the '<' and climbs, rests above, and steps into the hole again: each
entry is a 1 in 4 chance to skip Medusa's level altogether, and a fresh random landing otherwise. The first climb finds the
hole we fell through (if the known map reaches it) or digs a new one beside the '>' (the default dive logic does that, the '>'
being avoided), which is then one step from the '>' for every later entry.

dive_logic.DiveLogic.reentry_strategy() wraps plan()/act() as a preempt layer next to raven_cycle (global_logic).

The pieces (all flagged, see jf_config's medusa lane block for the evidence):
  * plan() -> _standoff_plan(): on Medusa-3's island, hold an intact Elbereth until a window is open (sight, HP, no hostile within
    max(4, steps to the '<' + 2)), a blind hold writes again only when hurt, the hold gives up after MEDUSA_STANDOFF_MAX(_OK)
    turns or when something hurts us on an Elbereth that stood intact the observation before;
  * plan() -> _medusa_plan(): climb at once (no dig on the island), walk to the '<' round the monsters (_walk_step: a bounded
    BFS over the walkable squares not taken by a monster, an Elbereth when every closer square is taken), Elbereth before the
    walk when two ravens are next to us;
  * plan() -> _above_plan(): on the level above, wait for sight, rest to MEDUSA_REENTRY_REST, step onto (or '>' on) the recorded
    hole, else leave the digging of a new one beside the '>' to the dive;
  * _with_meal(): the layer loops above the dive's eaters, so a Hungry hero eats at the next idle action.
A walk, a hold or a rest is one game action per call; reentry_strategy loops plan() -> act() until the plan ends."""

from . import jf_config, utils
from .exceptions import AgentPanic
from .glyph import G, Hunger, SS

FALL_TRAPS = frozenset({SS.S_trap_door, SS.S_hole})


class Reentry:
    def __init__(self, dive):
        self.dive = dive
        self.holes = {}          # level key -> (y, x) of the last hole we dug there and fell through
        self.cycles = 0          # climbs off Medusa's level
        self.landings = 0        # arrivals on Medusa's level
        self.entries = {}        # level key -> steps/plunges into the hole there
        self.plunges = {}        # level key -> '>' presses on the hole square
        self._rest_since = {}    # level key -> first turn of the current rest
        self._last_key = None
        self._skips = 0
        self._walk_blocked = {}  # level key -> turn until which a blocked walk is left to the other layers
        self._scare_tries = {}   # (level key, square, cycles, landings) -> Elbereths written before the walk to the '<'
        self._t_first = None     # turn of the first landing on Medusa's level (the layer gives up MEDUSA_REENTRY_TOTAL turns later)
        self._total_logged = False
        self._entry_turn = -99   # turn of the last step / plunge into the hole above Medusa
        self._walk_turn = -99    # turn of the last step of a walk to the '<'
        self._walk_block_turn = -99   # turn a walk to the '<' found every closer square taken (MEDUSA_REENTRY_AROUND)
        self._bumped = {}        # square -> turn until which an unseen monster there is assumed (a blind step that did not move us)
        self._so = None          # MEDUSA_STANDOFF: the current episode {ep, key, t0, quiet, engr_turn, engr_n, off, active}
        self._so_tries = {}      # MEDUSA_STANDOFF: (level key, square) -> Elbereths written there
        self._logged = set()

    # ------------------------------------------------------------------ hooks

    def note_fall(self, key, spot, new_key):
        """dive_logic.update(): we fell from `spot` of level `key` (a hole we dug or a trap door) to `new_key`. The trap stays
        on the level, and every later entry goes through fall_through()'s one-in-four extra level."""
        if new_key[0] != key[0] or new_key[1] <= key[1]:
            return
        if self.dive.agent.blstats.time - self._entry_turn <= 2:
            return   # we fell through the hole we know by stepping onto it: `spot` is the square we stood on before the step
        self.holes[key] = (int(spot[0]), int(spot[1]))
        self.plunges.pop(key, None)

    def _above_key(self):
        med = self.dive.medusa_level
        if med is None:
            return None
        return (int(med[0]), int(med[1]) - 1)

    def note_level(self):
        """Called from plan(): book-keep arrivals (landings on Medusa's level, skips)."""
        agent = self.dive.agent
        key = agent.current_level().key()
        if key == self._last_key:
            return
        prev, self._last_key = self._last_key, key
        d = self.dive
        if d.medusa_level is None or prev is None:
            return
        med = (int(d.medusa_level[0]), int(d.medusa_level[1]))
        k = (int(key[0]), int(key[1]))
        p = (int(prev[0]), int(prev[1]))
        bl = agent.blstats
        if k == med:
            self.landings += 1
            agent.log(f'REENTRY landing {self.landings} on Medusa\'s level at {(int(bl.y), int(bl.x))} hp {bl.hitpoints}/'
                      f'{bl.max_hitpoints} (cycles {self.cycles})')
        elif p == (med[0], med[1] - 1) and k[0] == med[0] and k[1] > med[1] and self.cycles > 0:
            self._skips += 1
            agent.log(f'REENTRY skipped Medusa\'s level: {p} -> {k} after {self.cycles} climb(s), {self.landings} landing(s)')

    # ------------------------------------------------------------------- plan

    def plan(self):
        """The next action or None. No game action here: this also runs as a mere condition check."""
        d = self.dive
        agent = d.agent
        if not ((jf_config.MEDUSA_REENTRY or jf_config.MEDUSA_STANDOFF) and d.diving) or d.medusa_level is None:
            return None
        if agent.character.prop.polymorph or d.levitating():
            return None
        self.note_level()
        level = agent.current_level()
        key = level.key()
        if level.dungeon_number != d.medusa_level[0]:
            return None
        if self._t_first is None and d.on_medusa_level():
            self._t_first = int(agent.blstats.time)
        if self._t_first is not None and agent.blstats.time - self._t_first > jf_config.MEDUSA_REENTRY_TOTAL:
            if not self._total_logged:
                self._total_logged = True
                agent.log(f'REENTRY given up: {agent.blstats.time - self._t_first} turns since the first landing')
            return None
        if d.on_medusa_level():
            if jf_config.MEDUSA_STANDOFF:
                so = self._standoff_plan(level)
                if so is not None:
                    return self._with_meal(so)
            return self._with_meal(self._medusa_plan(level)) if jf_config.MEDUSA_REENTRY else None
        if jf_config.MEDUSA_REENTRY and (int(key[0]), int(key[1])) == self._above_key():
            return self._with_meal(self._above_plan(level, key))
        return None

    def _with_meal(self, action):
        """The layer loops for hundreds of turns above the dive's eaters (eat_from_inventory sits below it, eat_deep acts at the
        castle only): a Hungry hero with food in the pack eats it at the next idle action (a hold, a rest) with nothing
        next to her; Weak with nothing to eat the layer gives way (the prayer layer above it, or the dive digging on --
        starving banks no depth)."""
        if action is None:
            return None
        agent = self.dive.agent
        bl = agent.blstats
        if bl.hunger_state >= Hunger.WEAK and not agent.edible_carried_food():
            return None
        if action[0] in ('so_wait', 'rest') and bl.hunger_state >= Hunger.HUNGRY and agent.edible_carried_food() and \
                not self._hostile_near(1) and not agent.character.prop.polymorph:
            return ('eat', None)
        return action

    # ---------------------------------------------------------------- standoff

    def _standoff_plan(self, level):
        """MEDUSA_STANDOFF: on Medusa-3's island hold an intact Elbereth (a ('so_engrave') / ('so_wait') action) until a WINDOW
        is open, and only then let the dig / the walk to the '<' act. The window: sight, HP at MEDUSA_STANDOFF_HP of max, and
        no hostile within MEDUSA_STANDOFF_WINDOW squares (a raven 5 squares off needs two of its moves to be next to us). Why:
        the island's ravens do not thin out (harness: 200 turns on Elbereth, 80/80 HP at the end, 2 to 9 ravens within 9
        squares all the time -- a fleeing raven comes back, the level holds 30 of them), but the hold itself is safe, and
        the bare rounds that kill are the pit's (it deletes the engraving: dig.c digactualhole -> del_engr_at) and a flood's
        crawl-out; started when nothing is within 5 squares, the engraving is back before the first raven is next to us.
        Dust scuffs 1 turn in 40 + 3 Dex (allmain.c): the engraving is read back every step while we can see
        (inventory.update), written again when it is gone, or, blind, when we were hurt since the last one. When the window
        closes in the middle of a walk the hold starts again on the square we stand on. Returns an action or None (not
        applicable / the window is open / the hold gave up)."""
        d = self.dive
        agent = d.agent
        bl = agent.blstats
        if d._medusa_variant_name() != 'medusa-3':
            return None
        if d._dig_wand() is not None or d._medusa_lift_action() is not None or d._eel_hold_escape_due():
            return None   # a known wand (one action) or a lift: the dive's own plan
        if d._dig_max_wet() == 0 or agent.character.prop.polymorph:
            return None
        key = level.key()
        turn = int(bl.time)
        st = self._so
        if st is None or st['key'] != key or st['land'] != self.landings:
            st = self._so = dict(key=key, land=self.landings, t0=turn, engr_turn=-99, engr_n=0, off=False, holding=False,
                                 hold_t=0, held=0)
        if st['off']:
            return None
        blind = bool(agent.character.prop.blind)
        hp_ok = bl.hitpoints >= jf_config.MEDUSA_STANDOFF_HP * bl.max_hitpoints
        # (the cap is MEDUSA_STANDOFF_MAX while we are blind or short of HP -- the hold is then also the rest -- and
        # MEDUSA_STANDOFF_MAX_OK once we see and have the HP: the ravens that the hold scared are still fleeing when the
        # walk starts, and the walks that began at the cap cost 2.4 HP on average, the same as those at a window)
        limit = jf_config.MEDUSA_STANDOFF_MAX if (blind or not hp_ok) else jf_config.MEDUSA_STANDOFF_MAX_OK
        if turn - st['t0'] > limit:
            st['off'] = True
            agent.log(f'STANDOFF given up (time {turn - st["t0"]}), held {st["held"]} turns, hp {bl.hitpoints}/{bl.max_hitpoints}')
            return None
        pos = (int(bl.y), int(bl.x))

        def cheb(m):
            return max(abs(int(m[1]) - pos[0]), abs(int(m[2]) - pos[1]))
        close = [m for m in agent.get_visible_monsters() if cheb(m) <= 3]
        if any(d._melee_ignores_elbereth(m[3]) for m in close):
            st['off'] = True   # something that fights through Elbereth (or hurt us while one stood): the dive's own layers
            agent.log(f'STANDOFF given up: {[m[3].mname for m in close[:3]]} ignores Elbereth')
            return None
        hurt_turn = d._hurt_on_elbereth_strict if jf_config.MEDUSA_STANDOFF_HURT_STRICT else d._hurt_on_elbereth
        if turn - hurt_turn <= 3 and st['holding']:
            # HP fell while an intact Elbereth stood under us: a gaze, a spell, a missile, a jellyfish -- sitting on it is
            # no use (m3-w3a seed 37: a pyrolisk's gaze and a jellyfish took 22 HP in the 250-turn hold)
            st['off'] = True
            agent.log(f'STANDOFF given up: hurt on an intact Elbereth (hp {bl.hitpoints}/{bl.max_hitpoints})')
            return None
        # every hostile in view within the radius, over the water too (get_visible_monsters keeps only those next to a
        # square we can walk to)
        mask = agent.monster_tracker.monster_mask & ~agent.monster_tracker.peaceful_monster_mask
        ys, xs = mask.nonzero()
        R = jf_config.MEDUSA_STANDOFF_RADIUS
        dists = sorted(max(abs(int(y) - pos[0]), abs(int(x) - pos[1])) for y, x in zip(ys, xs)
                       if (int(y), int(x)) != pos and max(abs(int(y) - pos[0]), abs(int(x) - pos[1])) <= R)
        # the window is wider the longer the walk it has to cover: a raven at distance D is next to us after about (D - 1) / 1.1
        # turns (speed 20, a third of a bat-class monster's moves at random) and a d-step walk takes d / 1.25 (speed 15)
        need = jf_config.MEDUSA_STANDOFF_WINDOW
        d_up = None
        if jf_config.MEDUSA_REENTRY and self.cycles < jf_config.MEDUSA_REENTRY_MAX:
            ups = self._stairs_up(level)
            if ups:
                dis = agent.bfs()
                ds = [int(dis[p]) for p in ups if dis[p] >= 0]
                if pos in ups:
                    ds.append(0)
                d_up = min(ds) if ds else None
        if d_up is not None:
            need = max(need, d_up + 2)
        window = (not blind) and hp_ok and (not dists or dists[0] >= need)
        # a walk to the '<' that is already under way and nearly there is finished, not held: every raven that has to be
        # waited out costs a blind Elbereth spiral (a blind dust Elbereth holds 1 time in 3), the stairs end the whole thing
        if not window and d_up is not None and d_up <= jf_config.MEDUSA_REENTRY_COMMIT and \
                bl.hitpoints >= 0.3 * bl.max_hitpoints and turn - self._walk_block_turn > 2 and \
                (turn - self._walk_turn <= 2 or (blind and d._hurt_since(turn - 3))):
            # (blind and being bitten with the '<' this near: three blind Elbereths at 1 in 3 cost more rounds than the walk)
            return None
        if window:
            if st['holding']:
                st['holding'] = False
                agent.log(f'STANDOFF window open at {pos} after {turn - st["hold_t"]} turns, hp {bl.hitpoints}/{bl.max_hitpoints}, '
                          f'hostiles within {R}: {dists[:6]}')
            return None
        if not agent.can_engrave():
            return None
        if not st['holding']:
            st['holding'] = True
            st['hold_t'] = turn
            agent.log(f'STANDOFF hold at {pos}: hostiles within {R} {dists[:6]}, blind {blind}, hp {bl.hitpoints}/{bl.max_hitpoints}')
        st['held'] += 1
        engraving = (agent.inventory.engraving_below_me or '').lower()
        tries = self._so_tries.get((key, pos), 0)
        if not blind:
            if engraving != 'elbereth':
                if tries >= jf_config.MEDUSA_STANDOFF_TRIES:
                    agent.log(f'STANDOFF: the engraving at {pos} will not take')
                    return None
                return ('so_engrave', (key, pos))
            return ('so_wait', None)
        # blind: the dust Elbereth cannot be read back (and holds ~1 time in 3): write again when hurt since the last one.
        # (A refresh every MEDUSA_STANDOFF_REFRESH turns without a hurt wiped out a standing Elbereth for one that holds 1
        # time in 3: m3-w6a seeds 168/176/177/199 lost 15-30 HP to it, hold after hold.)
        refresh = jf_config.MEDUSA_STANDOFF_REFRESH
        if st['engr_n'] == 0 or d._hurt_since(st['engr_turn']) or (refresh and turn - st['engr_turn'] >= refresh):
            if tries < 3 * jf_config.MEDUSA_STANDOFF_TRIES:
                return ('so_engrave', (key, pos))
        return ('so_wait', None)

    def _stairs_up(self, level):
        ups = {(int(y), int(x)) for y, x in zip(*utils.isin(level.objects, G.STAIR_UP).nonzero())}
        # the '<' we came down by shows us, not the stairs: the stair memory knows it
        ups |= {(int(p[0]), int(p[1])) for p, dest in level.stair_destination.items()
                if dest[0][0] == level.dungeon_number and dest[0][1] < level.level_number}
        return ups

    def _why(self, reason):
        """Log, once per landing, why the climb is not planned (diagnostics)."""
        k = (self.landings, reason)
        if k not in self._logged:
            self._logged.add(k)
            bl = self.dive.agent.blstats
            self.dive.agent.log(f'REENTRY idle: {reason} (pos {(int(bl.y), int(bl.x))}, floods {self.dive._medusa_floods}, '
                                f'hp {bl.hitpoints}/{bl.max_hitpoints})')
        return None

    def _medusa_plan(self, level):
        d = self.dive
        agent = d.agent
        bl = agent.blstats
        if self.cycles >= jf_config.MEDUSA_REENTRY_MAX:
            return self._why('climbs used up')
        name = d._medusa_variant_name()
        if name != 'medusa-3' and not (name == 'medusa-4' and jf_config.MEDUSA_REENTRY_M4):
            return None
        if d.digging_tool() is None:
            return self._why('no digging tool')   # nothing to dig the hole above with: the dive's own logic
        if d._dig_wand() is not None or d._medusa_lift_action() is not None:
            return self._why('a known digging wand / a lift')   # one flood roll, or a lift: the dive's own plan first
        if d._eel_hold_escape_due():
            return self._why('held by an eel')
        if d._in_own_pit():
            return None
        if d._dig_max_wet() == 0:
            return self._why('a dry square')   # a dry square to dig from: no lottery to avoid
        if self.cycles == 0 and d._medusa_floods < jf_config.MEDUSA_REENTRY_FLOODS and \
                bl.hitpoints >= jf_config.MEDUSA_REENTRY_HP * bl.max_hitpoints:
            return None   # the first landing digs its first attempts as the dive always did (the flock is still small)
        ups = self._stairs_up(level)
        if not ups:
            return self._why('no < known')
        pos = (int(bl.y), int(bl.x))
        if pos in ups:
            return ('climb', pos)
        dis = agent.bfs()
        reach = [(int(dis[p]), p) for p in ups if 0 <= dis[p] <= jf_config.MEDUSA_REENTRY_STEPS]
        if not reach:
            return self._why('the < is out of reach: %s' % sorted((int(dis[p]), p) for p in ups))
        nearest, up = min(reach)
        # ravens already round us and the '<' is more than a step away: the Elbereth first (they flee for rnd(10) turns,
        # a fleeing monster does not attack), then the walk -- a walk through four biting ravens cost 55 HP in the harness
        if jf_config.MEDUSA_REENTRY_SCARE and nearest >= 2 and not agent.character.prop.blind and \
                len(self._hostile_near(1)) >= 2 and (agent.inventory.engraving_below_me or '').lower() != 'elbereth' \
                and agent.can_engrave():
            spot = (level.key(), pos, self.cycles, self.landings)
            if self._scare_tries.get(spot, 0) < 2:
                return ('scare', spot)
        return ('walk', up)

    def _hostile_near(self, radius):
        agent = self.dive.agent
        bl = agent.blstats
        return [m for m in agent.get_visible_monsters()
                if max(abs(int(m[1]) - int(bl.y)), abs(int(m[2]) - int(bl.x))) <= radius]

    def _above_plan(self, level, key):
        d = self.dive
        agent = d.agent
        bl = agent.blstats
        if self.cycles == 0:
            return None   # we never climbed: the dive digs its first hole as usual
        pos = (int(bl.y), int(bl.x))
        if self._hostile_near(3) or utils.any_in(agent.glyphs, G.SWALLOW):
            return None   # the fight / Elbereth layers first
        hole = self.holes.get(key)
        if hole is not None and bl.time < self._walk_blocked.get(key, -1):
            hole = None
        # rest first: every landing on the island costs HP (and a raven's claw leaves us blind for a score of turns; the dive's
        # own plan would dig a NEW hole meanwhile -- a fresh dig falls exactly one level), and the next landing comes with
        # the ravens that gathered
        blind = bool(agent.character.prop.blind)
        if (blind or bl.hitpoints < jf_config.MEDUSA_REENTRY_REST * bl.max_hitpoints) and \
                bl.hunger_state < Hunger.WEAK and not self._hostile_near(6):
            since = self._rest_since.setdefault(key, bl.time)
            if bl.time - since <= (jf_config.MEDUSA_REENTRY_BLIND_MAX if blind and
                                   bl.hitpoints >= jf_config.MEDUSA_REENTRY_REST * bl.max_hitpoints
                                   else jf_config.MEDUSA_REENTRY_REST_MAX):
                return ('rest', None)
        else:
            self._rest_since.pop(key, None)
        if hole is None:
            return None   # the dive digs a new one beside the '>' (the stairs we came up by are avoided)
        if level.key() in d.undiggable:
            return None
        if pos == hole:
            if self.plunges.get(key, 0) >= 3:
                self.holes.pop(key, None)
                return None
            return ('plunge', hole)
        if utils.adjacent(pos, hole):
            return ('step', hole)
        dis = agent.bfs()
        nb = [(int(dis[n]), n) for n in agent.neighbors(hole[0], hole[1], shuffle=False) if dis[n] != -1]
        nb = [t for t in nb if t[0] <= jf_config.MEDUSA_REENTRY_HOLE_STEPS]
        if not nb:
            return None   # not reachable over the map we know: a new hole beside the '>' will do
        return ('walk_hole', min(nb)[1])

    # -------------------------------------------------------------------- act

    def _engrave_elbereth(self):
        """Write an Elbereth in the dust here, noting it for the standoff (blind, it is written again only when we are
        hurt after the last one)."""
        agent = self.dive.agent
        if self._so is not None:
            self._so['engr_turn'] = int(agent.blstats.time)
            self._so['engr_n'] += 1
        agent.engrave('Elbereth')

    def _walk_step(self, up):
        """MEDUSA_REENTRY_AROUND: one step towards the '<' that goes round the monsters we know of -- seen, or remembered as
        an unseen-monster 'I' by an attack on us, or bumped into blind a moment ago. The plain step (dive_logic.
        _raven_step_toward) hits whatever stands on the straight path, turn after turn, with the whole flock biting
        (m3-w6a seed 176: nine turns of 'hitting the monster in the way', 69 -> 16 HP, 5 of 18 deaths on the island began
        so). When every neighbour closer to the '<' is taken the hero writes an Elbereth instead (a fight with one raven
        at a time does not end: the next one takes its square) and the standoff holds from there."""
        d = self.dive
        agent = d.agent
        bl = agent.blstats
        pos = (int(bl.y), int(bl.x))
        turn = int(bl.time)
        level = agent.current_level()
        walkable = level.walkable & ~utils.isin(agent.glyphs, G.BOULDER)
        taken = agent.monster_tracker.monster_mask.copy()
        for sq, until in list(self._bumped.items()):
            if until < turn:
                del self._bumped[sq]
            else:
                taken[sq] = True
        taken[pos] = False
        up = (int(up[0]), int(up[1]))
        h, w = walkable.shape
        dist = {up: 0}
        frontier = [up]
        while frontier:
            nxt = []
            for (y, x) in frontier:
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        ny, nx = y + dy, x + dx
                        if (dy or dx) and 0 <= ny < h and 0 <= nx < w and (ny, nx) not in dist and \
                                (walkable[ny, nx] or (ny, nx) == pos) and not taken[ny, nx]:
                            dist[(ny, nx)] = dist[(y, x)] + 1
                            nxt.append((ny, nx))
            frontier = nxt
        here = dist.get(pos)
        best = None
        for ny, nx in agent.neighbors(pos[0], pos[1], shuffle=False):
            n = (ny, nx)
            if n in dist and walkable[n] and not taken[n] and (best is None or dist[n] < best[0]):
                best = (dist[n], n)
        if best is None or (here is not None and best[0] >= here and best[0] > 0 and pos != up):
            # nothing closer is free: the Elbereth (or the one that stands, waited on) while something is on the way
            self._walk_block_turn = turn
            blind = bool(agent.character.prop.blind)
            st = self._so
            standing = (agent.inventory.engraving_below_me or '').lower() == 'elbereth'
            if not agent.can_engrave():
                what = 'hitting the monster in the way'
                act = 'hit'
            elif (not blind and standing) or (blind and st is not None and st['engr_n'] > 0 and
                                              not d._hurt_since(st['engr_turn'])):
                what = 'waiting on the Elbereth'
                act = 'wait'
            else:
                what = 'Elbereth'
                act = 'engrave'
            if (self.cycles, up, 'blocked', what) not in self._logged:
                self._logged.add((self.cycles, up, 'blocked', what))
                agent.log(f'REENTRY: the way to the < at {up} is taken (from {pos}, d={here}); {what}')
            if act == 'hit':
                d._raven_step_toward(up)
            elif act == 'wait':
                d._task('reentry: the way is taken, hold')
                agent.search(1)
            else:
                self._engrave_elbereth()
            return False
        step = best[1]
        try:
            agent.move(step[0], step[1])
        except AgentPanic as e:
            if 'Monster on a next tile' in str(e):
                self._bumped[step] = turn + 3
            elif (int(agent.blstats.y), int(agent.blstats.x)) == pos:
                self._bumped[step] = turn + 3   # an unseen monster there: the next step goes round it
            else:
                raise
        return True

    def act(self, action):
        d = self.dive
        agent = d.agent
        bl = agent.blstats
        what, arg = action
        key = agent.current_level().key()
        if what == 'walk':
            if (self.cycles, 'walk') not in self._logged:
                self._logged.add((self.cycles, 'walk'))
                agent.log(f'REENTRY to the < at {arg} (hp {bl.hitpoints}/{bl.max_hitpoints}, blind '
                          f'{bool(agent.character.prop.blind)}, hostiles {[m[3].mname for m in self._hostile_near(6)[:4]]})')
            self._walk_turn = int(bl.time)
            if jf_config.MEDUSA_REENTRY_AROUND:
                self._walk_step(arg)
            else:
                d._raven_step_toward(arg)
            return
        if what == 'so_engrave':
            self._so_tries[arg] = self._so_tries.get(arg, 0) + 1
            d._task('standoff: Elbereth')
            self._engrave_elbereth()
            return
        if what == 'eat':
            d._task('reentry: eat')
            for item in agent.edible_carried_food():
                agent.log(f'REENTRY eating {str(item)[:50]} (hunger {bl.hunger_state}, hp {bl.hitpoints}/{bl.max_hitpoints})')
                agent.inventory.eat(item)
                return
            agent.search(1)
            return
        if what == 'so_wait':
            d._task('standoff: hold the Elbereth')
            agent.search(1)
            return
        if what == 'scare':
            self._scare_tries[arg] = self._scare_tries.get(arg, 0) + 1
            agent.log(f'REENTRY Elbereth before the walk to the <: {[m[3].mname for m in self._hostile_near(1)[:4]]} '
                      f'next to us (hp {bl.hitpoints}/{bl.max_hitpoints})')
            self._engrave_elbereth()
            return
        if what == 'climb':
            self.cycles += 1
            agent.log(f'REENTRY climb {self.cycles}: up the stairs at hp {bl.hitpoints}/{bl.max_hitpoints}')
            agent.move('<')
            # the '>' we stand on now leads straight back to the island's '<': the dive must not take it
            d._avoid_stairs_until[(agent.current_level().key(), (int(agent.blstats.y), int(agent.blstats.x)))] = 10 ** 9
            self._rest_since.pop(agent.current_level().key(), None)
            return
        if what == 'rest':
            d._task('reentry: rest above Medusa')
            if d._rest_elbereth():
                return
            agent.search(20 if not agent.get_visible_monsters() else 1)
            return
        if what == 'walk_hole':
            start = (int(bl.y), int(bl.x))
            d._task('reentry: to the hole')
            agent.log(f'REENTRY walking to the hole {self.holes.get(key)} via {arg}')
            try:
                agent.go_to(*arg, max_steps=1)
            finally:
                if (int(agent.blstats.y), int(agent.blstats.x)) == start:
                    self._walk_blocked[key] = agent.blstats.time + 10
            return
        if what == 'step':
            self._entry_turn = int(bl.time)
            self.entries[key] = self.entries.get(key, 0) + 1
            agent.log(f'REENTRY stepping into the hole at {arg} (entry {self.entries[key]}, hp {bl.hitpoints}/{bl.max_hitpoints})')
            y0, x0 = int(bl.y), int(bl.x)
            with agent.atom_operation():
                agent.direction(agent.calc_direction(y0, x0, arg[0], arg[1]))
            if agent.current_level().key() == key:
                if (int(agent.blstats.y), int(agent.blstats.x)) == tuple(arg):
                    agent.log('REENTRY: the hole did not trigger (we stand on it); the next step plunges')
                else:
                    agent.log(f'REENTRY: stepped, not on the hole: {(agent.message or "")[-70:]!r}')
                    if not (agent.in_pit() or 'still in a pit' in (agent.message or '')):
                        # (a hero in a pit needs several turns to climb out: the same step is tried again, not left to the
                        # dive's own plan, which digs a new hole)
                        self._walk_blocked[key] = agent.blstats.time + 5
            return
        if what == 'plunge':
            self._entry_turn = int(bl.time)
            self.plunges[key] = self.plunges.get(key, 0) + 1
            self.entries[key] = self.entries.get(key, 0) + 1
            agent.log(f'REENTRY plunging into the hole under us at {arg} (entry {self.entries[key]})')
            with agent.atom_operation():
                agent.direction('>')
            return
        raise AgentPanic(f'REENTRY: unknown action {what!r}')
