"""WISH_TELEPORT_ROUTE: a wand of wishing -> the bottom of Gehennom by two controlled level teleports.

teleport.c level_tele(): with teleport control, any level asked for past the bottom of the Dungeons of Doom is
find_hell() -- the Valley of the Dead, castle depth + 1 -- from ANY level of the Dungeons, Dlvl 1 included; from
Gehennom a big number clamps to the vibrating-square level (bottom-1; the Sanctum needs the invocation), Dlvl
~44-52. read.c seffects(): a cursed (or confused) scroll of teleportation calls level_tele(), and noteleport
levels don't stop it (only Sokoban, the endgame and carrying the Amulet do). LEVELPORT_DEEP answers the prompt
with 50 (the top of the progress table). So a ring of teleport control plus two cursed scrolls of teleportation
score 0.78-0.81 wherever we are, past Medusa, the castle and the Valley in two turns.

A wand of wishing always gives two wishes: the engrave-test wish, rnd(3) - 1 more charges, and one wrested
charge (zap.c zappable(): 1 chance in 121 per zap at 0 charges; the wand then turns to dust). Dev evidence:
base3-jf14 s14 and s8, base4arm/base5arm-jf16 s5 found a wand of wishing on Dlvl 1-3 (2-4 wishes, spent on gray
dragon scale mail and life saving) and died at Dlvl 25-28.

WISH_CHARGING_FIRST: the first wish from the wand is '2 blessed scrolls of charging'. The route's wishes zap the wand
down to (x:0) (the first 'Nothing happens' tells an unknown count), then one scroll is read on it: read.c recharge()
gives a never-recharged wand of wishing 3 charges (blessed; a second recharge explodes it), i.e. c + 2 wishes in all.

  route_wish(agent)                  the next wish the route still needs, or None
  note_wished(agent, text, letter)   remember where the wished (cursed) scrolls went
  teleport_route_strategy(agent)     put the ring on, wrest the wand, read the scrolls
"""

import re

import nle.nethack as nh
from nle.nethack import actions as A

from . import jf_config, utils
from . import objects as O
from .strategy import Strategy

TC_RING = O.from_name('teleport control', nh.RING_CLASS)
TELE_SCROLL = O.from_name('teleportation', nh.SCROLL_CLASS)
WISH_WAND = O.from_name('wishing', nh.WAND_CLASS)
WISH_TC_RING = 'blessed ring of teleport control'
# readobjnam: a count of 2 is granted when 2 < rnd(6) (4 times in 6), else 1; 3 would be granted only half the time
WISH_TELE_SCROLLS = '2 cursed scrolls of teleportation'
# WISH_CHARGING_FIRST: one scroll recharges the wand; the second is a spare (a lost one, the castle's own wand)
CHARGING_SCROLL = O.from_name('charging', nh.SCROLL_CLASS)
WISH_CHARGING = '2 blessed scrolls of charging'
# ROUTE_GLOVES_FIX: do_wear.c puts a ring on under uncursed gloves, but cursed gloves ('You cannot remove your gloves
# to put on the ring.') or a welded weapon block it without using a move -- the ring step looped (front-strong
# fs7-k6 s9: 385k steps after the castle wand). A blessed scroll of remove curse uncurses the whole pack.
REMOVE_CURSE = O.from_name('remove curse', nh.SCROLL_CLASS)
WISH_REMOVE_CURSE = 'blessed scroll of remove curse'
PUTON_BLOCKED = ('cannot remove your gloves', 'cannot free your weapon hand')
MAX_WREST_ZAPS = 500       # P(no wrest in 500 zaps) = (120/121)^500 ~ 1.6%

DUNGEONS_OF_DOOM, GEHENNOM = 0, 1


def _items(agent):
    return list(agent.inventory.items)


