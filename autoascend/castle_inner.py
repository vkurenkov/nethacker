"""CASTLE_INNER (castle-inner lane): from inside the castle to the wand of wishing.

The hero stands inside the shell -- on the lock-out square (07,08) after the crusher closed the bridge behind her, on
the portcullis after a no-tune entry, or at the east end of the throne room after the back door -- and the castle's
wand of wishing lies in a chest in one of the four corner towers: (04,02) (58,02) (04,14) (58,14), on a burned
Elbereth under a cursed scroll of scare monster (castle.des). The way: antechamber (07..14,05..11), the closed door
(15,08), the one-wide hall (16..25,08), the closed door (26,08), the throne room (27..37,05..11), the LOCKED door
(32,04) or (32,12), the one-wide hallway row 3 or 13, a tower door, the tower, the chest. Everything here is
geometric: it needs nothing from the Crusher or FrontDoor but the hero's map square.

What the harness runs of the old wand leg (castle_front._wand_step, 46 lock-out states of castle-crush-a, R0) taught
(NetHack 3.6.6 source in brackets):
* 26% pass. 43% reach a hallway, 35% a tower, 22% the chest; 20 of 46 states died in the throne room, most to an @
  (soldier, sergeant, lieutenant) 30-50 turns after the hand-off.
* The barracks' 36 soldiers are awake in 31 of 46 states (a court lich casting 'aggravate monster' [mcastu.c
  MGC_AGGRAVATION, undirected: cast from anywhere], a bugle [muse.c, awaken_soldiers], a cursed potion of
  invisibility). They are locked in ((26,05) and (26,11) are locked) until a court giant smashes a door [monmove.c
  m_move doorbuster]. They move greedily toward our square [monmove.c m_move, set_apparxy: an awake monster knows
  exactly where we are], so while we stay west they jam against the barracks' west wall, and the moment we walk east
  along the hall they run east along the barracks and pour out into the throne room by a broken door.
* The old leg kicked locked doors: dokick.c:902 wake_nearby() on EVERY kick (radius^2 = XL*20), lock.c:250 on every
  turn of a blunt #force. Here: a key unlocks a door, a pick-axe or mattock digs through it in 3 turns (dig.c dig():
  a dwarf doubles the effort every turn, > 100 opens a door), silently, a wand of digging or striking razes it.
* A xorn walks through walls at speed 9 [monst.c] while we move at ~16 (Fast): never stand and trade blows with it.

Milestones are logged as 'INNER M:<name>' for the harness funnels.
"""

import collections
import heapq

import numpy as np
import nle.nethack as nh
from nle.nethack import actions as A

from . import jf_config
from .castle_front import TOWERS
from .castle_logic import to_bot, to_map, map_char
from .exceptions import AgentPanic
from .glyph import G, MON, SS
from .level import Level
from .strategy import Strategy

PORTCULLIS = (6, 8)
LOCK_SQUARE = (7, 8)
DOOR_A = (15, 8)          # antechamber -> hall, closed
DOOR_B = (26, 8)          # hall -> throne room, closed
THRONE_ENTRY = (27, 8)
DOOR_N = (32, 4)          # throne room -> north hallway (row 3), LOCKED
DOOR_S = (32, 12)         # ... south hallway (row 13), LOCKED
UNDER_N = (32, 5)
UNDER_S = (32, 11)
SECRET_E = (38, 8)        # castle.des: a locked secret door; behind it the trap doors (40..55,08)
BEFORE_SECRET = (37, 8)
TRAPDOOR = (40, 8)
TRAPDOORS = frozenset({(40, 8), (44, 8), (48, 8), (52, 8), (55, 8)})   # castle.des: a walker falls to the Valley
HOLD_SQUARE = (25, 8)     # CASTLE_INNER_HOLD: the hall's east end, one door short of the throne room
GRIND_PIT = (24, 8)       # CASTLE_INNER_GRIND: the pit plugging the hall; we wait three squares west of it
GRIND_FIGHT = (23, 8)     # ... step up here to kill whatever is trapped in it
GRIND_STAND = (21, 8)
# squares where nothing can be engraved: the antechamber's fountain (engrave.c doengrave: 'You can't write on the
# fountain!', castle-gate F326: a xorn killed a hero that kept trying on it) and, to be safe, the throne
NO_WRITE = frozenset({(10, 8), (36, 8)})

ANTE = frozenset((x, y) for x in range(7, 15) for y in range(5, 12))
CORRIDOR_SQUARES = None   # filled below: the one-wide squares (hall, hallways, east hall), where a mob comes single file
HALL = frozenset((x, 8) for x in range(16, 26))
THRONE = frozenset((x, y) for x in range(27, 38) for y in range(5, 12))
HALLWAY_N = frozenset((x, 3) for x in range(8, 55))
HALLWAY_S = frozenset((x, 13) for x in range(8, 55))
EAST_HALL = frozenset((x, 8) for x in range(39, 56))
TOWER_SQUARES = frozenset(p for t in TOWERS.values() for p in t[4])
TOWER_DOORS = frozenset(t[1] for t in TOWERS.values())
INSIDE = ANTE | HALL | THRONE | HALLWAY_N | HALLWAY_S | EAST_HALL | TOWER_SQUARES | TOWER_DOORS | \
    frozenset({PORTCULLIS, DOOR_A, DOOR_B, DOOR_N, DOOR_S, SECRET_E})
CORRIDOR_SQUARES = HALL | HALLWAY_N | HALLWAY_S | EAST_HALL

# the hallway square beside each tower's door
TOWER_OUTSIDE = {'NW': (8, 3), 'NE': (54, 3), 'SW': (8, 13), 'SE': (54, 13)}
TOWER_ORDERS = {
    # castle-gate's census: the 8 tower guards leave their towers and walk the hallways toward us, gathering at the
    # WEST ends (x 8..11); the NE/SE towers end up without guards
    'east': ('NE', 'NW', 'SE', 'SW'),
    'west': ('NW', 'NE', 'SE', 'SW'),     # castle_front.TOWER_ORDER
    # the throne room's heavy remnants (trolls, ogres, giants: 117 of 141 in the 51 real-kit hand-offs) stand at the NE corner
    # (35..37, 5..7), lined up with the north door's work square (32,5): the south door first
    'south': ('SE', 'SW', 'NE', 'NW'),
    'seast': ('SE', 'NE', 'SW', 'NW'),
}
DIRS8 = ((-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1))
DIR_NAME = {(0, -1): 'n', (0, 1): 's', (1, 0): 'e', (-1, 0): 'w', (1, -1): 'ne', (-1, -1): 'nw', (1, 1): 'se',
            (-1, 1): 'sw'}
Mon = collections.namedtuple('Mon', 'y x p name lvl speed ign ww fly adj dist peaceful unseen')


def inside(p):
    return p in INSIDE


