"""landing-b lane (lane 12, readiness program phase 2): the castle landing of a kit with a tonal instrument, from the fall to the
crusher square, beyond what the landing lane did (castle_landing.py, dive_logic LANDING_*, castle_logic LANDING_ROUTE).

Two switches, both OFF (jf_config.LANDING_LICH, LANDING_OUTRUN); one strategy, placed in the chain where castle_landing's guard
sits (above fight2, dig_first, the Elbereth rests and the castle passage; below the crusher, the emergency layer, the known items
and the minotaur guard).

What the NetHack 3.6.6 source says about a covetous master lich / arch-lich (about 19% of castles have one among the court's 'L'
squares: castle.des $monster[...], makemon.c / mkclass keeps going past 'too strong' on a coin flip) -- the reasons for LANDING_LICH:

* wizard.c tactics() runs at the start of every dochug of a covetous monster: a healthy one (mhp == mhpmax) is STRAT_NONE and
  `if (!rn2(!mtmp->mflee ? 5 : 33)) mnexto(mtmp)` puts it next to the hero from anywhere (rloc ignores noteleport); a wounded one
  (mhp < mhpmax) goes STRAT_HEAL, teleports to the up stairs every move and harasses from there. monmove.c m_move: `if
  (is_covetous(ptr)) { ... mmoved = 0; goto postmov; }` -- a covetous monster never WALKS. So it is where it last teleported to.
* dochug (monmove.c 574-640) enters its movement branch when the monster is not nearby, flees, or is scared; there it rolls ONE
  undirected spell per move (`dist2 <= 49 && !mspec_used`, castmu(mtmp, a, FALSE, FALSE)): summon nasties (mcastu.c spell 15-17 of
  rn2(ml): 3/ml ~ 16% a move at ml 19), aggravate (13-14, wakes the 36 barracks soldiers), haste self, disappear (the lich turns
  invisible), cure self. A summon needs couldsee() of the lich's square. castmu sets mspec_used = max(2, 10 - m_lev) in 3.6.6:
  one cast per 2 turns at most.
* Adjacent and not scared the lich attacks (mattacku): the touch is cold (a Valkyrie resists it: 'The frost doesn't seem cold!',
  but potions shatter) and castmu picks a USEFUL spell with retries: psi bolt (d(ml/2+1, 6): ~35 HP), stun (~10 turns of random
  steps), weaken, destroy armor, curse items, aggravate, summon; an arch-lich (ml 25+) also the touch of death (spells 20-24,
  5 of 20 useful ones; `rn2(m_lev) > 12` kills a hero without magic resistance: ~48%).
* onscary() (monmove.c 135-182): liches respect a dust Elbereth (not @, minotaurs, shopkeepers, blind or peaceful monsters;
  Elbereth works everywhere but Gehennom). distfleeck() sets `scared` for a monster next to us on it: dochug then skips mattacku
  (no melee, no directed spell, no touch of death) and monflee(rnd(10), 1 in 7 rnd(100)) -- and the teleport rate drops from 1/5
  to 1/33 per move while it flees. A scared monster does not interrupt an occupation (hack.c monster_nearby: !onscary), so a dig
  goes on beside it. Our own melee wipes up to 3 letters of a dust Elbereth (uhitm.c u_wipe_engr(3)); a dig does not
  (engrave.c / dig.c: only axe-on-floor and wand zaps do).
* nasty() (wizard.c): rnd(XL/3) outer rounds, each creating monsters (20 tries) until one is neutral or chaotic like the lich: ~2
  summoned nasties per cast at XL 7-9. 6 of 42 ignore Elbereth in melee (minotaur, captain, elf-lord, Elvenking, Aleax, couatl),
  6 dragons and an iron golem breathe from range.

LANDING_LICH therefore only does the cheap part: Elbereth under us when a lich stands next to us and nothing that ignores
Elbereth does (the existing LandingGuard step 0 did it for visible liches only, behind LANDING_GUARD), also against an invisible
one (its touch and spell messages), and with mode 2 before a dig of the maze route while a lich was seen lately.

LANDING_ELBDIG: the same Elbereth for every monster that respects it, before a dig of the maze route (3 turns standing: apply + 3
dig moves for a dwarf, dig.c effort doubling) when one is within 3 squares and none that ignores it is: a dig beside a monster
that Elbereth scares is not interrupted (hack.c monster_nearby), the monster does not attack (dochug: scared), and it flees for
rnd(10) turns. fight2 would hit it instead (a xorn costs ~100 HP to kill with a long sword, F347) and an unscared one stops
every dig turn.

LANDING_OUTRUN: monmove.c dochug case 1 -- a monster that moved returns without a melee attack (only ranged attackers shoot
after moving) -- and mon.c mcalcmove (speed rounded randomly to multiples of 12, 'a normal-speed player fleeing a normal-speed
monster cannot be gapped'): a walking hero is meleed only on the turns a faster monster gets a second move. fight2 instead waits
for a hostile that is not adjacent (878 of the first 40 turns' 2751 fight2 turns in 400 landings had nobody adjacent). With the
route's next square a plain step we take it.
"""
import re