def tc_ring(agent):
    ring = next((i for i in _items(agent) if i.is_unambiguous() and i.object == TC_RING), None)
    if ring is None and jf_config.T_ROUTE_FIRE:
        # the ring we wished for, found by its letter: wished blind it is 'o - a ring' (no appearance to name) and wished
        # hallucinating the inventory glyph is a random one -- either way WISH_LEARN cannot name it, the route took it for no ring at
        # all and wished again until the wand was empty (wp14 W15-blind / W16-hallu: 12 of 12 games)
        # (item_manager.get_item_from_text turns a bare 'a ring' into an 'unknown' object while blind: no ring category, never
        # equipped -- so match the letter and the word, and ask _ring_on() whether it is worn)
        letter = getattr(agent, '_tc_ring_letter', None)
        if letter is not None:
            ring = next((i for i in _items(agent) if agent.inventory.items.get_letter(i) == letter and
                         'ring' in (i.text or '')), None)
    return ring


def _count(item):
    """The stack size: item.count, or (T_ROUTE_FIRE) the number the inventory line starts with -- an item parsed blind is an 'unknown'
    object with count 1 whatever '2 scrolls' says, and the route wished for more scrolls than it needed."""
    if jf_config.T_ROUTE_FIRE:
        m = re.match(r'(\d+) ', item.text or '')
        if m:
            return int(m.group(1))
    return item.count


def _ring_on(ring):
    """The ring is worn: the item flag, or the inventory line says '(on left hand)' (an item parsed blind has no flag)."""
    return bool(ring.equipped) or (jf_config.T_ROUTE_FIRE and '(on ' in (ring.text or ''))


def wishing_wand(agent):
    """A wand of wishing that can still give a wish: not a cancelled one ('(0:-1)': zappable() never wrests from
    spe < 0, so zapping it would only burn MAX_WREST_ZAPS turns)."""
    return next((i for i in _items(agent) if i.is_unambiguous() and i.object == WISH_WAND and
                 not re.search(r'\(\d+:-\d+\)', i.text or '')), None)


def tele_scrolls(agent):
    """The stack the scroll wishes went to (they are cursed; the inventory doesn't show it: bknown is unset)."""
    letter = getattr(agent, '_tele_letter', None)
    if letter is None:
        return None
    for it in _items(agent):
        if agent.inventory.items.get_letter(it) == letter and it.category == nh.SCROLL_CLASS:
            return it
    return None


def charging_scroll(agent):
    """WISH_CHARGING_FIRST: the stack the charging wish went to (blessed unless Luck < 0; bknown is unset)."""
    letter = getattr(agent, '_charging_letter', None)
    if letter is None:
        return None
    for it in _items(agent):
        if agent.inventory.items.get_letter(it) == letter and it.category == nh.SCROLL_CLASS:
            return it
    return None


def _recharged(agent, wand):
    """The wand was recharged: by us, or its known count says so ('(1:3)'). A second recharge explodes it."""
    if getattr(agent, '_wish_recharged', False):
        return True
    m = re.search(r'\((\d+):-?\d+\)', wand.text or '') if wand is not None else None
    return m is not None and int(m.group(1)) > 0


def _known_empty(agent, wand):
    """A zap said 'Nothing happens' (agent.zap: inventory.empty_wands), or the known count is 0."""
    return agent.inventory.is_known_empty(wand) or bool(re.search(r'\(\d+:0\)', wand.text or ''))


def _spe_below_cap(wand):
    """T_ROUTE_EARLY_CHARGE: reading a blessed charging scroll on a wand of wishing sets spe to 3 when it is below 3, and
    explodes the wand at 3 (read.c recharge: spe++ then wand_explode when > 3). The wish that asked for the scroll has
    spent a charge, so spe <= 2 -- unless the displayed count says otherwise."""
    m = re.search(r'\((\d+):(-?\d+)\)', wand.text or '')
    return m is None or int(m.group(2)) < 3


def _charging_wanted(agent):
    """WISH_CHARGING_FIRST: the next wand wish is the charging scrolls (asked once; a wish for them that failed --
    Luck, a full pack -- leaves the old route)."""
    if not jf_config.WISH_CHARGING_FIRST or getattr(agent, '_charging_asked', False) or \
            charging_scroll(agent) is not None or not _wand_source(agent):
        return False
    return not _recharged(agent, wishing_wand(agent))


def note_asked(agent, text):
    """The wish prompt was answered with `text` (power.note_wish)."""
    if text == WISH_CHARGING:
        agent._charging_asked = True
    elif text == WISH_REMOVE_CURSE:
        agent._remove_curse_asked = True


