"""SHOP_WISH (castle-entry lane, ledger F334/F314): the unaffordable wand of wishing on a shop shelf.

The wand lottery is where every realised pass of the base comes from: a wand of wishing that is engrave-tested gives a wish at
once, and the wish route (tele_route.py: a ring of teleport control, two cursed scrolls of teleportation) takes the hero past
the Castle in two turns (harness 24/24). F334: 3 of the 9 wands of wishing the bot saw in 720 real games sat on the shelf of a
general store on Dlvl 3-4, quoted 667-889 zm, and were left there (median gold 47 at XL 7, F320).

NetHack 3.6.6 (handoff/nethack-3.6.6/src), what this relies on:
  * objects.c: wishing and death are the only base-500 wands (prob 5 each). shk.c get_cost() turns the base into the shelf quote
    of ONE unidentified object: base x charisma factor (>18: 1/2, 18: 2/3, 16-17: 3/4, 11-15: 1, 8-10: 4/3, 6-7: 3/2, <=5: 2),
    x 4/3 for one object in four (o_id % 4 == 0, type not identified), x 4/3 for a dunce cap / a Tourist below XL 15 / a shirt
    with no suit or cloak over it. possible_quotes() below enumerates them; a quote no other wand base (100, 150, 175, 200) can
    produce is wishing or death, one in two each.
  * pickup of shop goods needs no gold (shk.c addtobill); an unpaid wand can be engrave-tested: engrave.c doengrave WAND_CLASS
    zappable() takes a charge, check_unpaid() bills a USAGE FEE to the shopkeeper's debit (nothing when the charge taken was the
    last one: spe <= 0; the full quote at spe 1, a quarter at spe > 1: shk.c cost_per_charge), zapnodir() of a wand of wishing is
    makewish() (zap.c), a wand of death only prints 'The bugs on the floor stop moving!' (the same line as sleep).
  * the wish route and the wrest zaps run in the shop (the ring goes on, scrolls are read there) and the hero leaves by LEVEL
    TELEPORT. That IS a robbery: do.c goto_level() calls check_special_room(TRUE) before it leaves the OLD level, shk.c
    u_left_shop(newlev) -> rob_shop() ('You escaped the shop without paying!', alignment -1, setpaid() so the wand becomes ours,
    hot_pursuit) and call_kops() puts the Kops near the down stairs and the shopkeeper. Harmless once the hero is gone -- unless
    the shopkeeper stands next to the hero: a pursuing shopkeeper comes along (dog.c keepdogs: levl_follower is_fshk), so the
    test square is chosen at least 3 squares from him. (t-route's F334 read the NEW level's room table; the first harness run
    printed the robbery message right after the level prompt.) Walking out with a bill is the deadly kind: so while anything is
    unpaid agent.bfs() closes the shop's door squares.
  * a wand of death is the other half: its test leaves a usage fee on the debit (quote / 4, the wand has 4-8 charges) that
    must be paid before the hero can leave on foot (dopay pays the debit first); settle() pays it from the gold we have or from
    junk sold to the shopkeeper (SHOP_WISH_SELL), then drops the wand back on the shelf.

Flow (Strategy `strategy`, first in global_logic's shop layer, so buy_food / buy_instrument never drop the unpaid wand):
  scan   inside a shop of the Dungeons of Doom (no hostile in view, nothing wrong with us): walk onto each shelf square whose map
         glyph is a wand, so the 'for sale' quote shows;
  take   a wand whose quote only wishing / death can produce goes into the pack (unpaid); gold >= quote: just pay;
  test   on a free shop square: Inventory._engrave_single_wand(): 'You may wish for an object.' -> the agent's wish handler
         answers with tele_route's wish and tele_route.teleport_route_strategy (above this layer) does the rest;
  settle the death branch (above).
Only the Dungeons of Doom: a controlled level teleport from the Mines would land at the Mines' end.
"""
import re

import nle.nethack as nh
import numpy as np
from nle.nethack import actions as A

