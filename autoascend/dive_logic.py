"""Depth-first plan for the BALROG progression score.

The episode score is the best milestone ever reached (death costs nothing):
depth dominates (Dlvl 12 = 0.21, Dlvl 20 = 0.38, Dlvl 25 = 0.47) and stepping
into the Quest home through the magic portal on Dlvl 11-16 is worth 0.366 on
its own. So instead of AutoAscend's Mines/Sokoban tour, this plan:

  * explores the first levels fully while under-levelled (items, XP),
  * then dives the Dungeons of Doom by the nearest '>' / trap door / hole,
  * on the Quest portal level (announced by a telepathic message) sweeps the
    candidate rooms until the hidden portal fires, then walks back out,
  * and keeps diving afterwards.

The plan is a restartable loop of short tasks: fights, eating, prayer etc.
preempt it at any step, so all decisions are re-derived from game state.
"""

import re

import nle.nethack as nh
import numpy as np
from nle.nethack import actions as A
from scipy import ndimage

from . import objects as O

from . import jf_config, jf_log, utils
from .character import Character
from .exceptions import AgentPanic
from .glyph import G, MON, SS, Hunger
from .level import Level
from .item import Item, flatten_items
from .strategy import Strategy

ROOM_FLOOR = frozenset({SS.S_room, SS.S_darkroom})
PLAIN_FLOOR = frozenset({SS.S_room, SS.S_darkroom, SS.S_corr, SS.S_litcorr})
WET = frozenset({SS.S_pool, SS.S_water, SS.S_lava})
CORRIDORS = frozenset({SS.S_corr, SS.S_litcorr})
DOORWAYS = frozenset({SS.S_ndoor}) | G.DOORS
FALL_TRAPS = frozenset({SS.S_trap_door, SS.S_hole})
PORTAL = frozenset({SS.S_magic_portal})

GEHENNOM = 1
MAIN_LINE = (Level.DUNGEONS_OF_DOOM, GEHENNOM)

PORTAL_MESSAGES = ('telepathic message', 'pleading for help', 'demanding your attendance')

# XP gate: while XL < REQUIRED_XL[depth of the next level], the current level is explored
# fully first (items + XP), within FULL_EXPLORE_TURNS. Dlvl 1-4 are always explored fully.
# Deeper than the table: the last entry applies.
REQUIRED_XL = {2: 99, 3: 99, 4: 99, 5: 99, 6: 6, 7: 7, 8: 8, 9: 8, 10: 9, 11: 9, 12: 10}
# trap doors and holes can drop several levels at once
TRAPDOOR_LOOKAHEAD = 3
# rest (search) to this fraction of max HP before taking a way down (astra: 95-100%)
REST_BEFORE_DESCEND = 0.95   # astra left a level at >= 95% HP on 97% of descents
# rest (search) whenever below this and nothing hostile is in view (astra guard.py: 2/3)
REST_BELOW = 0.66
# Dwarves and gnomes find nearly every Mines inhabitant peaceful: bank Mines' End depth
# (Dlvl 10-13, up to 0.26) safely before the main-dungeon dive.
MINES_ROUTE = True
MINES_BRANCH_MAX_DEPTH = 4     # the Mines branch staircase is on Dlvl 2-4
MINES_MIN_LEVELS = 8           # dungeon.def: the Mines have 8-9 levels, Mines' End is the last
# XP gate inside the Mines: before going to Mines level k, explore the current level fully while
# XL < MINES_REQUIRED_XL[k] (hostile orcs/ants there are the XP). Empty = no gate.
MINES_REQUIRED_XL = {}
# astra: retreat onto Elbereth at 45-65% HP, rest there with searches, never attack from it
# hand-over from AutoAscend's levelling tour to the dive
DIVE_XL = 10
DIVE_TURN = 10 ** 9
ELBERETH_REST_BELOW = 0.4
ELBERETH_REST_UNTIL = 0.85
# breathers, spitters and casters: Elbereth doesn't stop them hurting you from a distance
RANGED_MONSTERS = frozenset((
    'winter wolf cub', 'winter wolf', 'hell hound pup', 'hell hound', 'red naga', 'black naga',
    'golden naga', 'guardian naga', 'cobra', 'lich', 'demilich', 'master lich', 'arch-lich',
    'kobold shaman', 'orc shaman', 'gnomish wizard', 'energy vortex', 'yellow light', 'black light',
    'mind flayer', 'master mind flayer', 'titan', 'couatl', 'ki-rin', 'Aleax', 'Angel',
    'nalfeshnee', 'pit fiend', 'balrog', 'djinni', 'storm giant'))
# XP farm: under-levelled on a fully explored level, wait on the up staircase (escape route)
# for random spawns instead of descending. 0 disables.
FARM_TURNS = 0
# retreat: below this HP fraction, with prayer/Elbereth unavailable, climb the up stairs if close
RETREAT_BELOW = 0.35
RETREAT_MAX_DISTANCE = 12
ARRIVAL_WATCH_TURNS = 30       # how long after arriving a crowd still sends us back up
# ...or when this fraction of max HP was lost within RETREAT_WINDOW turns
RETREAT_FAST_LOSS = 0.3
RETREAT_WINDOW = 3
# arrival check: back up the stairs at once into a crowd (a b1 dive died 12 turns after walking
# onto Dlvl 12 among a leocrotta, ogre king, soldier ants, killer bee, Woodland-elf, ...)
CROWD_SIZE = 3
CROWD_RADIUS = 6
BOSS_MONSTERS = ('minotaur', 'ettin', 'titan', 'lich', 'demilich', 'master lich', 'arch-lich',
                 'purple worm', 'green slime', 'cockatrice', 'Olog-hai', 'ogre king', 'soldier',
                 'sergeant', 'lieutenant', 'captain', 'mind flayer', 'master mind flayer',
                 'energy vortex', 'black dragon', 'red dragon', 'white dragon', 'blue dragon',
                 'green dragon', 'yellow dragon', 'orange dragon', 'silver dragon', 'gray dragon')
ARRIVAL_RETREAT_REST = 150     # turns to wait upstairs before trying that staircase again
FULL_EXPLORE_TURNS = 2500      # per level, while under-levelled
PORTAL_SWEEP_TURNS = 3000      # per portal level visit
STUCK_EXPLORE_TURNS = 4000     # searching for a hidden way down before trying other things
# Digging down (pick-axe, or a wand of digging): a few turns per level instead of hundreds spent
# finding the '>', and the only way past Medusa's island without levitation (4 of 8 s4 dives ended
# on her level, walking into the water). A '>' this close is still taken (it keeps an up staircase
# under us on arrival).
DIG_STAIRS_RADIUS = 8
# Dig before fighting: fight2 engages anything within 7 squares, but a hole takes a dwarf only 3-4 dig
# steps and a monster interrupts the dig only once it attacks or first comes into view (monmove.c
# disturb, mhitu.c): with no hostile within DIG_FIRST_RADIUS, keep digging out instead.
DIG_FIRST = True
DIG_FIRST_RADIUS = 2
DIG_FIRST_MIN_HP = 0.35
# Elbereth before each dig step when hostiles are in view: a monster that respects it neither attacks
# nor, on first sight, interrupts the dig (monmove.c disturb() checks onscary). Digging the pit wipes it
# (dig.c del_engr_at), so it is engraved again from inside the pit (can_reach_floor allows it there).
# The early dig-dive deaths are crowd landings: ogre lord + owlbear, titan + warhorse, soldier ants...
ELBERETH_DIG = False
ELBERETH_DIG_RADIUS = 6
# Resting to 95% on a deep level lets its monsters come to us (an s7 dig-dive rested for 150 turns on
# Dlvl 15 until a leocrotta took it to 2 HP): with a digging tool, rest only below this.
DIG_REST_BELOW = 0.6
DIG_MAX_TRIES = 20             # applies on one level without falling through: floor can't be holed
FETCH_TOOL_TURNS = 3000        # budget for walking back to a pick-axe the tour dropped
# Dwarves carry a pick-axe or a mattock 37.5% of the time (makemon.c) and are peaceful to a dwarf:
# with no digging tool yet, the dive kills the peaceful dwarves it meets in the Mines (never in
# Minetown: the Watch). Each kill costs Luck -1 half of the time, so prayer waits 600 turns per kill.
DWARF_HUNT = True
DWARF_HUNT_MAX_KILLS = 6
HUNT_IN_TOUR = False           # the tour hunts too (in the Mines) from HUNT_MIN_XL
HUNT_MIN_XL = 8
# With a digging tool the dive is a few turns per level and XL matters much less (s7 public seed 10:
# Dlvl 4 -> 26 in ~200 turns of digging, past Medusa): dive as soon as one is in hand from this XL,
# and keep one during the tour (it drops them for lighter loot).
DIG_DIVE_XL = 10
KEEP_TOOL_IN_TOUR = False
# The portal sweep (Home 1 = 0.366) costs ~1500 turns of exploring the level; digging reaches
# Dlvl 20+ (0.38+) within a few hundred turns, so no sweep while holding a digging tool.
SWEEP_WITH_TOOL = False
# Tool run (off: None): end the tour's Dlvl 1 grind at this XL instead of XL 8 and head for the Mines
# to take a dwarf's pick-axe (HUNT_MIN_XL / DIG_DIVE_XL follow it). The XL 5-8 grind is where unseen
# games starve (9 of 30 died on Dlvl 1 at XL 3-7).
TOOL_RUN_XL = None
# Rescue dive: a failed prayer during the Dlvl 1 grind leaves the god angry and the game starving (92
# past games: median survival ~1,050 turns after the first failure, 24 of 40 first failures on Dlvl 1).
# Such a game dives at once: down the Mines (peaceful to a dwarf; Mines' End is Dlvl 10-13, 0.13-0.26),
# hunting dwarves on the way, digging in the main dungeon if it gets a pick-axe. Fires only in games
# that are otherwise lost.
RESCUE_DIVE = True
# Ditch the pet for the Dlvl 1 grind (off: experiment). On 15 unseen grinds the pet ate ~40% of the
# corpses (497 meals vs our 732) and made ~10% of the kills (no XP for us); food is what the grind runs
# out of (hunger prayers, their failures, starvation). Take it down to Dlvl 2 and come back up alone
# (a pet only follows when adjacent, and can't climb stairs on its own).
DITCH_PET = False
DITCH_PET_AFTER = 300          # turns into the game (Dlvl 1 explored, its '>' known)
DITCH_PET_BUDGET = 300
DWARF_HUNT_TURNS = 400         # per level
# a dive leaving the Mines without a digging tool explores each Mines level (not Minetown) this long
# looking for dwarves before climbing on (about 2 dwarves per Mines filler level, 37.5% armed with one)
DWARF_SEARCH_TURNS = 300
# Tool quest: a tool-less dive stuck this deep with no way down (Medusa's water, half of all dives)
# has banked its depth, so the long trip back to the Mines for a dwarf's pick-axe can only add.
TOOL_QUEST_DEPTH = 18
TOOL_QUEST_STUCK_TURNS = 800
TOOL_QUEST_TURNS = 12000
# Early detour: a dive with no digging tool that is still shallow (it started in Sokoban or the main
# dungeon, never climbing out through the Mines) first visits Mines levels 1-3 for a dwarf's pick-axe:
# ~50% find one, and a digger's dive is worth ~+0.1 over a stairs dive.
EARLY_DETOUR = True
EARLY_DETOUR_DEPTH = 12
EARLY_DETOUR_MINES_LEVELS = 3
EARLY_DETOUR_TURNS = 2500
DWARF_NAMES = ('dwarf', 'dwarf lord', 'dwarf king')