def _wand_source(agent):
    """The wish comes from a wand of wishing (an engrave-test or a zap just now, or one we know): >= 2 wishes. A
    throne, fountain or lamp gives one, and a ring of teleport control alone scores nothing."""
    return wishing_wand(agent) is not None or \
        agent.step_count - getattr(agent, '_last_wand_use_step', -10 ** 9) <= 60


def _tc_known(agent):
    """A TC ring we wished/identified, or (TC_ROUTE) teleport control learned any other way: the intrinsic from a
    tengu, a ring the game's TC prompts proved."""
    if tc_ring(agent) is not None:
        return True
    if jf_config.TC_ROUTE:
        from . import power_route   # (power_route imports power, which imports this module)
        return power_route.tc_known(agent)
    return False


def route_wish(agent):
    if not jf_config.WISH_TELEPORT_ROUTE or getattr(agent, '_tele_route_done', False):
        return None
    if _charging_wanted(agent):
        return WISH_CHARGING
    if not _tc_known(agent):
        # the ring is worth a wish when more wishes follow (a wand: the scrolls come next) -- and with TC_ROUTE even
        # a single one (fountain demon, throne, lamp): 9 of 12 revealed castle kits carry teleport scrolls, 1 in 8
        # of them cursed, which the castle gamble / identify / altar tests turn into jumps; power-route's estimate
        # of P(score > 0.647): TC ring 8-10%, levitation ring ~5%, gray dragon scale mail ~1%
        return WISH_TC_RING if (_wand_source(agent) or jf_config.TC_ROUTE) else None
    if jf_config.ROUTE_GLOVES_FIX and getattr(agent, '_tele_puton_blocked', False) and \
            not getattr(agent, '_remove_curse_asked', False) and remove_curse_scroll(agent) is None:
        return WISH_REMOVE_CURSE
    scrolls = tele_scrolls(agent)
    # T_ROUTE_FIRE: in Gehennom the first jump is behind us and ONE scroll is the second -- jf95 s13 (T_ROUTE_TOP) wished for two
    # more in the Valley, one turn each, and died there with the scroll it already held unread
    need = 1 if (jf_config.T_ROUTE_FIRE and agent.blstats.dungeon_number == GEHENNOM) else 2
    if scrolls is None or _count(scrolls) < need:
        return WISH_TELE_SCROLLS
    return None


# --- single_wish_value (t-route): what ONE wish is worth to the T route, for the wishes lane's single-wish policy ---
# P(pass) of the route by state, castle depth uniform over 25..29 (a single controlled jump passes only at 29: the
# Valley is castle + 1). Harness T-kits (ledger, t-route results): TC worn/known + 2 known-cursed scrolls 45/45 (K1/K2),
# one known-cursed scroll 9/45 = 0.20 (K3, = the castle-29 share); real wand-of-wishing games 8 of 8 (F309).
T_P_TWO = 0.90         # TC + 2 sure triggers
T_P_AT29 = 0.20        # castle depth 29
T_P_SECOND = 0.05      # a 2nd trigger found elsewhere (a level teleporter, the confused lottery) after a single jump
T_P_NONE = 0.02        # TC and only scrolls of unknown BUC (T_BLIND_READ: a stack is cursed 1 time in 8; ~49% of games hold one,
                       # a pass needs a stack of 2 or castle 29), level teleporters met on the way (census F309)
T_P_NONE_BASE = 0.003  # the same without T_BLIND_READ: the wishes lane's harness, a bare TC ring on 61 real kits x 5 salts 8/305 vs 7/305


def _p_pass(tc, tickets):
    if not tc:
        return 0.0
    if tickets >= 2:
        return T_P_TWO
    if tickets == 1:
        return T_P_AT29 * T_P_TWO + (1 - T_P_AT29) * T_P_SECOND
    return T_P_NONE if jf_config.T_BLIND_READ else T_P_NONE_BASE


