"""PASSTUNE_CRUSHER (castle-redteam lane, ledger F104): the castle's drawbridge as a weapon, for a kit that carries a
tonal instrument (7 of 105 true castle kits: fire horn 3, frost horn 2, tooled horn 2, wooden/magic flute 2).

NetHack 3.6.6 facts this is built on:
* music.c do_play_instrument (~690-838): any instrument but a drum asks 'Improvise?' (not while stunned, confused or
  hallucinating: then it improvises); 'n' asks 'What tune are you playing? [5 notes, A-G]'. On the castle level, with
  the drawbridge span (05,08) or its portcullis (06,08) inside our 3x3, a wrong tune gives Mastermind feedback
  ('You hear N tumblers click and M gears turn.'; nothing at all for 0 and 0) and the right one opens or closes the
  bridge and makes the tune known ('Play the passtune?' from then on). passtune.py solves it: ~5.2 plays, max 7.
* dbridge.c do_entity (560-760): CLOSING the bridge kills every non-flyer that isn't a wall-walker or a ghost on the
  span (jumps 4 in 10 and drowns in the raised span's water, else rides it in to the portcullis and is crushed) and on
  the portcullis (2 in 10 jump onto the span and drown, else crushed). OPENING it crushes whatever swims under the
  span. Flyers dodge 5/8 on the span, 2/8 on the portcullis. The kills are ours (e_died -> xkilled: XP).
* The crusher square (04,07) (or (04,09)) is diagonal to the span and in the tune's 3x3, but in line with no square
  of the antechamber ((06,07)/(06,09) are wall), so nothing inside can throw or zap at us; the only castle-side square
  next to us is the span. Elbereth there holds the eels, sharks and the whole court; the @ soldiers ignore it but
  must stand on the span to reach us, and at speed 10 vs our 12-16 we close the bridge before their blow.
* makemon.c ~1318: the drawbridge eels are generated asleep 4 times in 5, and a stealthy Valkyrie never disturbs them.
  Soldiers and court are awake (no M3_WAITFORU) and walk toward us, one at a time through the portcullis.
* Then in along row 08 (castle_front.FrontDoor's FRONT_V3 walk-in, lures back to the crusher when 2+ come): at a
  castle on Dlvl 29 through the throne room to the locked secret door (38,08) and the trap door (40,08) -- the
  Valley, Dlvl 30; at any other depth to a corner tower's chest for the wand of wishing, named by one zap so that
  WISH_TELEPORT_ROUTE (tele_route) spends its wishes (as CASTLE_TREASURY hands it over).

Milestones: 'CRUSH M:<name>' (start, square, tune, open, crush, crush_over, throne, secret, trapdoor, tower, chest,
wand, stop) and 'CRUSH kill ...' lines, for the harness measurement.
"""

import re

import nle.nethack as nh
from nle.nethack import actions as A

from . import jf_config
from . import passtune
from .castle_front import FrontDoor, SPAN, PORTCULLIS, THRONE_ROOM, THRONE_ENTRY, HALL_HOLD, SOLDIER_NAMES
from .castle_logic import to_bot, to_map, map_char
from .glyph import G, MON, SS, Hunger
from .item import Item
from .strategy import Strategy

TONAL = frozenset({'tooled horn', 'frost horn', 'fire horn', 'wooden flute', 'magic flute', 'wooden harp',
                   'magic harp', 'bugle'})
CRUSH_SQUARES = ((4, 7), (4, 9))
# the pull spell's square: on row 08 the court's greedy steps (monmove.c m_move toward us) run straight west through
# the throne-room door (26,08) and the hallway onto the span; from (04,07) they jam against the throne room's west wall
# and meet us there on the way in (rt-a1b: 9 of 16 deaths in or at the throne room). It is in line with row 08, so it
# comes after the antechamber's soldiers (spears, wands) are crushed.
PULL_SQUARE = (4, 8)
LOCK_SQUARE = (7, 8)   # first square inside: the portcullis (06,08) is in our 3x3 for the tune
SECRET_DOOR = (38, 8)
BEFORE_SECRET = (37, 8)
AFTER_SECRET = (39, 8)
TRAPDOOR = (40, 8)
M1_FLY, M1_WALLWALK = 0x1, 0x8
REST_HP_WALK = 0.45   # rest on Elbereth on the way in below this share of HP (to FrontDoor's RESUME_HP 0.75)
# PASSTUNE_SWEEP: the throne room's first square. From (26,08) the awake barracks army only oscillates in its doorway
# (26,05)/(26,11) (m_move takes the first candidate even when it is farther: (27,y) is farther from a hero at x=26 than
# the door square); from x >= 27 the squares inside the room are the nearer ones and it pours out.
SWEEP_BAIT = (27, 8)
DOOR_U = {'N': (32, 5), 'S': (32, 11)}     # PASSTUNE_DOORS: the throne room square under each locked door to the tower hallways
DOOR_SQ = {'N': (32, 4), 'S': (32, 12)}
CONF_SOURCES = ('confusion', 'booze')   # PASSTUNE_TAME_CONF: the potions that confuse (potion.c: confusion 16-22 turns, booze 3d8)
TAME_BOX = 5            # read.c SCR_TAMING: bd = confused ? 5 : 1 -- every monster within this Chebyshev distance, walls or not
FOUNTAIN = (10, 8)     # the antechamber's fountain, on row 08: 'You can't write on the fountain!' (engrave.c) -- no Elbereth there (F326)

_OPEN_RE = re.compile(r'drawbridge (?:coming|going) down|gears turning and chains rattling')
_CLOSE_RE = re.compile(r'drawbridge (?:coming|going) up|chains rattling and gears turning')
_GONE_RE = re.compile(r'drawbridge disintegrates|portcullis of the drawbridge falls|drawbridge collapses')
_DEATH_RE = re.compile(r'crushed underneath the drawbridge|crushed by the falling portcullis|a crushing sound|'
                       r'falls? into the moat\.|disappears? behind the drawbridge')
_KILL_RE = re.compile(r'You (?:kill|destroy) (?:the |an? )?([^!]+)!')


_FALL_RE = re.compile(r'You fall into the water|You sink like a rock|You try to crawl out of the water')


def note_message(agent):
    """CRUSH_BRIDGE_GONE (agent.update, every observation): remember the turn of a message that says the drawbridge is destroyed --
    a monster's wand of striking along the bridge (dbridge.c destroy_drawbridge, muse.c mbhit), not only the Crusher's own toggles.
    CRUSH_WATER_GUARD: the turn of a fall into the water."""
    try:
        msg = agent.single_message or ''
        if jf_config.CRUSH_BRIDGE_GONE and _GONE_RE.search(msg):
            agent._bridge_gone_turn = int(agent._observation['blstats'][nh.NLE_BL_TIME])
        if jf_config.CRUSH_WATER_GUARD and _FALL_RE.search(msg):
            agent._water_fall_turn = int(agent._observation['blstats'][nh.NLE_BL_TIME])
    except Exception:
        pass


