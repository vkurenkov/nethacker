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

import nle.nethack as nh
import numpy as np
from nle.nethack import actions as A
from scipy import ndimage

from . import objects as O

from . import jf_log, utils
from .character import Character
from .exceptions import AgentPanic
from .glyph import G, MON, SS, Hunger
from .level import Level
from .item import flatten_items
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
DIVE_XL = 11
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
        self.undiggable = set()            # level keys where the floor is too hard to dig
        self._hp_history = []              # (turn, hp) of the last few turns
        self._arrived = None               # (level key, turn) of the last stairs arrival
        self._avoid_stairs_until = {}      # (level key, (y, x)) -> turn: don't take this '>' before

    # ------------------------------------------------------------------ state

    def update(self):
        agent = self.agent
        level = agent.current_level()
        key = level.key()
        turn = agent.blstats.time
        if not self._hp_history or self._hp_history[-1][0] != turn:
            self._hp_history.append((turn, agent.blstats.hitpoints))
            self._hp_history = self._hp_history[-12:]
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

    def should_dive(self):
        if self.diving:
            return True
        agent = self.agent
        gl = agent.global_logic
        from .global_logic import Milestone
        if agent.blstats.experience_level >= DIVE_XL or gl.milestone >= Milestone.GO_DOWN or \
                agent.blstats.time >= DIVE_TURN:
            agent.log(f'DIVE phase starts (milestone {gl.milestone.name})')
            self.diving = True
            self.mines_done = True  # the tour handled the Mines; from here it's the main dungeon
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
        if bl.hitpoints >= threshold * bl.max_hitpoints or agent.current_level().dungeon_number == GEHENNOM:
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
        ups = [p for p in zip(*utils.isin(level.objects, G.STAIR_UP).nonzero())
               if 0 <= dis[p] <= RETREAT_MAX_DISTANCE]
        if not ups:
            yield False
        yield True
        y, x = min(ups, key=lambda p: dis[p])
        agent.log(f'RETREAT upstairs at hp {bl.hitpoints}/{bl.max_hitpoints}')
        # don't come straight back down the same staircase into the same fight
        if self._arrived is not None and self._arrived[0] == level.key():
            self._avoid_stairs_until[self._arrived[2]] = bl.time + ARRIVAL_RETREAT_REST
        if (bl.y, bl.x) != (y, x):
            agent.go_to(y, x)
        if (agent.blstats.y, agent.blstats.x) == (y, x):
            agent.move('<')

    # ---------------------------------------------------------------- mines

    def use_mines(self):
        return MINES_ROUTE and not self.mines_done and \
            self.agent.character.race in (Character.DWARF, Character.GNOME)

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

    def try_dig_down(self):
        """Astra's shortcut: zap a wand of digging down (one level per charge; on Medusa's level it
        skips the water). Dig from plain floor with no water around (a hole beside water floods)."""
        agent = self.agent
        level = agent.current_level()
        if level.key() in self.undiggable or level.dungeon_number not in MAIN_LINE:
            return False
        wand = self.digging_wand()
        if wand is None:
            return False
        y, x = agent.blstats.y, agent.blstats.x

        def diggable_spot(py, px):
            if level.objects[py, px] not in PLAIN_FLOOR:
                return False
            around = agent.glyphs[max(py - 1, 0):py + 2, max(px - 1, 0):px + 2]
            return not utils.isin(around, WET).any()

        if not diggable_spot(y, x):
            dis = agent.bfs()
            spots = [(dis[p], p) for p in zip(*utils.isin(level.objects, PLAIN_FLOOR).nonzero())
                     if dis[p] > 0 and diggable_spot(*p)]
            if not spots:
                return False
            agent.go_to(*min(spots)[1])
            return True
        if self.rest_if_hurt():
            return True
        key = level.key()
        agent.log(f'DIVE zapping {wand.text!r} down')
        agent.zap(wand, '>')
        if agent.current_level().key() == key and ('too hard to dig' in agent.message or
                                                    'here is too hard' in agent.message):
            self.undiggable.add(key)
        return True

    def descend(self):
        agent = self.agent
        if self.try_dig_down():
            return
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