def single_wish_value(agent):
    """(wish text, estimated gain in P(pass)) of the best wish the T route could make with the pack as it is, or
    (None, 0.0) when no T wish is worth asking for. The wishes lane compares it with its other single-wish candidates
    (a lasting lift, ...) and asks for this one only when it wins; route_wish() stays the wand-of-wishing path."""
    try:
        from . import power_route
        tc = _tc_known(agent)
        tickets = sum(i.count for i in power_route.cursed_tele_scrolls(agent))
        now = _p_pass(tc, tickets)
        options = [(WISH_TELE_SCROLLS, _p_pass(tc, tickets + 2))]
        if not tc:
            options.append((WISH_TC_RING, _p_pass(True, tickets)))
        text, p = max(options, key=lambda o: o[1])
        gain = p - now
        return (text, gain) if gain > 0.005 else (None, 0.0)
    except Exception:
        return (None, 0.0)


def remove_curse_scroll(agent):
    """ROUTE_GLOVES_FIX: the stack the remove curse wish went to."""
    letter = getattr(agent, '_remove_curse_letter', None)
    if letter is None:
        return None
    for it in _items(agent):
        if agent.inventory.items.get_letter(it) == letter and it.category == nh.SCROLL_CLASS:
            return it
    return None


def note_wished(agent, text, letter):
    if text == WISH_TC_RING:
        agent._tc_ring_letter = letter
    if text == WISH_TELE_SCROLLS:
        agent._tele_letter = letter
        agent.log(f'TELEPORT route: cursed scrolls of teleportation at {letter!r}')
    elif text == WISH_CHARGING:
        agent._charging_letter = letter
        agent.log(f'TELEPORT route: blessed scrolls of charging at {letter!r}')
    elif text == WISH_REMOVE_CURSE:
        agent._remove_curse_letter = letter
        agent.log(f'TELEPORT route: blessed remove curse at {letter!r}')


def _read_charging(agent, wand, scroll):
    """Read the charging scroll on the wand ('This is a charging scroll.' -> 'What do you want to charge?')."""
    sl = agent.inventory.items.get_letter(scroll)
    wl = agent.inventory.items.get_letter(wand)
    agent.log(f'TELEPORT route: reading {scroll.text!r} ({sl}) on {wand.text!r} ({wl})')
    agent._wish_recharged = True     # whatever happens: a second recharge would explode the wand
    with agent.atom_operation():
        agent.step(A.Command.READ)
        agent.type_text(sl)
        if 'What do you want to charge?' in agent.single_message:
            agent.type_text(wl)
        if 'What do you want to charge?' in agent.single_message:
            agent.step(A.Command.ESC)
    agent.log(f'TELEPORT route: charging -> {agent.message[:160]!r}')
    agent.inventory.empty_wands.discard(wand.text)
    agent._tele_zaps = 0
    agent.inventory.items.update(force=True)


def _wallwalker_ok(agent):
    """CASTLE_TREASURY: a wall-walking form runs the route too -- the xorn that took the castle's wand of wishing has
    hands, eyes and fingers (monst.c: no M1_NOHANDS/NOEYES/NOLIMBS), so it zaps, reads and puts the ring on, and the
    Valley below is where its form would run out before the route could start."""
    if not jf_config.CASTLE_TREASURY:
        return False
    try:
        from . import castle_cross
        return castle_cross.wallwalker(agent)
    except Exception:
        return False


def _scroll_seen(scroll):
    """The scroll's label was seen (dknown): the inventory line names its appearance ('labeled X', 'unlabeled', 'called')
    or its type. A scroll wished or picked up while blind shows as a bare '2 scrolls'."""
    t = (scroll.text or '') if scroll is not None else ''
    return any(w in t for w in ('labeled', 'called', ' of '))


def _status_blocks_read(agent, scroll):
    """A status that makes a read wrong. Stunned or confused: always (a random level / our energy instead of the wand).
    T_ROUTE_FIRE: read.c doread() refuses a blind hero only a scroll never seen ('Being blind, you cannot read the formula on the
    scroll' tests dknown), level_tele() looks at neither blindness nor hallucination -- the route used to wait for both to
    pass, hundreds of turns on a tower square."""
    prop = agent.character.prop
    if prop.stun or prop.confusion:
        return True
    if jf_config.T_ROUTE_FIRE:
        return bool(prop.blind) and not _scroll_seen(scroll)
    return bool(prop.blind or prop.hallu)