from . import jf_config
from .strategy import Strategy

LICHES = frozenset(('lich', 'demilich', 'master lich', 'arch-lich'))
COVETOUS = frozenset(('master lich', 'arch-lich'))
# what a lich (seen or not) leaves in the message window: its name with an action, an invisible one's touch / spell, a summon
_LICH_MSG = re.compile(
    r"(?:master lich|arch-lich|demilich|\blich)\b[^.!]*?(?: touches you| casts a spell| points| suddenly appears| gestures)"
    r"|Something casts a spell at you|Something points|It touches you!\s+You're covered in frost"
    r"|Monsters? appears? from nowhere|You feel that monsters are aware of your presence|Oh no, (?:he|she|it)'s using the touch of death",
    re.I)


_SUMMON_MSG = re.compile(r"Monsters? appears? from nowhere", re.I)


class LandingB:
    def __init__(self, dive):
        self.dive = dive
        self.agent = dive.agent
        self.lich_turn = -10 ** 9      # last game turn a lich (or its signature) was seen on this level
        self.summon_turn = -10 ** 9    # last game turn 'Monsters appear from nowhere!' (a lich's summon nasties) was read
        self.lich_key = None
        self.lich_engraves = 0         # Elbereths written against a lich this game
        self.outrun_steps = 0
        self.dash_steps = 0
        self.logged = set()
        self.wandid_tests = 0          # LANDING_WANDID: engrave tests started this game
        self.wandid_tried = set()      # ...and the wand glyphs they were for (a test that did not complete is tried once more)
        self.wandid_retried = set()

    # ------------------------------------------------------------------ state

    def _in_castle_west(self):
        """The crusher is armed, its walk to the square is ahead and we are still in the west maze (the crusher's own strategy
        takes over in the courtyard)."""
        dive = self.dive
        c = dive.crusher
        if not jf_config.PASSTUNE_CRUSHER or c.done or c.destroyed or c.tune is not None or 'square' in c.logged:
            return False
        if not c.on_castle():
            return False
        if dive.castle._floating() or self.agent.character.prop.polymorph:
            return False
        if dive.castle._pos()[0] >= 0:
            return False
        return c._instrument() is not None

    def _note_lich(self):
        """Remember that a lich is about: seen in the monster list, or named in the messages of the last step."""
        agent = self.agent
        key = agent.current_level().key()
        if self.lich_key != key:
            self.lich_key = key
            self.lich_turn = -10 ** 9
        msg = agent.message or ''
        seen = bool(_LICH_MSG.search(msg))
        if _SUMMON_MSG.search(msg):
            self.summon_turn = agent.blstats.time
        if not seen:
            for m in agent.get_visible_monsters():
                if getattr(m[3], 'mname', '') in LICHES:
                    seen = True
                    break
        if seen:
            self.lich_turn = agent.blstats.time
            self.dive.lich_seen_turn = agent.blstats.time   # (dive_logic._scare_ignores: an unseen adjacent monster is then the lich)
        return seen

    def _hostiles(self):
        """Visible hostile monsters that can reach us: (row, col, permonst, dist)."""
        out = []
        for dis, y, x, mon, _ in self.agent.get_visible_monsters():
            if getattr(mon, 'mmove', 12) == 0:
                continue   # sessile (molds, jellies, ...)
            out.append((int(y), int(x), mon, int(dis)))
        return out

    def _unsteady(self):
        """Stunned (random steps), confused (1 in 5), blind or hallucinating: no walking by this layer (wait_out_unexpected_state below)."""
        p = self.agent.character.prop
        return bool(p.stun or p.confusion or p.blind or p.hallu)

    def _adjacent(self, a, b):
        return max(abs(a[0] - b[0]), abs(a[1] - b[1])) <= 1

    # ------------------------------------------------------------------ LANDING_LICH

    def _lich_next_to_us(self, hostiles, pos):
        """A lich within 1 (seen), or an unseen monster next to us right after a lich's message (an invisible lich)."""
        for y, x, mon, _ in hostiles:
            if getattr(mon, 'mname', '') in LICHES and self._adjacent((y, x), pos):
                return True
        if self.agent.blstats.time - self.lich_turn <= 2:
            for y, x, mon, _ in hostiles:
                if getattr(mon, 'mname', '') == 'unknown' and self._adjacent((y, x), pos):
                    return True
        return False

    def _near_split(self, hostiles, pos, radius=3):
        """(Elbereth-ignorers within `radius` squares of us, the other hostiles within it) -- the minotaur / @ class and the rest."""
        ign, resp = [], []
        for h in hostiles:
            if max(abs(h[0] - pos[0]), abs(h[1] - pos[1])) > radius:
                continue
            (ign if self.dive._melee_ignores_elbereth(h[2]) else resp).append(h)
        return ign, resp

    def _dash_ok(self, ign, resp):
        """Mode 3: on an Elbereth we trust (written lately, or read intact) with a lich about or respecters beside us and nothing that
        ignores Elbereth within 2: the maze route goes on -- a dig from the square (a scared monster does not stop it), a step off it
        (the scared ones flee for rnd(10) turns) -- instead of the layers below (fight2, zaps at the 'unknown', the scare pile)
        which attack from the square and wipe it (hypocrite: mon.c setmangry) or stand about."""
        agent = self.agent
        bl = agent.blstats
        if ign or bl.hitpoints < 0.35 * bl.max_hitpoints:
            return False
        if agent.in_pit() or self.dive.levitating() or self._unsteady():
            return False
        if (agent.inventory.engraving_below_me or '').lower() != 'elbereth':
            return False   # (engrave() reads the dust back: a typo is seen at once and written again)
        return bl.time - self.lich_turn <= jf_config.LANDING_LICH_MEMORY or bool(resp)

    def _elbereth_wanted(self, hostiles, pos):
        """Mode 1: a lich next to us and no Elbereth-ignorer next to us. Mode 2: also before a dig of the maze route (4 turns
        standing) while a lich was seen in the last LANDING_LICH_MEMORY turns and nothing is next to us."""
        agent = self.agent
        if self.lich_engraves >= jf_config.LANDING_LICH_ENGRAVES:
            return None
        if self._unsteady() or not agent.can_engrave() or self.dive.levitating() or agent.in_pit():
            return None   # (engrave.c 1053: each letter is also mixed up 1 in 4 stunned, 1 in 7 confused, 1 in 2 hallucinating, 1 in 11
            #  blind -- a stunned hero writes a whole Elbereth 7% of the time: lnd-b l3 jf83-s13~s2 burned 8 writes in 4 turns beside a lich)
        engraving = (agent.inventory.engraving_below_me or '').lower()
        if engraving == 'elbereth':
            return None
        for y, x, mon, _ in hostiles:
            if self._adjacent((y, x), pos) and self.dive._melee_ignores_elbereth(mon):
                return None   # the minotaur / @ next to us: Elbereth is not the answer (the guards and fight2 are)
        lich_on = jf_config.LANDING_LICH
        if lich_on and self._lich_next_to_us(hostiles, pos):
            return 'a lich next to us'
        if lich_on and agent.blstats.time - self.summon_turn <= 2 and \
                any(self._adjacent((y, x), pos) or d <= 2 for y, x, _, d in hostiles):
            return 'nasties summoned'
        if lich_on and jf_config.LANDING_LICH_MODE >= 2 and \
                agent.blstats.time - self.lich_turn <= jf_config.LANDING_LICH_MEMORY and \
                not any(self._adjacent((y, x), pos) for y, x, _, _ in hostiles):
            peek = self.dive.castle.route_peek()
            if peek is not None and peek[0] == 'dig':
                return 'a dig ahead with a lich about'
        if jf_config.LANDING_ELBDIG:
            near3 = [h for h in hostiles if max(abs(h[0] - pos[0]), abs(h[1] - pos[1])) <= 3]
            if near3 and not any(self.dive._melee_ignores_elbereth(h[2]) for h in near3):
                peek = self.dive.castle.route_peek()
                if peek is not None and peek[0] == 'dig':
                    return 'a dig ahead with ' + getattr(near3[0][2], 'mname', '?') + ' near'
        return None

    # ------------------------------------------------------------------ LANDING_WANDID

    def _wandid_wanted(self, hostiles, pos):
        """LANDING_WANDID: the first untested unknown wand, if this is a quiet moment for a 2-turn engrave test: nothing hostile within
        LANDING_WANDID_QUIET squares, no minotaur in view at all (the guard owns that phase), not blind / stunned / in a pit / afloat, not at
        the moat's edge, a bare square to engrave on (castle_power._engrave_test checks)."""
        agent = self.agent
        if self.wandid_tests >= jf_config.LANDING_WANDID_MAX:
            return None
        if self._unsteady() or agent.in_pit() or self.dive.levitating() or not agent.can_engrave():
            return None
        for y, x, mon, d in hostiles:
            if d <= jf_config.LANDING_WANDID_QUIET or getattr(mon, 'mname', '') == 'minotaur':
                return None
        from . import castle_power
        from .castle_logic import MOAT_EDGE
        if self.dive.castle._pos() in MOAT_EDGE:
            return None
        wands = [w for w in castle_power._untested_wands(agent) if w.glyphs[0] not in self.wandid_tried]
        return wands[0] if wands else None

    # ------------------------------------------------------------------ LANDING_OUTRUN

    def _outrun_target(self, hostiles, pos):
        """The route's next square (bot row, col) if taking it now is an outrun: a plain step that ends out of reach of every
        awake hostile in view; None otherwise."""
        agent = self.agent
        castle = self.dive.castle
        if agent.in_pit() or self.dive.levitating() or self._unsteady():
            return None
        near = [h for h in hostiles if self._adjacent((h[0], h[1]), pos)]
        if near and jf_config.LANDING_OUTRUN_MODE < 2:
            return None
        if self.dive.on_scare_scroll() and any(max(abs(h[0] - pos[0]), abs(h[1] - pos[1])) <= 5 and
                                               self.dive._scare_ignores(h[2]) for h in hostiles):
            return None   # standing on our scroll of scare monster with a minotaur / @ about: the hold is the pile's (CASTLE_SCARE)
        peek = castle.route_peek()
        if peek is None:
            return None
        from .castle_logic import to_bot
        ty, tx = to_bot(*peek[1])
        if peek[0] == 'dig':
            # mode 3: a dig starts while nothing is within 3 squares (fight2 would wait for the monster to arrive; the apply costs
            # one move and the effort is kept when the monster interrupts: dig.c 'You continue digging')
            if jf_config.LANDING_OUTRUN_MODE >= 3 and not any(max(abs(y - pos[0]), abs(x - pos[1])) <= 3 for y, x, _, _ in hostiles):
                return ty, tx
            return None
        if peek[0] != 'step':
            return None
        for y, x, mon, _ in hostiles:
            if self._adjacent((y, x), (ty, tx)):
                return None
        return ty, tx

    # ------------------------------------------------------------------ the strategy

    def strategy(self):
        def f():
            lich_on = jf_config.LANDING_LICH
            outrun_on = jf_config.LANDING_OUTRUN
            elbdig_on = jf_config.LANDING_ELBDIG
            wandid_on = jf_config.LANDING_WANDID
            if not (lich_on or outrun_on or elbdig_on or wandid_on):
                yield False
                return
            agent = self.agent
            level = agent.current_level()
            from .level import Level
            if level.dungeon_number != Level.DUNGEONS_OF_DOOM or agent.blstats.depth < 25:
                yield False
                return
            if not self._in_castle_west():
                if lich_on:
                    self._note_lich()
                yield False
                return
            if lich_on:
                self._note_lich()
            pos = (int(agent.blstats.y), int(agent.blstats.x))
            hostiles = self._hostiles()
            act = None
            if lich_on or elbdig_on:
                why = self._elbereth_wanted(hostiles, pos)
                if why is not None:
                    act = ('elbereth', why)
                elif ((lich_on and jf_config.LANDING_LICH_MODE >= 3) or elbdig_on) and hostiles:
                    ign, resp = self._near_split(hostiles, pos)
                    if self._dash_ok(ign, resp):
                        peek = self.dive.castle.route_peek()
                        if peek is not None and (peek[0] == 'dig' or (peek[0] == 'step' and lich_on)):
                            act = ('dash', peek[0])
            if act is None and wandid_on:
                wand = self._wandid_wanted(hostiles, pos)
                if wand is not None:
                    act = ('wandid', wand)
            if act is None and outrun_on and hostiles:
                target = self._outrun_target(hostiles, pos)
                if target is not None:
                    act = ('outrun', target)
            if act is None:
                yield False
                return
            yield True
            bl = agent.blstats
            if act[0] == 'elbereth':
                self.lich_engraves += 1
                agent.log(f'LANDINGB Elbereth: {act[1]} (hp {bl.hitpoints}/{bl.max_hitpoints}, '
                          f'{self.lich_engraves} this game)')
                agent.engrave('Elbereth')
                return
            if act[0] == 'wandid':
                from . import castle_power
                wand = act[1]
                g = wand.glyphs[0]
                self.wandid_tests += 1
                self.wandid_tried.add(g)
                agent.log(f'LANDINGB wandid: engrave-testing {wand.text!r} at the landing (test {self.wandid_tests}, hp {bl.hitpoints}/{bl.max_hitpoints})')
                try:
                    castle_power._engrave_test(self.dive.castle, wand)
                finally:
                    # a test cut short by a preempting layer (ARMOR_UP wearing boots took the turn in the smoke) is tried once more
                    if g not in agent.inventory.item_manager._already_engraved_glyphs and g not in self.wandid_retried:
                        self.wandid_retried.add(g)
                        self.wandid_tried.discard(g)
                return
            if act[0] == 'dash':
                self.dash_steps += 1
                if self.dash_steps <= 3 or self.dash_steps % 10 == 0:
                    agent.log(f'LANDINGB dash {self.dash_steps}: route {act[1]} on a trusted Elbereth '
                              f'(hp {bl.hitpoints}/{bl.max_hitpoints})')
                before = agent.step_count
                self.dive.crusher.approach_step()
                if agent.step_count == before:
                    agent.search()
                return
            self.outrun_steps += 1
            if 'outrun' not in self.logged or self.outrun_steps % 10 == 0:
                self.logged.add('outrun')
                near = sorted(hostiles, key=lambda h: h[3])[:3]
                agent.log(f'LANDINGB outrun step {self.outrun_steps} to {act[1]} past '
                          f'{[(getattr(h[2], "mname", "?"), h[3]) for h in near]} (hp {bl.hitpoints}/{bl.max_hitpoints})')
            before = agent.step_count
            self.dive.crusher.approach_step()
            if agent.step_count == before:
                agent.search()

        return Strategy(f)