def _apply_dev_overrides():
    """Dev experiments only: JF_CFG='{"REQUIRED_XL": {...}, ...}' overrides the constants above.
    The arena never sets it, so submissions always run the defaults."""
    import json
    import os
    raw = os.environ.get('JF_CFG')
    if not raw:
        return
    for name, value in json.loads(raw).items():
        if name in ('REQUIRED_XL', 'MINES_REQUIRED_XL'):
            value = {int(k): int(v) for k, v in value.items()}
        if name in globals():
            globals()[name] = value


_apply_dev_overrides()


class DiveLogic:
    def __init__(self, agent):
        self.agent = agent
        self.portal_level = None       # (dnum, lnum) of the Quest portal level
        self.visited_quest = False
        self.quest_arrival = None      # (y, x) of the portal on the Quest home level
        self.level_first_turn = {}     # level key -> turn first seen
        self.fully_explored = set()    # level keys explored to exhaustion
        self.sweep_started = None      # turn the current portal sweep began
        self.sweep_given_up = set()    # portal level keys whose sweep ran out of budget
        self._last_key = None
        self._last_task = None
        self.mines_done = False        # reached the bottom of the Mines, or gave the route up
        self._elbereth_resting = False
        self.diving = False
        self.rescue = False                # the dive began as a rescue from a failed Dlvl 1 grind
        self.undiggable = set()            # level keys where the floor is too hard to dig
        self._hp_history = []              # (turn, hp) of the last few turns
        self._last_pos = None              # (level key, (y, x)) at the previous update
        self._arrived = None               # (level key, turn) of the last stairs arrival
        self._avoid_stairs_until = {}      # (level key, (y, x)) -> turn: don't take this '>' before
        self._retreat_blocked_until = -1   # turn until which a failed retreat isn't retried
        self._dig_tries = {}               # level key -> pick-axe applies without falling through
        self._dig_blocked_until = -1       # turn until which applying the pick-axe isn't retried
        self._fetch = None                 # (level key, (y, x), turn started) of a known pick-axe
        self._fetch_given_up = set()       # (level key, (y, x)) of pick-axes not worth another trip
        self._fetch_scan_turn = -10 ** 9   # last turn the levels were scanned for pick-axes
        self._bad_dig_spots = set()        # (level key, (y, x)) where a boulder etc. blocks digging
        self.tool_spots = set()            # (level key, (y, x)) where a pick-axe was dropped or seen
        self._dwarves_killed = 0
        self._spot_visits = {}             # (level key, (y, x)) -> go_to attempts
        self._climb_trap_tries = {}        # level key -> times traps were opened for a climb
        self._ditch_state = 0              # pet ditch: 0 idle, 1 down with it, 2 up without it, 3 over
        self._ditch_started = None
        self._hunting = False              # our last attack was on a peaceful dwarf
        self._hunt_started = {}            # level key -> turn the hunt began there
        self._search_started = {}          # level key -> turn the dwarf search began there
        self._quest_started = None         # turn the tool quest began
        self._quest_over = False
        self._quest_early = False          # the running quest is the early (shallow) Mines detour
        self._early_done = False

    # ------------------------------------------------------------------ state

    def update(self):
        agent = self.agent
        level = agent.current_level()
        key = level.key()
        turn = agent.blstats.time
        if not self._hp_history or self._hp_history[-1][0] != turn:
            self._hp_history.append((turn, agent.blstats.hitpoints))
            self._hp_history = self._hp_history[-12:]
        # A fall is instant, so the trap door's glyph is never seen and the map forgets it: a dive
        # climbing out of the Mines fell through the same trap door twice. Remember where we fell.
        pos = (agent.blstats.y, agent.blstats.x)
        prev = self._last_pos
        if prev is not None and prev[0] != key and (self.diving or jf_config.LATE_FIXES):
            msg_all = agent.message
            if 'trap door opens up under you' in msg_all or 'hole under you' in msg_all or \
                    'You fall through' in msg_all:
                old_level = agent.levels.get(prev[0])
                if old_level is not None:
                    old_level.objects[prev[1]] = SS.S_trap_door
                    agent.log(f'DIVE fell through a trap door at {prev[1]} on {prev[0]}; remembered')
        self._last_pos = (key, pos)
        self._note_digging_tools(key, pos)
        if self._hunting and self._DWARF_KILLED.search(agent.message):
            self._hunting = False
            self._dwarves_killed += 1
            agent.prayer_hold_until = max(getattr(agent, 'prayer_hold_until', -1), turn) + 600
            # its things lie under its corpse (so the pile shows a corpse glyph), and fight2 may have
            # killed it with a thrown dagger: check every pile within 2 squares
            y0, x0 = pos
            area = agent.glyphs[max(y0 - 2, 0):y0 + 3, max(x0 - 2, 0):x0 + 3]
            piles = [(int(py) + max(y0 - 2, 0), int(px) + max(x0 - 2, 0))
                     for py, px in zip(*utils.isin(area, G.OBJECTS, G.BODIES).nonzero())]
            for p in piles:
                self.tool_spots.add((key, p))
            agent.log(f'DIVE killed a dwarf ({self._dwarves_killed}); piles to check: {piles}')
        if key not in self.level_first_turn:
            self.level_first_turn[key] = turn
        if key != self._last_key:
            agent.log(f'DIVE level {key} depth {agent.blstats.depth}')
            self._last_key = key

        msg = agent.message
        if level.dungeon_number == Level.DUNGEONS_OF_DOOM and any(m in msg for m in PORTAL_MESSAGES):
            if self.portal_level != key:
                agent.log(f'DIVE quest portal level detected: {key}')
            self.portal_level = key

        if level.dungeon_number == Level.QUEST and not self.visited_quest:
            self.visited_quest = True
            self.quest_arrival = (agent.blstats.y, agent.blstats.x)
            agent.log(f'DIVE entered the Quest home at {self.quest_arrival}')

    _DWARF_KILLED = re.compile(r"You kill (the|a|an) (poor )?dwarf( lord| king)?!")
    _TOOL_PICKED_UP = re.compile(r"\b[a-zA-Z] - (an?|\d+) [^.]*(pick-axe|dwarvish mattock)")

    def _note_digging_tools(self, key, pos):
        """Remember where pick-axes lie. The tour picks them up and drops them again for lighter loot
        (s4 public seed 9: 7 times), and the level item memory doesn't keep a big drop reliably.
        Drops happen inside atomic operations, so read every message since the last update."""
        history = self.agent._message_history
        start = getattr(self, '_history_seen', 0)
        if start > len(history):   # a fresh agent after a driver restart
            start = 0
        self._history_seen = len(history)
        msg = ' '.join(history[start:] + [self.agent.message])
        if 'pick-axe' not in msg and 'dwarvish mattock' not in msg:
            return
        picked = max((m.start() for m in self._TOOL_PICKED_UP.finditer(msg)), default=-1)
        dropped = max((msg.rfind(f'{verb} {tool}') for verb in ('You drop a', 'You see here a')
                       for tool in ('pick-axe', 'dwarvish mattock')), default=-1)
        if picked > dropped:
            self.tool_spots.discard((key, pos))
        elif dropped > picked and not self.agent.current_level().shop_interior[pos]:
            self.tool_spots.add((key, pos))

    def should_dive(self):
        if self.diving:
            return True
        agent = self.agent
        gl = agent.global_logic
        from .global_logic import Milestone
        xl = agent.blstats.experience_level
        rescue = RESCUE_DIVE and agent.prayer_failed and gl.milestone == Milestone.BE_ON_FIRST_LEVEL
        if xl >= DIVE_XL or gl.milestone >= Milestone.GO_DOWN or agent.blstats.time >= DIVE_TURN or \
                (xl >= self._min_xl(DIG_DIVE_XL) and self.digging_tool() is not None) or rescue:
            agent.log(f'DIVE phase starts (milestone {gl.milestone.name}{", rescue" if rescue else ""})')
            self.diving = True
            self.rescue = rescue
            # the tour handled the Mines; from here it's the main dungeon (a rescue takes the Mines route)
            self.mines_done = not rescue
        return self.diving

    def turns_on_level(self):
        return self.agent.blstats.time - self.level_first_turn.get(self.agent.current_level().key(),
                                                                    self.agent.blstats.time)

    # ------------------------------------------------------------- targets

    def _stairs_ok(self, level, y, x):
        """A '>' is worth taking unless it is known to lead off the main line (e.g. the Mines)."""
        dest = level.stair_destination.get((y, x))
        if dest is None:
            return True
        return dest[0][0] in MAIN_LINE

    def down_targets(self):
        """Reachable ways down on this level: [(distance, y, x, kind)], nearest first."""
        agent = self.agent
        level = agent.current_level()
        if level.dungeon_number not in MAIN_LINE:
            return []
        dis = agent.bfs()
        targets = []
        for y, x in zip(*utils.isin(level.objects, G.STAIR_DOWN).nonzero()):
            if dis[y, x] != -1 and self._stairs_ok(level, y, x) and \
                    self._avoid_stairs_until.get((level.key(), (y, x)), -1) <= agent.blstats.time:
                targets.append((dis[y, x], y, x, 'stairs'))
        # trap doors and holes are not walkable for bfs: reach a neighbour, then step in
        strong = agent.blstats.experience_level >= self.required_xl(agent.blstats.depth + TRAPDOOR_LOOKAHEAD)
        for y, x in zip(*utils.isin(level.objects, FALL_TRAPS).nonzero()):
            if not strong:
                break
            d = self._neighbour_distance(dis, y, x)
            if d is not None:
                targets.append((d + 1, y, x, 'trap'))
        targets.sort()
        return targets

    def _neighbour_distance(self, dis, y, x):
        best = None
        for ny, nx in self.agent.neighbors(y, x, shuffle=False):
            if dis[ny, nx] != -1 and (best is None or dis[ny, nx] < best):
                best = dis[ny, nx]
        return best

    # ------------------------------------------------------------ strategy

    def exploration(self, search_prio_limit):
        return self.agent.global_logic.exploration_strategy(search_prio_limit)

    @Strategy.wrap
    def strategy(self):
        yield True
        idle = 0
        while True:
            before = self.agent.step_count
            self.plan_step()
            if self.agent.step_count != before:
                idle = 0
                continue
            # a task that returns without acting would spin forever: let a turn pass
            idle += 1
            if idle >= 3:
                self.agent.log(f'DIVE no progress in task {self._last_task!r}: '
                               f'targets={self.down_targets()[:3]} -> searching')
                self.agent.search()
                idle = 0

    def _task(self, name):
        if name != self._last_task:
            self.agent.log(f'DIVE task {name}')
            self._last_task = name
        # diagnostics: a task stuck on one level for long -> dump the screen once per 1000 turns
        if jf_log.enabled() and self.turns_on_level() > 1000:
            mark = self.turns_on_level() // 1000
            if mark != getattr(self, '_last_dump_mark', None):
                self._last_dump_mark = mark
                screen = '\n'.join(bytes(row).decode('latin-1').rstrip()
                                   for row in self.agent.last_observation['tty_chars'])
                dis = self.agent.bfs()
                ups = [(int(y), int(x), int(dis[y, x])) for y, x in
                       zip(*utils.isin(self.agent.current_level().objects, G.STAIR_UP).nonzero())]
                self.agent.log(f'DIVE stuck in task {name!r} on level {self.agent.current_level().key()} '
                               f'for {self.turns_on_level()} turns; up stairs (y,x,dist)={ups}\n{screen}')

    def plan_step(self):
        agent = self.agent
        level = agent.current_level()
        dnum = level.dungeon_number

        # astra guard.py: don't walk on below 2/3 HP; rest while nothing hostile is in view
        bl = agent.blstats
        if bl.hitpoints < REST_BELOW * bl.max_hitpoints and not agent.get_visible_monsters() and \
                bl.hunger_state < Hunger.WEAK:
            self._task('rest')
            agent.search(20)
            return

        if dnum == Level.QUEST:
            self._task('leave quest')
            return self.leave_quest()

        if self.should_fetch_digging_tool():
            self._task('fetch digging tool')
            return self.fetch_digging_tool()

        if self.should_hunt_dwarf():
            self._task('hunt dwarf')
            return self.hunt_dwarf()

        if self.should_search_dwarves():
            self._task('search for dwarves')
            self.exploration(None).until(agent, lambda: bool(self._peaceful_dwarves()) or
                                         self.digging_tool() is not None).run()
            return

        if self.should_tool_quest():
            self._task('tool quest')
            return self.tool_quest()

        if dnum == Level.GNOMISH_MINES and self.use_mines():
            self._task('mines descent')
            return self.mines_step()

        if dnum not in MAIN_LINE:
            self._task('return to main dungeon')
            return self.return_to_main_dungeon()

        if self.should_sweep_portal():
            self._task('portal sweep')
            return self.portal_sweep()

        if self.should_explore_fully():
            self._task('explore fully')
            explored = self.exploration(0).run(return_condition=True)
            if not explored:
                self.fully_explored.add(level.key())
            return

        if self.should_farm():
            self._task('farm xp')
            return self.farm_xp()

        if self.use_mines():
            if self.go_to_mines():
                return
            if agent.blstats.depth > MINES_BRANCH_MAX_DEPTH:
                agent.log('DIVE mines branch not found above; giving the Mines route up')
                self.mines_done = True

        self._task('descend')
        return self.descend()

    # ------------------------------------------------------------- elbereth

    def _ignores_elbereth(self, mon):
        # monmove.c onscary(): @ humans and elves (incl. shopkeepers, guards, priests), minotaurs,
        # peacefuls and blind monsters are not scared; nothing is in Gehennom. permonst.mlet is the
        # monster class as a character (ord() == class number), not the display symbol.
        # Also useless: monsters that hurt from range (breath, spit, spells) -- a b3a dive rested on
        # Elbereth at Dlvl 25 next to a yellow dragon and died to its acid breath.
        mlet = getattr(mon, 'mlet', '')
        cls = ord(mlet) if isinstance(mlet, str) and len(mlet) == 1 else -1
        name = getattr(mon, 'mname', '')
        return cls in (MON.S_HUMAN, MON.S_DRAGON) or name in ('minotaur', 'unknown') or name in RANGED_MONSTERS

    def _near_hostiles(self, radius=2):
        agent = self.agent
        y0, x0 = agent.blstats.y, agent.blstats.x
        return [m for m in agent.get_visible_monsters()
                if max(abs(m[1] - y0), abs(m[2] - x0)) <= radius]

    @Strategy.wrap
    def elbereth_rest(self):
        agent = self.agent
        bl = agent.blstats
        resting = self._elbereth_resting
        threshold = ELBERETH_REST_UNTIL if resting else ELBERETH_REST_BELOW
        # a fast hitter (a leocrotta took a dive from 100 to 14 HP in 6 turns) can't be outrun: hide
        # behind Elbereth as soon as HP falls fast, not only below 40%
        falling = not resting and self._fast_hp_loss()
        if (bl.hitpoints >= threshold * bl.max_hitpoints and not falling) or \
                agent.current_level().dungeon_number == GEHENNOM:
            self._elbereth_resting = False
            yield False
        near = self._near_hostiles()
        # a lone weak monster is better killed than hidden from (engraving gives it a free hit)
        if len(near) == 1 and getattr(near[0][3], 'mlevel', 99) <= 2 and bl.hitpoints >= 6:
            self._elbereth_resting = False
            yield False
        if not near or any(self._ignores_elbereth(m[3]) for m in near) or \
                agent.character.prop.blind or agent.character.prop.polymorph:
            self._elbereth_resting = False
            yield False
        engraving = (agent.inventory.engraving_below_me or '').lower()
        if engraving != 'elbereth' and not agent.can_engrave():
            self._elbereth_resting = False
            yield False
        yield True
        if not self._elbereth_resting:
            agent.log(f'ELBERETH rest start: {[m[3].mname for m in near]}')
        self._elbereth_resting = True
        if engraving != 'elbereth':
            agent.engrave('Elbereth')
            return
        agent.search()

    def _fast_hp_loss(self):
        bl = self.agent.blstats
        recent = [hp for t, hp in self._hp_history if t >= bl.time - RETREAT_WINDOW]
        return bool(recent) and max(recent) - bl.hitpoints >= RETREAT_FAST_LOSS * bl.max_hitpoints

    def _crowded_arrival(self):
        """Just walked down into a crowd or next to a boss: (level key, stairs above) to retreat to."""
        agent = self.agent
        if self._arrived is None:
            return None
        key, turn, above = self._arrived
        if agent.current_level().key() != key or agent.blstats.time - turn > ARRIVAL_WATCH_TURNS:
            return None
        near = self._near_hostiles(radius=CROWD_RADIUS)
        if len(near) >= CROWD_SIZE or any(getattr(m[3], 'mname', '') in BOSS_MONSTERS for m in near):
            return above
        return None

    @Strategy.wrap
    def retreat_upstairs(self):
        """Low or fast-falling HP (or a crowded arrival): take the up stairs if they are close."""
        agent = self.agent
        bl = agent.blstats
        # a retreat that can't move (a Grey-elf in the way) must not keep pre-empting the fight: an
        # s4 dive 'retreated' 9 times in 2 turns without fighting back and died
        if bl.time < self._retreat_blocked_until:
            yield False
        crowd = self._crowded_arrival()
        in_trouble = bl.hitpoints < RETREAT_BELOW * bl.max_hitpoints or self._fast_hp_loss()
        if crowd is None and (RETREAT_BELOW <= 0 or not in_trouble or not self._near_hostiles(radius=3)):
            yield False
        if crowd is not None:
            self._avoid_stairs_until[crowd] = bl.time + ARRIVAL_RETREAT_REST
            self._arrived = None
            agent.log(f'RETREAT crowded arrival: {[m[3].mname for m in self._near_hostiles(CROWD_RADIUS)]}')
        level = agent.current_level()
        if level.dungeon_number == Level.SOKOBAN or bl.depth <= 1:
            yield False
        dis = agent.bfs()
        # fleeing across the level from a faster monster only hands it free hits: on fast HP loss
        # (without low HP) take the stairs only if they are a step or two away
        reach = RETREAT_MAX_DISTANCE if (crowd is not None or bl.hitpoints < RETREAT_BELOW * bl.max_hitpoints) else 2
        ups = [p for p in zip(*utils.isin(level.objects, G.STAIR_UP).nonzero())
               if 0 <= dis[p] <= reach]
        if not ups:
            yield False
        yield True
        y, x = min(ups, key=lambda p: dis[p])
        agent.log(f'RETREAT upstairs at hp {bl.hitpoints}/{bl.max_hitpoints}')
        # don't come straight back down the same staircase into the same fight
        if self._arrived is not None and self._arrived[0] == level.key():
            self._avoid_stairs_until[self._arrived[2]] = bl.time + ARRIVAL_RETREAT_REST
        start = (bl.y, bl.x, level.key())
        try:
            if (bl.y, bl.x) != (y, x):
                agent.go_to(y, x, max_steps=1)
            if (agent.blstats.y, agent.blstats.x) == (y, x):
                agent.move('<')
        finally:
            if (agent.blstats.y, agent.blstats.x, agent.current_level().key()) == start:
                self._retreat_blocked_until = agent.blstats.time + 15

    # ---------------------------------------------------------------- mines

    def use_mines(self):
        # with a pick-axe, digging the main dungeon beats banking Mines' End
        return MINES_ROUTE and not self.mines_done and \
            self.agent.character.race in (Character.DWARF, Character.GNOME) and \
            (not self.diving or self.digging_tool() is None)

    def _stairs_down(self, level):
        return list(zip(*utils.isin(level.objects, G.STAIR_DOWN).nonzero()))

    def go_to_mines(self):
        """Head for the Mines branch '>': a known one, else an untried '>' on a level with two."""
        agent = self.agent
        target = None
        for key, level in agent.levels.items():
            if level.dungeon_number != Level.DUNGEONS_OF_DOOM:
                continue
            downs = self._stairs_down(level)
            for p in downs:
                dest = level.stair_destination.get(p)
                if dest is not None and dest[0][0] == Level.GNOMISH_MINES:
                    target = (key, p)
            if target is None and len(downs) >= 2:
                untried = [p for p in downs if level.stair_destination.get(p) is None]
                if untried:
                    target = (key, untried[0])
            if target is not None:
                break
        if target is None:
            return False
        key, (y, x) = target
        self._task('go to mines branch')
        if agent.current_level().key() != key:
            path = agent.exploration.get_path_to_level(*key)
            if path is None:
                return False
            agent.exploration.follow_level_path_strategy(path, agent.exploration.go_to_strategy).run()
            return True
        if (agent.blstats.y, agent.blstats.x) != (y, x):
            if agent.bfs()[y, x] == -1:
                return False
            agent.go_to(y, x)
            return True
        if self.rest_if_hurt():
            return True
        agent.move('>')
        return True

    def mines_step(self):
        """Stairs-first descent to Mines' End; the bottom is the level without a '>'."""
        agent = self.agent
        level = agent.current_level()
        need_xl = MINES_REQUIRED_XL.get(level.level_number + 1, 0)
        if agent.blstats.experience_level < need_xl and level.key() not in self.fully_explored and \
                self.turns_on_level() < FULL_EXPLORE_TURNS:
            self._task('mines level-up')
            if not self.exploration(0).run(return_condition=True):
                self.fully_explored.add(level.key())
            return
        dis = agent.bfs()
        seen = self._stairs_down(level)
        downs = [p for p in seen if dis[p] != -1]
        if not downs:
            reachable = lambda: any(agent.bfs()[p] != -1 for p in self._stairs_down(agent.current_level()))
            if self.exploration(0).until(agent, reachable).run(return_condition=True):
                return
            if not seen and level.level_number >= MINES_MIN_LEVELS:
                agent.log(f'DIVE Mines bottom reached at depth {agent.blstats.depth}')
                self.mines_done = True
                return
            # a '>' is known but cut off: search for another way, within a budget
            if self.turns_on_level() > STUCK_EXPLORE_TURNS:
                agent.log('DIVE Mines stairs unreachable; giving the Mines route up')
                self.mines_done = True
                return
            self.exploration(None).until(agent, reachable).run()
            return
        y, x = min(downs, key=lambda p: dis[p])
        if (agent.blstats.y, agent.blstats.x) != (y, x):
            agent.go_to(y, x)
            return
        if self.rest_if_hurt():
            return
        agent.move('>')

    def rest_if_hurt(self):
        """Never take a way down while hurt. With nothing around, rest; with monsters around, wait a
        turn and let the fight logic deal with them (b4 stair-danced into a gargoyle: retreat up,
        the gargoyle followed, 'nothing to rest from' was false, so it went straight back down)."""
        agent = self.agent
        if agent.blstats.hitpoints >= REST_BEFORE_DESCEND * agent.blstats.max_hitpoints:
            return False
        self._task('rest before descending')
        agent.search(1 if agent.get_visible_monsters() else 20)
        return True

    # ------------------------------------------------------------- descend

    def required_xl(self, depth):
        return REQUIRED_XL.get(depth, REQUIRED_XL[max(REQUIRED_XL)])

    def should_explore_fully(self):
        agent = self.agent
        key = agent.current_level().key()
        if key in self.fully_explored:
            return False
        # the XP gate is for the stairs dive: a digger spends a few turns per level (an XL9 s7 dig-dive
        # explored Dlvl 16 'to level up' and met an umber hulk); a rescue has no time for it
        if self.digging_tool() is not None or self.rescue:
            return False
        if agent.blstats.hunger_state >= Hunger.HUNGRY and agent.inventory.items.total_nutrition() == 0:
            return False  # corpses and food are deeper
        if self.turns_on_level() > FULL_EXPLORE_TURNS:
            return False
        return agent.blstats.experience_level < self.required_xl(agent.blstats.depth + 1)

    def should_farm(self):
        agent = self.agent
        if FARM_TURNS <= 0 or agent.current_level().key() not in self.fully_explored:
            return False
        if agent.blstats.hunger_state >= Hunger.WEAK and not agent.is_safe_to_pray(1000):
            return False  # nothing left to fix hunger here
        if self.turns_on_level() > FULL_EXPLORE_TURNS + FARM_TURNS:
            return False
        return agent.blstats.experience_level < self.required_xl(agent.blstats.depth + 1)

    def farm_xp(self):
        agent = self.agent
        level = agent.current_level()
        dis = agent.bfs()
        ups = [p for p in zip(*utils.isin(level.objects, G.STAIR_UP).nonzero()) if dis[p] != -1]
        if ups:
            y, x = min(ups, key=lambda p: dis[p])
            if (agent.blstats.y, agent.blstats.x) != (y, x):
                agent.go_to(y, x)
                return
        agent.search(20)

    def digging_wand(self):
        for item in flatten_items(self.agent.inventory.items):
            if item.is_wand() and item.is_unambiguous() and \
                    item.object == O.from_name('digging', nh.WAND_CLASS) and \
                    not self.agent.inventory.is_known_empty(item):
                return item
        return None

    @staticmethod
    def is_digging_tool(item, shield_stuck):
        """A pick-axe, or a dwarvish mattock (both hands: the shield comes off first, so not with a
        cursed shield). A third of the dwarves' digging tools are mattocks."""
        if not item.is_unambiguous() or item.status == Item.CURSED:
            return False
        if item.object == O.from_name('pick-axe'):
            return True
        return item.object == O.from_name('dwarvish mattock') and not shield_stuck

    def _shield_stuck(self):
        shield = self.agent.inventory.items.off_hand
        return shield is not None and shield.status == Item.CURSED

    def best_digging_tool(self, items):
        shield_stuck = self._shield_stuck()
        tools = [i for i in flatten_items(items) if self.is_digging_tool(i, shield_stuck)]
        # the pick-axe first: it is lighter and one-handed
        tools.sort(key=lambda i: i.object != O.from_name('pick-axe'))
        return tools[0] if tools else None

    @Strategy.wrap
    def dig_first(self):
        """Preempts fight2 while diving with a digging tool: finish the hole rather than walk to a fight."""
        agent = self.agent
        if not DIG_FIRST or not self.diving:
            yield False
        level = agent.current_level()
        if level.key() in self.undiggable or level.dungeon_number not in MAIN_LINE or \
                agent.blstats.time < self._dig_blocked_until:
            yield False
        monsters = agent.get_visible_monsters()
        if not monsters:
            yield False   # nothing to run from: the dive plan digs as usual
        bl = agent.blstats
        if bl.hitpoints < DIG_FIRST_MIN_HP * bl.max_hitpoints or \
                any(max(abs(m[1] - bl.y), abs(m[2] - bl.x)) <= DIG_FIRST_RADIUS for m in monsters):
            yield False
        tool = self.digging_tool()
        if tool is None or not self._diggable_spot(bl.y, bl.x) or \
                (tool.object == O.from_name('dwarvish mattock') and agent.inventory.items.off_hand is not None):
            yield False
        # a '>' a few steps away is the plan's business, and so is the portal level
        if self.should_sweep_portal():
            yield False
        yield True
        agent.log(f'DIVE digging out, hostiles at {[(m[3].mname, int(m[0])) for m in monsters[:3]]}')
        self.dig_with_tool(tool)

    def mattock_digger(self):
        """Diving with a mattock and no pick-axe: shields are left behind (the mattock needs both hands)."""
        if not self.diving:
            return False
        tool = self.best_digging_tool(self.agent.inventory.items)
        return tool is not None and tool.object == O.from_name('dwarvish mattock')

    def digging_tool(self):
        inv = self.agent.inventory.items
        tool = self.best_digging_tool(inv)
        if tool is None:
            return None
        # a cursed weapon welded to the hand can't be swapped for the pick-axe
        main = inv.main_hand
        if main is not None and main is not tool and main.status == Item.CURSED:
            return None
        return tool

    def _known_digging_tools(self):
        """Pick-axes lying where we have seen them (the tour picks them up and drops them again)."""
        found = []
        shield_worn = self._shield_stuck()
        for key, level in self.agent.levels.items():
            if key[0] not in (Level.DUNGEONS_OF_DOOM, Level.GNOMISH_MINES):
                continue
            for y, x in zip(*(level.item_count > 0).nonzero()):
                if (key, (y, x)) in self._fetch_given_up or level.shop_interior[y, x]:
                    continue
                if any(self.is_digging_tool(i, shield_worn) for i in flatten_items(level.items[y, x])):
                    found.append((key, (int(y), int(x))))
        for key, (y, x) in self.tool_spots:
            if (key, (y, x)) not in self._fetch_given_up and (key, (int(y), int(x))) not in found and \
                    (key[0] in (Level.DUNGEONS_OF_DOOM, Level.GNOMISH_MINES)):
                found.append((key, (int(y), int(x))))
        return found

    def should_fetch_digging_tool(self):
        if self.digging_tool() is not None:
            self._fetch = None
            return False
        if self._fetch is not None:
            return True
        agent = self.agent
        if agent.blstats.time - self._fetch_scan_turn < 50:
            return False
        self._fetch_scan_turn = agent.blstats.time
        here = agent.current_level().key()
        best = None
        for key, pos in self._known_digging_tools():
            if key == here:
                dis = agent.bfs()
                if dis[pos] == -1 and self._neighbour_distance(dis, *pos) is None:
                    continue
                cost = 0
            else:
                path = agent.exploration.get_path_to_level(*key)
                if path is None:
                    continue
                cost = len(path)
            if best is None or cost < best[0]:
                best = (cost, key, pos)
        if best is None:
            return False
        _, key, pos = best
        agent.log(f'DIVE fetching the digging tool at {pos} on {key}')
        self._fetch = (key, pos, agent.blstats.time)
        return True

    def fetch_digging_tool(self):
        agent = self.agent
        key, (y, x), started = self._fetch
        if agent.blstats.time - started > FETCH_TOOL_TURNS:
            agent.log(f'DIVE digging tool at {(y, x)} on {key}: out of time')
            self._fetch_given_up.add((key, (y, x)))
            self._fetch = None
            return
        if agent.current_level().key() != key:
            # one staircase at a time: follow_level_path_strategy asserts when a peaceful blocks the
            # stairs (an s7 dive panicked on a Mines '<' for turns); _take_stairs waits it out
            path = agent.exploration.get_path_to_level(*key)
            if not path:
                agent.log(f'DIVE digging tool at {(y, x)} on {key}: no way there')
                self._fetch_given_up.add((key, (y, x)))
                self._fetch = None
                return
            (sy, sx), _, direction = path[0]
            if not self._take_stairs([(sy, sx)], direction):
                # cut off (peacefuls, boulders): explore for a way to it, within FETCH_TOOL_TURNS
                self.exploration(None).until(agent, lambda: agent.bfs()[sy, sx] != -1).run()
            return
        pos = (agent.blstats.y, agent.blstats.x)
        if pos != (y, x):
            dis = agent.bfs()
            if dis[y, x] != -1:
                agent.go_to(y, x)
                return
            # a dwarf's fresh tunnel isn't on our map: reach a neighbour, then step in
            tries = self._spot_visits.get((key, (y, x)), 0) + 1
            self._spot_visits[(key, (y, x))] = tries
            if self._neighbour_distance(dis, y, x) is None or tries > 6:
                agent.log(f'DIVE digging tool at {(y, x)} on {key}: unreachable')
                self._fetch_given_up.add((key, (y, x)))
                self._fetch = None
                return
            if not utils.adjacent(pos, (y, x)):
                agent.go_to(y, x, stop_one_before=True)
                return
            agent.move(agent.calc_direction(pos[0], pos[1], y, x))
            return
        agent.inventory.pickup_and_drop_items().run()
        if self.digging_tool() is None:
            agent.log(f'DIVE no usable digging tool at {(y, x)} on {key}')
        else:
            agent.log(f'DIVE picked up {self.digging_tool().text!r}')
        self._fetch_given_up.add((key, (y, x)))
        self.tool_spots.discard((key, (y, x)))
        self._fetch = None

    def _peaceful_dwarves(self):
        agent = self.agent
        glyphs = [MON.from_name(n) for n in DWARF_NAMES]
        mask = agent.monster_tracker.peaceful_monster_mask & utils.isin(agent.glyphs, glyphs)
        if not mask.any():
            return []
        dis = agent.bfs()
        found = []
        for y, x in zip(*mask.nonzero()):
            d = self._neighbour_distance(dis, y, x)
            if d is not None:
                found.append((d, int(y), int(x)))
        return sorted(found)

    def keep_digging_tool(self):
        return self.diving or KEEP_TOOL_IN_TOUR

    @Strategy.wrap
    def hunt_strategy(self):
        """The tour's Mines visit hunts too, and checks the piles a killed dwarf left (the dive does
        both from plan_step)."""
        if self.diving or not DWARF_HUNT or not HUNT_IN_TOUR:
            yield False
        spot = self._local_tool_spot() if self.digging_tool() is None else None
        if spot is None and not self.should_hunt_dwarf():
            yield False
        yield True
        if spot is not None:
            self._visit_tool_spot(spot)
        else:
            self.hunt_dwarf()

    def _local_tool_spot(self):
        agent = self.agent
        here = agent.current_level().key()
        dis = agent.bfs()
        spots = [(dis[p], p) for k, p in self.tool_spots
                 if k == here and (k, p) not in self._fetch_given_up and dis[p] != -1]
        return min(spots)[1] if spots else None

    def _visit_tool_spot(self, spot):
        agent = self.agent
        key = agent.current_level().key()
        if (agent.blstats.y, agent.blstats.x) != spot:
            tries = self._spot_visits.get((key, spot), 0) + 1
            self._spot_visits[(key, spot)] = tries
            if tries > 20:
                self._fetch_given_up.add((key, spot))
                return
            agent.go_to(*spot)
            return
        agent.inventory.pickup_and_drop_items().run()
        agent.log(f'DIVE checked the pile at {spot}: tool {self.digging_tool()!r}')
        self._fetch_given_up.add((key, spot))
        self.tool_spots.discard((key, spot))

    def first_level_done(self):
        """The tour's Dlvl 1 grind ends at XL 8 (DT6A), or earlier for a tool run."""
        xl = self.agent.blstats.experience_level
        return xl >= 8 or (TOOL_RUN_XL is not None and xl >= TOOL_RUN_XL)

    def _min_xl(self, default):
        return default if TOOL_RUN_XL is None else min(default, TOOL_RUN_XL)

    @Strategy.wrap
    def ditch_pet_strategy(self):
        agent = self.agent
        from .global_logic import Milestone
        if not DITCH_PET or self._ditch_state == 3 or self.diving or \
                agent.global_logic.milestone != Milestone.BE_ON_FIRST_LEVEL:
            yield False
        bl = agent.blstats
        level = agent.current_level()
        first = (Level.DUNGEONS_OF_DOOM, 1)
        if self._ditch_state == 0:
            if level.key() != first or not agent.has_pet or bl.time < DITCH_PET_AFTER or \
                    agent.get_visible_monsters() or bl.hitpoints < 0.8 * bl.max_hitpoints:
                yield False
            dis = agent.bfs()
            if not any(dis[p] != -1 for p in self._stairs_down(level)):
                yield False
            agent.log('DITCH pet: taking it down to Dlvl 2')
            self._ditch_state = 1
            self._ditch_started = bl.time
        if bl.time - self._ditch_started > DITCH_PET_BUDGET:
            agent.log(f'DITCH pet: out of time (state {self._ditch_state})')
            self._ditch_state = 3
            yield False
        yield True
        pos = (bl.y, bl.x)
        pet_adjacent = any(utils.adjacent(pos, (int(y), int(x)))
                           for y, x in zip(*utils.isin(agent.glyphs, G.PETS).nonzero()))
        key = level.key()
        if self._ditch_state == 1:
            if key == (Level.DUNGEONS_OF_DOOM, 2):
                self._ditch_state = 2
                return
            if key != first:
                self._ditch_state = 3
                return
            dis = agent.bfs()
            downs = [p for p in self._stairs_down(level) if dis[p] != -1]
            if not downs:
                self._ditch_state = 3
                return
            y, x = min(downs, key=lambda p: dis[p])
            if pos != (y, x):
                agent.go_to(y, x)
            elif pet_adjacent:
                agent.move('>')
            else:
                agent.search()   # wait for the pet to come close enough to follow
            return
        # state 2: on Dlvl 2 with the pet; climb back when it is not adjacent
        if key == first:
            agent.log(f'DITCH pet: back on Dlvl 1, pet left behind: {not agent.has_pet}')
            self._ditch_state = 3
            return
        ups = [p for p in zip(*utils.isin(level.objects, G.STAIR_UP).nonzero())]
        if not ups:
            self._ditch_state = 3
            return
        y, x = ups[0]
        if pos != (y, x):
            agent.go_to(y, x)
        elif not pet_adjacent:
            agent.move('<')
        else:
            agent.search()   # let it wander off

    def should_hunt_dwarf(self):
        agent = self.agent
        if not DWARF_HUNT or self._dwarves_killed >= DWARF_HUNT_MAX_KILLS:
            return False
        if not self.diving and (not HUNT_IN_TOUR or agent.blstats.experience_level < self._min_xl(HUNT_MIN_XL)):
            return False
        if self.digging_tool() is not None or self._fetch is not None:
            return False
        level = agent.current_level()
        # dwarves wander the main dungeon too; never in Minetown (the Watch defends peacefuls)
        if level.dungeon_number not in (Level.GNOMISH_MINES, Level.DUNGEONS_OF_DOOM) or \
                level.key() == agent.global_logic.minetown_level:
            return False
        if level.dungeon_number == Level.DUNGEONS_OF_DOOM and not self.diving:
            return False
        bl = agent.blstats
        if bl.hitpoints < 0.7 * bl.max_hitpoints or bl.hunger_state >= Hunger.WEAK:
            return False
        started = self._hunt_started.setdefault(level.key(), bl.time)
        if bl.time - started > DWARF_HUNT_TURNS:
            return False
        return bool(self._peaceful_dwarves())

    def should_search_dwarves(self):
        agent = self.agent
        if not DWARF_HUNT or not self.diving or self._dwarves_killed >= DWARF_HUNT_MAX_KILLS:
            return False
        if self.digging_tool() is not None or self._fetch is not None:
            return False
        level = agent.current_level()
        if level.dungeon_number != Level.GNOMISH_MINES or level.key() == agent.global_logic.minetown_level:
            return False
        bl = agent.blstats
        if bl.hitpoints < 0.7 * bl.max_hitpoints or bl.hunger_state >= Hunger.WEAK:
            return False
        started = self._search_started.setdefault(level.key(), bl.time)
        return bl.time - started <= DWARF_SEARCH_TURNS

    def should_tool_quest(self):
        agent = self.agent
        if not DWARF_HUNT or self._quest_over or not self.diving:
            return False
        if self.digging_tool() is not None:
            if self._quest_started is not None:
                agent.log('DIVE tool quest done: got a digging tool')
                self._quest_started = None
            return False
        bl = agent.blstats
        if self._quest_started is not None:
            budget = EARLY_DETOUR_TURNS if self._quest_early else TOOL_QUEST_TURNS
            if bl.time - self._quest_started > budget or self._quest_target() is None:
                agent.log('DIVE tool quest given up' + (' (early detour)' if self._quest_early else ''))
                if self._quest_early:
                    self._early_done = True
                else:
                    self._quest_over = True
                self._quest_started = None
                self._quest_early = False
                return False
            return True
        level = agent.current_level()
        if EARLY_DETOUR and not self._early_done and level.dungeon_number == Level.DUNGEONS_OF_DOOM and \
                bl.depth <= EARLY_DETOUR_DEPTH:
            self._quest_early = True
            if self._quest_target() is not None:
                agent.log(f'DIVE no digging tool at depth {bl.depth}: early detour to the Mines')
                self._quest_started = bl.time
                return True
            self._quest_early = False
            self._early_done = True
        if level.dungeon_number != Level.DUNGEONS_OF_DOOM or bl.depth < TOOL_QUEST_DEPTH or \
                self.turns_on_level() < TOOL_QUEST_STUCK_TURNS or self.down_targets() or \
                self._quest_target() is None:
            return False
        agent.log(f'DIVE stuck on {level.key()} with no way down: tool quest to the Mines')
        self._quest_started = bl.time
        return True

    def _quest_target(self):
        """The shallowest known Mines level (not Minetown) whose dwarf search isn't used up."""
        agent = self.agent
        now = agent.blstats.time
        minetown = agent.global_logic.minetown_level
        keys = sorted(k for k in agent.levels if k[0] == Level.GNOMISH_MINES and k != minetown and
                      (not self._quest_early or k[1] <= EARLY_DETOUR_MINES_LEVELS))
        for key in keys:
            started = self._search_started.get(key)
            if started is None or now - started <= DWARF_SEARCH_TURNS:
                return key
        return None

    def tool_quest(self):
        agent = self.agent
        target = self._quest_target()
        if agent.current_level().key() == target:
            # should_search_dwarves / should_hunt_dwarf run first; nothing left here but to wait a turn
            agent.search()
            return
        path = agent.exploration.get_path_to_level(*target)
        if not path:
            # levels we fell into have no known stairs: climb one level at a time until the levels the
            # tour walked (and their stairs) connect us to the Mines
            level = agent.current_level()
            if level.dungeon_number != Level.DUNGEONS_OF_DOOM or agent.blstats.depth <= 1:
                agent.log(f'DIVE tool quest: no way to {target}')
                self._search_started[target] = -10 ** 9   # skip it
                return
            ups = list(zip(*utils.isin(level.objects, G.STAIR_UP).nonzero()))
            if ups and self._take_stairs(ups, '<'):
                return
            self.exploration(None).until(agent, lambda: any(
                agent.bfs()[p] != -1 for p in zip(*utils.isin(agent.current_level().objects,
                                                               G.STAIR_UP).nonzero()))).run()
            return
        (sy, sx), _, direction = path[0]
        if not self._take_stairs([(sy, sx)], direction):
            self.exploration(None).until(agent, lambda: agent.bfs()[sy, sx] != -1).run()

    def hunt_dwarf(self):
        agent = self.agent
        targets = self._peaceful_dwarves()
        if not targets:
            return
        _, y, x = targets[0]
        pos = (agent.blstats.y, agent.blstats.x)
        if not utils.adjacent(pos, (y, x)):
            agent.go_to(y, x, stop_one_before=True, max_steps=2)
            return
        agent.log(f'DIVE attacking a peaceful dwarf at {(y, x)} for its digging tool')
        self._hunting = True
        with agent.atom_operation():
            agent.step(A.Command.FIGHT)
            agent.direction(agent.calc_direction(pos[0], pos[1], y, x))
        # it is hostile now: re-list the monsters so the fight logic takes over
        agent.monster_tracker.on_panic()

    def _wet_neighbours(self, py, px):
        agent = self.agent
        level = agent.current_level()
        around = agent.glyphs[max(py - 1, 0):py + 2, max(px - 1, 0):px + 2]
        around_known = level.objects[max(py - 1, 0):py + 2, max(px - 1, 0):px + 2]
        return int((utils.isin(around, WET) | utils.isin(around_known, WET)).sum())

    def _diggable_spot(self, py, px, max_wet=0):
        agent = self.agent
        level = agent.current_level()
        # a square always covered by objects (a leprechaun hall is gold wall to wall) never shows its
        # floor: an s12 digger found no 'floor' there and explored the hall until it starved
        terrain = level.objects[py, px]
        if not (terrain in PLAIN_FLOOR or (terrain == -1 and level.walkable[py, px])) or \
                level.shop[py, px] or level.shop_interior[py, px] or (level.key(), (py, px)) in self._bad_dig_spots:
            return False
        # a hole next to water or lava fills with it (dig.c fillholetyp: n moat squares around fill it
        # with probability n/(n+1)); only islands with no dry square (Medusa variants) accept the risk
        return self._wet_neighbours(py, px) <= max_wet

    def try_dig_down(self):
        """Dig down with a pick-axe (or zap a wand of digging down): one level per hole, and on
        Medusa's level it skips the water. Dig from plain floor with no water around (a hole beside
        water floods) and outside shops (the shopkeeper grabs the pack of a customer falling through)."""
        agent = self.agent
        level = agent.current_level()
        key = level.key()
        if key in self.undiggable or level.dungeon_number not in MAIN_LINE:
            return False
        tool = self.digging_tool() if agent.blstats.time >= self._dig_blocked_until else None
        wand = self.digging_wand() if tool is None else None
        if tool is None and wand is None:
            return False
        # a '>' a few steps away is as fast, and arriving on the up stairs keeps a way back
        dis = agent.bfs()
        for d, _, _, kind in self.down_targets():
            if kind == 'stairs' and d <= DIG_STAIRS_RADIUS:
                return False
        y, x = agent.blstats.y, agent.blstats.x
        candidates = utils.isin(level.objects, PLAIN_FLOOR) | ((level.objects == -1) & level.walkable)
        floor = [p for p in zip(*candidates.nonzero()) if dis[p] >= 0]
        max_wet = 0
        if not any(self._diggable_spot(*p) for p in floor):
            # all reachable floor borders water: take the square with the fewest wet neighbours
            wet = [self._wet_neighbours(*p) for p in floor if self._diggable_spot(*p, max_wet=8)]
            if not wet:
                return False
            max_wet = min(wet)
        if not self._diggable_spot(y, x, max_wet):
            spots = [(dis[p], p) for p in floor if dis[p] > 0 and self._diggable_spot(*p, max_wet)]
            if not spots:
                return False
            agent.go_to(*min(spots)[1])
            return True
        if tool is not None:
            if agent.blstats.hitpoints < DIG_REST_BELOW * agent.blstats.max_hitpoints:
                self._task('rest before digging')
                agent.search(1 if agent.get_visible_monsters() else 20)
                return True
            self.dig_with_tool(tool)
            return True
        if self.rest_if_hurt():
            return True
        agent.log(f'DIVE zapping {wand.text!r} down')
        agent.zap(wand, '>')
        if agent.current_level().key() == key and ('too hard to dig' in agent.message or
                                                    'here is too hard' in agent.message):
            self.undiggable.add(key)
        return True

    def _elbereth_before_digging(self):
        agent = self.agent
        if not ELBERETH_DIG or agent.current_level().dungeon_number == GEHENNOM or \
                agent.character.prop.blind or agent.character.prop.polymorph:
            return False
        if (agent.inventory.engraving_below_me or '').lower() == 'elbereth' or not agent.can_engrave():
            return False
        bl = agent.blstats
        near = [m for m in agent.get_visible_monsters()
                if max(abs(m[1] - bl.y), abs(m[2] - bl.x)) <= ELBERETH_DIG_RADIUS]
        if not near or any(self._ignores_elbereth(m[3]) for m in near):
            return False
        agent.log(f'DIVE Elbereth before digging: {[m[3].mname for m in near]}')
        agent.engrave('Elbereth')
        return True

    def dig_with_tool(self, tool):
        agent = self.agent
        key = agent.current_level().key()
        spot = (agent.blstats.y, agent.blstats.x)
        if self._elbereth_before_digging():
            return
        shield = agent.inventory.items.off_hand
        if tool.object == O.from_name('dwarvish mattock') and shield is not None:
            # a mattock needs both hands; a digger falls through the floor anyway, so leave the shield
            agent.log(f'DIVE dropping {shield.text!r} to dig with a mattock')
            agent.inventory.takeoff(shield)
            shield = next((i for i in agent.inventory.items if i.is_armor() and not i.equipped and
                           i.text.split(' (')[0] == shield.text.split(' (')[0]), None)
            if shield is not None:
                agent.inventory.drop(shield)
            return
        tries = self._dig_tries.get(key, 0) + 1
        self._dig_tries[key] = tries
        agent.log(f'DIVE digging down with {tool.text!r} (try {tries})')
        with agent.atom_operation():
            tool = agent.inventory.move_to_inventory(tool)
            agent.step(A.Command.APPLY)
            agent.type_text(agent.inventory.items.get_letter(tool))
            prompted = 'In what direction do you want to dig?' in agent.single_message
            if prompted:
                agent.direction('>')
            elif agent.single_message.startswith('In what direction'):
                agent.step(A.Command.ESC)
        msg = agent.message
        if agent.current_level().key() != key:
            return
        if not prompted:
            # can't swap weapons (welded), stuck in a web, ...: try again later
            agent.log(f'DIVE could not dig: {msg!r}')
            self._dig_blocked_until = agent.blstats.time + 100
        elif "isn't enough room to dig" in msg or 'hole fills with' in msg or \
                ('too hard to' in msg and 'here is too hard to dig' not in msg):
            # a flooded hole (we crawled out elsewhere), a boulder, or stairs/altar/throne under objects
            self._bad_dig_spots.add((key, spot))
            self._dig_tries[key] = tries - 1
        elif 'here is too hard to dig' in msg or tries >= DIG_MAX_TRIES:
            agent.log(f'DIVE floor here cannot be dug through ({msg!r})')
            self.undiggable.add(key)
            if agent.blstats.depth >= 20:
                # the Castle (or another bottom level): what could still get us further?
                inv = '; '.join(f'{agent.inventory.items.get_letter(i)} - {i.text}'
                                for i in agent.inventory.items.all_items)
                agent.log(f'DIVE bottom reached at depth {agent.blstats.depth}; inventory: {inv}')

    def descend(self):
        agent = self.agent
        if self.try_dig_down():
            return
        targets = self.down_targets()
        if not targets and utils.isin(agent.current_level().objects, G.STAIR_DOWN).any() and \
                self._walk_through_traps():
            targets = self.down_targets()
        if not targets:
            self.exploration(None).until(agent, lambda: bool(self.down_targets())).run()
            return

        _, y, x, kind = targets[0]
        if kind == 'stairs':
            if (agent.blstats.y, agent.blstats.x) != (y, x):
                agent.go_to(y, x)
                return
            if self.rest_if_hurt():
                return
            agent.log(f'DIVE going down stairs at {(y, x)}')
            above = (agent.current_level().key(), (y, x))
            agent.move('>')
            self._arrived = (agent.current_level().key(), agent.blstats.time, above)
            return

        # trap door / hole: stand next to it, then step in
        if not utils.adjacent((agent.blstats.y, agent.blstats.x), (y, x)):
            agent.go_to(y, x, stop_one_before=True)
            return
        if self.rest_if_hurt():
            return
        self.step_onto(y, x, 'trap door')

    def step_onto(self, y, x, what):
        agent = self.agent
        key = agent.current_level().key()
        agent.log(f'DIVE stepping onto {what} at {(y, x)}')
        with agent.atom_operation():
            agent.direction(agent.calc_direction(agent.blstats.y, agent.blstats.x, y, x))
        if agent.current_level().key() == key and (agent.blstats.y, agent.blstats.x) == (y, x):
            # didn't fall (e.g. "You escape a trap door."): step off so the next try steps on again
            agent.log(f'DIVE {what} did not trigger')
            raise AgentPanic(f'{what} did not trigger')

    # ------------------------------------------------------------- branches

    def _walk_through_traps(self, climbing=False):
        """AutoAscend's BFS treats every known trap as a wall (exploration relents only after thousands
        of turns of searching). A dive whose staircase is walled off only by a trap walks through it: an
        s13 dive spent 5,000 turns on Mines level 1 whose '<' lay behind a trap in a 1-wide corridor."""
        agent = self.agent
        if agent._last_turn - agent._allow_walking_through_traps_turn <= 50:
            return False   # already allowed: the traps are not what blocks us
        if climbing:
            # a known trap door is escaped only 1 time in 5 (trap.c): climbing through one dropped that
            # dive back down the Mines twice. First try the way up without trap doors and holes; if that
            # is still cut off next time, the trap door is the only way: take the 1-in-5 chances
            level = agent.current_level()
            falls = utils.isin(level.objects, FALL_TRAPS)
            tries = self._climb_trap_tries.get(level.key(), 0)
            self._climb_trap_tries[level.key()] = tries + 1
            if tries == 0:
                level.forbidden |= falls
            else:
                level.forbidden &= ~falls
        agent.log('DIVE stairs cut off: walking through known traps')
        agent._allow_walking_through_traps_turn = agent._last_turn
        agent.last_bfs_step = -1   # the BFS cache ignores the flag
        return True

    def _take_stairs(self, stairs, direction):
        """Reach one of `stairs` and climb it. A peaceful standing on (or next to) the staircase
        makes it 'unreachable' for AutoAscend's BFS; in the peaceful Mines that stranded a dive for
        13k turns until it starved. Approach a neighbour square, wait for the square to clear."""
        agent = self.agent
        pos = (agent.blstats.y, agent.blstats.x)
        if pos in stairs:
            if direction == '>' and self.rest_if_hurt():
                return True
            agent.move(direction)
            return True
        dis = agent.bfs()
        reachable = [p for p in stairs if dis[p] != -1]
        if reachable:
            agent.go_to(*min(reachable, key=lambda p: dis[p]))
            return True
        near = [(self._neighbour_distance(dis, *p), p) for p in stairs]
        near = [(d, p) for d, p in near if d is not None]
        if not near:
            if self._walk_through_traps(climbing=direction == '<'):
                return self._take_stairs(stairs, direction)
            return False
        d, (y, x) = min(near)
        if not utils.adjacent(pos, (y, x)):
            agent.go_to(y, x, stop_one_before=True)
            return True
        if agent.monster_tracker.monster_mask[y, x]:
            agent.search()  # a peaceful is on the stairs: wait for it to move
            return True
        agent.move(agent.calc_direction(pos[0], pos[1], y, x))
        return True

    def return_to_main_dungeon(self):
        """Back to the main line from a side branch: up out of the Mines, down out of Sokoban."""
        agent = self.agent
        level = agent.current_level()
        stairs = G.STAIR_DOWN if level.dungeon_number == Level.SOKOBAN else G.STAIR_UP
        direction = '>' if level.dungeon_number == Level.SOKOBAN else '<'
        exits = list(zip(*utils.isin(level.objects, stairs).nonzero()))
        if exits and self._take_stairs(exits, direction):
            return
        self.exploration(None).until(agent, lambda: any(
            agent.bfs()[p] != -1 for p in zip(*utils.isin(agent.current_level().objects,
                                                           stairs).nonzero()))).run()

    def leave_quest(self):
        """Home 1 is banked on arrival; walk back through the portal and keep diving."""
        agent = self.agent
        level = agent.current_level()
        portals = [(y, x) for y, x in zip(*utils.isin(level.objects, PORTAL).nonzero())]
        if not portals and self.quest_arrival is not None:
            portals = [self.quest_arrival]
        if not portals:
            self.exploration(None).until(agent, lambda: utils.isin(agent.current_level().objects,
                                                                   PORTAL).any()).run()
            return
        y, x = portals[0]
        pos = (agent.blstats.y, agent.blstats.x)
        if pos == (y, x):
            # standing on the arrival portal: step off, then back on
            dis = agent.bfs()
            for ny, nx in agent.neighbors(y, x):
                if dis[ny, nx] == 1 and not agent.monster_tracker.monster_mask[ny, nx]:
                    with agent.atom_operation():
                        agent.direction(agent.calc_direction(y, x, ny, nx))
                    return
            agent.search()
            return
        if not utils.adjacent(pos, (y, x)):
            agent.go_to(y, x, stop_one_before=True)
            return
        self.step_onto(y, x, 'magic portal')

    # --------------------------------------------------------- portal sweep

    def should_sweep_portal(self):
        agent = self.agent
        key = agent.current_level().key()
        if self.visited_quest or self.portal_level != key or key in self.sweep_given_up:
            return False
        if not SWEEP_WITH_TOOL and self.digging_tool() is not None:
            return False
        if self.sweep_started is None:
            self.sweep_started = agent.blstats.time
        if agent.blstats.time - self.sweep_started > PORTAL_SWEEP_TURNS:
            agent.log('DIVE portal sweep out of budget')
            self.sweep_given_up.add(key)
            return False
        return True

    def portal_candidates(self):
        """Unvisited floor squares of rooms that can hold the portal.

        mklev's find_branch_room puts a branch portal on a free ROOM square of an
        ordinary room that holds neither staircase (when the level has > 2 rooms).
        """
        agent = self.agent
        level = agent.current_level()
        objs = level.objects
        floor = utils.isin(objs, ROOM_FLOOR)
        furniture = utils.isin(objs, G.STAIR_UP, G.STAIR_DOWN, G.ALTAR, G.FOUNTAIN, G.TRAPS)
        # squares showing an item (terrain never seen) next to room floor are room floor too
        unknown = level.walkable & (objs == -1)
        unknown &= utils.dilate(floor, radius=1, with_diagonal=False)
        roomish = floor | furniture | unknown
        labels, n = ndimage.label(roomish)
        cand = (floor | unknown) & ~level.was_on & ~level.shop
        if n > 2:
            for y, x in zip(*utils.isin(objs, G.STAIR_UP, G.STAIR_DOWN).nonzero()):
                if labels[y, x]:
                    cand &= labels != labels[y, x]
        return cand

    def portal_sweep(self):
        agent = self.agent
        level = agent.current_level()
        portals = list(zip(*utils.isin(level.objects, PORTAL).nonzero()))
        if portals:
            y, x = portals[0]
            if not utils.adjacent((agent.blstats.y, agent.blstats.x), (y, x)):
                agent.go_to(y, x, stop_one_before=True)
                return
            self.step_onto(y, x, 'magic portal')
            return

        # rooms first: the portal is on a room square, so finish uncovering the map
        if self.exploration(0).run(return_condition=True):
            return

        dis = agent.bfs()
        cand = self.portal_candidates() & (dis > 0)
        if not cand.any():
            # astra: 2 of 3 portal rooms were closed off (hidden door, locked closet). With every
            # known room swept, search for hidden passages (explore1 with searching) until new
            # candidates appear or the sweep budget runs out.
            if not getattr(self, '_sweep_searching', False):
                agent.log('DIVE portal sweep: known rooms swept, searching for hidden rooms')
                self._sweep_searching = True
            self.exploration(None).until(agent, lambda: bool(
                (self.portal_candidates() & (agent.bfs() > 0)).any() or
                utils.isin(agent.current_level().objects, PORTAL).any())).run()
            return
        ys, xs = cand.nonzero()
        i = int(np.argmin(dis[ys, xs]))
        agent.go_to(ys[i], xs[i])