def _prayer_due(agent):
    """A safe emergency prayer is due (mino_guard's _prayer_first): its 3 invulnerable turns and full HP come before the
    route's next zap when the route runs above the emergency layer (T_ROUTE_TOP)."""
    try:
        mino = getattr(agent.global_logic, 'mino', None)
        return bool(mino is not None and mino._prayer_first())
    except Exception:
        return False


def _elbereth_wanted(agent):
    """ROUTE_ELBERETH: something that respects Elbereth stands next to us and nothing that ignores it does -> one dust Elbereth before
    the next route action (monmove.c onscary: all but @, minotaurs, shopkeepers/guards, blind and peaceful monsters; none in Gehennom).
    3.6.6 erases it only when WE attack (mon.c setmangry); a wand zap with no target, a ring and a read leave it, and a scared monster
    makes no melee attack (dochug: !scared). At most 2 tries per square (1 letter in 25 of a dust writing is garbled), 5 per route."""
    if not jf_config.ROUTE_ELBERETH:
        return False
    try:
        return _elbereth_wanted2(agent)
    except Exception:   # (a top-priority layer: a failed check must not stop the bot)
        return False


def _elbereth_wanted2(agent):
    bl = agent.blstats
    if bl.dungeon_number != DUNGEONS_OF_DOOM or agent.character.prop.blind or not agent.can_engrave():
        return False   # (the route only completes in the Dungeons; none of it in Gehennom, Elbereth is void there)
    if (agent.inventory.engraving_below_me or '').lower() == 'elbereth':
        return False
    tries = getattr(agent, '_route_elb', None)
    if tries is None:
        tries = agent._route_elb = {}
    here = (bl.dungeon_number, bl.level_number, int(bl.y), int(bl.x))
    if tries.get(here, 0) >= 2 or sum(tries.values()) >= 5:
        return False
    adj = [m for m in agent.get_visible_monsters() if max(abs(m[1] - bl.y), abs(m[2] - bl.x)) <= 1]
    if not adj:
        return False
    dive = agent.global_logic.dive
    return not any(dive._melee_ignores_elbereth(m[3]) for m in adj)


def _elbereth_write(agent):
    bl = agent.blstats
    here = (bl.dungeon_number, bl.level_number, int(bl.y), int(bl.x))
    agent._route_elb[here] = agent._route_elb.get(here, 0) + 1
    adj = [getattr(m[3], 'mname', '?') for m in agent.get_visible_monsters()
           if max(abs(m[1] - bl.y), abs(m[2] - bl.x)) <= 1]
    ok = agent.engrave('Elbereth')
    agent.log(f'TELEPORT route: Elbereth first (next to {adj}) -> {ok}, below me: {agent.inventory.engraving_below_me!r}')