from . import jf_config
from . import objects as O
from .exceptions import AgentPanic
from .glyph import Hunger
from .level import Level
from .strategy import Strategy

BASE500 = frozenset({'wishing', 'death'})
WATCHDOG_TURNS = 400        # game turns the wish route gets after a wishing verdict before the wand is given back
_WAND_GLYPHS = None


def _wand_glyphs():
    global _WAND_GLYPHS
    if _WAND_GLYPHS is None:
        _WAND_GLYPHS = np.array([nh.GLYPH_OBJ_OFF + i for i in range(nh.NUM_OBJECTS)
                                 if ord(nh.objclass(i).oc_class) == nh.WAND_CLASS], dtype=np.int64)
    return _WAND_GLYPHS


# ------------------------------------------------------------------------------------------------ price knowledge

def possible_quotes(base, cha, dunce):
    """Every quote shk.c get_cost can give for ONE unidentified object of this base price, as a set (the 1-in-4
    surcharge on or off; dunce: a dunce cap, a Tourist below XL 15 or a visible shirt)."""
    out = set()
    for surcharge in (False, True):
        mult, div = 1, 1
        if surcharge:
            mult, div = mult * 4, div * 3
        if dunce:
            mult, div = mult * 4, div * 3
        if cha > 18:
            div *= 2
        elif cha == 18:
            mult, div = mult * 2, div * 3
        elif cha >= 16:
            mult, div = mult * 3, div * 4
        elif cha <= 5:
            mult *= 2
        elif cha <= 7:
            mult, div = mult * 3, div * 2
        elif cha <= 10:
            mult, div = mult * 4, div * 3
        tmp = base * mult
        if div > 1:
            tmp = (tmp * 10 // div + 5) // 10
        out.add(max(tmp, 1))
    return out


def dunce_options(agent):
    """The quote multipliers that may apply besides charisma (a list of the possibilities)."""
    try:
        from .character import Character
        items = agent.inventory.items
        certain = (agent.character.role == Character.TOURIST and agent.blstats.experience_level < 15) or \
                  (items.shirt is not None and items.suit is None and items.cloak is None) or \
                  (items.helm is not None and items.helm.is_unambiguous() and items.helm.object.name == 'dunce cap')
        if certain:
            return [True]
        if items.helm is not None and any(o.name == 'dunce cap' for o in items.helm.objs):
            return [False, True]
    except Exception:
        pass
    return [False]


def wand_types_for_quote(agent, unit):
    """Names of the wand types whose base price can produce this unit quote."""
    cha = int(agent.blstats.charisma)
    opts = dunce_options(agent)
    out = set()
    for o in O.objects:
        if isinstance(o, O.Wand) and any(unit in possible_quotes(o.cost, cha, d) for d in opts):
            out.add(o.name)
    return out


def unit_quote(item):
    """The price of ONE unit as the shelf shows it (the text shows the stack's total), or None."""
    if not item.price or item.count < 1 or item.price % item.count:
        return None
    return item.price // item.count


def is_candidate(agent, item, st=None):
    """A wand for sale that only a wand of wishing / death can be: by its quote, and by what its appearance can still be."""
    from .item import Item
    if item.category != nh.WAND_CLASS or item.shop_status != Item.FOR_SALE or item.count != 1:
        return False
    unit = unit_quote(item)
    if unit is None:
        return False
    names = wand_types_for_quote(agent, unit) & {o.name for o in item.objs}
    return bool(names) and names <= BASE500


# ------------------------------------------------------------------------------------------------ state

class State:
    def __init__(self):
        self.scanned = set()        # (level key, y, x) shelf squares looked at
        self.finished = set()       # level keys where nothing more is to be done
        self.death_glyphs = set()   # appearances proven to be a wand of death
        self.tries = {}             # small retry counters
        self.price = {}             # wand glyph -> unit quote it was taken at
        self.debit = 0              # usage fee read from the messages (an estimate for settle)
        self.logged = set()
        self.result = None          # 'wishing' | 'death' | None
        self.taken = 0
        self.owes_level = None      # level key where a usage fee is on the shopkeeper's debit (the door stays closed)
        self.wishing_since = None   # game turn of the wishing verdict (watchdog: the wish route should be gone by WATCHDOG_TURNS)


def state(agent):
    st = getattr(agent, '_shop_wish', None)
    if st is None:
        st = agent._shop_wish = State()
    return st


def _log(agent, msg):
    agent.log(f'SHOPWISH {msg}')


def _note(agent, st, msg, limit=60):
    """A progress line, at most `limit` per game (the session's actions repeat while the hero walks)."""
    n = st.tries.get('notes', 0)
    if n < limit:
        st.tries['notes'] = n + 1
        _log(agent, msg)


# ------------------------------------------------------------------------------------------------ the pack

def unpaid_items(agent):
    from .item import Item, flatten_items
    return [i for i in flatten_items(agent.inventory.items) if i.shop_status == Item.UNPAID]


def held_wand(agent):
    """An unpaid wand in the pack (the one we took), or None."""
    for i in unpaid_items(agent):
        if i.category == nh.WAND_CLASS:
            return i
    return None


def holding(agent):
    """SHOP_WISH_LOCK: anything unpaid in the pack, or a usage fee on this level's shopkeeper's debit (cached per step:
    agent.bfs() asks all the time)."""
    if not jf_config.SHOP_WISH:
        return False
    c = getattr(agent, '_shop_wish_hold', None)
    if c is not None and c[0] == agent.step_count:
        return c[1]
    try:
        st = state(agent)
        key = agent.current_level().key()
        if st.owes_level is not None and st.owes_level != key:
            st.owes_level = None            # we left that level (a robbery clears the bill: shk.c setpaid): nothing is owed here
        v = bool(unpaid_items(agent)) or st.owes_level == key
    except Exception:
        v = False
    agent._shop_wish_hold = (agent.step_count, v)
    agent._shop_wish_holding = v        # (supply's buy / sell / scan stand aside while it is true)
    return v


def owes(agent):
    """A usage fee is on this level's shopkeeper's debit."""
    return jf_config.SHOP_WISH and state(agent).owes_level == agent.current_level().key()


def protected(agent):
    """The unpaid wand a session carries: pay_or_drop_unpaid() must not drop it."""
    if not jf_config.SHOP_WISH:
        return []
    w = held_wand(agent)
    return [w] if w is not None else []


def _kind(agent, st, wand):
    """'wishing' | 'death' | 'unknown' for the wand we hold."""
    if wand.is_unambiguous():
        if wand.object.name == 'wishing':
            return 'wishing'
        if wand.object.name == 'death':
            return 'death'
    if wand.glyphs and wand.glyphs[0] in st.death_glyphs:
        return 'death'
    return 'unknown'


# ------------------------------------------------------------------------------------------------ context

def _context_ok(agent):
    """May a session act now? (no agent action here)"""
    if not jf_config.SHOP_WISH:
        return False
    bl = agent.blstats
    prop = agent.character.prop
    if prop.polymorph or prop.blind or prop.hallu or prop.confusion or prop.stun:
        return False
    if bl.hunger_state >= Hunger.WEAK:
        return False
    level = agent.current_level()
    if level.dungeon_number != Level.DUNGEONS_OF_DOOM or not level.shop_interior.any():
        return False
    return True


def _in_shop(agent):
    level = agent.current_level()
    bl = agent.blstats
    return bool(level.shop[bl.y, bl.x] or level.shop_interior[bl.y, bl.x])


def _hostiles(agent):
    return bool(agent.get_visible_monsters())


# ------------------------------------------------------------------------------------------------ the plan

def _next_scan(agent, st):
    """The nearest reachable shelf square showing a wand that we have not looked at, or None."""
    level = agent.current_level()
    key = level.key()
    glyphs = agent.glyphs
    mask = level.shop_interior & np.isin(glyphs, _wand_glyphs())
    if not mask.any():
        return None
    dis = agent.bfs()
    best = None
    for y, x in zip(*mask.nonzero()):
        if (key, int(y), int(x)) in st.scanned or dis[y, x] == -1:
            continue
        if best is None or dis[y, x] < best[0]:
            best = (dis[y, x], int(y), int(x))
    return best


def plan(agent):
    """What to do now: None | ('scan', y, x) | ('take', item) | ('test', wand) | ('settle', wand). No agent action."""
    st = state(agent)
    level = agent.current_level()
    wand = held_wand(agent)
    if wand is not None:
        kind = _kind(agent, st, wand)
        if kind == 'wishing':
            if st.wishing_since is None:
                # (the engrave test of a wand of wishing is cut short by the wish route taking over, so _test never sets this)
                st.wishing_since = int(agent.blstats.time)
            elif agent.blstats.time - st.wishing_since > WATCHDOG_TURNS:
                # the wish route has not taken us away (it never started, or something it needs is missing): the shop's door is
                # shut while anything is unpaid -- put the wand back and pay the fee, the game goes on as the base would play it
                _log(agent, f'watchdog: {agent.blstats.time - st.wishing_since} turns since the wishing verdict, still here: '
                            f'giving the wand back')
                st.result = 'abandoned'
                st.wishing_since = None
                return ('settle', wand)
            return None                     # tele_route's: wishes, ring, scrolls, the controlled jump
        if kind == 'death' or st.tries.get('tests', 0) >= 2:
            return ('settle', wand)         # (a wand tested twice with no verdict goes back as well: every test costs a charge)
        return ('test', wand)
    if st.owes_level == level.key() and st.result != 'wishing':
        return ('settle', None)
    if level.key() in st.finished or not _context_ok(agent) or not _in_shop(agent):
        return None
    if _hostiles(agent) or agent._carries_digging_tool():
        return None
    here = (level.key(), int(agent.blstats.y), int(agent.blstats.x))
    for it in agent.inventory.items_below_me:
        if is_candidate(agent, it, st) and st.tries.get(('take',) + here, 0) < 2:
            return ('take', it)
    target = _next_scan(agent, st)
    if target is not None:
        return ('scan', target[1], target[2])
    return None


# ------------------------------------------------------------------------------------------------ actions

def _scan(agent, st, y, x):
    level = agent.current_level()
    key = (level.key(), y, x)
    st.scanned.add(key)
    dis = agent.bfs()
    if dis[y, x] == -1:
        return
    if (agent.blstats.y, agent.blstats.x) != (y, x):
        agent.go_to(y, x)
    if (agent.blstats.y, agent.blstats.x) == (y, x):
        agent.inventory.get_items_below_me()
        for it in agent.inventory.items_below_me:
            if it.category == nh.WAND_CLASS:
                unit = unit_quote(it)
                types = sorted(wand_types_for_quote(agent, unit) & {o.name for o in it.objs}) if unit else None
                _log(agent, f'wand on the shelf at {(y, x)}: {it.text!r} unit quote {unit} cha {int(agent.blstats.charisma)}'
                            f' gold {int(agent.blstats.gold)} -> {types if types is None or len(types) < 6 else "many"}')


def _take(agent, st, item):
    inv = agent.inventory
    unit = unit_quote(item)
    bl = agent.blstats
    tk = ('take', agent.current_level().key(), int(bl.y), int(bl.x))
    st.tries[tk] = st.tries.get(tk, 0) + 1
    _log(agent, f'taking {item.text!r} (quote {unit}, gold {int(bl.gold)}) at {(int(bl.y), int(bl.x))}')
    inv.pickup(item, 1)
    inv.items.update(force=True)
    st.taken += 1
    w = held_wand(agent)
    if w is None:
        _log(agent, 'the pickup left nothing unpaid in the pack')
        return
    if w.glyphs:
        st.price[w.glyphs[0]] = unit
    if int(agent.blstats.gold) >= (unit or 10 ** 9):
        agent.step(A.Command.PAY)       # we can afford it: just pay (the generic [yn] handler answers 'y')
        inv.items.update(force=True)
        _log(agent, f'paid: {"yes" if held_wand(agent) is None else "NO"}')


def _shk_positions(agent):
    from .glyph import G
    return [(int(y), int(x)) for y, x in zip(*np.nonzero(np.isin(agent.glyphs, list(G.SHOPKEEPER))))]


def _free_square(agent, st):
    """The empty shop-interior square to engrave (and then run the wish route) on. The level teleport that ends the route is a
    robbery for the shopkeeper (hack.c check_special_room(TRUE) runs on the OLD level, shk.c u_left_shop -> rob_shop: 'You escaped
    the shop without paying!', he goes into hot pursuit), and a pursuing shopkeeper NEXT to us when we leave comes along (dog.c
    keepdogs: is_fshk). So: 3+ squares from him if any such square, else 2, else (nothing else) next to him; within a tier the
    hero's own square wins (no walking back and forth between two equally good squares: runs/sw-dg7 seed 0), then the nearest."""
    from .glyph import G
    level = agent.current_level()
    bl = agent.blstats
    inv = agent.inventory
    shks = _shk_positions(agent)

    def tier(y, x):
        d = min([max(abs(y - sy), abs(x - sx)) for sy, sx in shks] or [9])
        return 0 if d >= 3 else 1 if d == 2 else 2

    def bad(y, x):
        return st.tries.get(('bad', level.key(), int(y), int(x)), 0) > 0

    dis = agent.bfs()
    glyphs = agent.glyphs
    free = level.shop_interior & (level.item_count == 0) & (dis != -1) & ~np.isin(glyphs, list(G.OBJECTS)) & \
        ~np.isin(glyphs, list(G.MONS))
    best = None
    if level.shop_interior[bl.y, bl.x] and not inv.items_below_me and level.item_count[bl.y, bl.x] == 0 and \
            not bad(bl.y, bl.x):
        best = ((tier(bl.y, bl.x), 0), int(bl.y), int(bl.x))
    for y, x in zip(*free.nonzero()):
        if bad(y, x):
            continue
        key = (tier(y, x), int(dis[y, x]))
        if best is None or key < best[0]:
            best = (key, int(y), int(x))
    return None if best is None else (best[1], best[2])


def _test(agent, st, wand):
    inv = agent.inventory
    level = agent.current_level()
    if not agent.can_engrave() or agent.character.prop.polymorph:
        _log(agent, 'cannot engrave now: waiting')
        agent.search(1)
        return
    spot = _free_square(agent, st)
    if spot is None:
        _log(agent, 'no empty shop square to engrave on: dropping the wand back')
        inv.drop([wand])
        st.finished.add(level.key())
        return
    bl = agent.blstats
    if (int(bl.y), int(bl.x)) != spot:
        _note(agent, st, f'walking to the test square {spot}')
        try:
            agent.go_to(*spot)
        except AgentPanic as e:        # (the shopkeeper stepped into the way, the square filled up: take another one)
            key = ('bad', level.key(), spot[0], spot[1])
            st.tries[key] = st.tries.get(key, 0) + 1
            _log(agent, f'could not walk to {spot} ({e}): another square')
        return
    glyph = wand.glyphs[0] if wand.glyphs else None
    _log(agent, f'engrave-testing {wand.text!r} at {spot}')
    with agent.atom_operation():
        types = inv._engrave_single_wand(wand)
    if types is None:
        key = ('bad', level.key(), spot[0], spot[1])
        st.tries[key] = st.tries.get(key, 0) + 1
        st.tries['engrave_fail'] = st.tries.get('engrave_fail', 0) + 1
        _log(agent, f'the engrave test said nothing usable on {spot} ({st.tries["engrave_fail"]})')
        if st.tries['engrave_fail'] >= 4:
            inv.drop([wand])
            st.finished.add(level.key())
        return
    st.tries['tests'] = st.tries.get('tests', 0) + 1
    names = {o.name for o in types}
    if glyph is not None:
        inv.item_manager._already_engraved_glyphs.add(glyph)
        inv.item_manager._glyph_to_possible_wand_types[glyph] = types
        inv.item_manager.possible_objects_from_glyph(glyph)
    msg = agent.message or ''
    m = re.search(r'Usage fee, (\d+)', msg)
    if m:
        st.debit += int(m.group(1))
    _log(agent, f'engrave test -> {sorted(names)} usage fee {st.debit}')
    # a wand with more than one charge left bills a usage fee (shk.c cost_per_charge); the message may have scrolled by, so the
    # door stays closed until a PAY says there is nothing (more) to pay
    st.owes_level = level.key()
    if not st.debit:
        st.debit = (st.price.get(glyph, 0) or 0) // 4 + 1
    inv.items.update(force=True)
    if names == {'wishing'}:
        st.result = 'wishing'
        st.wishing_since = int(agent.blstats.time)
    elif 'wishing' not in names and glyph is not None and glyph in st.price:
        # the quote only wishing and death can produce, and the engrave test made no wish (a wand of wishing always does:
        # zapnodir -> makewish): death. The grind's test says only 'glows, then fades' (the dust wands print their line after
        # the text, which the grind does not write), the dive's test 'the bugs stop moving'
        st.result = 'death'
        st.death_glyphs.add(glyph)
        inv.item_manager._glyph_to_possible_wand_types[glyph] = [O.from_name('death', nh.WAND_CLASS)]
        inv.item_manager.possible_objects_from_glyph(glyph)
        inv.items.update(force=True)


def _junk(agent, keep_wand):
    """Items we can sell to pay a debt, most valuable first (never worn / wielded / unpaid / the digging tool)."""
    from .item import Item, flatten_items
    out = []
    for it in flatten_items(agent.inventory.items):
        if it.equipped or it.shop_status == Item.UNPAID or it is keep_wand or it.category in (nh.COIN_CLASS, nh.FOOD_CLASS):
            continue
        if any(o.name in ('pick-axe', 'dwarvish mattock') for o in it.objs):
            continue
        if it.is_container():
            continue
        cost = max((getattr(o, 'cost', 0) or 0) for o in it.objs) if it.objs else 0
        if it.category in (nh.WEAPON_CLASS, nh.ARMOR_CLASS) and cost <= 20:
            continue
        out.append((cost * it.count, it))
    out.sort(key=lambda t: -t[0])
    return [it for _, it in out]


def _sell(agent, item):
    """Drop the whole stack in the shop and accept the shopkeeper's offer. The offer ('Possogroenoe offers 56 gold pieces for your
    steel wand.  Sell it? [ynaq] (y)') is recognised by its text: NLE's misc[0] flag was not set for it, so a first version that
    waited for the flag sold nothing and the generic prompt handler quit every offer (runs/sw-j-f1)."""
    inv = agent.inventory
    letter = inv.items.get_letter(item)

    def gen():
        yield letter
        for _ in range(8):
            obs = agent._observation
            sm = agent.single_message or ''
            if '[ynaq]' in sm or '[yn]' in sm or 'Sell it?' in sm or 'Sell them?' in sm:
                yield 'y'
            elif obs['misc'][2]:          # --More--
                yield A.MiscAction.MORE
            else:
                return

    gold0 = int(agent.blstats.gold)
    with agent.atom_operation():
        agent.step(A.Command.DROP, gen())
    inv.items.update(force=True)
    return int(agent.blstats.gold) - gold0


def _settle(agent, st, wand):
    """The death branch: the wand goes back on the shelf, then the usage fee on the debit is paid -- from the gold we have, else
    from junk sold to the shopkeeper (one sale per step) -- and the door is open again."""
    inv = agent.inventory
    level = agent.current_level()
    t = st.tries.get('settle', 0)
    st.tries['settle'] = t + 1
    if t > 60:
        _log(agent, 'settle: giving up (the door stays closed: robbery is worse than a stall)')
        st.finished.add(level.key())
        return
    if wand is not None:
        _log(agent, f'death branch: {wand.text!r} goes back on the shelf')
        inv.drop([wand])
        inv.items.update(force=True)
        return
    need = st.debit
    gold = int(agent.blstats.gold)
    if gold < need and jf_config.SHOP_WISH_SELL:
        for it in _junk(agent, None):
            key = ('sold', level.key(), it.text)
            if st.tries.get(key, 0):
                continue                    # (tried: the shopkeeper wanted nothing of it)
            st.tries[key] = 1
            got = _sell(agent, it)
            _log(agent, f'sold {it.text!r} for {got} (gold {int(agent.blstats.gold)}, need {need})')
            return                          # one sale attempt per step: the pack is rebuilt, the next step re-plans
        _log(agent, f'nothing left to sell (gold {int(agent.blstats.gold)}, need {need})')
    agent.step(A.Command.PAY)
    msg = agent.message or ''
    _log(agent, f'pay -> {msg[:160]!r} (gold {int(agent.blstats.gold)}, need {need})')
    inv.items.update(force=True)
    if 'pay that debt' in msg or 'debt is covered' in msg or 'do not owe' in msg or 'pay the remainder' in msg:
        st.debit = 0
        st.owes_level = None
        st.result = None
        st.finished.add(level.key())
        _log(agent, 'the usage fee is paid: the door is open again')
        return
    agent.search(3)         # not enough gold and nothing to sell: try again (the stall is the lesser evil)


# ------------------------------------------------------------------------------------------------ the strategy

MAX_ACTIONS = 60


def _plan_safe(agent):
    try:
        return plan(agent)
    except Exception as e:      # a planning bug must not take the agent down: log it (once per message) and stand aside
        st = state(agent)
        msg = f'{type(e).__name__}: {e}'
        if msg not in st.logged:
            st.logged.add(msg)
            _log(agent, f'plan failed: {msg[:200]}')
        return None


def _session(agent):
    """The whole session (scan, take, test, settle) in ONE body. agent.preempt() hands the layers BELOW this one the next action
    when a preempting body returns (a layer calls its own update functions again only after the base strategy's first step), so
    one action per call left the wand just taken to inventory.wand_engrave_identify: it engraved the unpaid wand at once, kept
    no record, the usage fee was never booked here and the shop's door stayed closed for good (runs/sw-dg3)."""
    st = state(agent)
    for _ in range(MAX_ACTIONS):
        p = _plan_safe(agent)
        if p is None:
            return
        before = agent.step_count
        kind = p[0]
        if kind != 'scan':
            _note(agent, st, f'session: {kind} at {(int(agent.blstats.y), int(agent.blstats.x))} turn {int(agent.blstats.time)}')
        if kind == 'scan':
            _scan(agent, st, p[1], p[2])
        elif kind == 'take':
            _take(agent, st, p[1])
        elif kind == 'test':
            _test(agent, st, p[1])
        elif kind == 'settle':
            _settle(agent, st, p[1])
        if agent.step_count == before:      # nothing was done in the game: do not spin
            st.tries['nostep'] = st.tries.get('nostep', 0) + 1
            if st.tries['nostep'] % 3 == 0:
                return


def strategy(agent):
    def f():
        if not jf_config.SHOP_WISH:
            yield False
            return
        p = _plan_safe(agent)
        if p is None:
            if held_wand(agent) is not None:
                st0 = state(agent)
                n = st0.tries.get('idle_logs', 0)
                if n < 12:
                    st0.tries['idle_logs'] = n + 1
                    _log(agent, f'holding {held_wand(agent).text!r} but the plan is empty (hostiles {_hostiles(agent)} '
                                f'in shop {_in_shop(agent)} context {_context_ok(agent)})')
            yield False
            return
        yield True
        _session(agent)

    return Strategy(f)