class Crusher(FrontDoor):
    ALWAYS_V3 = True

    def __init__(self, dive):
        super().__init__(dive)
        self.solver = passtune.Solver()
        self.tune = None              # the passtune, once a play opened the bridge
        self.bridge_open = False      # our belief (messages first, the map as a fallback)
        self.destroyed = False
        self.plays = 0                # Mastermind plays
        self.first_play_turn = None
        self.toggles = 0
        self.crush_kills = 0          # death messages seen on our toggles
        self.killed = []              # names from 'You kill/destroy ...' on our toggles
        self.crush_over = False       # the crusher phase is done: walk in (a lure brings it back)
        self.busy_turn = None         # last game turn something stood on the bridge or died on it
        self.entry_turn = None        # game turn this spell at the crusher began (a lure starts a new one)
        self.crush_steps = 0
        self.not_tonal = set()        # instrument glyphs that turned out not to play tunes (a horn of plenty)
        self.silent = 0               # plays in a row with no feedback line
        self.secret_found = False
        self.pulling = False          # the pull spell: crushing from (04,08), on row 08 (PASSTUNE_PULL)
        self.pulls = 0
        self.locked_out = False       # PASSTUNE_LOCKOUT: the bridge closed behind us from inside (07,08)
        self.garrison_known_dead = False   # dev replays (jf_scenario crusher_state): the recording's crusher had crushed the garrison
        self.sweep_returns = 0        # runs back with a train (or a scare) behind us
        self.sweeps = 0               # PASSTUNE_SWEEP: trains started (a walk to the throne room door and back)
        self.sweep_state = None       # None | 'out' | 'bait' | 'lock'
        self.sweep_steps = 0
        self.bait_turn = None
        self.retreat_run = False      # running back to the crusher square: no stopping to fight what trails us
        self.sweep_dist = []          # nearest castle-side hostile at the last steps of the bait wait
        self.sweep_seen = []          # (name, map square) of the hostiles in view at the last look
        self.door_done = set()        # PASSTUNE_DOORS: doors ('N', 'S') whose train is over
        self.door = None
        self.dwait_turn = None
        self.fountain_steps = 0       # PASSTUNE_FOUNTAIN_STEP: consecutive guard checks on the fountain square
        self.trick_state = None       # PASSTUNE_TRICK: None | 'go' | 'wait' (cross the bridge, let a west-bank pest follow)
        self.tricks = 0
        self.trick_turn = None
        self.tame_state = None        # PASSTUNE_TAME_CONF: None | 'quaff' | 'read' | 'done'
        self.pet_waits = 0            # PASSTUNE_PET_GUARD: turns spent waiting for a pet to leave the bridge (this episode)
        self.pet_probed = False       # ...a search turn already spent to reveal a pet hiding under the raised span
        self.pet_gave_up = False      # ...the wait ran out with the bridge still blocked
        self.pet_waited_total = 0
        self.horn_turn = None         # PASSTUNE_HORN_XORN: game turn of the last blow
        self.horn_blows = 0
        self.horn_pre = False         # ...the one blow before the walk-in
        self.tame_tries = 0
        self._cut_play = None         # CRUSH_PLAY_SAFE: (guess or None, result) of a play whose booking a preempting strategy cut short
        self.budget_go = False        # CRUSH_BUDGET_GO: the step budget ended the crush phase (walk in for good)
        self.water_falls = 0          # CRUSH_WATER_GUARD: falls into the water that reset the bridge belief

    # ------------------------------------------------------------------ helpers

    def _log(self, msg):
        self.agent.log(f'CRUSH {msg}')

    def _instrument(self):
        """A tonal instrument (known or not): every type it may be plays tunes, or at least one does and it hasn't
        shown itself a horn of plenty (an unknown 'horn' may be one: apply.c hornoplenty asks no 'Improvise?')."""
        best = None
        sure = None
        for it in self.agent.inventory.items:
            if it.category != nh.TOOL_CLASS:
                continue
            names = {getattr(o, 'name', '') for o in it.objs}
            if not names & TONAL:
                continue
            g = it.glyphs[0] if it.glyphs else None
            if g in self.not_tonal:
                continue
            exact = None
            if jf_config.INSTRUMENT_GLYPH or jf_config.INSTRUMENT_PREFER:
                # the item's own glyph names the exact tool: a horn of plenty is none, a 'horn' whose glyph says tooled horn is sure
                from . import instruments
                exact = instruments.glyph_name(g)
                if exact is not None and exact not in TONAL:
                    continue
            if names <= TONAL or exact is not None:
                if not jf_config.INSTRUMENT_PREFER:
                    return it
                # INSTRUMENT_PREFER (instruments lane): play the best type -- tooled horn 5.9% of kits pass, flute 2.8%, harp 1.7%
                if sure is None or instruments.item_rank(it) < instruments.item_rank(sure):
                    sure = it
                continue
            best = best or it
        return sure if sure is not None else best

    def _depth(self):
        return int(self.agent.blstats.depth)

    def _open(self):
        """Is the bridge down? Once we play it, our own belief (the toggles' messages) is the truth: the map's memory
        of the span keeps a lowered bridge after we close it from out of sight (rt-a1c s2: 'That drawbridge is up!'
        turn-inactivity loops walking onto it)."""
        if self._cut_play is not None:
            self._book_cut_play()   # CRUSH_PLAY_SAFE
        if 'That drawbridge is up' in (self.agent.message or ''):
            self.bridge_open = False
        if jf_config.CRUSH_WATER_GUARD and self.bridge_open and getattr(self.agent, '_water_fall_turn', None) is not None:
            # CRUSH_WATER_GUARD: a fall into the water at the span proves the bridge is not down, whatever our record says
            ft = self.agent._water_fall_turn
            self.agent._water_fall_turn = None
            p = self._pos()
            if p[0] <= 6 and 5 <= p[1] <= 11:
                self.bridge_open = False
                self.water_falls += 1
                self._log(f'fell into the water at turn {ft} next to the span: the bridge is not down (belief reset, fall {self.water_falls})')
        if self.tune is not None or self.toggles:
            return self.bridge_open
        return self._sym(PORTCULLIS) == SS.S_ndoor or self._sym(SPAN) in (SS.S_vodbridge, SS.S_hodbridge)

    def _span_dry(self):
        return self._open()

    def _note(self, msg):
        """Bridge state and our kills from a toggle's messages."""
        if _GONE_RE.search(msg):
            self.destroyed = True
        if _OPEN_RE.search(msg):
            self.bridge_open = True
        elif _CLOSE_RE.search(msg):
            self.bridge_open = False
        deaths = len(_DEATH_RE.findall(msg))
        names = _KILL_RE.findall(msg)
        n = max(deaths, len(names))
        if n:
            self.busy_turn = self.agent.blstats.time
            self.crush_kills += n
            self.killed += names
            self._log(f'kill {n} (total {self.crush_kills}) {names} turn {self.agent.blstats.time}: {msg[:200]!r}')

    def _cant_play(self):
        p = self.agent.character.prop
        return p.hallu or p.confusion or p.stun

    def _crush_square(self):
        if self.pulling and not self._monster_at(PULL_SQUARE) and not self._boulder(PULL_SQUARE):
            return PULL_SQUARE
        for sq in CRUSH_SQUARES:
            if self._pos() == sq:
                return sq
        for sq in CRUSH_SQUARES:
            if not self._monster_at(sq) and not self._boulder(sq):
                return sq
        return CRUSH_SQUARES[0]

    @staticmethod
    def _crushable(mon):
        """Dies when the bridge closes on it: not a wall-walker or a ghost (automiss); a flyer dodges 5/8 (span) or
        2/8 (portcullis) and is still worth a toggle."""
        if mon is None:
            return True
        flags = getattr(mon, 'mflags1', 0)
        mlet = getattr(mon, 'mlet', '')
        cls = ord(mlet) if isinstance(mlet, str) and len(mlet) == 1 else -1   # (the class number as a character)
        return not (flags & M1_WALLWALK) and cls != MON.S_GHOST

    def _bridge_targets(self):
        """Hostile monsters on the span or the portcullis (read from the glyphs: get_visible_monsters drops monsters
        whose neighbourhood the BFS can't reach)."""
        agent = self.agent
        peaceful = agent.monster_tracker.peaceful_monster_mask
        out = []
        for p in (SPAN, PORTCULLIS):
            y, x = to_bot(*p)
            g = int(agent.glyphs[y, x])
            if nh.glyph_is_pet(g) or peaceful[y, x]:
                continue
            if nh.glyph_is_monster(g):
                mon = MON.permonst(g)
                if self._crushable(mon):
                    out.append((p, getattr(mon, 'mname', '?')))
            elif g == nh.GLYPH_INVISIBLE and p == SPAN:
                out.append((p, 'unseen'))
        return out

    # ------------------------------------------------------------------ eligibility

    def active(self):
        if not jf_config.PASSTUNE_CRUSHER or self.done or self.destroyed or not self.on_castle():
            return False
        agent = self.agent
        if jf_config.CRUSH_BRIDGE_GONE and getattr(agent, '_bridge_gone_turn', None) is not None and self._pos()[0] <= 5:
            # the bridge was destroyed by something that is not ours to play (62 of the 67 'passtune no longer moves the bridge'
            # stops) while we are still on the west bank; a hero already inside keeps its walk-in / wand leg
            self.destroyed = True
            self._log(f'the drawbridge is gone (message at turn {agent._bridge_gone_turn}): no more toggles')
            self._stop('the drawbridge was destroyed')
            return False
        if agent.character.prop.polymorph:
            return False
        c = self.dive.castle
        if c.levitating() or c.water_walking():
            return False   # a lift is working: the crossing's
        if self._instrument() is None:
            return False
        pos = self._pos()
        if pos[0] >= 57 and self.phase != 'wand':
            return False   # east side: the back door is the castle logic's
        if self.tune is None and pos[0] < 0:
            # still in the west maze: approach_step walks us out at the dive plan's level -- holding control here kept
            # fight2, the Elbereth rests and the retreats out of the maze walk (rt-b2-on: 42 of 105 kits dead within 30
            # turns vs 29 with the crusher off, most while 'approaching the courtyard')
            return False
        return True

    def approach_step(self):
        """Dive plan hook (below the safety layers): out of the west maze to the courtyard for the crusher. True if it
        acted."""
        if not jf_config.PASSTUNE_CRUSHER or self.done or self.destroyed or self.tune is not None or \
                not self.on_castle():
            return False
        agent = self.agent
        if agent.character.prop.polymorph or self._instrument() is None:
            return False
        c = self.dive.castle
        if c.levitating() or c.water_walking() or self._pos()[0] >= 0:
            return False
        self.tries['approach'] += 1
        if self.tries['approach'] > 600:
            self._stop('the courtyard stays out of reach')
            return False
        if not self.logged:
            inst = self._instrument()
            self._mile('start', f'depth {self._depth()} instrument {inst.text if inst else None!r} (maze approach)')
        self._set_state('approaching the courtyard from the west maze')
        before = agent.step_count
        c._approach(c._tspot(), route=True)
        return agent.step_count != before

    def strategy(self):
        def f():
            if not self.active():
                yield False
            yield True
            steps = 0
            while self.active() and steps < 300:
                before = self.agent.step_count
                if not self._step():
                    break
                steps += 1
                if self.agent.step_count == before:
                    self.agent.search()

        return Strategy(f)

    # ------------------------------------------------------------------ the plan

    def _step_v3(self):
        agent = self.agent
        pos = self._pos()
        if self._cut_play is not None:
            self._book_cut_play()   # CRUSH_PLAY_SAFE: before anything reads the bridge belief (the wait loops never call _toggle)
        if not self.logged:
            inst = self._instrument()
            inv = '; '.join(i.text for i in self.dive.castle._items())
            self._mile('start', f'depth {self._depth()} instrument {inst.text if inst else None!r} inv: {inv}')
        if self._held() and self._held_escape():
            return True
        if self._fountain_guard():
            return True
        if self.tame_state == 'read' and self._tame_conf_step():
            return True   # (the read follows the quaff at once: the crush phase would wait the confusion out)
        if self._tame_mino_due() and self._tame_conf_step('mino'):
            return True
        if self._xorn_horn():
            return True
        if self.trick_state:
            return self._trick_step()
        if self.sweep_state == 'return':
            return self._sweep_step()
        if self.phase is None and not self.crush_over:
            return self._crush_phase()
        if not self._open() and not self.locked_out:
            # walking in needs the bridge down: back to a crusher square and play the tune
            self.crush_over = False
            self.sweep_state = None
            return self._crush_phase()
        self._mile('path', 'bridge down, walking in')
        if agent.wield_best_melee_weapon():
            return True
        if self.crush_over and not self.sweep_state and not self.sweeps and not self.locked_out and self._sweep_due():
            self._sweep_begin('from a replayed crush_over state')
        if self.sweep_state:
            return self._sweep_step()
        if self._inner_takes_over() and self.inner_owns():
            return self.dive.inner.step()   # castle-inner (lane 2): everything from the hand-off on
        if self.phase == 'wand':
            return self._wand_step()
        if self.phase == 'trapdoor':
            return self._trapdoor_step()
        if pos in THRONE_ROOM:
            self._mile('throne')
            self.phase = 'trapdoor' if (self._depth() >= 29 and jf_config.PASSTUNE_C29_TRAPDOOR) else 'wand'
            self._log(f'in the throne room at depth {self._depth()}: {self.phase}')
            return self._trapdoor_step() if self.phase == 'trapdoor' else self._wand_step()
        # no hallway hold (FRONT_V3's (25,08) hold met the barracks' captains: rt-a1 5 of 16 deaths): straight in
        return self._advance(THRONE_ENTRY, None)

    def _hold_v3(self):
        """Every hold is the crusher square: FrontDoor's lures and retreats come back here, and what follows us over
        the span is crushed. After the lock-out there is no way back: hold where we are (fight an @/minotaur next to
        us, else Elbereth and rest)."""
        if self.locked_out:
            near = self._near()
            if near:
                if self._scare_walkin(near):
                    return True
                return self._attack(self._pick_target(near))
            if not self._engraved() and self._can_write():
                self._set_state('Elbereth: holding inside')
                self.agent.engrave('Elbereth')
                return True
            self._set_state('holding inside on Elbereth')
            self.agent.search(3)
            return True
        self.hold_i = 0
        if self.crush_over:
            # a lure or a retreat: a new spell at the crusher for what follows us
            self.entry_turn = self.busy_turn = self.agent.blstats.time
            self.phase = None
        self.crush_over = False
        self.hold_over = False
        return self._crush_phase()

    # ---- the walk in (weak kits): only Elbereth-ignorers are fought

    def _near(self):
        """The attackers FrontDoor's fight decisions see: only monsters that ignore Elbereth (@, minotaurs) -- a weak
        hero loses to the court's xorns and earth elementals (not crushable: they pass the portcullis), so those are
        walked past, or waited out on Elbereth when they block the way (_attack_at)."""
        return [m for m in super()._near() if self.dive._melee_ignores_elbereth(m[3])]

    def _attack_at(self, p):
        """A monster on our path at p: one that respects Elbereth is waited out on Elbereth (scared, it flees and
        clears the way); only after that fails, or for an @/minotaur, the blow."""
        y, x = to_bot(*p)
        g = int(self.agent.glyphs[y, x])
        mon = MON.permonst(g) if nh.glyph_is_monster(g) else None
        if mon is not None and not nh.glyph_is_pet(g) and not self.dive._melee_ignores_elbereth(mon) and \
                self.tries[('block', p)] < 10 and \
                not (jf_config.CRUSH_WIPE_COMMIT and self._commit_active() and self._commit_worthy(mon)):
            self.tries[('block', p)] += 1
            if not self._engraved() and self._can_write():
                self._set_state(f'Elbereth: {getattr(mon, "mname", "?")} blocks {p}')
                self.agent.engrave('Elbereth')
            else:
                self._set_state(f'waiting on Elbereth for {getattr(mon, "mname", "?")} to leave {p}')
                self.agent.search()
            return True
        return super()._attack_at(p)

    def _advance(self, target, next_hold):
        """In along row 08 to target. 2+ crushable Elbereth-ignorers in view west of the throne room: back to the
        crusher (they follow us onto the span). Hurt with no ignorer near: Elbereth and rest. An ignorer next to us
        is fought; everything else is walked past."""
        agent = self.agent
        pos = self._pos()
        bl = agent.blstats
        near = self._near()
        if near and self._read_taming(near):
            return True
        if pos[0] <= 26 and self._lure(8, 2):
            return True
        if jf_config.PASSTUNE_PET_GUARD and jf_config.PASSTUNE_LOCKOUT and not self.locked_out and pos == LOCK_SQUARE and \
                self._open() and not self._cant_play() and self.tries['lockout'] < 4:
            if self.tame_state != 'done' and self._pet_wait(True):
                return True
            if self.pet_gave_up or self.tame_state == 'done':
                # a pet stands in the doorway, or we tamed the neighbourhood (its tame monsters follow us in and a close crushes
                # them: 4 of 29 remaining pet kills): leave the bridge open behind us rather than crush a pet
                self.tries['lockout'] = 99
                self._log('lock-out skipped: a pet or a peaceful stays on the bridge, or the neighbourhood is tame')
        if jf_config.PASSTUNE_LOCKOUT and not self.locked_out and pos == LOCK_SQUARE and self._open() and \
                not self._cant_play() and self.tries['lockout'] < 4:
            # inside, the portcullis in our 3x3: close the bridge behind us -- the maze's minotaur, the courtyard's
            # wanderers and the moat's eels stay on the other side (rt-a2c: 4 of 18 deaths a minotaur from the west on
            # the way in, 2 eels at the span); whatever stands on the span or the portcullis now is crushed
            self.tries['lockout'] += 1
            self._toggle('lock-out: closing the bridge behind us')
            if not self.bridge_open:
                self.locked_out = True
                self._mile('lockout')
            return True
        if self._contact():
            return True
        self._update_resting(REST_HP_WALK)
        if self.resting:
            if near:
                if pos[0] <= 26 and self.retreats < 6 and not self.locked_out:
                    self._retreat(near)
                    return self._hold_v3()
                return self._attack(self._pick_target(near))
            if not self._engraved() and self._can_write():
                self._set_state('Elbereth to rest on the way in')
                agent.engrave('Elbereth')
                return True
            self._set_state('resting on Elbereth on the way in')
            agent.search(3)
            return True
        if near:
            return self._attack(self._pick_target(near))
        if pos[1] == 8 and PORTCULLIS[0] <= pos[0] < target[0] and target[1] == 8:
            return self._walk_dir('e', f'along row 08 to {target}')
        if pos[0] <= 14:
            return self._go((max(pos[0], PORTCULLIS[0]), 8), f'back to row 08 on the way to {target}')
        return self._go(target, f'on to {target}')

    def _lure(self, radius, count):
        """count+ crushable hostiles (anything the bridge kills: every class but wall-walkers and ghosts) within
        radius -> back to the crusher: they follow us over the span."""
        if self.lures >= jf_config.PASSTUNE_LURES or self.locked_out:
            return False
        bl = self.agent.blstats
        # only what is inside the castle (map x >= 6) has to come over the span to reach the crusher square; the
        # courtyard's own monsters (x <= 4) never do
        crowd = [m for m in self._land_hostiles() if max(abs(m[1] - bl.y), abs(m[2] - bl.x)) <= radius and
                 self._crushable(m[3]) and to_map(m[1], m[2])[0] >= 6]
        if jf_config.CRUSH_LURE_MOBILE:
            # CRUSH_LURE_MOBILE: a monster that never moves (spotted / blue jelly, molds, lichens: mmove 0) cannot follow us over the
            # span, so it is no crowd to lure (the sweep's _train_worthy knows it)
            crowd = [m for m in crowd if getattr(m[3], 'mmove', 12) > 0 and getattr(m[3], 'mname', '') != 'lizard']
        ign = [m for m in crowd if self.dive._melee_ignores_elbereth(m[3])]
        if len(crowd) >= count or (ign and self._hp_frac() < 0.6):
            self.lures += 1
            self._log(f'lure {self.lures} at {self._pos()}: {[getattr(m[3], "mname", "?") for m in crowd]} -> the crusher')
            self._hold_v3()
            return True
        return False

    def _contact(self):
        """An Elbereth-respecting monster next to us that just hurt us (the court's xorns: 3 claws and a 4d6 bite,
        not crushable, following through the walls): Elbereth, then wait until it has fled."""
        agent = self.agent
        if self.tries['contact'] >= 150:
            return False
        resp = [m for m in super()._near() if not self.dive._melee_ignores_elbereth(m[3])]
        if not resp or not agent._hurt_recently(2):
            return False
        if jf_config.CRUSH_WIPE_COMMIT and self._commit_active() and all(self._commit_worthy(m[3]) for m in resp):
            return False   # (a fight we started by wiping the engraving goes on: the livelock wipe / hurt / Elbereth / wipe ...)
        self.tries['contact'] += 1
        if not self._engraved() and self._can_write():
            self._set_state(f'Elbereth: {[getattr(m[3], "mname", "?") for m in resp]} hurt us')
            agent.engrave('Elbereth')
            return True
        self._set_state(f'on Elbereth until {[getattr(m[3], "mname", "?") for m in resp]} flee')
        agent.search()
        return True

    def _rest_inside(self):
        if self._contact():
            return True
        return super()._rest_inside()

    def _scare_walkin(self, near):
        """PASSTUNE_SCARE_WALKIN: in the throne room (pos[0] >= THRONE_ENTRY[0]) -- past the lock-out, where there is
        no way back to the crusher square -- a known scroll of scare monster is dropped before fighting an
        Elbereth-ignorer (@ or minotaur): onscary (monmove.c) checks a scroll on our square BEFORE the human/
        minotaur exclusions (F104), so it keeps a soldier or sergeant off us the same way Elbereth keeps the rest of
        the court off. Gated to the throne room to save whatever we carry (usually 0 or 1) for the one spot with no
        other defence: R217's cand-k full games -- both real walk-ins (castle 25, full HP) died to an @ 9 and 42
        turns after entering, to the blow alone. _drop_scare's own budget (4 tries, really capped by how many we
        carry) is shared with the crusher square's own use of it."""
        if not jf_config.PASSTUNE_SCARE_WALKIN or not near or self._on_scare() or \
                self._pos()[0] < THRONE_ENTRY[0]:
            return False
        return self._drop_scare()

    def _wand_defend(self, near):
        return self._scare_walkin(near)

    def _zap_door(self, d):
        """A locked door on the way: an unlocking tool (no kick: a kick wipes our Elbereth), then a digging beam
        (zap.c zap_dig razes it), then striking (FrontDoor)."""
        agent = self.agent
        pos = self._pos()
        tool = next((i for i in agent.inventory.items if i.is_unambiguous() and
                     i.object.name in ('skeleton key', 'lock pick', 'credit card')), None)
        if tool is not None and self.tries[('unlock', pos, d)] < 8:
            self.tries[('unlock', pos, d)] += 1
            self._set_state(f'unlocking the door {d} with {tool.text!r}')
            with agent.atom_operation():
                agent.step(A.Command.APPLY)
                agent.type_text(agent.inventory.items.get_letter(tool))
                if 'direction' in agent.single_message:
                    agent.direction(d)
            self._log(f'unlock {d}: {agent.message[:120]!r}')
            return True
        dig = self._usable('digging')
        if dig is not None and self.tries[('door_dig', pos, d)] < 2:
            self.tries[('door_dig', pos, d)] += 1
            self._set_state(f'zapping digging {d} at a locked door')
            agent.zap(dig, d)
            self._log(f'door dig {d}: {agent.message[:120]!r}')
            return True
        return super()._zap_door(d)

    def _go(self, p, why):
        """Out of the west maze first: castle_logic's approach explores it or digs east (CASTLE_WEST_DIG) to the
        courtyard -- FrontDoor's own path only knows the squares seen so far, and gave up after 20 tries (rt-b-on:
        14 of 105 real kits stopped '(4, 7) unreachable' in the dark maze)."""
        pos = self._pos()
        if pos[0] < 0 <= p[0] and self._path(pos, p) is None:
            self.tries['approach'] += 1
            if self.tries['approach'] > 400:
                self._stop('the courtyard stays out of reach')
                return False
            self._set_state(f'approaching the courtyard {why}')
            c = self.dive.castle
            return bool(c._approach(c._tspot(), route=True))
        return super()._go(p, why)

    def _walk_dir(self, d, why):
        """FrontDoor's walk, with a boulder in the way dug through (pick-axe) or fractured (striking) instead of the
        stop (rt-a1 s1: a giant's boulder in the doorway (26,08), 'You hear a monster behind the boulder')."""
        pos = self._pos()
        dx, dy = {'n': (0, -1), 's': (0, 1), 'e': (1, 0), 'w': (-1, 0)}[d]
        nxt = (pos[0] + dx, pos[1] + dy)
        if self._boulder(nxt) and self.tries[('boulder_push', nxt)] >= 2:
            self.tries[('boulder_fix', nxt)] += 1
            if self.tries[('boulder_fix', nxt)] <= 6:
                wand = self._usable('striking')
                if wand is not None and self.tries[('boulder_zap', nxt)] < 2:
                    self.tries[('boulder_zap', nxt)] += 1
                    self._set_state(f'zapping striking {d} at the boulder {nxt}')
                    self.agent.zap(wand, d)
                    return True
                if self.dive.castle._smash_boulder():
                    return True
        if self._boulder(nxt):
            self.tries[('boulder_push', nxt)] += 1
        return super()._walk_dir(d, why)

    # ---- PASSTUNE_HORN_XORN: a scaring horn/drum blown at the xorns (they pass the bridge, the Elbereth holds only while we stand)

    def _scare_item(self):
        """An instrument that scares when improvised (tooled horn, a drum, an unknown horn): opp_items.instrument_kind."""
        from . import opp_items
        for it in self.agent.inventory.items:
            if opp_items.instrument_kind(self.agent, it) in ('scare', 'horn'):
                return it
        return None

    def _blow(self, horn, why):
        from . import opp_items
        now = int(self.agent.blstats.time)
        self.horn_turn = now
        self.horn_blows += 1
        self._set_state(f'blowing {horn.text!r}: {why}')
        res = opp_items.play(self.agent, horn, 'e')
        self._log(f'horn {self.horn_blows}: {why}: {(res["msg"] or "")[:100]!r}')
        self._mile('horn', f'{why}')
        return True

    def _xorn_horn(self):
        """PASSTUNE_HORN_XORN: a xorn in view within PASSTUNE_HORN_RANGE squares (and inside the instrument's scare radius):
        blow. Every monster inside distu < XL*10 that fails resist() (xorn MR 20: 4 in 5) flees untimed (music.c
        awaken_monsters), about 25 of its moves, and a fleeing monster that can move away does not attack."""
        press = jf_config.PASSTUNE_HORN_PRESS
        if not (jf_config.PASSTUNE_HORN_XORN or press) or self.horn_blows >= jf_config.PASSTUNE_HORN_MAX:
            return False
        agent = self.agent
        bl = agent.blstats
        now = int(bl.time)
        if self.horn_turn is not None and now - self.horn_turn < jf_config.PASSTUNE_HORN_GAP:
            return False
        near = []
        if jf_config.PASSTUNE_HORN_XORN and self._pos()[0] >= 5:   # (on the west bank the Elbereth holds them and a blast would scare the garrison off the span)
            for m in agent.get_visible_monsters():
                if getattr(m[3], 'mname', '') != 'xorn' or nh.glyph_is_pet(int(m[4])):
                    continue
                d = max(abs(int(m[1]) - int(bl.y)), abs(int(m[2]) - int(bl.x)))
                if d <= jf_config.PASSTUNE_HORN_RANGE:
                    near.append(d)
        crowd = 0
        if press and not near and self._pos()[0] >= LOCK_SQUARE[0]:
            # PASSTUNE_HORN_PRESS: inside the castle, 2+ hostiles within 4 squares: everything within the scare radius that fails
            # resist() (soldiers MR 0, sergeants 5, trolls/ogres/giants 0-10; liches and elementals resist) flees untimed
            crowd = sum(1 for m in self._land_hostiles()
                        if max(abs(int(m[1]) - int(bl.y)), abs(int(m[2]) - int(bl.x))) <= 4)
        if not near and crowd < 2:
            return False
        horn = self._scare_item()
        if horn is None:
            return False
        return self._blow(horn, f'{len(near)} xorn(s) in view, nearest {min(near)}' if near else f'{crowd} hostiles within 4')

    def _horn_before_walkin(self):
        """PASSTUNE_HORN_XORN: once, at the quiet decision on the Elbereth: the xorns hovering in the antechamber and its walls
        (1.6 inside the crusher square's box at crush_over) are scared away for the first stretch of the walk-in."""
        if not jf_config.PASSTUNE_HORN_XORN or self.horn_pre or self._cant_play():
            return False
        self.horn_pre = True
        horn = self._scare_item()
        if horn is None:
            return False
        return self._blow(horn, 'before the walk-in')

    # ---- PASSTUNE_TAME_CONF: a confused scroll of taming (an 11x11 area) when the crusher decides to walk in

    def _known_potion(self, names):
        for it in self.agent.inventory.items:
            if it.category == nh.POTION_CLASS and it.is_unambiguous() and it.object.name in names and \
                    it.status != Item.CURSED and 'unpaid' not in (it.text or ''):
                return it
        return None

    def _tame_conf_items(self):
        """(scroll of taming, confusion potion) -- both KNOWN, the scroll not known cursed -- or None."""
        scroll = self._known_scroll('taming')
        if scroll is None or scroll.status == Item.CURSED or 'unpaid' in (scroll.text or ''):
            return None
        potion = self._known_potion(CONF_SOURCES)
        if potion is None:
            return None
        return scroll, potion

    def _tame_box(self):
        """Names of the visible monsters inside the scroll's box around us, for the log."""
        bl = self.agent.blstats
        out = []
        for m in self.agent.get_visible_monsters():
            if max(abs(int(m[1]) - int(bl.y)), abs(int(m[2]) - int(bl.x))) <= TAME_BOX:
                out.append(getattr(m[3], 'mname', '?'))
        return out

    def _tame_mino_due(self):
        """PASSTUNE_TAME_MINO: a hostile minotaur (MR 0: the scroll always tames it; Elbereth does not stop it and it takes ~45 HP
        a turn: 84 of 448 base games died to one before crush_over) in view within 7 squares, no go yet."""
        if not jf_config.PASSTUNE_TAME_MINO or self.tame_state is not None:
            return False
        bl = self.agent.blstats
        for m in self.agent.get_visible_monsters():
            if getattr(m[3], 'mname', '') == 'minotaur' and not nh.glyph_is_pet(int(m[4])):
                if max(abs(int(m[1]) - int(bl.y)), abs(int(m[2]) - int(bl.x))) <= 7:
                    return True
        return False

    def _tame_conf_step(self, trigger='decision'):
        """Quaff the confusion potion, read the scroll next turn (confused: every monster within 5 that fails resist() is
        tamed, humans and the like made peaceful), then wait the confusion out on the Elbereth (a confused hero only
        improvises: no tune). True if it acted. One go per game. trigger: 'decision' (the crusher's quiet decision,
        PASSTUNE_TAME_CONF) or 'mino' (PASSTUNE_TAME_MINO)."""
        if self.tame_state == 'done':
            return False
        if self.tame_state is None:
            if not (jf_config.PASSTUNE_TAME_CONF if trigger == 'decision' else jf_config.PASSTUNE_TAME_MINO):
                return False
        elif not (jf_config.PASSTUNE_TAME_CONF or jf_config.PASSTUNE_TAME_MINO):
            return False
        agent = self.agent
        prop = agent.character.prop
        if self.tame_state is None:
            if self._tame_conf_items() is None or prop.confusion or prop.hallu or prop.stun:
                self.tame_state = 'done'
                return False
            self.tame_state = 'quaff'
        self.tame_tries += 1
        if self.tame_tries > 6:
            self._log('tame_conf: given up')
            self.tame_state = 'done'
            return False
        scroll = self._known_scroll('taming')
        if scroll is None or scroll.status == Item.CURSED or 'unpaid' in (scroll.text or ''):
            self.tame_state = 'done'
            return False
        if self.tame_state == 'quaff':
            potion = self._known_potion(CONF_SOURCES)
            if potion is None:
                self.tame_state = 'done'
                return False
            self._set_state(f'tame_conf: quaffing {potion.text!r}')
            box = self._tame_box()
            agent.inventory.quaff(potion)
            self._log(f'tame_conf: quaffed {potion.text!r}: {(agent.message or "")[:100]!r}; confused {prop.confusion}; '
                      f'in the box {box}')
            self._mile('tame_quaff', f'{box}')
            self.tame_state = 'read'
            return True
        # 'read' (the potion may have been the last one: only the scroll is needed now)
        if not prop.confusion:
            self._log('tame_conf: not confused after the potion')
            self.tame_state = 'quaff' if (self.tame_tries < 4 and self._known_potion(CONF_SOURCES) is not None) else 'done'
            return self._tame_conf_step() if self.tame_state == 'quaff' else False
        self._set_state(f'tame_conf: reading {scroll.text!r} confused')
        box = self._tame_box()
        with agent.atom_operation():
            agent.step(A.Command.READ)
            agent.type_text(agent.inventory.items.get_letter(scroll))
        self._log(f'tame_conf: read: {(agent.message or "")[:120]!r}; in the box before {box}')
        self._mile('tame_read', f'{box}')
        self.tame_state = 'done'
        return True

    def _inner_prep(self):
        """castle-inner's readiness gate before the hand-off (CASTLE_INNER only; the flag is not in a tree without that
        lane): eat when Hungry, wait out Blind/Confused/Stunned/Hallucinating, rest to its HP gate. True if it acted."""
        if not self._inner_takes_over():
            return False
        return bool(self.dive.inner.prep_step())

    def _inner_takes_over(self):
        """castle-inner exists and wants the hand-off (its takes_over(): the flag is on, the module is not done, and for
        CASTLE_INNER_EXCAL the hero has Excalibur); an older castle-inner without takes_over(): the flag alone."""
        inner = getattr(self.dive, 'inner', None)
        if inner is None:
            return False
        t = getattr(inner, 'takes_over', None)
        if t is not None:
            return bool(t())
        return bool(getattr(jf_config, 'CASTLE_INNER', False))

    def inner_owns(self):
        """The hand-off to castle_inner: the bridge is closed behind us (locked out) and no sweep or trick is running --
        at (07,08) after the legacy lock-out, at the throne room door (27,08) after a quiet sweep. With the lock-out
        switched off: inside (x >= 7) with the bridge down."""
        if self.sweep_state or self.trick_state:
            return False
        if self.locked_out:
            return True
        return (not jf_config.PASSTUNE_LOCKOUT) and self._pos()[0] >= LOCK_SQUARE[0] and self._open()

    def _fountain_guard(self):
        """PASSTUNE_FOUNTAIN_STEP: never stand on the fountain when something is going on -- it cannot hold an Elbereth,
        and a xorn killed a hero that kept trying (F326). Steps to a free neighbour when hurt, hurt recently or a
        monster is within 2."""
        if not jf_config.PASSTUNE_FOUNTAIN_STEP:
            return False
        if self._pos() != FOUNTAIN:
            self.fountain_steps = 0
            return False
        self.fountain_steps += 1
        if self.fountain_steps < 2:
            return False   # passing through: only a hero that STAYS on it (a fight, a rest, a wait) has to step off
        agent = self.agent
        bl = agent.blstats
        near = [m for m in agent.get_visible_monsters() if max(abs(m[1] - bl.y), abs(m[2] - bl.x)) <= 2]
        if not (near or self._hp_frac() < 0.7 or agent._hurt_recently(3)):
            return False
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, -1), (-1, 1), (1, 1)):
            q = (FOUNTAIN[0] + dx, FOUNTAIN[1] + dy)
            if self._walkable(q) and not self._monster_at(q) and not self._boulder(q) and q != FOUNTAIN:
                self._set_state(f'off the fountain to {q}')
                y, x = to_bot(*q)
                agent.direction(agent.calc_direction(bl.y, bl.x, y, x))
                return True
        return False

    # ---- PASSTUNE_TRICK: let a west-bank pest follow us over the bridge and close it on it

    def _west_pests(self):
        """[(distance, monster)] of the Elbereth-ignoring hostile land monsters in view on the west bank (map x <= 4):
        a minotaur or an @ that is not one of the castle's soldiers coming from inside."""
        bl = self.agent.blstats
        out = []
        for m in self._land_hostiles():
            mx, _ = to_map(m[1], m[2])
            if mx <= 4 and self.dive._melee_ignores_elbereth(m[3]) and self._crushable(m[3]):
                out.append((max(abs(m[1] - bl.y), abs(m[2] - bl.x)), m))
        out.sort(key=lambda t: t[0])
        return out

    def _trick_due(self):
        """With the garrison dead, the bridge down and nothing on it, an Elbereth-ignoring pest still 3..7 squares away on
        the west bank (a minotaur ignores Elbereth and takes ~42 HP a turn; the bridge kills it for nothing): walk over
        to (07,08); it follows (m_move heads straight for us), and the tune closes the bridge on it."""
        if self.tricks >= jf_config.PASSTUNE_TRICKS or not self._garrison_dead() or not self.bridge_open or \
                self._cant_play() or self._pos() not in CRUSH_SQUARES:
            return False
        pests = self._west_pests()
        if not pests or not (3 <= pests[0][0] <= 7):
            return False
        if self._sweep_east((5, 8)):      # something already coming from inside: not now
            return False
        names = [(getattr(m[3], 'mname', '?'), to_map(m[1], m[2])) for _, m in pests[:4]]
        self.tricks += 1
        self.trick_state = 'go'
        self.trick_turn = self.agent.blstats.time
        self._mile('trick', f'{names}, nearest {pests[0][0]}')
        self._log(f'trick {self.tricks}: over the bridge to {LOCK_SQUARE} for {names}')
        return True

    def _trick_step(self):
        agent = self.agent
        pos = self._pos()
        now = agent.blstats.time
        st = self.trick_state
        if now - self.trick_turn > jf_config.PASSTUNE_TRICK_TURNS or self._cant_play():
            self._log(f'trick {self.tricks}: given up at {pos} ({now - self.trick_turn} turns)')
            self.trick_state = None
            self.retreat_run = False
            return True
        if st == 'go':
            if pos == LOCK_SQUARE:
                self.trick_state = 'wait'
                return self._trick_step()
            near = self._near()
            if near:
                return self._attack(self._pick_target(near))
            if pos[1] != 8 or pos[0] < PORTCULLIS[0]:
                return self._go((max(pos[0], PORTCULLIS[0]), 8), 'the trick: to row 08')
            return self._walk_dir('e', 'the trick: over the bridge')
        # wait at (07,08) for the pest to be on the span or the portcullis
        targets = self._bridge_targets() if self.bridge_open else []
        if targets:
            self._toggle('trick: crush ' + ','.join(n for _, n in targets))
            if not self.bridge_open:
                self.locked_out = True
                self.trick_state = None
                self.sweep_state = 'return'
                self._mile('trick_kill', f'{[n for _, n in targets]} at turn {now}')
            return True
        near = self._near()
        if near:
            return self._attack(self._pick_target(near))
        self._set_state('the trick: waiting at the portcullis for the pest to cross')
        agent.search()
        return True

    # ---- PASSTUNE_SWEEP: the lure train

    def _garrison_dead(self):
        """The antechamber's garrison (8 soldiers and a lieutenant) is crushed: >= 8 @ kills on our toggles."""
        return self.garrison_known_dead or sum(1 for n in self.killed if n in SOLDIER_NAMES) >= 8

    def _sweep_due(self):
        """PASSTUNE_SWEEP: the quiet test passed -- before the hand-off, walk to the throne room door and back with
        whatever follows (the awake barracks army and the court's stragglers), so that the bridge crushes it instead
        of the walk-in meeting it in the throne room (21 of 47 baseline walk-in deaths were @ soldiers)."""
        return bool(jf_config.PASSTUNE_SWEEP and self.tune is not None and not self.locked_out and
                    self.sweeps < jf_config.PASSTUNE_SWEEPS and self.lures < jf_config.PASSTUNE_LURES and
                    self._garrison_dead() and not self._cant_play() and
                    self.agent.blstats.hunger_state < Hunger.WEAK)

    def _sweep_quiet_need(self):
        """Quiet turns before a sweep: short for the first, long after a train (its stragglers walk ~25 squares at speed
        10; the second sweep of the first smoke walked into them in the antechamber: 80 -> 25 HP in 7 turns)."""
        return jf_config.PASSTUNE_SWEEP_QUIET if not self.sweep_returns else jf_config.PASSTUNE_SWEEP_QUIET_TRAIN

    def _sweep_begin(self, why):
        self.sweeps += 1
        self.sweep_state = 'out'
        self.sweep_steps = 0
        self.sweep_dist = []
        self.crush_over = True
        self._log(f'sweep {self.sweeps}: to the throne room door {why}: kills {self.crush_kills}, lures {self.lures}')

    @staticmethod
    def _train_worthy(mon):
        """A monster worth a lure: a soldier of any rank, or anything of level >= 4 but a lizard (a lizard in the
        antechamber turned sweeps around in the first harness smoke)."""
        name = getattr(mon, 'mname', '')
        if name in SOLDIER_NAMES:
            return True
        if name in ('', 'unknown', 'lizard') or getattr(mon, 'mmove', 12) <= 0:
            return False   # (a spotted jelly in the hallway turned three sweeps around: it never follows)
        return getattr(mon, 'mlevel', 0) >= 4

    def _sweep_east(self, pos):
        """[(distance, monster)] of the train-worthy crushable hostile land monsters in view that are EAST of us inside
        the castle (the ones that would follow us west), nearest first (peacefuls are not in get_visible_monsters)."""
        bl = self.agent.blstats
        out = []
        for m in self._land_hostiles():
            mx, _ = to_map(m[1], m[2])
            if mx >= 6 and mx > pos[0] and self._crushable(m[3]) and self._train_worthy(m[3]):
                out.append((max(abs(m[1] - bl.y), abs(m[2] - bl.x)), m))
        out.sort(key=lambda t: t[0])
        return out

    def _sweep_any(self):
        """_sweep_east without the side: every train-worthy crushable hostile in view inside the castle."""
        bl = self.agent.blstats
        out = []
        for m in self._land_hostiles():
            mx, _ = to_map(m[1], m[2])
            if mx >= 6 and self._crushable(m[3]) and self._train_worthy(m[3]):
                out.append((max(abs(m[1] - bl.y), abs(m[2] - bl.x)), m))
        out.sort(key=lambda t: t[0])
        return out

    def _sweep_return(self, why):
        """Run back to the crusher square (04,07) with the train behind us; the crush loop takes over there. Sealed
        in (the bridge closed behind us at (07,08)): back to (07,08) first, where the tune re-opens it."""
        self.lures += 1
        self.sweep_returns += 1
        self.retreat_run = True
        if self.sweep_state in ('dgo', 'ddig', 'dwait') and self.door and \
                self._sym(DOOR_SQ[self.door]) not in G.DOOR_CLOSED:
            self.door_done.add(self.door)   # its train is on the way
        if not self.locked_out and self._pos()[0] <= LOCK_SQUARE[0]:
            self.sweeps = max(0, self.sweeps - 1)   # turned round before it left the antechamber door: not a spent sweep
        self._mile('sweep_back', f'sweep {self.sweeps} from {self._pos()}: {why}')
        self._log(f'sweep {self.sweeps}: run back from {self._pos()}: {why}')
        if self.locked_out:
            self.sweep_state = 'return'
            return self._sweep_step()
        self.sweep_state = None
        return self._hold_v3()

    def _sweep_step(self):
        agent = self.agent
        pos = self._pos()
        now = agent.blstats.time
        st = self.sweep_state
        self.sweep_steps += 1
        if self.sweep_steps > jf_config.PASSTUNE_SWEEP_STEPS or (self._cant_play() and st != 'return'):
            self._log(f'sweep {self.sweeps}: given up after {self.sweep_steps} steps (state {st}, sealed {self.locked_out})')
            self.sweeps = jf_config.PASSTUNE_SWEEPS
            if self.locked_out:
                self.sweep_state = 'return'
                self.sweep_steps = 0
                return self._sweep_step()
            self.sweep_state = None
            return self._hold_v3()
        doors = st in ('dgo', 'ddig', 'dwait')
        hs = self._sweep_any() if doors else self._sweep_east(pos)
        near_d = hs[0][0] if hs else None
        if st in ('out', 'bait') or doors:
            trig = bool(hs) and near_d <= jf_config.PASSTUNE_SWEEP_RANGE
            if doors and trig:
                # under a door the court's east-wall stickers hover 3-5 squares away without coming: only a soldier in
                # range, a monster within 2, or one that closes in is a train
                trig = near_d <= 2 or any(getattr(m[3], 'mname', '') in SOLDIER_NAMES and d <= jf_config.PASSTUNE_SWEEP_RANGE
                                          for d, m in hs)
            if st in ('bait', 'ddig', 'dwait') and hs and not trig:
                # standing still: a train-worthy hostile closing in from afar is a train too
                self.sweep_dist = (self.sweep_dist + [near_d])[-4:]
                if doors:   # (hoppers near the door: a strict 4-step approach, not a 2-square drop in 3 steps)
                    d4 = self.sweep_dist
                    trig = len(d4) >= 4 and d4[0] > d4[1] > d4[2] > d4[3]
                else:
                    trig = len(self.sweep_dist) >= 3 and self.sweep_dist[-1] <= self.sweep_dist[-3] - 2
            elif not hs:
                self.sweep_dist = []
            if trig:
                names = [(getattr(m[3], 'mname', '?'), to_map(m[1], m[2])) for _, m in hs[:6]]
                return self._sweep_return(f'{len(hs)} hostile east of us, nearest {near_d}: {names}')
            if self._hp_frac() < jf_config.PASSTUNE_SWEEP_HP:
                return self._sweep_return(f'hurt: hp {self._hp_frac():.2f}')
        if st != 'return' and self._contact():
            return True
        near = self._near()
        if st == 'return':
            if pos == LOCK_SQUARE:
                if self._cant_play():
                    agent.search()
                    return True
                if self._pet_wait(False):
                    return True
                self._toggle('sweep: re-opening the bridge for the train')
                if self.bridge_open:
                    self.locked_out = False
                    self.sweep_state = None
                    self._log(f'sweep {self.sweeps}: bridge open again at {pos}')
                    return self._hold_v3()
                self.tries['unseal'] += 1
                if self.tries['unseal'] > 6:
                    self.sweep_state = None
                return True
            if pos[0] < LOCK_SQUARE[0] or pos[1] != 8:
                return self._go(LOCK_SQUARE, 'sweep: back to the lock-out square')
            return self._walk_dir('w', 'sweep: back to the lock-out square')
        if near:
            return self._attack(self._pick_target(near))
        if doors:
            return self._door_step(st)
        if st == 'out':
            if pos == LOCK_SQUARE and not self.locked_out and jf_config.PASSTUNE_SWEEP_SEAL:
                if self.tries['seal'] < 8 and not self._cant_play():
                    if self._pet_wait(True):
                        return True
                    self.tries['seal'] += 1
                    self._toggle('sweep: closing the bridge behind us')
                    if not self.bridge_open:
                        self.locked_out = True
                        self._mile('sweep_seal', f'sweep {self.sweeps}')
                    return True
            if pos == SWEEP_BAIT or (pos == (SWEEP_BAIT[0] - 1, 8) and self._monster_at(SWEEP_BAIT)):
                # (a peaceful standing on the first square: wait in the doorway rather than fight it -- Luck -1 half the time)
                self.sweep_state = st = 'bait'
                self.bait_turn = now
                self.sweep_dist = []
                self._mile('sweep_bait', f'sweep {self.sweeps} at {pos}')
            else:
                if pos[1] != 8 or pos[0] < PORTCULLIS[0]:
                    return self._go((max(pos[0], PORTCULLIS[0]), 8), 'sweep: to row 08')
                return self._walk_dir('e', f'sweep: along row 08 to {SWEEP_BAIT}')
        if st == 'bait':
            if pos != SWEEP_BAIT and not (pos == (SWEEP_BAIT[0] - 1, 8) and self._monster_at(SWEEP_BAIT)):
                self.sweep_state = 'out'
                return self._sweep_step()
            seen = [(getattr(m[3], 'mname', '?'), to_map(m[1], m[2])) for _, m in self._sweep_east(pos)[:8]]
            self.sweep_seen = seen
            if now - self.bait_turn >= jf_config.PASSTUNE_SWEEP_WAIT:
                if self.locked_out and self._hp_frac() < jf_config.PASSTUNE_SWEEP_REST and \
                        now - self.bait_turn < jf_config.PASSTUNE_SWEEP_REST_TURNS and \
                        agent.blstats.hunger_state < Hunger.WEAK:
                    # sealed in and nothing coming: heal before the hand-off, on an Elbereth (the court respects it; the
                    # bridge is up behind us, the army is dead or locked in)
                    if not self._engraved() and self._can_write() and self.tries['bait_elbereth'] < 6:
                        self.tries['bait_elbereth'] += 1
                        self._set_state('sweep: Elbereth at the throne room door to rest')
                        agent.engrave('Elbereth')
                        return True
                    self._set_state('sweep: resting sealed in at the throne room door')
                    agent.search(3)
                    return True
                if self.locked_out and self._inner_prep():
                    return True
                self._mile('sweep_quiet', f'sweep {self.sweeps}: nothing came in {now - self.bait_turn} turns; in view '
                                          f'(far / not coming): {seen}; sealed {self.locked_out}')
                self._log(f'sweep {self.sweeps}: the throne room is quiet; far hostiles {seen}')
                self.sweep_state = None
                if self.locked_out:
                    if jf_config.PASSTUNE_DOORS and self._door_todo():
                        return self._door_next()
                    self._handoff_log()
                return True
            self._set_state(f'sweep {self.sweeps}: waiting at the throne room door for the train')
            agent.search()
            return True
        self.sweep_state = None
        return True

    def _barracks_doors(self):
        """{'N': symbol class, 'S': ...} of the barracks doors (26,05)/(26,11) as the map shows them from the throne room:
        'closed' (still locked: the army cannot come out on that side), 'open' (smashed by a court giant or open), 'unseen'."""
        out = {}
        for side, p in (('N', (26, 5)), ('S', (26, 11))):
            sym = self._sym(p)
            out[side] = 'closed' if sym in G.DOOR_CLOSED else \
                'open' if sym in (SS.S_ndoor, SS.S_vodoor, SS.S_hodoor) else 'unseen'
        return out

    def _door_todo(self):
        """Doors still to open: only on a side whose barracks door is still shut -- standing under the throne room door
        (row 05 / row 11) is in line with the barracks door and releases the awake army onto the hero (greedy m_move: from
        (25,05) the door square is nearer to anything on row <= 05), and the way out of the room passes its exit."""
        if self.dive.digging_tool() is None:
            return []
        bd = self._barracks_doors()
        return [d for d in ('N', 'S') if d not in self.door_done and
                (bd[d] == 'closed' or jf_config.PASSTUNE_DOORS_ARMY)]

    def _door_next(self):
        todo = self._door_todo()
        if not todo:
            self.sweep_state = None
            self._handoff_log()
            return True
        self.door = todo[0]
        self.sweep_state = 'dgo'
        self.sweep_steps = 0
        self._log(f'sweep {self.sweeps}: door train {self.door}: to {DOOR_U[self.door]}')
        return self._door_step('dgo')

    def _door_step(self, st):
        """PASSTUNE_DOORS: sealed in and the throne room quiet -- dig the locked door to a tower hallway open (silent: the
        barracks stay asleep) from the square under it, on an Elbereth (the court respects it), and wait for the tower
        guards (@, they ignore it) to come through: they and whatever else comes run the bridge, like any train."""
        agent = self.agent
        bl = agent.blstats
        now = bl.time
        which = self.door
        U, D = DOOR_U[which], DOOR_SQ[which]
        pos = self._pos()
        if st == 'dgo':
            if pos == U:
                self.sweep_state = 'ddig'
                return self._door_step('ddig')
            return self._go(U, f'door train: to {U} under the {which} door')
        if st == 'ddig':
            if pos != U:
                self.sweep_state = 'dgo'
                return self._door_step('dgo')
            if self._sym(D) in G.DOOR_CLOSED:
                if not self._engraved() and self._can_write() and self.tries['door_elb'] < 10:
                    self.tries['door_elb'] += 1
                    self._set_state(f'door train: Elbereth under the {which} door')
                    agent.engrave('Elbereth')
                    return True
                tool = self.dive.digging_tool()
                if tool is None or self.tries[('door_dig', which)] >= 10:
                    self._log(f'door train {which}: could not open the door (tool {tool is not None}, tries '
                              f'{self.tries[("door_dig", which)]})')
                    self.door_done.add(which)
                    return self._door_next()
                self.tries[('door_dig', which)] += 1
                d = agent.calc_direction(bl.y, bl.x, *to_bot(*D))
                self._set_state(f'door train: digging {d} through the {which} door')
                with agent.atom_operation():
                    tool = agent.inventory.move_to_inventory(tool)
                    agent.step(A.Command.APPLY)
                    agent.type_text(agent.inventory.items.get_letter(tool))
                    if 'In what direction do you want to dig?' in agent.single_message:
                        agent.direction(d)
                    elif agent.single_message.startswith('In what direction'):
                        agent.step(A.Command.ESC)
                self._log(f'door train {which}: dig {d}: {(agent.message or "")[:100]!r}')
                return True
            self.sweep_state = 'dwait'
            self.dwait_turn = now
            self._mile('door_open', f'{which} door open at turn {now}')
            return self._door_step('dwait')
        # dwait: on Elbereth under the open door, waiting for the guards
        if pos != U:
            self.sweep_state = 'dgo'
            return self._door_step('dgo')
        if now - self.dwait_turn >= jf_config.PASSTUNE_DOOR_WAIT:
            self._log(f'door train {which}: nothing came through in {now - self.dwait_turn} turns')
            self.door_done.add(which)
            return self._door_next()
        if not self._engraved() and self._can_write() and self.tries['door_elb'] < 20:
            self.tries['door_elb'] += 1
            self._set_state(f'door train: Elbereth under the {which} door')
            agent.engrave('Elbereth')
            return True
        self._set_state(f'door train: waiting under the open {which} door for the guards')
        agent.search()
        return True

    def _handoff_log(self):
        self._mile('handoff', f'kills {self.crush_kills} sweeps {self.sweeps} lures {self.lures} toggles {self.toggles} '
                              f'hp {self._hp_frac():.2f} pos {self._pos()} seen {self.sweep_seen} '
                              f'barracks doors {self._barracks_doors()} doors done {sorted(self.door_done)}')

    # ---- the crusher

    def _crush_phase(self):
        agent = self.agent
        pos = self._pos()
        self.crush_steps += 1
        if self.crush_steps > jf_config.PASSTUNE_MAX_STEPS:
            if jf_config.CRUSH_BUDGET_GO and not self.budget_go and self.tune is not None and \
                    self._hp_frac() >= jf_config.PASSTUNE_RESUME_HP:
                # CRUSH_BUDGET_GO: the step budget is a safety valve, not a plan -- a healthy hero at the square with the tune known
                # walks in for good (no more lures) instead of quitting with the bridge open and no plan (13 distinct kits of the
                # corpus ended there at full HP and died within ~100 turns: strength-w1-instr h15.jf96-s13~s2, castle 29, 160/160 HP)
                self.budget_go = True
                self.lures = jf_config.PASSTUNE_LURES
                self.crush_over = True
                self.hold_over = True
                self.hold_i = 0
                self.crush_steps = 0
                self._log(f'crusher budget spent: no more lures, walking in (kills {self.crush_kills}, toggles {self.toggles})')
                return True
            self._stop(f'crusher budget spent ({self.crush_steps} steps)')
            return False
        sq = self._crush_square()
        near = self._near()
        line = (SPAN, PORTCULLIS)
        ignorers = [m for m in near if to_map(m[1], m[2]) not in line and self.dive._melee_ignores_elbereth(m[3])]
        if pos != sq:
            if ignorers and not self.retreat_run:
                return self._attack(self._pick_target(ignorers))
            return self._go(sq, 'to the crusher square')
        self.retreat_run = False
        self._mile('square', f'at {sq}')
        # 1) crush first: a hostile on the span or the portcullis with the bridge down
        targets = self._bridge_targets() if self.tune is not None and self.bridge_open else []
        if targets:
            self.busy_turn = agent.blstats.time
        if targets and not self._cant_play():
            return self._toggle('crush ' + ','.join(n for _, n in targets))
        # 1b) PASSTUNE_TRICK: a pest on the west bank (minotaur, a non-soldier @) and the garrison dead: cross, let it follow
        if jf_config.PASSTUNE_TRICK and self._trick_due():
            return True
        # 2) something that ignores Elbereth next to us off the bridge line (the maze minotaur, an @ in the courtyard)
        if ignorers:
            return self._attack(self._pick_target(ignorers))
        # 3) Elbereth (the eels, sharks and the court respect it); a known scroll of scare monster once
        if not self._on_scare() and self.tries['crush_scare'] < 1 and self._drop_scare():
            self.tries['crush_scare'] += 1
            return True
        if not self._engraved() and self._can_write() and self.tries['crush_elbereth'] < 300:
            self.tries['crush_elbereth'] += 1
            self._set_state('Elbereth on the crusher square')
            agent.engrave('Elbereth')
            return True
        if jf_config.SHIELD_SQUARE and self.dive.square_shield_step():
            return True   # SHIELD_SQUARE (armour3): a mattock kit's kept shield goes on here, under its Elbereth, before the tune
        if self._cant_play():
            self._set_state('waiting out stun/confusion/hallucination on the crusher square')
            agent.search()
            return True
        if self.tune is None:
            return self._mastermind()
        return self._crush_loop()

    def _crush_loop(self):
        agent = self.agent
        hp = self._hp_frac()
        if self.bridge_open:
            if self.crush_over:
                return True
            if hp < jf_config.PASSTUNE_REST_HP and not (jf_config.PASSTUNE_PET_GUARD and self.tame_state == 'done'):
                # (after a taming read the court is ours: rest with the bridge open -- closing it, then opening it again, crushed
                # the tame sea monsters under the span: 13 of 29 remaining pet kills in the guarded subset)
                self.resting = True
                if self._pet_wait(True):
                    return True
                return self._toggle('close to rest')
            now = agent.blstats.time
            if self.entry_turn is None:
                self.entry_turn = now
            if self.busy_turn is None:
                self.busy_turn = now
            quiet, spell = now - self.busy_turn, now - self.entry_turn
            if hp >= jf_config.PASSTUNE_RESUME_HP and (quiet >= jf_config.PASSTUNE_QUIET or
                                                        spell >= jf_config.PASSTUNE_MAX_SPELL or
                                                        (quiet >= self._sweep_quiet_need() and
                                                         hp >= jf_config.PASSTUNE_SWEEP_START_HP and self._sweep_due())):
                # nothing has come over for a while (or the castle keeps trickling out): in -- a crowd on the way
                # sends FrontDoor._advance's lure back here
                if self._tame_conf_step():
                    return True
                if self._horn_before_walkin():
                    return True
                if self._inner_prep():
                    return True
                if jf_config.PASSTUNE_PULL and self.pulls < 1 and not self.pulling:
                    self.pulling = True
                    self.pulls += 1
                    self.entry_turn = self.busy_turn = now
                    self._mile('pull', f'kills {self.crush_kills}: to {PULL_SQUARE}')
                    self._log(f'pull spell from {PULL_SQUARE} after quiet {quiet} / spell {spell}')
                    return True
                self.pulling = False
                self.crush_over = True
                self.hold_over = True
                self.hold_i = 0
                self._mile('crush_over', f'kills {self.crush_kills} toggles {self.toggles} quiet {quiet} '
                                         f'spell {spell} {self.killed}')
                if self._sweep_due():
                    self._sweep_begin(f'after quiet {quiet} / spell {spell}')
                    return self._sweep_step()
                self._log(f'walking in after quiet {quiet} / spell {spell}: kills {self.crush_kills}')
                return True
            self._set_state('bridge down: waiting on the crusher square')
            agent.search()
            return True
        # bridge up
        if self.resting and hp < jf_config.PASSTUNE_RESUME_HP:
            self._set_state('bridge up: resting on the crusher square')
            agent.search(3)
            return True
        self.resting = False
        if self._pet_wait(False):
            return True
        return self._toggle('open')

    def _pet_wait(self, closing):
        """PASSTUNE_PET_GUARD: True (after spending a search turn) if the toggle should wait: a tame or peaceful monster stands on
        the span or the portcullis square (a close crushes it, dbridge.c; killing a pet costs alignment -15 and Luck -1, a peaceful
        -5 and Luck -1 half the time, and a negative Luck makes every prayer fail), or, when we have tamed sea monsters, one may
        hide under the raised span (an open crushes it: 31 of 100 pet kills in the taming arm; a search shows adjacent hiders).
        Gives up after PASSTUNE_PET_WAIT turns per toggle."""
        if not jf_config.PASSTUNE_PET_GUARD:
            return False
        agent = self.agent
        self.pet_gave_up = False
        bl = agent.blstats
        under_attack = self._hp_frac() < 0.6 or any(
            max(abs(int(m[1]) - int(bl.y)), abs(int(m[2]) - int(bl.x))) <= 2 for m in self._land_hostiles())
        if under_attack:
            self.pet_waits = 0
            self.pet_probed = False
            return False   # (the first guarded version waited 7 turns at the lock-out square while a swarm took 60 HP)
        if self.pet_waits >= jf_config.PASSTUNE_PET_WAIT:
            self.pet_waits = 0
            self.pet_probed = False
            self.pet_gave_up = True
            return False
        peaceful = agent.monster_tracker.peaceful_monster_mask
        blocked = False
        for p in (SPAN, PORTCULLIS):
            y, x = to_bot(*p)
            g = int(agent.glyphs[y, x])
            if nh.glyph_is_pet(g) or (nh.glyph_is_monster(g) and peaceful[y, x]):
                blocked = True
        probe = False
        if not blocked and not closing and self.tame_state == 'done' and not self.pet_probed and \
                max(abs(self._pos()[0] - SPAN[0]), abs(self._pos()[1] - SPAN[1])) <= 1:
            probe = True
            self.pet_probed = True
        if not (blocked or probe):
            self.pet_waits = 0
            self.pet_probed = False
            return False
        self.pet_waits += 1
        self.pet_waited_total += 1
        self._set_state('waiting: ' + ('a pet or a peaceful is on the bridge' if blocked else 'a search for a pet under the span'))
        agent.search()
        return True

    def _toggle(self, why):
        """Play the known tune: opens a raised bridge, closes a lowered one."""
        self._book_cut_play()
        self.toggles += 1
        before_open = self.bridge_open
        res = self._play(None)
        msg = res['msg']
        self._note(msg)
        self._set_state(f'played the passtune ({why})')
        if self.bridge_open == before_open and not _OPEN_RE.search(msg) and not _CLOSE_RE.search(msg):
            self.tries['toggle_fail'] += 1
            self._log(f'toggle did nothing ({why}): {msg[:160]!r}')
            if self.tries['toggle_fail'] > 12:
                self._stop('the passtune no longer moves the bridge')
                return False
        else:
            self._mile('open' if self.bridge_open else 'crush', f'toggle {self.toggles}')
        return True

    def _book_cut_play(self):
        """CRUSH_PLAY_SAFE (F362): the apply of the last play was done but a preempting strategy (MinoGuard in 84 of 117 cases) fired
        in the atom block's end-of-block update, before _toggle noted the bridge's new state and before _mastermind learned the
        tune or the feedback. Book it now."""
        cut, self._cut_play = self._cut_play, None
        if cut is None or not jf_config.CRUSH_PLAY_SAFE:
            return
        guess, res = cut
        self._log(f'booking a play cut by a preempting strategy: {guess} -> {(res["msg"] or "")[-100:]!r}')
        if guess is None:
            self._note(res['msg'])
        else:
            self._mastermind_after(guess, res)

    def _mastermind(self):
        agent = self.agent
        self._book_cut_play()
        if self.tune is not None:
            return True
        if self.plays >= jf_config.PASSTUNE_MAX_PLAYS:
            self._stop(f'tune not found in {self.plays} plays')
            return False
        guess = self.solver.next_guess()
        if guess is None:
            left = self.solver.reset(keep_last=True)
            self._log(f'no consistent tune left: history reset without its last entry -> {left}')
            if left == 0:
                self.solver.reset()
            guess = self.solver.next_guess()
        if self.first_play_turn is None:
            self.first_play_turn = agent.blstats.time
        self.plays += 1
        res = self._play(guess)
        return self._mastermind_after(guess, res)

    def _mastermind_after(self, guess, res):
        """What one Mastermind play told us (the part of _mastermind that follows the play: CRUSH_PLAY_SAFE books it for a play
        a preempting strategy cut short as well)."""
        agent = self.agent
        msg = res['msg']
        self._note(msg)
        if self.bridge_open or _OPEN_RE.search(msg):
            self.tune = guess
            self.bridge_open = True
            self._mile('tune', f'{guess} plays {self.plays} turns {agent.blstats.time - self.first_play_turn}')
            return True
        if res['plenty']:
            inst = res['item']
            if inst is not None and inst.glyphs:
                self.not_tonal.add(inst.glyphs[0])
            self.plays -= 1
            self._log(f'{inst.text if inst else "?"!r} asked no Improvise?: a horn of plenty')
            return True
        if 'emitting vibrations' in msg or not res['improvise']:
            self.plays -= 1
            self.tries['no_play'] += 1
            self._log(f'no tune played (deaf / no prompt): {msg[:120]!r}')
            if self.tries['no_play'] > 20:
                self._stop('cannot play a tune')
                return False
            agent.search()
            return True
        fb = passtune.parse_feedback(msg)
        if fb is None:
            if 'strange sound' not in msg:
                # the tune never reached the game (an interrupted prompt): don't count it
                self.plays -= 1
                self.tries['lost_play'] += 1
                self._log(f'lost play {guess}: {msg[:160]!r}')
                if self.tries['lost_play'] > 10:
                    self._stop('plays keep getting lost')
                    return False
                return True
            fb = (0, 0)   # music.c: nothing at all for no gear and no tumbler
        left = self.solver.update(guess, *fb)
        self._log(f'play {self.plays}: {guess} -> gears {fb[0]} tumblers {fb[1]}; {left} tunes left')
        if left == 0:
            left = self.solver.reset(keep_last=True)
            self._log(f'inconsistent feedback: dropped the last play -> {left} tunes')
            if left == 0:
                self.solver.reset()
        return True

    def _play(self, tune):
        """Apply the instrument: 'Improvise?' n, then the tune (or 'Play the passtune?' y once it is known).
        Returns dict(msg, improvise, plenty, item)."""
        agent = self.agent
        item = self._instrument()
        out = dict(msg='', improvise=False, plenty=False, item=item)
        if item is None:
            return out
        letter = agent.inventory.items.get_letter(item)
        seen = dict(applied=False, improvise=False, passtune=False, tune=False)
        notes = (tune or self.tune or '').lower()

        def gen():
            if 'What do you want to use or apply?' not in agent.single_message:
                return
            seen['applied'] = True
            yield letter
            for _ in range(16):
                msg = agent.single_message or ''
                if 'Improvise?' in msg and not seen['improvise']:
                    seen['improvise'] = True
                    yield 'n'
                    continue
                if 'Play the passtune?' in msg and not seen['passtune']:
                    seen['passtune'] = True
                    yield 'y' if tune is None else 'n'
                    continue
                if 'What tune are you playing' in msg and not seen['tune']:
                    seen['tune'] = True
                    for ch in notes:
                        yield ch
                    yield '\r'
                    continue
                if 'In what direction?' in msg:
                    yield A.Command.ESC   # never a horn's ray here
                    continue
                misc = agent._observation['misc']
                if misc[2] and not misc[1]:
                    yield ' '
                    continue
                return

        def result():
            msg = agent.message or ''
            out['msg'] = msg
            out['improvise'] = seen['improvise']
            maybe_plenty = 'horn of plenty' in {getattr(o, 'name', '') for o in item.objs}
            out['plenty'] = maybe_plenty and seen['applied'] and not seen['improvise'] and not self._cant_play() and \
                'strange sound' not in msg and 'vibrations' not in msg
            self._log(f'played {item.text!r} ({letter}) tune {notes or "?"} passtune={seen["passtune"]} '
                      f'-> {msg[:200]!r}')
            return out

        if jf_config.CRUSH_PLAY_SAFE:
            from .exceptions import AgentChangeStrategy
            try:
                with agent.atom_operation():
                    agent.step(A.Command.APPLY, gen())
            except AgentChangeStrategy:
                # the apply is played: keep its result for the next toggle / play (see _book_cut_play)
                self._cut_play = (tune, result())
                raise
        else:
            with agent.atom_operation():
                agent.step(A.Command.APPLY, gen())
        result()
        agent.inventory.items.update(force=True)
        return out

    # ---- castle 29: the secret door (38,08) and the trap door (40,08)

    def _trapdoor_step(self):
        agent = self.agent
        pos = self._pos()
        near = self._near()
        if near and self._read_taming(near):
            return True
        if near and self._hp_frac() < 0.35 and pos in THRONE_ROOM and self.retreats < 6:
            self.phase = None
            self.hold_i = 1
            self._retreat(near)
            return self._hold_v3()
        if near and self._scare_walkin(near):
            return True
        if self._rest_inside():
            return True
        if near:
            return self._attack(self._pick_target(near))
        if pos[1] == 8 and pos[0] >= AFTER_SECRET[0]:
            self._mile('secret', 'through the secret door')
            y, x = to_bot(*TRAPDOOR)
            if pos == TRAPDOOR or self.tries['plunge'] > 0:
                # standing on a trap door that didn't open (it was seen): '>' (LIFT_PLUNGE's way)
                self.tries['plunge'] += 1
                self._set_state('> on the trap door')
                agent.step(A.MiscDirection.DOWN)
                if self.tries['plunge'] > 6:
                    self._stop('the trap door does not take us')
                    return False
                return True
            self._mile('trapdoor', 'stepping onto (40,08)')
            return self._walk_dir('e', 'onto the trap door (40,08)')
        if pos == SECRET_DOOR:
            return self._walk_dir('e', 'through the secret door')
        if pos != BEFORE_SECRET:
            return self._go(BEFORE_SECRET, 'to the secret door (38,08)')
        # at (37,08): find and open the secret door
        if self._door(SECRET_DOOR) or self._sym(SECRET_DOOR) in (SS.S_ndoor, SS.S_vodoor, SS.S_hodoor):
            self.secret_found = True
            return self._walk_dir('e', 'through the secret door (38,08)')
        dig = self._usable('digging')
        if dig is not None and self.tries['secret_dig'] < 2:
            # zap.c zap_dig: a digging beam razes a secret door despite NON_DIGGABLE (one per zap on a maze level)
            self.tries['secret_dig'] += 1
            self._set_state('zapping digging east at the secret door')
            agent.zap(dig, 'e')
            self._log(f'secret door dig zap: {agent.message[:120]!r}')
            return True
        if not self._engraved() and self._can_write() and self.tries['secret_elbereth'] < 20:
            # searching and door work stand still: Elbereth keeps the court's xorns/elementals off (kicks wipe it)
            self.tries['secret_elbereth'] += 1
            self._set_state('Elbereth before the secret door work')
            agent.engrave('Elbereth')
            return True
        if self.tries['secret_search'] < 30:
            self.tries['secret_search'] += 1
            self._set_state('searching for the secret door (38,08)')
            agent.search()
            return True
        if self.tries['secret_kick'] < 30:
            # dokick.c: 'Crash! You kick open a secret door!' / 'Your kick uncovers a secret door!'
            self.tries['secret_kick'] += 1
            self._set_state('kicking at the secret door (38,08)')
            with agent.atom_operation():
                agent.step(A.Command.KICK)
                agent.direction('e')
            self._log(f'secret door kick: {agent.message[:120]!r}')
            return True
        self._stop('the secret door (38,08) stayed shut')
        return False

    # ---- the tower wand: named by one zap, the wishes are tele_route's (as CASTLE_TREASURY hands it over)

    def _test_wand(self, wand):
        agent = self.agent
        inv = agent.inventory
        self._mile('wand', wand.text)
        if (wand.is_unambiguous() and wand.object.name == 'wishing') or self.tries['wand_zap'] >= 2:
            self._stop(f'wand in hand: {wand.text!r} (WISH_TELEPORT_ROUTE takes over)')
            return False
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


def strategy(dive):
    crusher = getattr(dive, 'crusher', None)
    if crusher is None:
        return Strategy(lambda: iter([False]))
    return crusher.strategy()