def teleport_route_strategy(agent, top=False):
    """top=True is the T_ROUTE_TOP layer (the last, highest preempt of the chain): the same route, but only with the flag
    on and no safe prayer due; top=False is the original layer."""
    def f():
        if top and not jf_config.T_ROUTE_TOP:
            yield False
            return
        if not jf_config.WISH_TELEPORT_ROUTE or getattr(agent, '_tele_route_done', False) or \
                (agent.character.prop.polymorph and not _wallwalker_ok(agent)):
            yield False
            return
        bl = agent.blstats
        ring = tc_ring(agent)
        scrolls = tele_scrolls(agent)
        wand = wishing_wand(agent)
        if ring is None and scrolls is None and wand is None:
            yield False
            return
        if top and _prayer_due(agent):
            yield False
            return
        if (wand is not None or scrolls is not None) and _elbereth_wanted(agent):
            # (a wand or the wished scrolls in hand: the wish route has work; a bare TC ring is power_route's)
            yield True
            _elbereth_write(agent)
            return
        near = [m for m in agent.get_visible_monsters() if max(abs(m[1] - bl.y), abs(m[2] - bl.x)) <= 3]

        # 1) wear the ring of teleport control (the prompt needs it on; a cursed one staying on is fine)
        blocked = jf_config.ROUTE_GLOVES_FIX and getattr(agent, '_tele_puton_blocked', False)
        if blocked and ring is not None and not _ring_on(ring) and remove_curse_scroll(agent) is None and \
                getattr(agent, '_remove_curse_asked', False) and not getattr(agent, '_puton_retried', False):
            # the scroll is gone (read by us or by another strategy -- power_route's castle gamble reads unknown
            # scrolls): try the ring once more
            agent._puton_retried = True
            agent._tele_puton_blocked = blocked = False
        if ring is not None and not _ring_on(ring) and blocked:
            rc = remove_curse_scroll(agent)
            if rc is not None:
                yield True
                rl = agent.inventory.items.get_letter(rc)
                agent.log(f'TELEPORT route: reading {rc.text!r} ({rl}): the ring is blocked')
                with agent.atom_operation():
                    agent.step(A.Command.READ)
                    agent.type_text(rl)
                agent.log(f'TELEPORT route: remove curse -> {agent.message[:120]!r}')
                agent._tele_puton_blocked = False
                agent._remove_curse_letter = None
                agent.inventory.items.update(force=True)
                return
            if route_wish(agent) != WISH_REMOVE_CURSE or wand is None:
                yield False   # nothing left to lift the curse: no loop on a put-on that takes no time
                return
            # else: on to step 2, which zaps the wand for the remove curse
        elif ring is not None and not _ring_on(ring):
            worn = [i for i in _items(agent) if i.category == nh.RING_CLASS and i.equipped]
            if len(worn) >= 2:
                # ROUTE_RING_SWAP: take one off (not a known-cursed one: 'You can't. It is cursed.') -- the route gave up
                # for good and looped: castle-redteam rt-ik-smoke jf73 s1 took the castle's wand of wishing, wished the
                # TC ring, then sat on 'both ring fingers busy' (two lift-test rings on) until a xorn killed it
                if jf_config.ROUTE_RING_SWAP and getattr(agent, '_tele_ring_swaps', 0) < 4:
                    from .item import Item   # (lazy: item -> inventory -> power -> tele_route)
                    off = [i for i in worn if getattr(i, 'status', None) != Item.CURSED and
                           not (i.is_unambiguous() and i.object.name == 'teleport control')]
                    if off:
                        agent._tele_ring_swaps = getattr(agent, '_tele_ring_swaps', 0) + 1
                        yield True
                        letter = agent.inventory.items.get_letter(off[0])

                        def rgen():
                            if 'What do you want to remove?' in agent.single_message:
                                yield letter

                        agent.log(f'TELEPORT route: both ring fingers busy, taking off {off[0].text!r}')
                        with agent.atom_operation():
                            agent.step(A.Command.REMOVE, rgen())
                        agent.log(f'TELEPORT route: remove -> {(agent.message or "")[:120]!r}')
                        agent.inventory.items.update(force=True)
                        return
                    if jf_config.ROUTE_GLOVES_FIX and not getattr(agent, '_remove_curse_asked', False):
                        # both worn rings cursed (do_wear.c: 'You can't. It is cursed.' makes them known): the same
                        # blessed remove curse ROUTE_GLOVES_FIX wishes for (rt-ik-swap jf73 s1: a cursed opal ring and
                        # a cursed levitation ring)
                        agent._tele_puton_blocked = True
                        agent.log('TELEPORT route: both worn rings are cursed -> blessed remove curse')
                        yield False
                        return
                agent.log('TELEPORT route: both ring fingers busy, cannot put the ring of teleport control on')
                yield False
                return
            yield True
            letter = agent.inventory.items.get_letter(ring)

            def gen():
                if 'What do you want to put on?' not in agent.single_message:
                    return
                yield letter
                if utils.asks_ring_hand(agent.single_message):
                    # T_ROUTE_FIRE: the LEFT finger -- a welded one-handed weapon (cursed pick-axe) is wielded in the right hand
                    # and do_wear.c refuses 'You cannot free your weapon hand' for the right finger only
                    yield 'l' if jf_config.T_ROUTE_FIRE else 'r'

            agent.log(f'TELEPORT route: putting on {ring.text!r}')
            with agent.atom_operation():
                agent.step(A.Command.PUTON, gen())
            if jf_config.ROUTE_GLOVES_FIX and any(w in (agent.message or '') for w in PUTON_BLOCKED):
                agent.log(f'TELEPORT route: the ring is blocked: {agent.message[:120]!r}')
                agent._tele_puton_blocked = True
            agent.inventory.items.update(force=True)
            return

        # 2) the wishes the route still needs: zap the wand, wresting its last charge when it is empty
        need = route_wish(agent)
        # WISH_CHARGING_FIRST: at (x:0), before any wrest (a wrest turns the wand to dust), read a charging scroll
        charging = charging_scroll(agent) if jf_config.WISH_CHARGING_FIRST else None
        # T_ROUTE_FIRE: the route is ~6-9 game turns of zaps/reads that end in a level teleport (everything but M2_STALK
        # followers stays behind); a monster in view within 3 (asleep, peaceful, behind a door...) used to hold every zap
        # back, and on a tower square or a castle landing the fight never ended. Only the 121-zap wrest loop still waits.
        quiet = not near
        if jf_config.T_ROUTE_FIRE and near and wand is not None and \
                not (_known_empty(agent, wand) and (charging is None or _recharged(agent, wand))):
            quiet = True
        early = jf_config.T_ROUTE_EARLY_CHARGE and charging is not None and wand is not None and \
            not _recharged(agent, wand) and _spe_below_cap(wand)
        if charging is not None and need is not None and wand is not None and quiet and \
                (_known_empty(agent, wand) or early) and not _recharged(agent, wand):
            if not _status_blocks_read(agent, charging):
                # (confused, the scroll charges our energy instead)
                yield True
                _read_charging(agent, wand, charging)
                return
            if jf_config.T_ROUTE_FIRE and _known_empty(agent, wand):
                yield False   # at (x:0) with the scroll waiting for a clear head: a wrest zap (1 in 121) only burns turns
                return
        if need is not None and wand is not None and quiet:
            zaps = getattr(agent, '_tele_zaps', 0)
            if zaps < MAX_WREST_ZAPS:
                yield True
                agent._tele_zaps = zaps + 1
                if zaps % 50 == 0:
                    agent.log(f'TELEPORT route: zapping {wand.text!r} for {need!r} (zap {zaps + 1})')
                agent.zap(wand, None)
                agent.inventory.items.update(force=True)
                return

        # 3) read: in the Dungeons once two scrolls are in hand (or no more wishes can come), then once in Gehennom
        if scrolls is None or ring is None or not _ring_on(ring):
            yield False
            return
        dnum = bl.dungeon_number
        if dnum not in (DUNGEONS_OF_DOOM, GEHENNOM) or _status_blocks_read(agent, scrolls):
            yield False   # Sokoban/Mines/Quest: no controlled trip to Gehennom; stunned or confused: a random one
            return
        if dnum == GEHENNOM and getattr(agent, '_tele_route_gehennom', False):
            yield False
            return
        if dnum == DUNGEONS_OF_DOOM and _count(scrolls) < 2 and need is not None and wand is not None and \
                getattr(agent, '_tele_zaps', 0) < MAX_WREST_ZAPS and not (jf_config.T_ROUTE_FIRE and bl.depth >= 29):
            # (T_ROUTE_FIRE: not on a depth-29 castle -- the Valley below it is depth 30, one jump is the pass)
            yield False   # another wish is coming: go through both levels in one go
            return
        yield True
        key = (bl.dungeon_number, bl.level_number)
        letter = agent.inventory.items.get_letter(scrolls)
        agent.log(f'TELEPORT route: reading {scrolls.text!r} ({letter}) on {key}, depth {bl.depth}')
        with agent.atom_operation():
            agent.step(A.Command.READ)
            agent.type_text(letter)
        agent.inventory.items.update(force=True)
        after = agent.blstats
        agent.log(f'TELEPORT route: now on {(after.dungeon_number, after.level_number)} depth {after.depth}: '
                  f'{agent.message[:120]!r}')
        if dnum == GEHENNOM:
            agent._tele_route_gehennom = True
            agent._tele_route_done = True

    return Strategy(f)