class CastleInner:
    def __init__(self, dive):
        self.dive = dive
        self.agent = dive.agent
        self.done = False
        self.logged = set()
        self.tries = collections.Counter()
        self._state = None
        self.locked = set()           # door squares that said 'This door is locked'
        self.broken = set()           # doors we dug or zapped through
        self.sdoor_found = set()
        self.tower_state = {}         # tower name -> 'chest' | 'empty'
        self.scare_at = set()         # the tower's chest square (burned Elbereth + scare monster scroll)
        self._wands_before = None
        self.chest_fail = 0
        self.steps = 0
        self.start_turn = None
        self.hold_t0 = None
        self.hold_quiet = None
        self.hold_done = False
        self.resting = False          # rest (Elbereth, search) until the resume share of HP: hysteresis
        self.last_engrave = -100
        self.gates = set()            # hallway squares where we dug a pit gate
        self.grind = None             # CASTLE_INNER_GRIND state
        self.side = None              # 'N' | 'S': the half whose towers we try now
        self.clearing = None          # CASTLE_INNER_XORN: the antechamber wait
        self.keyed = set()            # doors we unlocked with a key
        self.relocked = set()         # ... and locked again behind us
        self.blocked = {}             # map square -> game turn until which routes avoid it (a boulder, a peaceful)
        self.elb_wait = 0             # CASTLE_INNER_ELB: turns spent on Elbereth beside a dangerous respecter
        self.excal = None             # CASTLE_INNER_EXCAL: Excalibur in the pack, decided on the first look
        self.crowd_until = -1         # CASTLE_INNER_CROWD: turn until which we hold the corridor we retreated into
        self.last_horn = -100         # CASTLE_INNER_HORN: the turn of the last blow
        self.east = {}                # LIFT_EAST_WAND: the east-hall leg (phase, clocks); empty until it is decided

    # ------------------------------------------------------------------ plumbing

    def _log(self, msg):
        self.agent.log(f'INNER {msg}')

    def _set_state(self, state):
        if state != self._state:
            self._state = state
            self._log(f'{state} (pos {self._pos()}, turn {self.agent.blstats.time})')

    def _mile(self, name, extra=''):
        if name in self.logged:
            return
        self.logged.add(name)
        bl = self.agent.blstats
        self._log(f'M:{name} turn {bl.time} hp {bl.hitpoints}/{bl.max_hitpoints} pos {self._pos()} {extra}'.rstrip())

    def _stop(self, why):
        if not self.done:
            self.done = True
            self._mile('stop', why)

    def _pos(self):
        bl = self.agent.blstats
        return to_map(int(bl.y), int(bl.x))

    def _hpf(self):
        bl = self.agent.blstats
        return bl.hitpoints / max(1, bl.max_hitpoints)

    def on_castle(self):
        c = self.dive.castle
        level = self.agent.current_level()
        return c.castle_key is not None and level.key() == c.castle_key and \
            level.dungeon_number == Level.DUNGEONS_OF_DOOM

    def _glyph(self, p):
        y, x = to_bot(*p)
        return int(self.agent.glyphs[y, x])

    def _door_sym(self, p):
        """The remembered terrain symbol at p (doors: SS.S_vcdoor etc.)."""
        y, x = to_bot(*p)
        level = self.agent.current_level()
        if not (0 <= y < level.objects.shape[0] and 0 <= x < level.objects.shape[1]):
            return None
        return level.objects[y, x]

    def _is_open_door(self, p):
        """A doorway that needs no opening and allows diagonal steps: no door, or a broken one."""
        if p in self.broken:
            return True
        return self._door_sym(p) == SS.S_ndoor or self._glyph(p) == SS.S_ndoor

    def _closed_door(self, p):
        return self._glyph(p) in G.DOOR_CLOSED or self._door_sym(p) in G.DOOR_CLOSED

    # ------------------------------------------------------------------ eligibility

    def owned_elsewhere(self):
        """The Crusher runs its own phases until its lock-out; a no-tune entry (castle_entry) until its end state."""
        crusher = getattr(self.dive, 'crusher', None)
        if crusher is not None and crusher.active() and not crusher.locked_out:
            return True
        entry = getattr(self.dive, 'entry', None)
        if entry is not None and getattr(entry, 'owns', lambda: False)():
            return True
        if jf_config.LIFT_EAST_DROP and self._lift_at_east_trapdoor():
            return True
        return False

    def _lift_at_east_trapdoor(self):
        """LIFT_EAST_DROP: a lift crossing opened the back door and the hero hovers over the east trap door (55,8): the crossing
        (castle_logic._door_step) takes the lift off and the trap door drops her into the Valley; the walk to the wand starts
        from the throne room, never from here (see the flag's comment in jf_config)."""
        try:
            castle = self.dive.castle
            if not (self._pos() == (55, 8) and castle.committed() and castle.levitating()):
                return False
            # LIFT_EAST_WAND: at a castle that is not on 29, a lasting lift floats on into the east hall instead (the leg below)
            return not self._east_wanted()
        except Exception:
            return False

    def takes_over(self):
        """The Crusher asks before it hands the walk over (castle_crusher: inner_owns()): castle_inner wants it unless it is off,
        finished, or (CASTLE_INNER_EXCAL) the hero has no Excalibur -- then the Crusher's own wand leg walks."""
        if not jf_config.CASTLE_INNER or self.done:
            return False
        return not jf_config.CASTLE_INNER_EXCAL or self._excalibur()

    def _excalibur(self):
        if self.excal is None:
            self.excal = any('Excalibur' in (i.text or '') for i in self.agent.inventory.items)
        return self.excal

    def _dash(self):
        """CASTLE_INNER_ADAPT: a hero that does not kill a soldier in two blows (no Excalibur) goes by the dash form -- no rest
        before the throne room, no hold, Elbereth at once for a wall-walker or a level 8+ respecter -- the strong one by the
        configured rest and hold."""
        return bool(jf_config.CASTLE_INNER_ADAPT) and not self._excalibur()

    def _gate(self):
        return 0.0 if self._dash() else jf_config.CASTLE_INNER_GATE

    def _hold_on(self):
        return False if self._dash() else bool(jf_config.CASTLE_INNER_HOLD)

    def _elb_on(self):
        return True if self._dash() else bool(jf_config.CASTLE_INNER_ELB)

    def active(self):
        if not jf_config.CASTLE_INNER or self.done or not self.on_castle():
            return False
        if jf_config.CASTLE_INNER_EXCAL and not self._excalibur():
            return False    # only the hero that kills a soldier in two blows: the old leg dashes for the others
        if self.agent.character.prop.polymorph:
            return False
        if not inside(self._pos()):
            return False
        return not self.owned_elsewhere()

    def strategy(self):
        def f():
            if not self.active():
                yield False
            yield True
            steps = 0
            while self.active() and steps < 300:
                before = self.agent.step_count
                if not self.step():
                    break
                steps += 1
                if self.agent.step_count == before:
                    self.agent.search()

        return Strategy(f)

    # ------------------------------------------------------------------ perception

    def _mons(self):
        """Every monster glyph in view, the hero excluded: Mon(y, x, map pos, name, level, speed, ignores Elbereth,
        wall-walker, flyer, adjacent, Chebyshev distance, peaceful, unseen)."""
        agent = self.agent
        bl = agent.blstats
        g = agent.glyphs
        peaceful = agent.monster_tracker.peaceful_monster_mask
        out = []
        mask = ((g >= nh.GLYPH_MON_OFF) & (g < nh.GLYPH_PET_OFF)) | (g == nh.GLYPH_INVISIBLE)
        hallu = bool(agent.character.prop.hallu)   # (a hallucinated glyph says nothing about the class: all fight on)
        for y, x in zip(*np.nonzero(mask)):
            y, x = int(y), int(x)
            if (y, x) == (bl.y, bl.x):
                continue
            glyph = int(g[y, x])
            dist = max(abs(y - bl.y), abs(x - bl.x))
            if glyph == nh.GLYPH_INVISIBLE:
                out.append(Mon(y, x, to_map(y, x), 'unseen', 0, 12, False, False, False, dist == 1, dist, False, True))
                continue
            mon = MON.permonst(glyph)
            flags1 = int(getattr(mon, 'mflags1', 0))
            out.append(Mon(y, x, to_map(y, x), getattr(mon, 'mname', '?'), int(getattr(mon, 'mlevel', 0)),
                           int(getattr(mon, 'mmove', 12)), hallu or bool(self.dive._melee_ignores_elbereth(mon)),
                           bool(flags1 & 0x8), bool(flags1 & 0x1), dist == 1, dist, bool(peaceful[y, x]), False))
        out.sort(key=lambda m: m.dist)
        return out

    def _engraved(self):
        return (self.agent.inventory.engraving_below_me or '').lower() == 'elbereth'

    def _on_scare(self):
        return self._pos() in self.scare_at

    def _can_write(self):
        agent = self.agent
        if jf_config.LIFT_EAST_WAND and self.dive.castle.levitating():
            return False    # (engrave.c: 'You can't reach the floor' -- a hovering hero in the east hall lands first)
        return agent.can_engrave() and not agent.character.prop.blind and self._pos() not in NO_WRITE

    def _step_off(self, mons, why):
        """Off a square that can't hold an engraving (NO_WRITE) onto the neighbour that can, farthest from what is hostile.
        False if there is none."""
        pos = self._pos()
        now = self.agent.blstats.time
        occupied = {m.p for m in mons}
        hostile = [m for m in mons if not m.peaceful and not m.unseen]
        best, best_key = None, None
        for dx, dy in DIRS8:
            n = (pos[0] + dx, pos[1] + dy)
            if n in NO_WRITE or n in occupied or n in TRAPDOORS or self.blocked.get(n, -1) > now or \
                    not self._passable(n) or self._door_square(n) or self._boulder(n):
                continue
            if self._route(n) != [n]:
                continue
            gap = min((max(abs(n[0] - m.p[0]), abs(n[1] - m.p[1])) for m in hostile), default=9)
            key = (gap, -n[0])
            if best_key is None or key > best_key:
                best, best_key = n, key
        if best is None:
            return False
        self._set_state(f'stepping off {pos} to {best}: {why}')
        return self._walk_to(best)

    def _status_bad(self):
        p = self.agent.character.prop
        return bool(p.blind or p.confusion or p.stun or p.hallu)

    # ------------------------------------------------------------------ the static map

    def _passable(self, p):
        c = map_char(*p)
        if c in '.{\\+':
            return True
        if c == 'S':
            return p in self.sdoor_found or p in self.broken
        return False

    def _door_square(self, p):
        c = map_char(*p)
        return (c == '+' or (c == 'S' and p in self.sdoor_found)) and not self._is_open_door(p)

    def _route(self, goal, blocked=frozenset(), danger=None):
        """Shortest walk over the castle map (BFS, 8 directions): intact doors are crossed orthogonally only and a
        diagonal step needs one passable orthogonal neighbour. Squares in `blocked` (monsters) are not entered
        except the goal. With `danger` (square -> extra cost, CASTLE_INNER_AVOID) the cheapest walk (Dijkstra): a few steps
        of detour are paid to keep away from what stands in the room."""
        start = self._pos()
        if start == goal:
            return []
        levitating = self.dive.castle.levitating()
        prev = {start: None}
        if danger:
            best = {start: 0.0}
            heap = [(0.0, 0, start)]
            tick = 0
            while heap:
                cost, _, p = heapq.heappop(heap)
                if p == goal:
                    break
                if cost > best.get(p, 1e9):
                    continue
                for dx, dy in DIRS8:
                    n = (p[0] + dx, p[1] + dy)
                    if not self._passable(n):
                        continue
                    if n in blocked and n != goal:
                        continue
                    if n in TRAPDOORS and n != goal and not levitating:
                        continue
                    if dx and dy:
                        if self._door_square(p) or self._door_square(n):
                            continue
                        if not self._passable((p[0] + dx, p[1])) and not self._passable((p[0], p[1] + dy)):
                            continue
                    c = cost + 1.0 + danger.get(n, 0.0)
                    if c < best.get(n, 1e9):
                        best[n] = c
                        prev[n] = p
                        tick += 1
                        heapq.heappush(heap, (c, tick, n))
        else:
            todo = collections.deque([start])
            while todo:
                p = todo.popleft()
                if p == goal:
                    break
                for dx, dy in DIRS8:
                    n = (p[0] + dx, p[1] + dy)
                    if n in prev or not self._passable(n):
                        continue
                    if n in blocked and n != goal:
                        continue
                    if n in TRAPDOORS and n != goal and not levitating:
                        continue
                    if dx and dy:
                        if self._door_square(p) or self._door_square(n):
                            continue
                        if not self._passable((p[0] + dx, p[1])) and not self._passable((p[0], p[1] + dy)):
                            continue
                    prev[n] = p
                    todo.append(n)
        if goal not in prev:
            return None
        path = []
        p = goal
        while p != start:
            path.append(p)
            p = prev[p]
        return path[::-1]

    # ------------------------------------------------------------------ actions

    def _walk_to(self, nxt):
        """One step onto the adjacent map square nxt (a closed door opens by walking into it)."""
        agent = self.agent
        pos = self._pos()
        d = DIR_NAME[(nxt[0] - pos[0], nxt[1] - pos[1])]
        before = agent.blstats.time
        agent.direction(d)
        msg = agent.message or ''
        if 'This door is locked' in msg:
            self.locked.add(nxt)
            self._log(f'locked door at {nxt}')
            return True
        if self._pos() == pos and agent.blstats.time == before:
            self.tries[('stuck', pos, nxt)] += 1
            if self.tries[('stuck', pos, nxt)] > 12:
                self._log(f'stuck at {pos} going {d}: {msg[:80]!r}: routing around {nxt} for a while')
                self.blocked[nxt] = agent.blstats.time + 100
                self.tries[('stuck', pos, nxt)] = 0
        return True

    def _attack(self, m, why=''):
        agent = self.agent
        self._set_state(f'fighting {m.name} at {m.p}{why}')
        with agent.atom_operation():
            agent.step(A.Command.FIGHT)
            agent.direction(agent.calc_direction(agent.blstats.y, agent.blstats.x, m.y, m.x))
        return True

    def _engrave(self, why):
        self.tries['engrave'] += 1
        self.last_engrave = self.agent.blstats.time
        self._set_state(f'Elbereth: {why}')
        self.agent.engrave('Elbereth')
        return True

    def _search(self, n=1, why='waiting'):
        self._set_state(why)
        self.agent.search(n)
        return True

    def _usable(self, name):
        c = self.dive.castle
        return next((i for i in c._items() if c._usable_wand(i, name)), None)

    def _unlocker(self):
        return next((i for i in self.agent.inventory.items if i.is_unambiguous() and
                     i.object.name in ('skeleton key', 'lock pick', 'credit card')), None)

    def _shield_blocks(self, tool):
        """A two-handed tool (dwarvish mattock) can't be applied with a shield on."""
        try:
            two = bool(getattr(tool.objs[0], 'bi', False))
        except Exception:
            two = False
        blocked = two and self.agent.inventory.items.off_hand is not None
        if blocked and jf_config.MATTOCK_SHIELD:
            # MATTOCK_SHIELD (armour lane): every caller is about to apply the tool, so take the shield off (kept in the pack;
            # dive_logic.shield_up wears it again after MATTOCK_SHIELD_LOCK turns) instead of giving the dig up
            shield = self.agent.inventory.items.off_hand
            if shield.status != shield.CURSED:
                self._log(f'taking off {shield.text!r} for the two-handed {tool.text!r}')
                self.dive.shield_lock()
                self.agent.inventory.takeoff(shield)
                return self.agent.inventory.items.off_hand is not None
        return blocked

    # ------------------------------------------------------------------ door work

    def _open_door(self, door, d):
        """The locked door at `door`, in direction d from the hero's square: key, digging wand, pick-axe or mattock,
        striking wand; a kick only as the last resort (it wakes everything within sqrt(XL*20))."""
        agent = self.agent
        tool = self._unlocker()
        if tool is not None and self.tries[('unlock', door)] < 6:
            self.tries[('unlock', door)] += 1
            self._set_state(f'unlocking {door} with {tool.text!r}')
            with agent.atom_operation():
                agent.step(A.Command.APPLY)
                agent.type_text(agent.inventory.items.get_letter(tool))
                if 'direction' in agent.single_message:
                    agent.direction(d)
            msg = agent.message or ''
            self._log(f'unlock {door}: {msg[:120]!r}')
            if 'succeed in unlocking' in msg or 'unlock' in msg.lower():
                self.locked.discard(door)
                if 'succeed in unlocking' in msg:
                    self.keyed.add(door)
            return True
        wand = self._usable('digging')
        if wand is not None and self.tries[('wdig', door)] < 2:
            self.tries[('wdig', door)] += 1
            self._set_state(f'zapping digging {d} at the locked door {door}')
            agent.zap(wand, d)
            self._log(f'door dig zap {door}: {(agent.message or "")[:120]!r}')
            self.broken.add(door)
            self.locked.discard(door)
            return True
        dig = self.dive.digging_tool()
        if dig is not None and self.tries[('pdig', door)] < 8 and not self._shield_blocks(dig):
            self.tries[('pdig', door)] += 1
            self._set_state(f'digging through the locked door {door} with {dig.text!r}')
            with agent.atom_operation():
                dig = agent.inventory.move_to_inventory(dig)
                agent.step(A.Command.APPLY)
                agent.type_text(agent.inventory.items.get_letter(dig))
                if 'In what direction do you want to dig?' in agent.single_message:
                    agent.direction(d)
                elif agent.single_message.startswith('In what direction'):
                    agent.step(A.Command.ESC)
            msg = agent.message or ''
            self._log(f'door dig {door}: {msg[:120]!r}')
            if 'break through' in msg:
                self.broken.add(door)
                self.locked.discard(door)
            return True
        wand = self._usable('striking')
        if wand is not None and self.tries[('wstrike', door)] < 3:
            self.tries[('wstrike', door)] += 1
            self._set_state(f'zapping striking {d} at the locked door {door}')
            agent.zap(wand, d)
            self._log(f'door strike zap {door}: {(agent.message or "")[:120]!r}')
            return True
        if self.tries[('kick', door)] < 30:
            self.tries[('kick', door)] += 1
            self._set_state(f'kicking the locked door {door} (no key, wand or digging tool)')
            with agent.atom_operation():
                agent.step(A.Command.KICK)
                agent.direction(d)
            self._log(f'kick {door}: {(agent.message or "")[:100]!r}')
            return True
        self._stop(f'locked door at {door}')
        return False

    # ------------------------------------------------------------------ the plan

    def step(self):
        agent = self.agent
        if self.done:
            return False
        self.steps += 1
        if self.steps > 4000:
            self._stop('step budget spent')
            return False
        bl = agent.blstats
        if self.start_turn is None:
            self.start_turn = bl.time
            inv = '; '.join(i.text for i in self.dive.castle._items())
            self._mile('start', f'depth {int(bl.depth)} xl {int(bl.experience_level)} inv: {inv}')
        if agent.wield_best_melee_weapon():
            return True
        wand = self._wand_in_pack()
        if wand is not None and self._test_wand(wand):
            return True     # (the naming zap; a named wand falls through: fight what is next to us, then hold)
        if SECRET_E not in self.sdoor_found and (self._is_open_door(SECRET_E) or
                                                  self._door_sym(SECRET_E) in (SS.S_vodoor, SS.S_hodoor)):
            self.sdoor_found.add(SECRET_E)
        mons = self._mons()
        if jf_config.CASTLE_INNER_HORN and self._horn_step(mons):
            return True
        if jf_config.CASTLE_INNER_CROWD and self._crowd_step(mons):
            return True
        if self._combat(mons):
            return True
        return self._advance(mons)

    # ---- combat and defence

    def _horn_item(self):
        from . import opp_items
        agent = self.agent
        for it in agent.inventory.items:
            try:
                if opp_items.instrument_kind(agent, it) in ('scare', 'horn'):
                    return it
            except Exception:
                continue
        return None

    def _horn_step(self, mons):
        """CASTLE_INNER_HORN: a tooled horn (30% of the real kits carry the one that played the tune) blown on
        'Improvise?' makes every monster within distu < XL*10 (radius ~10) that fails resist() flee with no timer
        (music.c awaken_monsters/monflee; soldiers, trolls, ogres, giants have MR 0 and never resist, xorns 20 of 100); a fleeing
        monster that can move away does not attack and an untimed flee ends 1 time in 25 per move only at full HP. One action
        per blow: when two or more hostiles are within 4 squares, a wall-walker within 5, or an @ within 3 while we are
        under 85% HP -- at most every CASTLE_INNER_HORN_GAP turns, 30 blows. An unknown 'horn' is tried once (a frost or
        fire horn fires its ray at the nearest hostile, a horn of plenty gives food, both are then left alone)."""
        agent = self.agent
        if self.tries['horn'] >= 30 or self._on_scare() or self._status_bad() or agent.character.prop.polymorph:
            return False
        now = agent.blstats.time
        if now - self.last_horn < jf_config.CASTLE_INNER_HORN_GAP:
            return False
        near = [m for m in mons if not m.peaceful and not m.unseen and m.dist <= 6 and
                0 <= m.p[0] <= 62 and 0 <= m.p[1] <= 16 and map_char(*m.p) != '}']    # (not the moat's eels and sharks)
        if not near:
            return False
        hpf = self._hpf()
        trigger = (len(near) >= 2 and near[0].dist <= 4) or any(m.ww and m.dist <= 5 for m in near) or \
            (hpf < 0.85 and any(m.ign and m.dist <= 3 for m in near))
        if not trigger:
            return False
        horn = self._horn_item()
        if horn is None:
            return False
        from . import opp_items
        pos = self._pos()
        m0 = near[0]
        step = (max(-1, min(1, m0.p[0] - pos[0])), max(-1, min(1, m0.p[1] - pos[1])))
        d = DIR_NAME.get(step, 's')
        self.last_horn = now
        self.tries['horn'] += 1
        self._set_state(f'blowing {horn.text!r} at {[m.name for m in near[:4]]}')
        opp_items.play(agent, horn, d)
        return True

    def _crowd_step(self, mons):
        """CASTLE_INNER_CROWD: a mob forming round us in the open (3+ hostile within 2 squares, one of them an @ or minotaur,
        which no Elbereth stops) is fought from a one-wide square instead: the nearest hall or hallway square within 6 steps
        (not through a monster). There they come single file (two with a polearm) instead of four at once. Held there
        for 20 turns while the @ are about, so that the walk on does not step back into the room."""
        pos = self._pos()
        now = self.agent.blstats.time
        if pos in CORRIDOR_SQUARES or pos in TOWER_SQUARES or self._on_scare() or self.tries['crowd'] >= 60:
            return False
        near = [m for m in mons if not m.peaceful and not m.unseen and m.dist <= 2]
        if len(near) < 3 or not any(m.ign for m in near):
            return False
        occupied = {m.p for m in mons}
        prev = {pos: None}
        todo = collections.deque([(pos, 0)])
        target = None
        while todo:
            p, d = todo.popleft()
            if p in CORRIDOR_SQUARES and p != pos:
                target = p
                break
            if d >= 6:
                continue
            for dx, dy in DIRS8:
                n = (p[0] + dx, p[1] + dy)
                if n in prev or not self._passable(n) or n in occupied or n in TRAPDOORS:
                    continue
                if dx and dy:
                    if self._door_square(p) or self._door_square(n):
                        continue
                    if not self._passable((p[0] + dx, p[1])) and not self._passable((p[0], p[1] + dy)):
                        continue
                prev[n] = p
                todo.append((n, d + 1))
        if target is None:
            return False
        step = target
        while prev[step] != pos:
            step = prev[step]
        self.tries['crowd'] += 1
        self.crowd_until = now + 20
        self._set_state(f'a crowd of {[m.name for m in near]}: back to the one-wide square {target}')
        return self._walk_to(step)

    def _combat(self, mons):
        """Fight what is next to us, or engrave when that is the better answer. True if it acted."""
        adj = [m for m in mons if m.adj and not m.peaceful]
        if not adj:
            self.elb_wait = 0
            return False
        if self._on_scare():
            return False   # the scare monster scroll under us: nothing melees us, blows would only cost alignment
        now = self.agent.blstats.time
        seen = [m for m in adj if not m.unseen]
        ign = [m for m in seen if m.ign]
        res = [m for m in seen if not m.ign]
        hpf = self._hpf()
        if jf_config.LIFT_EAST_FIGHT and res and not ign and self.east.get('phase') in ('walk', 'dig', 'sieve', 'enter') and \
                hpf >= jf_config.LIFT_EAST_FIGHT_HP and not self._on_scare():
            # LIFT_EAST_FIGHT: in the one-wide east hall they come one at a time (the huge ones the trap door does not take, the wall-walkers): a
            # healthy hero kills them where they stand instead of writing Elbereth and letting them flee to come back (strong seeds 6, 16, 20: the
            # sieve sat 80 turns on Elbereth with the same giants and xorns returning, then walked into the doorway with all of them alive)
            target = min(res, key=lambda m: (m.lvl, m.dist))
            return self._attack(target, ' (east hall chokepoint)')
        if self._elb_on():
            # a wall-walker (xorn, earth elemental) or another heavy hitter next to us: write Elbereth at once, before it
            # gets its blows (it has just spent its move arriving), and let it go: it flees for rnd(10) turns and a walking
            # hero (speed 15 against the xorn's 9) is not caught again. Fighting a xorn costs ~35-60 HP (AC -2, ~36 HP,
            # 3 claws and a 4d6 bite), more than the 28% of garbled engravings (a round of blows) will ever cost.
            danger = [m for m in res if m.ww or m.lvl >= 8]
            if danger and self._east_afloat_leg() and self.east.get('phase') in ('walk', 'dig') and \
                    self._pos() not in TRAPDOORS and not any(m.ign for m in seen):
                return self._east_land('%s arrived while afloat' % [m.name for m in danger])
            if danger and not self._engraved() and self._can_write() and now - self.last_engrave >= 3 and \
                    self.tries['elb'] < 80:
                self.tries['elb'] += 1
                self.elb_wait = 0
                return self._engrave(f'{[m.name for m in danger]} arrived')
            if danger and self._engraved() and not ign and self.elb_wait < 4:
                self.elb_wait += 1
                return self._search(1, f'on Elbereth while {[m.name for m in danger]} flee')
        if ign:
            # an @/minotaur next to us: dust Elbereth does not scare it. Fight it. Only when badly hurt with a
            # respecter on us too is a written Elbereth worth the turn (they flee for rnd(10) turns; our own blow
            # scuffs the dust afterwards, so never twice within a few turns: v1 lost half its blows that way)
            if res and hpf < 0.5 and not self._engraved() and self._can_write() and \
                    now - self.last_engrave >= 6 and self.tries['engrave_mixed'] < 30:
                self.tries['engrave_mixed'] += 1
                return self._engrave(f'{[m.name for m in res]} beside {[m.name for m in ign]}')
            return self._attack(self._pick(ign))
        if res:
            # CASTLE_INNER_XORN: a lone wall-walker (xorn, earth elemental) next to us while we are healthy and nothing
            # that ignores Elbereth is near: kill it now, at the moment of our choosing. A xorn follows through the walls at
            # speed 9 wherever we go and joins every later fight (9 of 25 deaths of v2+hold had one beside them); alone it
            # costs ~25 HP (AC -2, ~36 HP, 3 claws + a 4d6 bite), in a crowd it deals 17 a turn to our back.
            if jf_config.CASTLE_INNER_XORN and len(res) == 1 and res[0].ww and hpf >= jf_config.CASTLE_INNER_XORN_HP and \
                    not any(m.ign and not m.peaceful and not m.unseen and m.dist <= 6 for m in mons):
                return self._attack(res[0], ' (xorn duty)')
            # only Elbereth-respecters adjacent. They follow slower than we walk (a same-speed chaser that must move to
            # stay adjacent does not attack that turn: monmove.c dochug case 1), so while healthy we walk on; hurt, we
            # write and rest (the engraving stops all of them; xorns, trolls, giants...)
            if self._engraved():
                return self._search(1, f'resting on Elbereth with {[m.name for m in res]} around') if self.resting \
                    else False
            if hpf < jf_config.CASTLE_INNER_LOW and self._can_write() and self.tries['engrave_res'] < 120:
                self.tries['engrave_res'] += 1
                self.resting = True
                return self._engrave(f'{[m.name for m in res]} hurt us')
            if hpf < jf_config.CASTLE_INNER_LOW and self._pos() in NO_WRITE and self.tries['stepoff'] < 40 and \
                    self._step_off(mons, f'{[m.name for m in res]} hurt us and no Elbereth can be written here'):
                self.tries['stepoff'] += 1
                self.resting = True
                return True
            return False
        # only a remembered unseen thing next to us (an invisible stalker, a hidden xorn...): a blow at it when it hurt
        # us just now, else no business of ours
        if adj and self.agent._hurt_recently(2) and hpf >= 0.4:
            return self._attack(adj[0], ' (unseen)')
        return False

    @staticmethod
    def _pick(ign):
        pri = {'captain': 0, 'lieutenant': 1, 'sergeant': 2}
        return sorted(ign, key=lambda m: (pri.get(m.name, 5), -m.lvl, m.dist))[0]

    # ---- progress

    def _advance(self, mons):
        pos = self._pos()
        hpf = self._hpf()
        p = self.agent.character.prop
        if (p.blind or p.confusion or p.stun) and not any(m.adj and not m.peaceful for m in mons):
            return self._search(2, 'waiting out blind/confused/stunned')
        if self._route_pending() or self._wand_in_pack() is not None:
            # the wand of wishing is in the pack and named: WISH_TELEPORT_ROUTE (tele_route, a higher layer) zaps, reads and
            # teleports; we hold the tower square (the scare monster scroll under us) and do nothing that moves, digs or
            # opens doors until it is done or the level changes (t-route's contract)
            if self._hold_for_route():
                return self._search(1, 'holding the tower square while the wish route runs')
            self._stop('wand in hand (WISH_TELEPORT_ROUTE takes over)')
            return False
        if pos in TOWER_SQUARES or pos in TOWER_DOORS:
            return self._tower_phase(mons)
        if self._resting(pos, mons):
            return self._rest(mons)
        if jf_config.LIFT_EAST_WAND and (pos in EAST_HALL or pos == SECRET_E) and self._east_wanted():
            return self._east_leg(pos, mons)
        if int(self.agent.blstats.depth) >= 29 and jf_config.PASSTUNE_C29_TRAPDOOR and \
                (pos in THRONE or pos in EAST_HALL or pos == SECRET_E):
            return self._trapdoor_step(mons)
        clear = self._ante_clear(pos, mons)
        if clear is not None:
            return clear
        grind = self._hall_grind(pos, mons)
        if grind is not None:
            return grind
        hold = self._hall_hold(mons)
        if hold is not None:
            return hold
        lock = self._lock_behind(pos, mons)
        if lock is not None:
            return lock
        gate = self._pit_gate(pos, mons)
        if gate is not None:
            return gate
        if jf_config.CASTLE_INNER_CROWD and pos in CORRIDOR_SQUARES and self.agent.blstats.time < self.crowd_until and \
                any(m.ign and not m.peaceful and not m.unseen and 1 < m.dist <= 6 for m in mons):
            return self._search(1, 'holding the one-wide square while the @ come')
        return self._goto(self._goal(), mons)

    def _lock_behind(self, pos, mons):
        """CASTLE_INNER_LOCK: a throne door we unlocked with a key is closed and locked again behind us. Monsters open
        a closed door but not a locked one (they carry no keys): the trolls, ogres, mummies and soldiers that follow us
        stay in the throne room; only giants (they smash it) and wall-walkers get through."""
        if not jf_config.CASTLE_INNER_LOCK:
            return None
        for door, beyond, back in ((DOOR_N, (32, 3), 's'), (DOOR_S, (32, 13), 'n')):
            if pos != beyond or door not in self.keyed or door in self.relocked or self.tries[('lockb', door)] >= 6:
                continue
            if any(m.p == door or (m.adj and not m.peaceful and not m.unseen and m.ign) for m in mons):
                return None
            tool = next((i for i in self.agent.inventory.items if i.is_unambiguous() and
                         i.object.name in ('skeleton key', 'lock pick')), None)
            if tool is None:
                continue
            agent = self.agent
            self.tries[('lockb', door)] += 1
            g = self._glyph(door)
            if g in G.DOOR_OPENED:
                self._set_state(f'closing the door {door} behind us')
                with agent.atom_operation():
                    agent.step(A.Command.CLOSE)
                    agent.direction(back)
                self._log(f'close {door}: {(agent.message or "")[:100]!r}')
                return True
            if g in G.DOOR_CLOSED or self._closed_door(door):
                self._set_state(f'locking the door {door} behind us with {tool.text!r}')
                with agent.atom_operation():
                    agent.step(A.Command.APPLY)
                    agent.type_text(agent.inventory.items.get_letter(tool))
                    if 'direction' in agent.single_message:
                        agent.direction(back)
                    if 'Lock it?' in agent.single_message:
                        agent.type_text('y')
                msg = agent.message or ''
                self._log(f'lock {door}: {msg[:100]!r}')
                if 'succeed in locking' in msg:
                    self.relocked.add(door)
                    self._mile('locked_behind', f'{door}')
                return True
            self.relocked.add(door)   # a broken door or no door: nothing to lock
        return None

    def _ante_clear(self, pos, mons):
        """CASTLE_INNER_XORN: the antechamber is the quiet room -- the barracks stream is dormant while we are west
        (the soldiers jam on the barracks' west wall), the court is at the far end -- and the only things that reach us
        here are the wall-walkers, which home in through the walls at speed 9. Wait for them here, at full HP, and fight
        them one at a time as they arrive (rest on Elbereth between), instead of meeting them in the hall or the throne
        room together with the army. Done when none has been in view for CLEAR_QUIET turns (after CLEAR_MIN), or after
        CLEAR_MAX."""
        if not jf_config.CASTLE_INNER_XORN or pos not in ANTE:
            return None
        now = self.agent.blstats.time
        c = self.clearing
        if c is None:
            c = self.clearing = dict(t0=now, last=now, done=False)
            self._mile('clearing', f'in the antechamber at {pos}')
        if c['done']:
            return None
        if any(m.ww and not m.peaceful and not m.unseen and m.dist <= 14 for m in mons):
            c['last'] = now
        waited, quiet = now - c['t0'], now - c['last']
        if (waited >= jf_config.CASTLE_INNER_CLEAR_MIN and quiet >= jf_config.CASTLE_INNER_CLEAR_QUIET) or \
                waited >= jf_config.CASTLE_INNER_CLEAR_MAX:
            c['done'] = True
            self._log(f'antechamber clear after {waited} turns (quiet {quiet}, hp {self._hpf():.2f})')
            return None
        if any(m.ign and not m.peaceful and not m.unseen and m.dist <= 8 for m in mons):
            return None   # an @ about: no waiting (the usual rules)
        return self._search(2, 'waiting in the antechamber for the wall-walkers')

    def _dig_pit_here(self, why):
        """Apply the digging tool downward: on the castle a hole is impossible, dig() makes a pit once the effort
        passes 50 (two turns for a dwarf) and we sit in it for u.utrap = 2..5 moves. True if it acted."""
        agent = self.agent
        dig = self.dive.digging_tool()
        if dig is None or self._shield_blocks(dig):
            return False
        self._set_state(f'digging a pit at {self._pos()} ({why})')
        with agent.atom_operation():
            dig = agent.inventory.move_to_inventory(dig)
            agent.step(A.Command.APPLY)
            agent.type_text(agent.inventory.items.get_letter(dig))
            if 'In what direction do you want to dig?' in agent.single_message:
                agent.direction('>')
            elif agent.single_message.startswith('In what direction'):
                agent.step(A.Command.ESC)
        msg = agent.message or ''
        self._log(f'pit dig at {self._pos()}: {msg[:120]!r}')
        return 'dig a pit' in msg or ('pit' in msg and 'dig' in msg)

    def _hall_grind(self, pos, mons):
        """CASTLE_INNER_GRIND: the stream and the court's remnants come at us through the one-wide hall. A pit at
        (24,08) plugs it: the first monster that steps in is trapped (1 turn in 40 to get out, trap.c mintrap), the queue
        behind it cannot pass, a monster three squares away from us cannot reach us, and the dust Elbereth we rest on
        keeps the xorns off. So they come one at a time, when we say: rest to full HP at (21,08), step up, kill the one in
        the pit, step back. When nothing has come for a while we climb through the pit ourselves."""
        if not jf_config.CASTLE_INNER_GRIND:
            return None
        g = self.grind
        if g is None:
            if pos != GRIND_PIT or self.dive.digging_tool() is None or self.tries['grind_dig'] >= 3 or \
                    any(m.adj and not m.peaceful and not m.unseen for m in mons):
                return None
            self.tries['grind_dig'] += 1
            if self._dig_pit_here('hall grinder'):
                self.grind = dict(t0=self.agent.blstats.time, quiet=self.agent.blstats.time, state='wait')
                self._mile('grind', f'pit at {GRIND_PIT}')
                return True
            return True
        if g['state'] == 'done':
            return None
        now = self.agent.blstats.time
        occupant = next((m for m in mons if m.p == GRIND_PIT), None)
        hostile = [m for m in mons if not m.peaceful and not m.unseen and not m.ww and not m.fly and m.dist <= 12 and
                   (m.p[1] == 8 or m.p in THRONE)]
        if hostile or occupant:
            g['quiet'] = now
        waited, quiet = now - g['t0'], now - g['quiet']
        hpf = self._hpf()
        if g['state'] == 'cross':
            if pos[0] > GRIND_PIT[0]:
                g['state'] = 'done'
                self._log(f'crossed the pit after {waited} turns, hp {hpf:.2f}')
                return None
            return self._goto(GRIND_PIT, mons) if pos != GRIND_PIT else self._walk_to((GRIND_PIT[0] + 1, 8))
        if (waited >= jf_config.CASTLE_INNER_GRIND_MIN and quiet >= jf_config.CASTLE_INNER_GRIND_QUIET and
                hpf >= 0.9 and not occupant) or waited >= jf_config.CASTLE_INNER_GRIND_MAX:
            g['state'] = 'cross'
            self._log(f'grind over after {waited} turns (quiet {quiet}, hp {hpf:.2f}): crossing the pit')
            return self._goto(GRIND_PIT, mons)
        # climbing out of the pit westward, then holding the stand square
        if pos[0] >= GRIND_PIT[0] and pos[1] == 8:
            return self._walk_to((pos[0] - 1, 8))
        if occupant is not None and hpf >= 0.9 and not any(m.ign and m.adj for m in mons):
            # step up and kill the one in the pit (it cannot leave; the queue behind it is two squares from us)
            if pos != GRIND_FIGHT:
                return self._walk_to((pos[0] + 1, 8)) if pos[0] < GRIND_FIGHT[0] else self._walk_to((pos[0] - 1, 8))
            return self._attack(occupant, ' (in the pit)')
        if occupant is not None and pos == GRIND_FIGHT and hpf >= 0.5:
            return self._attack(occupant, ' (in the pit)')
        if pos[0] > GRIND_STAND[0] and pos[1] == 8 and not (occupant is not None and pos == GRIND_FIGHT and hpf >= 0.5):
            return self._walk_to((pos[0] - 1, 8))
        if pos != GRIND_STAND:
            return self._goto(GRIND_STAND, mons)
        if not self._engraved() and self._can_write() and self.tries['grind_elbereth'] < 200:
            self.tries['grind_elbereth'] += 1
            return self._engrave('hall grinder')
        return self._search(3, 'waiting at the stand square behind the pit')

    def _gate_square(self):
        """The hallway square, a few steps beyond the throne door in the direction of the tower we try next, where a
        pit is dug behind us."""
        name = self._current_tower()
        if name is None:
            return None
        row = 3 if name in ('NW', 'NE') else 13
        return (34 if name in ('NE', 'SE') else 30, row)

    def _pit_gate(self, pos, mons):
        """CASTLE_INNER_PIT: the hallway is one square wide, so a pit in it is a gate: the first follower that steps in
        falls (trap.c mintrap: it escapes only 1 time in 40 per move, rn2(40)), and the queue behind it cannot pass; a
        monster that has been in a pit avoids pits. Every walker falls in (flyers, clingers and wall-walkers -- xorns,
        earth elementals -- do not), so the court's trolls, giants, ogres and the barracks' soldiers arrive one at a time
        with ~40 turns between them instead of a mob on our back. Dug with the pick-axe: dig.c dig(), effort > 50 makes a
        pit (two turns for a dwarf), on the castle a hole is impossible (pits only); we sit in it u.utrap = 2..5 turns."""
        if not jf_config.CASTLE_INNER_PIT or pos != self._gate_square() or pos in self.gates:
            return None
        if any(m.adj and not m.peaceful and not m.unseen and (m.ign or m.dist <= 1) for m in mons):
            return None
        dig = self.dive.digging_tool()
        if dig is None or self._shield_blocks(dig) or self.tries[('gate', pos)] >= 4:
            return None
        agent = self.agent
        self.tries[('gate', pos)] += 1
        self._set_state(f'digging a pit gate at {pos}')
        with agent.atom_operation():
            dig = agent.inventory.move_to_inventory(dig)
            agent.step(A.Command.APPLY)
            agent.type_text(agent.inventory.items.get_letter(dig))
            if 'In what direction do you want to dig?' in agent.single_message:
                agent.direction('>')
            elif agent.single_message.startswith('In what direction'):
                agent.step(A.Command.ESC)
        msg = agent.message or ''
        self._log(f'gate dig at {pos}: {msg[:120]!r}')
        if 'dig a pit' in msg or 'pit' in msg and 'dig' in msg:
            self.gates.add(pos)
            self._mile('gate', f'pit at {pos}')
        return True

    def _hall_hold(self, mons):
        """CASTLE_INNER_HOLD: at (25,08), behind the closed door (26,08), wait for the barracks stream. Their awake
        soldiers follow our square greedily, so as we walk east they run east along the barracks and leave by a
        broken door into the throne room just as we arrive (R0/v1: 17 of 46 states died in the first ten turns in the
        throne room, most to six soldiers around them). Here they come through the door one at a time (two with a
        polearm), nothing can flank us but the xorns (Elbereth) and thrown weapons are blocked by the closed door.
        Returns None when the hold is not (or no longer) wanted."""
        if not self._hold_on() or self.hold_done or self._pos() != HOLD_SQUARE or self.grind is not None:
            return None
        now = self.agent.blstats.time
        if self.hold_t0 is None:
            self.hold_t0 = self.hold_quiet = now
            self._mile('hold', f'at {HOLD_SQUARE}')
        if any(m.ign and not m.peaceful and m.dist <= 10 for m in mons):
            self.hold_quiet = now
        waited, quiet = now - self.hold_t0, now - self.hold_quiet
        if (waited >= jf_config.CASTLE_INNER_HOLD_MIN and quiet >= 10 and
                self._hpf() >= self._gate()) or waited >= jf_config.CASTLE_INNER_HOLD_MAX:
            self.hold_done = True
            self._log(f'hold over after {waited} turns (quiet {quiet}, hp {self._hpf():.2f})')
            return None
        if not self._engraved() and self._can_write() and self.tries['hold_elbereth'] < 60:
            self.tries['hold_elbereth'] += 1
            return self._engrave('hall hold')
        return self._search(2, 'holding (25,08) for the barracks stream')

    def _route_pending(self):
        """A known wand of wishing is in the pack and WISH_TELEPORT_ROUTE has not finished (t-route's own test: tele_route
        .wishing_wand(agent) is not None with the route not done)."""
        if not jf_config.WISH_TELEPORT_ROUTE or getattr(self.agent, '_tele_route_done', False):
            return False
        from . import tele_route
        return tele_route.wishing_wand(self.agent) is not None

    def _hold_for_route(self):
        """The wand of wishing is named and WISH_TELEPORT_ROUTE is wishing, reading, teleporting: stay on the tower
        square until the level changes or the route says it is done (the castle passage logic would dig and wander).
        A 'wish failed' zap (Luck < 0: 'Unfortunately, nothing happens', the charge is spent) is the route's to repeat."""
        if not self._route_pending() or self.tries['route_hold'] > 400:
            return False
        self.tries['route_hold'] += 1
        return True

    def _rest_ok(self, mons):
        return not any(m.ign and not m.peaceful and m.dist <= 8 for m in mons) and self.tries['rest'] < 900

    def _resting(self, pos, mons):
        """Rest (a written Elbereth, then search) from below `low` of max HP up to `high`, only while no @ or minotaur
        is in view within 8 (they ignore Elbereth). Before the throne room, behind two doors, the bar is higher."""
        hpf = self._hpf()
        safe = pos in HALL or pos == DOOR_A or pos in ANTE
        low = self._gate() if safe else jf_config.CASTLE_INNER_LOW
        high = 0.92 if safe else jf_config.CASTLE_INNER_RESUME
        ok = self._rest_ok(mons)
        if self.resting:
            if hpf >= high or not ok:
                self.resting = False
        elif hpf < low and ok:
            self.resting = True
        return self.resting

    def _rest(self, mons):
        self.tries['rest'] += 1
        if self._east_afloat_leg():
            # (LIFT_EAST_WAND) a rest in the east hall is on foot on a square that is not a trap door, so that Elbereth can be written
            pos = self._pos()
            if pos in TRAPDOORS:
                return self._walk_to((pos[0] - 1, 8))
            return self._east_land('resting')
        if self._pos() in NO_WRITE and self.tries['stepoff'] < 40 and self._step_off(mons, 'no Elbereth can be written here'):
            self.tries['stepoff'] += 1
            return True
        if not self._engraved() and self._can_write():
            return self._engrave('rest')
        if jf_config.CASTLE_INNER and self._eat_if_hungry(mons):
            return True
        return self._search(3, 'resting')

    # ---- where to

    def _tower_names(self):
        order = TOWER_ORDERS.get(jf_config.CASTLE_INNER_ORDER, TOWER_ORDERS['east'])
        names = [n for n in order if self.tower_state.get(n) != 'empty']
        if self.side is not None:
            # the towers of the chosen half (north: NE NW, south: SE SW) first, in the configured order
            names = [n for n in names if n[0] == self.side] + [n for n in names if n[0] != self.side]
        return names

    def _choose_side(self, mons):
        """CASTLE_INNER_SIDE: at the throne room entrance pick the half (north door (32,04) or south door (32,12)) whose
        approach is emptier: hostile walkers near the route and an open barracks door on that side (a broken
        (26,05)/(26,11) lets the awake soldiers out right at the route). Sticky once chosen, until its towers are done."""
        order = TOWER_ORDERS.get(jf_config.CASTLE_INNER_ORDER, TOWER_ORDERS['east'])
        left = {n[0] for n in order if self.tower_state.get(n) != 'empty'}
        if self.side in left:
            return self.side
        if len(left) == 1:
            self.side = next(iter(left))
            return self.side
        if not jf_config.CASTLE_INNER_SIDE:
            self.side = next(n[0] for n in order if self.tower_state.get(n) != 'empty')
            return self.side
        score = {}
        for side, door, under, barracks in (('N', DOOR_N, UNDER_N, (26, 5)), ('S', DOOR_S, UNDER_S, (26, 11))):
            sc = 0.0
            for m in mons:
                if m.peaceful or m.unseen or m.ww or m.fly:
                    continue
                d = max(abs(m.p[0] - under[0]), abs(m.p[1] - under[1]))
                near_barracks = max(abs(m.p[0] - barracks[0]), abs(m.p[1] - barracks[1])) <= 3
                sc += (3.0 if m.ign else 2.0) / (1 + d) + (1.0 if near_barracks else 0.0)
            g = self._glyph(barracks)
            if g in G.DOOR_OPENED or g == SS.S_ndoor:
                sc += 2.0
            score[side] = sc
        first = next(n[0] for n in order if self.tower_state.get(n) != 'empty')
        self.side = min(left, key=lambda sd: (score[sd], sd != first))
        self._log(f'side {self.side} chosen: scores {score}')
        return self.side

    def _current_tower(self):
        names = self._tower_names()
        if 'chest' in self.tower_state.values():
            for n in names:
                if self.tower_state.get(n) == 'chest':
                    return n
        return names[0] if names else None

    def _goal(self):
        """The next map square on the way to the wand."""
        pos = self._pos()
        name = self._current_tower()
        if name is None:
            self._stop('no tower chest found')
            return pos
        if pos in ANTE or pos in HALL or pos in (PORTCULLIS, DOOR_A, DOOR_B):
            return THRONE_ENTRY
        if pos in THRONE and pos != THRONE_ENTRY:
            return self._throne_goal()
        if pos == THRONE_ENTRY:
            return self._throne_goal()
        return TOWER_OUTSIDE[name]

    def _throne_goal(self):
        """The square under the door of the hallway of the tower we try next ((32,5) north, (32,11) south); from a
        hallway of the wrong half, the other hallway's door square."""
        name = self._current_tower()
        if name is None:
            return UNDER_N
        return UNDER_N if name in ('NW', 'NE') else UNDER_S

    def _throne_decide(self, mons):
        self._choose_side(mons)

    def _danger_map(self, mons):
        """CASTLE_INNER_AVOID: extra route cost around what stands in the room (the heavy remnants of the court wait at the
        throne room's NE corner, (35..37, 5..7), and a walk that passes along row 5 or 8 into them is the one that died:
        jf82-s2, jf80-s14, jf87-s8 in the real-kit hand-offs): 3 squares away 1, 2 away 2, next to it 3, times
        CASTLE_INNER_AVOID_W (an @ counts half as much again: it is not scared by anything we can write)."""
        w = jf_config.CASTLE_INNER_AVOID_W
        out = {}
        for m in mons:
            if m.peaceful or m.unseen or m.dist > 14:
                continue
            k = w * (1.5 if m.ign else 1.0)
            for dx in range(-3, 4):
                for dy in range(-3, 4):
                    d = max(abs(dx), abs(dy))
                    if d == 0:
                        continue
                    sq = (m.p[0] + dx, m.p[1] + dy)
                    out[sq] = out.get(sq, 0.0) + k * (4 - d)
        return out

    def _goto(self, goal, mons):
        pos = self._pos()
        if pos == goal:
            return self._arrived(goal, mons)
        now = self.agent.blstats.time
        held = frozenset(sq for sq, until in self.blocked.items() if until > now)
        blocked = held | frozenset(m.p for m in mons if not m.peaceful or m.dist <= 2)
        danger = self._danger_map(mons) if jf_config.CASTLE_INNER_AVOID else None
        path = self._route(goal, blocked, danger)
        if path is None:
            path = self._route(goal, held)
        if not path:
            self.tries['noroute'] += 1
            if self.tries['noroute'] > 60:
                self._stop(f'no route from {pos} to {goal} (blocked {sorted(held)})')
                return False
            return self._search(1, f'no path from {pos} to {goal}')
        nxt = path[0]
        occupant = next((m for m in mons if m.p == nxt), None)
        if occupant is not None:
            if occupant.peaceful:
                self.tries[('peaceful', nxt)] += 1
                if self.tries[('peaceful', nxt)] > 25:
                    self.blocked[nxt] = now + 60     # a giant standing in the hallway: try something else for a while
                    self.tries[('peaceful', nxt)] = 0
                return self._search(1, f'waiting for the peaceful {occupant.name} to move from {nxt}')
            return self._attack(occupant, ' (blocks the way)')
        if nxt in self.locked and self._door_square(nxt):
            return self._door_work(nxt, mons)
        if self._boulder(nxt):
            return self._boulder_fix(nxt)
        self._set_state(f'walking to {goal} via {nxt}')
        return self._walk_to(nxt)

    def _boulder(self, p):
        y, x = to_bot(*p)
        level = self.agent.current_level()
        if not (0 <= y < level.objects.shape[0] and 0 <= x < level.objects.shape[1]):
            return False
        return self.agent.glyphs[y, x] in G.BOULDER or level.objects[y, x] in G.BOULDER

    def _boulder_fix(self, nxt):
        """A boulder on the way (a giant's, in a hallway): push it (twice), else break it (striking: force bolt;
        pick-axe: apply), else wait a little, else route around it for a while."""
        agent = self.agent
        pos = self._pos()
        d = DIR_NAME[(nxt[0] - pos[0], nxt[1] - pos[1])]
        key = ('boulder', nxt)
        self.tries[key] += 1
        n = self.tries[key]
        if n <= 2 and not ((jf_config.LIFT_EAST_WAND or jf_config.INNER_BOULDER_LEV) and self.dive.castle.levitating()):
            return self._walk_to(nxt)
        wand = self._usable('striking')
        if wand is not None and self.tries[('bzap', nxt)] < 2:
            self.tries[('bzap', nxt)] += 1
            self._set_state(f'zapping striking {d} at the boulder {nxt}')
            agent.zap(wand, d)
            return True
        dig = self.dive.digging_tool()
        if dig is not None and self.tries[('bdig', nxt)] < 4 and not self._shield_blocks(dig):
            self.tries[('bdig', nxt)] += 1
            self._set_state(f'digging through the boulder {nxt}')
            with agent.atom_operation():
                dig = agent.inventory.move_to_inventory(dig)
                agent.step(A.Command.APPLY)
                agent.type_text(agent.inventory.items.get_letter(dig))
                if 'In what direction do you want to dig?' in agent.single_message:
                    agent.direction(d)
                elif agent.single_message.startswith('In what direction'):
                    agent.step(A.Command.ESC)
            self._log(f'boulder dig {nxt}: {(agent.message or "")[:100]!r}')
            return True
        if n <= 8:
            return self._search(2, f'waiting for the boulder at {nxt}')
        self.blocked[nxt] = agent.blstats.time + 150
        self.tries[key] = 0
        return self._search(1, f'the boulder at {nxt} stays: routing around it')

    def _arrived(self, goal, mons):
        pos = self._pos()
        name = self._current_tower()
        if name is not None and pos == TOWER_OUTSIDE[name]:
            return self._peek(name, mons)
        if pos in (UNDER_N, UNDER_S):
            # the door beyond is the next square on the way (locked or not): walk into it
            door = DOOR_N if pos == UNDER_N else DOOR_S
            if door in self.locked and self._door_square(door):
                return self._door_work(door, mons)
            return self._walk_to(door)
        if pos == THRONE_ENTRY:
            self._mile('throne', f'{[m.name for m in mons if m.dist <= 8][:8]}')
            self._throne_decide(mons)
            return self._goto(self._throne_goal(), mons)
        return self._search(1, f'at {goal}')

    # ---- the locked door

    def _door_work(self, door, mons):
        pos = self._pos()
        d = DIR_NAME[(door[0] - pos[0], door[1] - pos[1])]
        near = [m for m in mons if not m.peaceful and m.dist <= 4]
        res = [m for m in near if not m.ign]
        if res and not self._engraved() and self._can_write() and self.tries['door_elbereth'] < 4:
            self.tries['door_elbereth'] += 1
            return self._engrave('before the door work')
        self._mile('door', f'{door}')
        return self._open_door(door, d)

    # ---- the tower

    def _objects_at(self, p):
        y, x = to_bot(*p)
        g = self.agent.glyphs[y, x]
        return bool(nh.glyph_is_object(g)) or self.agent.current_level().item_count[y, x] > 0

    def _peek(self, name, mons):
        """At the hallway square beside tower `name`'s door: open the door and look for the chest."""
        row, door, inside_sq, chest, room = TOWERS[name]
        self._mile('hallway', f'row {row} at {self._pos()}')
        if door in self.locked:
            return self._door_work(door, mons)
        if self._closed_door(door):
            return self._walk_to(door)
        if self._objects_at(chest):
            self.tower_state[name] = 'chest'
            self._mile('chest_seen', f'{name} {chest}')
            return self._walk_to(door)
        g = self._glyph(chest)
        if g in (SS.S_room, SS.S_darkroom):
            self._log(f'the {name} tower is empty')
            self.tower_state[name] = 'empty'
            return True
        # not in view yet: step into the doorway
        self.tries[('look', name)] += 1
        if self.tries[('look', name)] > 6:
            self._log(f'the {name} chest square stays unseen: next tower')
            self.tower_state[name] = 'empty'
            return True
        return self._walk_to(door)

    def _tower_phase(self, mons):
        name = self._current_tower()
        pos = self._pos()
        if name is None:
            self._stop('no tower chest found')
            return False
        row, door, inside_sq, chest, room = TOWERS[name]
        if pos not in room and pos != door:
            other = self._tower_of(pos)
            return self._goto(TOWER_OUTSIDE[other], mons)
        if self.tower_state.get(name) == 'empty':
            return self._goto(TOWER_OUTSIDE[name], mons)
        self._mile('tower', name)
        if pos == chest:
            return self._chest_step(name)
        return self._goto(chest, mons)

    @staticmethod
    def _tower_of(pos):
        for n, t in TOWERS.items():
            if pos in t[4] or pos == t[1]:
                return n
        return None

    def _wand_in_pack(self):
        # the Crusher's own wand leg (FrontDoor._chest_step) can take the chest wand one step before it hands over to us
        # (cand-l4 gate jf910 s7: 'Z - a platinum wand' at T14487, then 610 turns of empty towers, killed by a xorn):
        # its wand is ours too
        for mod in (getattr(self.dive, 'crusher', None), getattr(self.dive, 'front', None)):
            w = mod._wand_in_pack() if mod is not None and hasattr(mod, '_wand_in_pack') else None
            if w is not None:
                return w
        before = self._wands_before
        if before is None:
            return None
        for it in self.agent.inventory.items:
            if it.is_wand() and self.agent.inventory.items.get_letter(it) not in before:
                return it
        return None

    def _chest_step(self, name):
        agent = self.agent
        inv = agent.inventory
        self._mile('chest', name)
        self.scare_at.add(self._pos())
        if self.chest_fail > 12:
            self.tower_state[name] = 'empty'
            self.chest_fail = 0
            return True
        if self._wands_before is None:
            self._wands_before = {inv.items.get_letter(i) for i in inv.items if i.is_wand()}
        try:
            below = inv.get_items_below_me() or inv.items_below_me or []
        except AgentPanic as e:
            self.chest_fail += 1
            self._log(f'look failed: {e}')
            return True
        chest = next((i for i in below if i.is_container() or i.is_possible_container()), None)
        if chest is None:
            self.chest_fail += 1
            self._log(f'no chest below us: {[i.text for i in below]}')
            if below or self.chest_fail >= 3:
                self.tower_state[name] = 'empty'   # someone's loot on the corner square: not the wand's tower
                self.chest_fail = 0
                return True
            agent.search()
            return True
        try:
            inv.check_container_content(chest)
        except (AgentPanic, AssertionError) as e:
            if jf_config.INNER_WELD_PRAY and ('free hand' in str(e) or agent.hands_welded()):
                # INNER_WELD_PRAY: a court caster cursed the wielded weapon (mcastu.c MGC_CURSE_ITEMS -> rndcurse): welded beside a shield it leaves no
                # free hand ('Without a free hand, you cannot loot anything.'). pray.c TROUBLE_UNUSEABLE_HANDS is major trouble and the prayer
                # uncurses the weapon; castle_front's chest step does this, this one marked the wand's tower 'empty' after 13 failed looks
                # (backdoor lane, strong east-start seeds 1, 21 and 3: all four towers visited, 'no tower chest found').
                self.tries['weld'] += 1
                if agent.is_safe_to_pray() and not agent.prayer_failed and self.tries['weld_prayed'] < 1:
                    self.tries['weld_prayed'] += 1
                    self._log(f'hands welded on the chest ({e}): praying')
                    self._mile('weld_pray')
                    agent.pray()
                    return True
                if self.tries['weld'] < 80:
                    self._log(f'hands welded on the chest ({e}): waiting for a safe prayer')
                    agent.search()
                    return True
            self.chest_fail += 1
            self._log(f'chest check failed: {e}')
            return True
        content = chest.content
        if content is not None and content.locked:
            return self._unlock_chest()
        items = list(content.items) if content is not None else []
        wands = [i for i in items if i.is_wand()]
        self._log(f'chest content: {[i.text for i in items]}')
        if not wands:
            self.chest_fail += 1
            return True
        try:
            inv.use_container(chest, [], wands[:1])
        except (AgentPanic, AssertionError) as e:
            self.chest_fail += 1
            self._log(f'take-out failed: {e}')
            return True
        inv.items.update(force=True)
        w = self._wand_in_pack()
        if w is not None:
            self._mile('wand', w.text)
        return True

    def _unlock_chest(self):
        """Key, lock pick or credit card (quiet), else #force with a blade (quiet; Excalibur never breaks, a plain
        sword 0.7% per failed turn), else bash (wake_nearby each turn; 1 in 3 wrecks the chest and each item in it
        1 in 3)."""
        agent = self.agent
        inv = agent.inventory
        tool = self._unlocker()
        if tool is not None and self.tries['chest_unlock'] < 8:
            self.tries['chest_unlock'] += 1
            letter = inv.items.get_letter(tool)

            def responses():
                if 'What do you want to use or apply?' not in agent.single_message:
                    return
                yield letter
                for _ in range(3):
                    msg = agent.single_message or ''
                    if 'In what direction?' in msg or 'direction' in msg.lower():
                        yield '.'
                        continue
                    if ('unlock it?' in msg or 'pick its lock?' in msg) and '[yn' in msg:
                        yield 'y'
                        return
                    return

            self._set_state(f'unlocking the chest with {tool.text!r}')
            with agent.atom_operation():
                agent.step(A.Command.APPLY, responses())
            self._log(f'chest unlock: {(agent.message or "")[-120:]!r}')
            inv.items.update(force=True)
            return True
        self.tries['force'] += 1
        if self.tries['force'] > 30:
            self.chest_fail += 100
            return True
        blade = self._best_blade()
        wielded = inv.items.main_hand
        if blade is not None and blade is not wielded and self.tries['wield_blade'] < 4:
            self.tries['wield_blade'] += 1
            self._set_state(f'wielding {blade.text!r} to pry the chest open')
            inv.wield(blade)
            return True
        self._set_state('forcing the chest lock')
        with agent.atom_operation():
            agent.step(A.Command.FORCE)
            if 'force its lock?' in agent.message or 'force its lid?' in agent.message or '[ynq]' in agent.message:
                agent.type_text('y')
        self._log(f'force: {agent.message[:160]!r}')
        return True

    def _best_blade(self):
        """The carried weapon that pries best (lock.c: oc_wldam*2 percent a turn): Excalibur / a long sword 24."""
        from . import castle_treasury as T
        best = None
        for it in self.agent.inventory.items:
            c = T._blade(it)
            if c is None or it.status == it.CURSED:
                continue
            if best is None or c > T._blade(best):
                best = it
        return best

    def _test_wand(self, wand):
        """The tower chest's wand IS the wand of wishing (castle.des): one zap names it and asks for the first wish;
        WISH_TELEPORT_ROUTE (tele_route) answers it and does the rest."""
        agent = self.agent
        inv = agent.inventory
        self._mile('wand', wand.text)
        if (wand.is_unambiguous() and wand.object.name == 'wishing') or self.tries['wand_zap'] >= 2:
            return False     # named (the wish prompt was answered by tele_route's wish text): no second zap of ours
        self.tries['wand_zap'] += 1
        letter = inv.items.get_letter(wand)
        agent._last_wand_use_step = agent.step_count   # tele_route._wand_source: this wish comes from a wand
        self._set_state(f'zapping the chest wand {wand.text!r} ({letter}) to name it')
        with agent.atom_operation():
            agent.step(A.Command.ZAP)
            if 'What do you want to zap?' in agent.single_message:
                agent.type_text(letter)
            if 'In what direction?' in agent.single_message:
                agent.step(A.Command.ESC)
        self._log(f'wand zap -> {(agent.message or "")[:200]!r}')
        self._mile('wish', f'{(agent.message or "")[:120]!r}')
        inv.items.update(force=True)
        return True

    # ---- LIFT_EAST_WAND (backdoor lane): the east hall, the secret door (38,08) dug from the east, then the wand leg

    EAST_DIG = (39, 8)        # the east hall's west end: the square beside the secret door, west of the last trap door (40,08)
    SIEVE_SQ = (41, 8)        # between the trap doors (40,08) and (44,08): whatever chases us down the hall falls at (40,08)

    def _east_afloat_leg(self):
        """The east leg is under way and we are hovering."""
        return jf_config.LIFT_EAST_WAND and self.east.get('phase') in ('walk', 'dig', 'sieve', 'enter') and \
            self.dive.castle.levitating()

    def _lasting_lift_item(self):
        """The ring or boots that float us (and come off again): the one that made us float, else a known levitation ring /
        levitation boots in the pack. None if there is none."""
        c = self.dive.castle
        src = c._lev_source
        items = c._items()
        if src is not None and src[0] in ('ring', 'boots'):
            for it in items:
                if it.glyphs and it.glyphs[0] == src[1] and (it.category == nh.RING_CLASS or it.is_armor()):
                    return it
        for it in items:
            if it.is_unambiguous() and ((it.category == nh.RING_CLASS and it.object.name == 'levitation') or
                                        (it.is_armor() and it.object.name == 'levitation boots')):
                return it
        return None

    def _east_why_not(self, need_afloat):
        """None if the east leg is on the cards, else why not. need_afloat: we must be hovering now (False: asked before the
        back door, with the lift taken off to kick it)."""
        agent = self.agent
        c = self.dive.castle
        if not jf_config.LIFT_EAST_WAND:
            return 'flag off'
        if int(agent.blstats.depth) >= 29:
            return 'castle 29: the trap door is the pass'
        if need_afloat and not c.levitating():
            return 'not afloat'
        if c._timed_levitation() and (need_afloat or c._lev_source is None or c._lev_source[0] == 'potion'):
            return 'a timed lift (a potion): it cannot be taken off and may run out'
        if self._lasting_lift_item() is None:
            return 'no lift item to take off'
        if self.dive.digging_tool() is None and self._usable('digging') is None:
            return 'nothing to dig the secret door with'
        if agent.character.prop.polymorph:
            return 'polymorphed'
        bl = agent.blstats
        # the strength gate: a threshold left at its default (HPmax 0, AC 99) is not a condition; with both set the hero qualifies by EITHER one
        # (HP-only and AC-only heroes both beat the Valley walk, ledger: castle-hp-east +10.5 pt, castle-ac-east +17.1 pt)
        conds = []
        if jf_config.LIFT_EAST_MIN_HPMAX > 0:
            conds.append(bl.max_hitpoints >= jf_config.LIFT_EAST_MIN_HPMAX)
        if jf_config.LIFT_EAST_MAX_AC < 99:
            conds.append(bl.armor_class <= jf_config.LIFT_EAST_MAX_AC)
        if conds and not any(conds):
            return f'too weak for the court (HPmax {bl.max_hitpoints}, AC {bl.armor_class}): the trap door'
        return None

    def east_planned(self):
        """castle_logic._door_step: would the east leg run if we floated onto (55,08)? Then a lift taken off to kick the door
        goes back on before the trap door."""
        try:
            return self.east.get('no') is None and self.east.get('phase') in (None, 'walk') and \
                self._east_why_not(False) is None
        except Exception:
            return False

    def _east_wanted(self):
        """The leg is decided once, on the first look at (55,08) afloat: True while it runs (including the drop of an abort)."""
        if not jf_config.LIFT_EAST_WAND:
            return False
        e = self.east
        if e.get('no') is not None:
            return False
        if e.get('phase') is not None:
            return e['phase'] in ('walk', 'dig', 'sieve', 'enter', 'abort')
        why = self._east_why_not(True)
        if why is not None:
            e['no'] = why
            self._log(f'east leg not taken: {why}')
            return False
        e['phase'] = 'walk'
        e['t0'] = self.agent.blstats.time
        self._mile('east_start', f'hp {self._hpf():.2f} at {self._pos()}')
        return True

    def _east_phase(self, phase, why=''):
        self.east['phase'] = phase
        self.east['t_' + phase] = self.agent.blstats.time
        self._log(f'east leg: {phase} {why}'.rstrip())

    def _east_abort(self, why):
        self._mile('east_abort', why)
        self._east_phase('abort', why)
        return True

    def _east_land(self, why=''):
        """Take the lift off (the east hall's squares west of the trap doors are safe to stand on)."""
        self._set_state(f'east leg: landing ({why})')
        self.dive.castle._stop_levitating()
        return True

    def _east_lift_on(self):
        item = self._lasting_lift_item()
        if item is None or self.tries['east_lift_on'] >= 14:
            return self._east_abort('cannot put the lift on again')
        self.tries['east_lift_on'] += 1
        kind = 'ring' if item.category == nh.RING_CLASS else 'boots'
        self._set_state(f'east leg: {kind} on again before the trap door')
        self.dive.castle._try(kind, item)
        return True

    def _east_gate(self):
        """The westernmost trap door still in the east hall. A giant's thrown boulder plugs one ('The boulder plugs a trap door.': jf79-s8~s2,
        the first sieve game, at (40,08) 55 turns after the secret door opened); a plugged square shows as plain floor once we are next to
        it. The sieve only works for a hero standing east of the gate."""
        gone = self.east.setdefault('gone', set())
        agent = self.agent
        pos = self._pos()
        for sq in sorted(TRAPDOORS):
            if sq in gone:
                continue
            if max(abs(sq[0] - pos[0]), abs(sq[1] - pos[1])) <= 1:
                y, x = to_bot(*sq)
                if int(agent.glyphs[y, x]) in (SS.S_room, SS.S_darkroom):
                    gone.add(sq)
                    self._log(f'east leg: the trap door {sq} is gone (plugged)')
                    continue
            return sq
        return None

    def _east_step(self, nxt, mons, drop=False):
        """One step along the east hall. A trap door ahead needs the lift on (unless we mean to fall: drop)."""
        c = self.dive.castle
        occupant = next((m for m in mons if m.p == nxt), None)
        if occupant is not None:
            if occupant.peaceful:
                return self._search(1, f'waiting for the peaceful {occupant.name} at {nxt}')
            return self._attack(occupant, ' (blocks the east hall)')
        if self._boulder(nxt):
            # a giant's thrown boulder in the hall: a levitating hero cannot push it (hack.c moverock: 'You don't have enough leverage'), which
            # looped 330-420 times without a game turn in 5 of 52 strong seeds until 'step budget spent' -- break it (striking / pick-axe)
            return self._boulder_fix(nxt)
        if nxt in TRAPDOORS and nxt not in self.east.get('gone', ()) and not drop and not c.levitating():
            return self._east_lift_on()
        self._set_state(f'east leg: to {nxt}')
        return self._walk_to(nxt)

    def _east_dig_secret(self, pos, mons):
        """The locked secret door (38,08) from (39,08): the pick-axe / mattock (dig.c: 'You break through a secret door!', a few
        turns, silent), a wand of digging; nothing else opens a door nobody has found. None: nothing left to try."""
        agent = self.agent
        if SECRET_E in self.broken or self._is_open_door(SECRET_E):
            self.sdoor_found.add(SECRET_E)
            self.broken.add(SECRET_E)
            return None
        if jf_config.LIFT_EAST_FIGHT:
            # a monster that cannot walk through walls stands ON the secret door: it is open already (the first dig was cut short
            # by its arrival; strong seed 16 then bashed a storm giant with the pick-axe four times: 'You begin bashing monsters')
            occ = next((m for m in mons if m.p == SECRET_E and not m.ww and not m.peaceful), None)
            if occ is not None:
                self.broken.add(SECRET_E)
                self.sdoor_found.add(SECRET_E)
                self._mile('east_open', f'a {occ.name} stands in the doorway at turn {agent.blstats.time}')
                return None
        dig = self.dive.digging_tool()
        if dig is not None and self.tries['esdig'] < 10 and not self._shield_blocks(dig):
            self.tries['esdig'] += 1
            self._set_state(f'east leg: digging through the secret door {SECRET_E} from the east')
            with agent.atom_operation():
                dig = agent.inventory.move_to_inventory(dig)
                agent.step(A.Command.APPLY)
                agent.type_text(agent.inventory.items.get_letter(dig))
                if 'In what direction do you want to dig?' in agent.single_message:
                    agent.direction('w')
                elif agent.single_message.startswith('In what direction'):
                    agent.step(A.Command.ESC)
            msg = agent.message or ''
            self._log(f'east secret door dig: {msg[:120]!r}')
            if 'secret door' in msg or 'break through' in msg or (jf_config.LIFT_EAST_FIGHT and 'bashing monsters' in msg):
                self.broken.add(SECRET_E)
                self.sdoor_found.add(SECRET_E)
                self._mile('east_open', f'at turn {agent.blstats.time}')
            return True
        wand = self._usable('digging')
        if wand is not None and self.tries['esdig_wand'] < 2:
            self.tries['esdig_wand'] += 1
            self._set_state('east leg: zapping digging west at the secret door')
            agent.zap(wand, 'w')
            self.broken.add(SECRET_E)
            self.sdoor_found.add(SECRET_E)
            self._mile('east_open', f'wand at turn {agent.blstats.time}')
            return True
        return None

    def _east_leg(self, pos, mons):
        """The leg's phases: walk (float west along the hall to (39,08)) -> dig (the secret door) -> [sieve (back to (41,08), land,
        Elbereth, let the court fall through the trap door (40,08))] -> enter (to (39,08), lift off) -> done: castle_inner's own leg
        takes the hero on through the throne room. abort: down through the nearest trap door."""
        e = self.east
        c = self.dive.castle
        agent = self.agent
        now = agent.blstats.time
        lev = c.levitating()
        hpf = self._hpf()
        phase = e['phase']
        if phase != 'abort' and now - e['t0'] > 700:
            return self._east_abort('the leg ran 700 turns')
        if phase != 'abort' and jf_config.LIFT_EAST_DROP_HP and hpf < jf_config.LIFT_EAST_DROP_HP and \
                any(m.adj and not m.peaceful for m in mons):
            return self._east_abort(f'hp {hpf:.2f} with something next to us: the trap door')
        if phase != 'abort' and jf_config.LIFT_EAST_LICH_ABORT:
            lich = next((m for m in mons if m.name in ('master lich', 'arch-lich') and not m.peaceful), None)
            if lich is not None:
                return self._east_abort(f'a {lich.name} (covetous: it summons nasties, lane 31: lich castles convert 0.6%)')
        if phase == 'abort':
            if pos in TRAPDOORS:
                if lev:
                    return self._east_land('abort: down through the trap door')
                return self._search(1, 'on the trap door (the plunge fires above us)')
            target = min(TRAPDOORS, key=lambda t: abs(t[0] - pos[0]))
            return self._east_step((pos[0] + (1 if target[0] > pos[0] else -1), 8), mons, drop=True)
        if phase == 'walk':
            if pos[0] <= self.EAST_DIG[0]:
                self._east_phase('dig')
                phase = 'dig'
            else:
                rest_hp = jf_config.LIFT_EAST_REST_HP
                if rest_hp and pos == (54, 8) and hpf < rest_hp and now - e.setdefault('t_rest0', now) < jf_config.LIFT_EAST_REST_MAX:
                    if lev:
                        return self._east_land('a rest before the dig')
                    if not self._engraved() and self._can_write() and self.tries['east_rest_elb'] < 30:
                        self.tries['east_rest_elb'] += 1
                        return self._engrave('a rest before the dig')
                    return self._search(3, 'east leg: resting before the dig')
                return self._east_step((pos[0] - 1, 8), mons)
        if phase == 'dig':
            if pos[0] > self.EAST_DIG[0]:
                return self._east_step((pos[0] - 1, 8), mons)
            r = self._east_dig_secret(pos, mons)
            if r is not None:
                return r
            if SECRET_E in self.broken:
                self._east_phase('sieve' if jf_config.LIFT_EAST_SIEVE else 'enter', 'secret door open')
                phase = e['phase']
            else:
                return self._east_abort('the secret door stayed shut')
        if phase == 'sieve':
            gate = self._east_gate()
            if gate is None:
                self._east_phase('enter', 'no trap door left to filter the court')
                phase = 'enter'
            else:
                sq = (gate[0] + 1, 8)
                if pos != sq:
                    nxt = (pos[0] + (1 if pos[0] < sq[0] else -1), 8)
                    return self._east_step(nxt, mons)
        if phase == 'sieve':
            if lev:
                return self._east_land('the sieve square')
            if jf_config.LIFT_EAST_FIGHT:
                hostile = [m for m in mons if not m.peaceful and (m.dist <= 2 or (m.p[1] == 8 and 38 <= m.p[0] <= 50 and not m.unseen))]
            else:
                hostile = [m for m in mons if not m.peaceful and not m.unseen and m.dist <= 12]
            if hostile:
                e['last_hostile'] = now
            waited = now - e['t_sieve']
            quiet = now - e.get('last_hostile', e['t_sieve'])
            if (waited >= jf_config.LIFT_EAST_SIEVE_MIN and quiet >= jf_config.LIFT_EAST_SIEVE_QUIET and hpf >= 0.8) or \
                    waited >= jf_config.LIFT_EAST_SIEVE_MAX:
                self._mile('east_sieve_done', f'after {waited} turns, quiet {quiet}, hp {hpf:.2f}')
                self._east_phase('enter', f'sieve over after {waited} turns')
                phase = 'enter'
            else:
                if jf_config.LIFT_EAST_FIGHT and hpf >= jf_config.LIFT_EAST_FIGHT_HP and hostile:
                    return self._search(1, 'east leg: the sieve, hostiles near (fighting at the chokepoint)')
                if not self._engraved() and self._can_write() and self.tries['east_elbereth'] < 40:
                    self.tries['east_elbereth'] += 1
                    return self._engrave('the east hall sieve')
                return self._search(2, 'east leg: the sieve (the court falls through (40,08))')
        if phase == 'enter':
            if pos[0] > self.EAST_DIG[0]:
                return self._east_step((pos[0] - 1, 8), mons)
            if lev:
                return self._east_land('the secret door square')
            if jf_config.LIFT_EAST_FIGHT:
                # LIFT_EAST_FIGHT: hold (39,08): the doorway (38,08) is open to three squares of the room ((37,7), (37,8), (37,9): a broken door allows
                # diagonals) -- strong seeds 6, 16, 20 lost 100+ HP in 10 turns standing in it -- but at (39,08) one monster at a time can reach us
                e.setdefault('t_hold0', now)
                near = [m for m in mons if not m.peaceful and not m.unseen and (m.dist <= 3 or (m.p[1] == 8 and 36 <= m.p[0] <= 40))]
                if near:
                    e['hold_last'] = now
                quiet = now - e.get('hold_last', e['t_hold0'])
                held = now - e['t_hold0']
                if held < jf_config.LIFT_EAST_HOLD and (quiet < jf_config.LIFT_EAST_SIEVE_QUIET or hpf < 0.8):
                    if hpf < 0.8 and not near and not self._engraved() and self._can_write() and self.tries['east_hold_elb'] < 20:
                        self.tries['east_hold_elb'] += 1
                        return self._engrave('the gate hold')
                    return self._search(1, 'east leg: holding the gate (39,08)')
            self._mile('east_in', f'hp {hpf:.2f} turn {now}')
            self._east_phase('done')
            return self._goto(self._goal(), mons)
        return self._goto(self._goal(), mons)

    # ---- castle 29: the secret door and the trap doors

    def _trapdoor_step(self, mons):
        agent = self.agent
        pos = self._pos()
        self._mile('trapdoor_leg', f'from {pos}')
        if pos in EAST_HALL or pos == SECRET_E:
            if pos == TRAPDOOR:
                return self._search(1, 'on the trap door')
            return self._goto(TRAPDOOR, mons)
        if pos != BEFORE_SECRET:
            return self._goto(BEFORE_SECRET, mons)
        # at (37,08): the secret door (38,08)
        if SECRET_E in self.broken or self._door_sym(SECRET_E) in (SS.S_ndoor, SS.S_vodoor, SS.S_hodoor):
            self.sdoor_found.add(SECRET_E)
            return self._walk_to(SECRET_E)
        near = [m for m in mons if not m.peaceful and m.dist <= 4 and not m.ign]
        if near and not self._engraved() and self._can_write() and self.tries['door_elbereth'] < 6:
            self.tries['door_elbereth'] += 1
            return self._engrave('before the secret door work')
        dig = self.dive.digging_tool()
        if dig is not None and self.tries['sdig'] < 8 and not self._shield_blocks(dig):
            self.tries['sdig'] += 1
            self._set_state(f'digging through the secret door {SECRET_E}')
            with agent.atom_operation():
                dig = agent.inventory.move_to_inventory(dig)
                agent.step(A.Command.APPLY)
                agent.type_text(agent.inventory.items.get_letter(dig))
                if 'In what direction do you want to dig?' in agent.single_message:
                    agent.direction('e')
                elif agent.single_message.startswith('In what direction'):
                    agent.step(A.Command.ESC)
            msg = agent.message or ''
            self._log(f'secret door dig: {msg[:120]!r}')
            if 'secret door' in msg:
                self.broken.add(SECRET_E)
                self.sdoor_found.add(SECRET_E)
            return True
        wand = self._usable('digging')
        if wand is not None and self.tries['sdig_wand'] < 2:
            self.tries['sdig_wand'] += 1
            self._set_state('zapping digging east at the secret door')
            agent.zap(wand, 'e')
            self.broken.add(SECRET_E)
            self.sdoor_found.add(SECRET_E)
            return True
        if self.tries['ssearch'] < 40:
            self.tries['ssearch'] += 1
            return self._search(1, 'searching for the secret door (38,08)')
        self._stop('the secret door stayed shut')
        return False

    def eat_blocked(self):
        """HUNGER_DEEP (agent.eat_deep) must not start a meal now: a food ration is 5 turns and 1 in 7 is rotten
        (confusion, blindness, up to 10 turns unconscious: real walk-in #1 ate at the throne door and was blind when a
        squad arrived; 16 of 46 harness games turned Hungry inside the leg). Blocked while an @ or minotaur is in view
        within 10, in the hall or the throne room, and in the hallways with anything hostile within 5; until Weak
        (the caller lets Weak through: ~100 turns after Hungry). Our own rests eat when it is calm."""
        if self.done or not self.on_castle():
            return False
        pos = self._pos()
        if not inside(pos):
            return False
        mons = self._mons()
        if any(m.ign and not m.peaceful and not m.unseen and m.dist <= 10 for m in mons):
            return True
        if pos in HALL or pos in THRONE or pos in (DOOR_A, DOOR_B):
            return True
        if (pos in HALLWAY_N or pos in HALLWAY_S) and any(not m.peaceful and m.dist <= 5 for m in mons):
            return True
        return False

    def _eat_if_hungry(self, mons):
        """A meal during a rest (on Elbereth, nothing hostile adjacent) when Hungry."""
        from .glyph import Hunger
        agent = self.agent
        if agent.blstats.hunger_state < Hunger.HUNGRY or self.tries['rest_eat'] >= 3 or \
                any(m.adj and not m.peaceful for m in mons) or agent.character.prop.polymorph:
            return False
        keep = {'eucalyptus leaf', 'sprig of wolfsbane', 'lump of royal jelly', 'tripe ration', 'tin'}
        food = [i for i in agent.edible_carried_food() if not ({getattr(o, 'name', '') for o in i.objs} & keep)]
        food.sort(key=lambda i: -(agent.inventory.BUY_FOOD_NUTRITION.get(i.object.name, 0) if i.is_unambiguous() else 0))
        if not food:
            return False
        self.tries['rest_eat'] += 1
        self._set_state(f'eating {food[0].text!r} while resting')
        agent.inventory.eat(food[0])
        return True

    # ---- the Crusher's readiness gate

    def prep_step(self):
        """Called by the Crusher when its quiet test passes, before it walks in: True if it acted (eat when Hungry,
        wait out Blind/Confused/Stunned/Hallucinating, rest to the gate). Real walk-in #1 ate a ration at the throne
        door, it was rotten, blind, and a squad took 98 HP in 2 turns."""
        if not jf_config.CASTLE_INNER or self.tries['prep'] > 400:
            return False
        if jf_config.CASTLE_INNER_EXCAL and not self._excalibur():
            return False
        agent = self.agent
        bl = agent.blstats
        mons = self._mons()
        if any(m.ign and not m.peaceful and m.dist <= 3 for m in mons):
            return False
        self.tries['prep'] += 1
        if self._status_bad():
            return self._search(3, 'prep: waiting out a bad status')
        from .glyph import Hunger
        if bl.hunger_state >= Hunger.HUNGRY and not any(m.adj and not m.peaceful for m in mons) and \
                self.tries['prep_eat'] < 3:
            food = list(agent.edible_carried_food())
            if food:
                self.tries['prep_eat'] += 1
                self._set_state(f'prep: eating {food[0].text!r}')
                agent.inventory.eat(food[0])
                return True
        if self._hpf() < self._gate():
            return self._rest(mons)
        return False


def strategy(dive):
    inner = getattr(dive, 'inner', None)
    if inner is None:
        return Strategy(lambda: iter([False]))
    return inner.strategy()
