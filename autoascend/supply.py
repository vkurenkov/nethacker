"""Supply lane (lane 4): what the bot carries to the Castle, bought in shops (jf_config 'supply lane' block).

The Castle's routes need things a Valkyrie almost never has when she arrives: a tonal instrument (the drawbridge
tune), a magic lamp (a wish), scare monster / earth / opening / striking. Shops sell them for a few dozen to a few
hundred zorkmids and the bot walks through ~1.3 shops per game without ever buying any of it. This module is the
shopping brain:

  * price knowledge: shop_math.py (shk.c get_cost) turns a quote on a shelf into the set of object types it can be,
    so a 'lamp' quoted 50 / 67 / 75 / 89 / 100 zm is a magic lamp (base 50) and one quoted 10-20 an oil lamp
    (objects.c; ledger F304), a 'horn' of base 15 is a tooled horn and one of base 50 is frost / fire / plenty;
  * glyph knowledge (ledger F308, user ruling 2026-10-01): the arena's glyphs of tools are not shuffled, so
    obs['glyphs'] / obs['inv_glyphs'] name the exact tool; glyph_obj() reads it, a per-square memory of the map glyph
    gives the type of a shelf item before we step on it (the LOOK text under us carries no glyph);
  * Supply.buy(): a preempt-chain strategy that walks to the most wanted affordable shelf item and pays for it;
    other lanes add wants through EXTRA_WANTS (id-engine: identify scrolls);
  * Supply.hold_food(): BUY_FOOD waits until the shop's shelves were all looked at, so food never eats the gold a
    lamp or an instrument needs;
  * keep rules for the pack (may_be_magic_lamp, magic_lamps) and the hand-over to the wishes lane (lane 5 rubs the
    lamp: wish_source.py reads magic_lamps(agent) or agent._magic_lamp_letters).

Everything is behind jf_config flags that are off in the commit that adds them (SUPPLY_*). The functions that only
read the pack or a shelf item are safe to call with the flags off.
"""
import math
import re

import nle.nethack as nh
import numpy as np
from nle.nethack import actions as A

from . import jf_config
from .exceptions import AgentPanic
from . import objects as O
from . import shop_math
from . import utils
from .glyph import G, Hunger, SHOP
from .item import Item, flatten_items
from .level import Level
from .strategy import Strategy

TONAL_NAMES = frozenset(('tooled horn', 'frost horn', 'fire horn', 'wooden flute', 'magic flute', 'wooden harp',
                         'magic harp', 'bugle'))
# the horns: blown (apply, improvise) they scare the monsters around (music.c awaken_monsters: a monster within a third of
# the range flees unless it resists). castle-gate R344/F347: horn kits die to the castle's minotaurs half as often
# (13/136 against 30/140 with a flute) and reach the crusher's crush_over 52% against 42-44%, so a horn is the instrument
# to carry; a horn of plenty is the only 'horn' that plays no tune
HORN_NAMES = frozenset(('tooled horn', 'frost horn', 'fire horn'))
# lower number = bought first (lane 3: any tonal instrument beats everything else; a lamp is a wish)
PRIO_INSTRUMENT = 0
PRIO_WAND500 = 0.5
PRIO_LAMP = 1
PRIO_SCARE = 1.5
PRIO_ARMOR = 3       # (SUPPLY_ARMOR) targets() lowers it by 0.1 per AC point the piece gives: the best piece first


# ------------------------------------------------------------------------------------------------ price knowledge

def dunce_options(agent):
    """The quote multipliers that may apply besides charisma: True = 4/3 more (a dunce cap, a Tourist below XL 15, a
    shirt with no suit or cloak over it). A list of the possibilities (an ambiguous 'conical hat' may be a dunce
    cap)."""
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


def unit_quote(item):
    """The price of ONE unit as the shelf shows it (the text shows the stack's total), or None."""
    if not item.price or item.count < 1 or item.price % item.count:
        return None
    return item.price // item.count


def consistent_objs(agent, item):
    """The types in item.objs whose base price can produce the quote on this shelf item (shk.c get_cost, with and
    without the 1-in-4 surcharge, with the charisma factor). Weapons and armour (a +N adds 10 per point) and types
    without a base price are never excluded. An item with no usable quote keeps all its types."""
    unit = unit_quote(item)
    if unit is None or item.shop_status != Item.FOR_SALE:
        return list(item.objs)
    cha = agent.blstats.charisma
    opts = dunce_options(agent)
    out = []
    for o in item.objs:
        cost = getattr(o, 'cost', None)
        if cost is None or isinstance(o, (O.Weapon, O.Armor, O.WepTool)):
            out.append(o)
        elif any(shop_math.quote_fits(cost, unit, cha, d) for d in opts):
            out.append(o)
    return out or list(item.objs)


# ------------------------------------------------------------------------------------------------ glyph knowledge

def glyph_obj(glyph):
    """The exact tool type behind an object glyph from the arena's observation (obs['glyphs'] / obs['inv_glyphs']),
    or None. NLE reports an object's glyph as GLYPH_OBJ_OFF + oc_descr_idx; shuffle_all() permutes the descriptions
    of rings, amulets, potions, scrolls, wands, spellbooks and the magic-appearance armour only, so for a TOOL the
    glyph index is the type itself (oil lamp vs magic lamp, the horns, flutes, harps, drums...). Ledger F308."""
    try:
        g = int(glyph)
        if not nh.glyph_is_normal_object(g):
            return None
        o = O.objects[nh.glyph_to_obj(g)]
        if o is None or O.get_category(o) != nh.TOOL_CLASS:
            return None
        return o
    except Exception:
        return None


def _is_tool(item):
    return item.category == nh.TOOL_CLASS


def tonal_share(objs):
    """Fraction (by generation probability) of the candidate types that play the drawbridge tune."""
    tot = sum(max(getattr(o, 'prob', 0) or 0, 1) for o in objs)
    ton = sum(max(getattr(o, 'prob', 0) or 0, 1) for o in objs if o.name in TONAL_NAMES)
    return ton / tot if tot else 0.0


def is_tonal_candidate(item):
    """Any of the item's possible types plays the tune (the pack-side test; castle_crusher finds a horn of plenty out
    by its missing 'Improvise?' prompt)."""
    return _is_tool(item) and any(o.name in TONAL_NAMES for o in item.objs)


def may_be_magic_lamp(item):
    """A pack/floor item that is or may be a magic lamp: the type is not ruled out (an unidentified 'lamp' is an oil
    lamp or a magic lamp unless the glyph or the price told them apart)."""
    return _is_tool(item) and any(o.name == 'magic lamp' for o in item.objs)


def certainly_magic_lamp(item):
    return _is_tool(item) and item.is_unambiguous() and item.object.name == 'magic lamp'


def pack_items(agent):
    try:
        return list(flatten_items(agent.inventory.items))
    except Exception:
        return []


def magic_lamps(agent):
    """Hand-over to the wishes lane: the carried items that are or may be a magic lamp (unpaid ones excluded)."""
    return [i for i in pack_items(agent) if may_be_magic_lamp(i) and i.shop_status != Item.UNPAID]


def tonal_in_pack(agent):
    return [i for i in pack_items(agent) if is_tonal_candidate(i) and i.shop_status != Item.UNPAID]


# ------------------------------------------------------------------------------------------------ the wants

class Want:
    """Something worth buying off a shelf. test(agent, item, glyph_obj, unit_price) -> bool decides a shelf item
    (item.objs is NOT yet narrowed: use consistent_objs(agent, item); glyph_obj is the exact tool type from the map
    glyph or None); need(agent) -> bool says whether the pack still wants one; cap is the highest unit price paid (an
    int or a callable)."""

    def __init__(self, tag, prio, cap, test, need, value=20.0):
        self.tag = tag
        self.prio = prio
        self._cap = cap
        self.test = test
        self.need = need
        self.value = value      # milli-passes the item is worth (SUPPLY_SELL sells pack items worth less than that)

    def cap(self):
        return self._cap() if callable(self._cap) else self._cap


def shelf_names(agent, item, gobj):
    """The names of the types a shelf item can be: the glyph's exact tool, else the types its quote allows."""
    if gobj is not None:
        return {gobj.name}
    return {o.name for o in consistent_objs(agent, item)}


def _test_instrument(agent, item, gobj, unit):
    """One instrument is wanted when the pack has none (anything that is probably tonal); with one in the pack, a second only
    if the pack holds no horn for certain: a certain horn (castle-gate: HORN_SCARE), or, while every one held may still be a
    horn of plenty, anything certainly tonal."""
    if not _is_tool(item):
        return False
    names = shelf_names(agent, item, gobj)
    if not names:
        return False
    st = agent.global_logic.supply.held_tonal()
    if not st['have']:
        if gobj is not None:
            return gobj.name in TONAL_NAMES
        return tonal_share(consistent_objs(agent, item)) >= 0.5
    if names <= HORN_NAMES:
        return True
    return st['doubtful_only'] and names <= TONAL_NAMES


def _test_lamp(agent, item, gobj, unit):
    if not _is_tool(item):
        return False
    if gobj is not None:
        return gobj.name == 'magic lamp'
    # base 50 against base 10 never overlap under any charisma or surcharge, so the quote alone decides
    return {o.name for o in consistent_objs(agent, item)} == {'magic lamp'}


def _test_wand500(agent, item, gobj, unit):
    """A wand quoted at base 500 is wishing or death (objects.c: the only two wands at 500; prob 5 each), so one in two is a
    wand of wishing: its engrave-test is a wish (zap.c zapnodir WAN_WISHING -> makewish); the metrics lane's census has 4 of 4
    wand-of-wishing games passing."""
    if item.category != nh.WAND_CLASS:
        return False
    names = {o.name for o in consistent_objs(agent, item)}
    # 'wishing' must still be possible: a wand an engrave test already showed to be death (castle-entry's SHOP_WISH tests it
    # unpaid and gives it back) is no 750 zm purchase
    return bool(names) and names <= {'wishing', 'death'} and 'wishing' in names


def _need_wand500(agent):
    if not jf_config.SUPPLY_WAND500:
        return False
    return not any(i.category == nh.WAND_CLASS and i.objs and {o.name for o in i.objs} <= {'wishing', 'death'} and
                   any(o.name == 'wishing' for o in i.objs) for i in pack_items(agent))


def _test_scare(agent, item, gobj, unit):
    """A shelf scroll the game shows by name as scare monster (the only scroll that stops the Castle's soldiers and its
    maze minotaurs from meleeing us on its square; castle-gate / castle-entry rank it right after the instrument)."""
    return item.category == nh.SCROLL_CLASS and item.is_unambiguous() and item.object.name == 'scare monster'


def _need_scare(agent):
    if not jf_config.SUPPLY_SCARE_BUY:
        return False
    have = sum(i.count for i in pack_items(agent)
               if i.category == nh.SCROLL_CLASS and i.is_unambiguous() and i.object.name == 'scare monster')
    return have < jf_config.SUPPLY_SCARE_N


def _need_instrument(agent):
    """One tonal instrument is enough (castle-gate: any of the 8 types plays the drawbridge tune); a second only when the pack
    holds no horn for certain (a horn scares the minotaurs: HORN_SCARE, R344), up to two."""
    if not jf_config.SUPPLY_INSTR_BUY:
        return False
    st = agent.global_logic.supply.held_tonal()
    if not st['have']:
        return True
    return len(st['have']) < 2 and not st['sure_horn']


def _need_lamp(agent):
    return jf_config.SUPPLY_LAMP_BUY and sum(i.count for i in magic_lamps(agent)) < jf_config.SUPPLY_LAMP_N


# SUPPLY_ARMOR: no piece heavier than this (a plate mail is 450, a splint 400: a Valkyrie that carries them is Burdened)
ARMOR_MAX_WT = 250
# the slot attribute of InventoryItems each bought armour subtype fills (cloaks and shirts are never bought)
_ARMOR_SLOTS = {O.ARM_SUIT: 'suit', O.ARM_HELM: 'helm', O.ARM_GLOVES: 'gloves', O.ARM_BOOTS: 'boots', O.ARM_SHIELD: 'off_hand'}


def armor_piece(item):
    """The armour type of an ARMOR_CLASS item when it is certain and not magical, else None. A Valkyrie knows the names of all
    non-magical armour (u_init.c knows_class(ARMOR_CLASS)), so a shelf shows a leather armor / leather gloves / low boots / orcish
    helm by name, while the magic appearances (old gloves, combat boots, a conical hat ...) stay ambiguous (item.objs holds several)."""
    try:
        if item.category != nh.ARMOR_CLASS or not item.is_unambiguous():
            return None
        o = item.object
        if not isinstance(o, O.Armor) or o.mgc:
            return None
        return o
    except Exception:
        return None


def armor_gain(o):
    """AC points an armour type gives at +0 (objects.c a_ac; the table stores ac - 10)."""
    return -o.ac


def _armor_slot_empty(agent, o):
    """The slot of armour type `o` is empty (nothing worn there) and the pack holds no unworn, not cursed piece for it; a shield
    is no use to a hero with a two-hander in the hand or a mattock digger (dive_logic drops it to dig)."""
    sub = o.sub
    attr = _ARMOR_SLOTS.get(sub)
    if attr is None:
        return False
    items = agent.inventory.items
    if getattr(items, attr) is not None:
        return False
    from .character import Character
    if sub == O.ARM_SUIT and agent.character.role == Character.MONK:
        return False
    if sub == O.ARM_SHIELD:
        mh = items.main_hand
        if mh is not None and getattr(mh.objs[0], 'bi', False):
            return False
        dive = getattr(agent.global_logic, 'dive', None)
        if dive is not None and dive.mattock_digger():
            return False
    for i in pack_items(agent):
        if i.equipped or i.shop_status == Item.UNPAID or i.status == Item.CURSED:
            continue
        p = armor_piece(i)
        if p is not None and p.sub == sub:
            return False
    return True


def _test_armor(agent, item, gobj, unit):
    """A shelf piece of armour for an empty slot (SUPPLY_ARMOR; see armor_piece for which pieces count)."""
    if not jf_config.SUPPLY_ARMOR:
        return False
    o = armor_piece(item)
    if o is None or o.wt > ARMOR_MAX_WT:
        return False
    try:
        return _armor_slot_empty(agent, o)
    except Exception:
        return False


def _need_armor(agent):
    return jf_config.SUPPLY_ARMOR


WANTS = [
    # values in milli-passes (1.0 = 0.001 expected passes per game; dev/readiness.py v1.2: a tonal instrument adds
    # F_CRUSHER ~0.048 per live arrival, x 0.42 arrivals alive ~ 20; a lamp is a 31% wish x P(pass | one wish, real castle kit,
    # kit-aware policy) 22/283 = 7.8% (wishes lane harness) x ~0.7 that the rub gets its quiet moment ~ 17 per live arrival,
    # x 0.42 arrivals alive ~ 7; 10 here: SUPPLY_SELL gives up half of it in pack junk, i.e. one or two unknown potions)
    Want('instrument', PRIO_INSTRUMENT, lambda: jf_config.SUPPLY_INSTR_MAX, _test_instrument, _need_instrument, 20.0),
    # 1 in 2 a wand of wishing: ~0.5 x 0.9 passes (F314), 450 milli-passes: worth selling most of the pack for
    Want('wand500', PRIO_WAND500, lambda: jf_config.SUPPLY_WAND500_MAX, _test_wand500, _need_wand500, 450.0),
    Want('lamp', PRIO_LAMP, lambda: jf_config.SUPPLY_LAMP_MAX, _test_lamp, _need_lamp, 10.0),
    Want('scare', PRIO_SCARE, lambda: jf_config.SUPPLY_SCARE_MAX, _test_scare, _need_scare, 20.0),
    # SUPPLY_ARMOR: a few AC points are worth a few milli-passes (never sold for: sell() leaves this tag alone)
    Want('armor', PRIO_ARMOR, lambda: jf_config.SUPPLY_ARMOR_MAX, _test_armor, _need_armor, 3.0),
]
# other lanes append here (id-engine: identify scrolls, prio >= 2); an entry is a Want
EXTRA_WANTS = []


def all_wants():
    return sorted(WANTS + list(EXTRA_WANTS), key=lambda w: w.prio)


# ------------------------------------------------------------------------------------------------ the strategy class

class Supply:
    def __init__(self, agent):
        self.agent = agent
        self.blocked = {}                # (dnum, dlvl, y, x) -> (failed walks, skip until turn)
        self.shop_entered = {}           # level key -> turn we were first inside a shop of it
        self.bought = []                 # (turn, tag, text, price)
        self.want = None                 # the best shelf item we could not pay: dict(tag, price, key, turn, text)
        self.lamp_letters = set()        # inventory letters of lamps bought for the magic-lamp price
        self.horn_letters = set()        # letters of instruments bought that are certainly a horn (tooled / frost / fire)
        self.tonal_letters = set()       # ... and of those that are certainly tonal (a quote that excludes a horn of plenty)
        self.armor_letters = set()       # letters of the armour pieces bought (SUPPLY_ARMOR): worn although their beatitude is unknown
        self.sold = []                   # (turn, item text, offer) of the sales that funded a purchase
        self.sold_for = {}               # want key -> (sale sessions so far, turn of the last one): 3 at most
        self.bad_spots = set()           # (level key, y, x): a drop there got no offer ('no charge': not a costly spot)
        self.town = {}                   # Minetown level key -> dict(start, done, explored, logged) (SUPPLY_TOWN)
        self.door_waits = {}             # shop key -> turns spent waiting in its doorway for the shopkeeper to step aside (SUPPLY_DOOR)
        self._glyph_mem = {}             # (level key, y, x) -> object glyph seen on that shop square
        self._seen = set()               # (level key, y, x, tag) logged as seen
        self._logged = set()             # (level key, y, x, text) of the shelf wands/rings/amulets logged

    # -- the instruments in the pack ----------------------------------------------------------------------------------

    def _letter(self, item):
        try:
            return self.agent.inventory.items.get_letter(item)
        except Exception:
            return None

    def is_sure_horn(self, item):
        """The item is certainly a horn that scares: its possible types are all horns (identified, or narrowed by the glyph),
        or we bought it for a quote that only a horn fits."""
        if not _is_tool(item) or not item.objs:
            return False
        return all(o.name in HORN_NAMES for o in item.objs) or self._letter(item) in self.horn_letters

    def is_sure_tonal(self, item):
        if not _is_tool(item) or not item.objs:
            return False
        return all(o.name in TONAL_NAMES for o in item.objs) or self._letter(item) in self.horn_letters or \
            self._letter(item) in self.tonal_letters

    def is_bought_armor(self, item):
        """An armour piece this module paid for (inventory.get_best_armorset wears it with its beatitude unknown)."""
        if not self.armor_letters:
            return False
        try:
            items = self.agent.inventory.items
            return items.all_letters[items.all_items.index(item)] in self.armor_letters
        except Exception:
            return False

    def held_tonal(self):
        """The pack's instruments: have (probably tonal items), sure_horn (one is certainly a scaring horn), doubtful_only
        (none is certainly tonal: every one may still be a horn of plenty)."""
        have = tonal_in_pack(self.agent)
        return dict(have=have, sure_horn=any(self.is_sure_horn(i) for i in have),
                    doubtful_only=not any(self.is_sure_tonal(i) for i in have))

    # -- the map glyph under a shelf item ------------------------------------------------------------------------

    def remember_glyphs(self, level):
        """Shop squares show their top object's glyph until we stand on them; keep it (the LOOK text under us has none)."""
        agent = self.agent
        try:
            mask = level.shop_interior & utils.isin(agent.glyphs, G.OBJECTS)
            key = level.key()
            for y, x in zip(*mask.nonzero()):
                self._glyph_mem[(key, int(y), int(x))] = int(agent.glyphs[y, x])
        except Exception:
            pass

    def glyph_at(self, level_key, y, x):
        return self._glyph_mem.get((level_key, int(y), int(x)))

    # -- what a shelf item is --------------------------------------------------------------------------------

    def shelf_want(self, item, level_key=None, y=None, x=None, single=True):
        """The Want a shelf item satisfies, or None."""
        agent = self.agent
        if item.shop_status != Item.FOR_SALE:
            return None
        unit = unit_quote(item)
        if unit is None:
            return None
        gobj = None
        if single and level_key is not None:
            g = self.glyph_at(level_key, y, x)
            gobj = glyph_obj(g) if g is not None else None
        for w in all_wants():
            try:
                if w.test(agent, item, gobj, unit):
                    return w
            except Exception:
                continue
        return None

    def log_shelf(self, item, level_key, y, x):
        """Log once the wands, rings and amulets on a shelf with the base prices their quote allows (the metrics lane's wand
        lottery: a wand quoted at base 500 is wishing or death)."""
        if item.category not in (nh.WAND_CLASS, nh.RING_CLASS, nh.AMULET_CLASS) or item.shop_status != Item.FOR_SALE:
            return
        k = (level_key, int(y), int(x), item.text)
        if k in self._logged:
            return
        self._logged.add(k)
        try:
            unit = unit_quote(item)
            objs = consistent_objs(self.agent, item) if unit else list(item.objs)
            bases = sorted({base_cost(o) for o in objs if base_cost(o)})
            names = sorted(o.name for o in objs)
            self.agent.log(f'SUPPLY shelf {item.text!r} unit={unit} bases={bases} types={names if len(names) <= 6 else len(names)}')
        except Exception:
            pass

    def targets(self, dis, unreachable=False):
        """Wanted shelf items on this level: [(prio, price, dist, y, x, want, item)], best first. `unreachable` selects the
        ones on shelf squares the BFS cannot reach right now instead (the shopkeeper stands at his post inside the door)."""
        agent = self.agent
        level = agent.current_level()
        key = level.key()
        out = []
        reserve = None
        for y, x in zip(*(level.shop_interior & (level.item_count > 0)).nonzero()):
            if (dis[y, x] == -1) != unreachable:
                if jf_config.SUPPLY_DEBUG and any('lamp' in (i.text or '') for i in level.items[y, x]):
                    self._dbg(f'targets(unreachable={unreachable}): lamp square {(int(y), int(x))} has dis {int(dis[y, x])}')
                continue
            items = level.items[y, x]
            for item in items:
                self.log_shelf(item, key, y, x)
                w = self.shelf_want(item, key, y, x, single=len(items) == 1)
                if w is None:
                    if jf_config.SUPPLY_DEBUG and 'lamp' in (item.text or ''):
                        self._dbg(f'targets: a lamp at {(int(y), int(x))} is no want: {item.text!r} shop_status={item.shop_status} '
                                  f'objs={[o.name for o in item.objs]} single={len(items) == 1}')
                    continue
                unit = unit_quote(item)
                if unit > w.cap() or not w.need(agent):
                    if jf_config.SUPPLY_DEBUG:
                        self._dbg(f'targets: {w.tag} at {(int(y), int(x))} skipped: unit {unit} cap {w.cap()} need {w.need(agent)}')
                    continue
                if w.tag == 'armor':
                    # SUPPLY_ARMOR: a lamp / instrument we could pay now keeps its gold (the reserve is read once per call)
                    if reserve is None:
                        try:
                            reserve = self.shelf_reserve()
                        except Exception:
                            reserve = 0
                    if reserve and unit <= agent.blstats.gold < unit + reserve:
                        continue
                bkey = (level.dungeon_number, level.level_number, int(y), int(x))
                if self.blocked.get(bkey, (0, -1))[1] > agent.blstats.time:
                    if jf_config.SUPPLY_DEBUG:
                        self._dbg(f'targets: {w.tag} at {(int(y), int(x))} blocked until {self.blocked[bkey][1]}')
                    continue
                seen = (key, int(y), int(x), w.tag)
                if seen not in self._seen:
                    self._seen.add(seen)
                    agent.log(f'SUPPLY seen {w.tag} {item.text!r} price={unit} gold={agent.blstats.gold} '
                              f'at {(int(y), int(x))}')
                prio = w.prio
                if w.tag == 'instrument':
                    # a horn first (HORN_SCARE: it scares the castle's minotaurs), a tooled horn (15 zm) before a frost / fire horn
                    g = self.glyph_at(key, y, x) if len(items) == 1 else None
                    names = shelf_names(agent, item, glyph_obj(g) if g is not None else None)
                    if names == {'tooled horn'}:
                        prio -= 0.2
                    elif names and names <= HORN_NAMES:
                        prio -= 0.1
                elif w.tag == 'armor':
                    o = armor_piece(item)
                    if o is not None:
                        prio -= 0.1 * armor_gain(o)      # the best piece first
                out.append((prio, unit, int(dis[y, x]), int(y), int(x), w, item))
        out.sort(key=lambda t: t[:5])
        return out

    # -- strategies --------------------------------------------------------------------------------------------

    def food_reserve(self):
        """SUPPLY_FOOD_RESERVE: the gold BUY_FOOD leaves alone. A lamp or instrument on a shelf of this level (reachable or not) that
        we could pay for right now (gold >= its price) but have not bought is not spent on food first (harness supply-twoshop: the
        67 zm of a lamp became a food ration and two fortune cookies on the way back to the lighting store; a ration can be bought
        in the next deli). Not while hungry or with less than one ration's nutrition carried. Read from the shelves each time, so a
        lamp that is gone releases the gold."""
        if not (jf_config.SUPPLY_BUY and jf_config.SUPPLY_FOOD_RESERVE):
            return 0
        try:
            agent = self.agent
            bl = agent.blstats
            if bl.hunger_state >= Hunger.HUNGRY or agent.inventory.carried_nutrition() < 800:
                return 0
            return self.shelf_reserve()
        except Exception:
            return 0

    def shelf_reserve(self):
        """The price of the cheapest lamp / instrument on a shelf of this level that we could pay right now and have not bought (0
        when there is none): the gold food and armour leave alone."""
        agent = self.agent
        bl = agent.blstats
        level = agent.current_level()
        key = level.key()
        best = 0
        for y, x in zip(*(level.shop_interior & (level.item_count > 0)).nonzero()):
            items = level.items[y, x]
            for item in items:
                w = self.shelf_want(item, key, y, x, single=len(items) == 1)
                if w is None or w.tag not in ('lamp', 'instrument'):
                    continue
                unit = unit_quote(item)
                if unit is None or unit > w.cap() or unit > bl.gold or not w.need(agent):
                    continue
                best = unit if best == 0 else min(best, unit)
        return best

    def _walk_failed(self, key):
        """A walk to a shelf / door / shop / sale spot failed (it PANICKED, or returned short): count it; a streak blocks the target
        for 100 / 400 / 2000 turns after 3 / 6 / 10 failures. Returns the streak. (The old rule blocked it for 2000 turns at the third
        failure of any kind: a walk cut short by a preempting strategy -- the altar BUC test, a meal, a fight -- counted too, and in
        Minetown, where peacefuls cross the path, the lamp's shelf was blocked for the whole sweep: harness supply-twoshop seed 6.)"""
        fails = self.blocked.get(key, (0, -1))[0] + 1
        pause = 0 if fails < 3 else 100 if fails < 6 else 400 if fails < 10 else 2000
        self.blocked[key] = (fails, self.agent.blstats.time + pause if pause else -1)
        return fails

    def _walk_to(self, key, y, x):
        """agent.go_to with that bookkeeping; True when we stand on (y, x). A preemption (AgentChangeStrategy) passes through
        untouched and is no failure."""
        agent = self.agent
        try:
            agent.go_to(y, x)
        except AgentPanic:
            self._walk_failed(key)
            raise
        if (agent.blstats.y, agent.blstats.x) != (y, x):
            self._walk_failed(key)
            return False
        return True

    def _dbg(self, text):
        """SUPPLY_DEBUG (logging only): at most one line per 25 game turns per text."""
        if not jf_config.SUPPLY_DEBUG:
            return
        try:
            now = self.agent.blstats.time
            last = getattr(self, '_dbg_last', {})
            self._dbg_last = last
            key = text[:40]
            if now - last.get(key, -10 ** 9) >= 25:
                last[key] = now
                self.agent.log(f'SUPPLY dbg {text} at {(self.agent.blstats.y, self.agent.blstats.x)}')
        except Exception:
            pass

    def town_sweeping(self, level):
        """SUPPLY_TOWN's sweep of this level is under way (started, not done, inside its turn budget)."""
        if not (jf_config.SUPPLY_TOWN and jf_config.SUPPLY_BUY):
            return False
        st = self.town.get(level.key())
        return bool(st) and not st['done'] and self.agent.blstats.time - st['start'] <= jf_config.SUPPLY_TOWN_TURNS

    def hold_food(self):
        """BUY_FOOD waits (SUPPLY_BUY) until the shop's shelves were all looked at, so a food ration never spends the
        gold a lamp or an instrument needs: they are in the squares we have not stood on yet."""
        if not jf_config.SUPPLY_BUY:
            return False
        try:
            agent = self.agent
            bl = agent.blstats
            level = agent.current_level()
            if jf_config.SUPPLY_TOWN_FOOD_LAST and bl.hunger_state < Hunger.HUNGRY and self.town_sweeping(level) and \
                    agent.inventory.carried_nutrition() >= 800:
                return True      # Minetown: the sweep looks at every shop first, the food ration is the last thing bought
            if bl.hunger_state >= Hunger.HUNGRY or not level.shop_interior[bl.y, bl.x]:
                return False
            first = self.shop_entered.setdefault(self.shop_key(level, bl.y, bl.x), bl.time)
            if bl.time - first > jf_config.SUPPLY_SCAN_TURNS:
                return False
            dis = agent.bfs()
            unchecked = utils.isin(agent.glyphs, G.OBJECTS, G.BODIES, G.STATUES) & (level.item_count == 0) & \
                (dis > 0) & self.shop_mask_at(level, bl.y, bl.x)
            return bool(unchecked.any())
        except Exception:
            return False

    # -- SUPPLY_DOOR: a shop whose door the shopkeeper blocks ----------------------------------------------------------

    def blocked_shops(self, dis):
        """[(distance, doorway square, interior cells, shop key)]: shops whose interior no square of which the BFS reaches (a
        peaceful shopkeeper is no walkable square to it, and he stands at his post just inside the door while we are away)
        but whose doorway it does, nearest first. A shop that used up its SUPPLY_DOOR_WAITS is left out."""
        level = self.agent.current_level()
        now = self.agent.blstats.time
        out = []
        for cells in self.shop_components(level):
            # the mask is sticky and dilated: it holds the shop's walls and a door that was shut when the shopkeeper was first seen
            # (the lighting store of harness supply-twoshop), so a reachable DOOR square must not make the shop look open; only the
            # floor inside counts, and the door squares themselves are the places to stand in
            floor = [(y, x) for y, x in cells if level.walkable[y, x] and level.objects[y, x] not in G.DOORS]
            if any(dis[y, x] != -1 for y, x in floor):
                continue
            ring = [(int(dis[ry, rx]), ry, rx) for ry, rx in self.doorway_cells(level, cells) if dis[ry, rx] != -1]
            ring += [(int(dis[y, x]), y, x) for y, x in cells if level.objects[y, x] in G.DOORS and dis[y, x] != -1]
            skey = (level.key(), min(cells))
            if not ring or self.door_waits.get(skey, 0) >= jf_config.SUPPLY_DOOR_WAITS:
                continue
            d, ry, rx = min(ring)
            if self.blocked.get((level.dungeon_number, level.level_number, ry, rx, 'door'), (0, -1))[1] > now:
                continue
            out.append((d, (ry, rx), cells, skey))
        out.sort(key=lambda t: t[0])
        return out

    def door_step(self, pos, skey):
        """One action towards getting in: walk to the shop's doorway, there let a turn pass (he steps off his post when we
        stand in the door with nothing unpaid; the next BFS then reaches the shelves)."""
        agent = self.agent
        level = agent.current_level()
        if (agent.blstats.y, agent.blstats.x) != pos:
            key = (level.dungeon_number, level.level_number, pos[0], pos[1], 'door')
            self._walk_to(key, pos[0], pos[1])
            return
        self.door_waits[skey] = self.door_waits.get(skey, 0) + 1
        if self.door_waits[skey] == 1:
            agent.log(f'SUPPLY waiting in the doorway {pos} of the shop at {skey[1]} for the shopkeeper to step aside')
        agent.search(1)

    @utils.debug_log('supply.buy')
    @Strategy.wrap
    def buy(self):
        agent = self.agent
        bl = agent.blstats
        inv = agent.inventory
        if not jf_config.SUPPLY_BUY or bl.hunger_state >= Hunger.WEAK:
            yield False
        if getattr(agent, '_shop_wish_holding', False):
            yield False      # castle-entry's SHOP_WISH holds an unpaid wand on purpose: nothing of ours touches the bill
        level = agent.current_level()
        if not level.shop_interior.any():
            yield False
        self._dbg('buy tick')
        if agent.character.prop.hallu or agent.character.prop.blind or agent.character.prop.polymorph:
            yield False
        self.remember_glyphs(level)
        if any(i.shop_status == Item.UNPAID for i in flatten_items(inv.items)):
            yield True
            inv.pay_or_drop_unpaid()
            self._late_purchase()
            return
        if getattr(self, '_pending', None) is not None:
            yield True
            self._late_purchase()
            return
        if agent._carries_digging_tool() or agent.get_visible_monsters():
            if jf_config.SUPPLY_DEBUG:
                self._dbg(f'buy: digging tool {agent._carries_digging_tool()} or hostiles in view '
                          f'{[(m[3].mname, m[0]) for m in agent.get_visible_monsters()[:4]]}')
            yield False
        if jf_config.SHOP_GUARD and agent.character.teleportitis and not agent.character.teleport_control:
            yield False
        dis = agent.bfs()
        cands = self.targets(dis)
        if not cands:
            if jf_config.SUPPLY_DEBUG:
                self._dbg(f'buy: no reachable wanted shelf item (gold {bl.gold})')
            if not jf_config.SUPPLY_DOOR:
                yield False
            # a wanted item we can pay, on a shelf the shopkeeper's post cuts off: go and stand in that shop's door
            wanted = [c for c in self.targets(dis, unreachable=True) if c[1] <= bl.gold]
            pick = None
            bshops = self.blocked_shops(dis)
            for d, door, cells, skey in bshops:
                if any((c[3], c[4]) in set(cells) for c in wanted):
                    pick = (door, skey)
                    break
            if pick is None:
                if jf_config.SUPPLY_DEBUG:
                    self._dbg(f'buy: door route: wanted-unreachable {[(c[5].tag, c[1], c[3], c[4]) for c in wanted]} '
                              f'blocked shops {[(b[0], b[1], len(b[2])) for b in bshops]}')
                if jf_config.SUPPLY_DEBUG and wanted:
                    for cells in self.shop_components(level):
                        ring = self.doorway_cells(level, cells)
                        doors = [(y, x, int(level.objects[y, x]), bool(level.walkable[y, x]), int(dis[y, x]),
                                  [int(dis[y + dy, x + dx]) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if (dy or dx)])
                                 for y, x in cells if level.objects[y, x] in G.DOORS]
                        self._dbg(f'buy: doors of comp {min(cells)}: {doors}')
                        self._dbg(f'buy: shop comp {min(cells)} size {len(cells)} reachable '
                                  f'{sum(1 for y, x in cells if dis[y, x] != -1)} doorway cells {ring} reachable ring '
                                  f'{[(r, int(dis[r])) for r in ring]} has wanted {any((c[3], c[4]) in set(cells) for c in wanted)}')
                yield False
            yield True
            self.door_step(*pick)
            return
        afford = [c for c in cands if c[1] <= bl.gold]
        if not afford:
            # the best one we cannot pay: SUPPLY_SELL looks at it
            prio, unit, d, y, x, w, item = cands[0]
            self.want = dict(tag=w.tag, price=unit, value=w.value, key=(level.key(), y, x), turn=bl.time,
                             text=item.text)
            yield False
        prio, unit, d, y, x, w, item = afford[0]
        tag = w.tag
        glyph = item.glyphs[0] if item.glyphs else None
        key = (level.dungeon_number, level.level_number, y, x)
        yield True
        if (bl.y, bl.x) != (y, x):
            if not self._walk_to(key, y, x):
                return
        here = [i for i in inv.items_below_me
                if i.shop_status == Item.FOR_SALE and unit_quote(i) == unit and (glyph is None or glyph in i.glyphs)
                and self.shelf_want(i, level.key(), y, x, single=len(inv.items_below_me) == 1) is not None]
        if not here:
            self.blocked[key] = (self.blocked.get(key, (0, -1))[0] + 1, agent.blstats.time + 500)
            return
        # a failed attempt (an exception, an unpaid drop) must not repeat in a tight loop
        self.blocked[key] = (self.blocked.get(key, (0, -1))[0] + 1, agent.blstats.time + 600)
        letters_before = set(inv.items.all_letters)
        names = None
        if tag == 'instrument':
            g = self.glyph_at(level.key(), y, x) if len(inv.items_below_me) == 1 else None
            names = shelf_names(agent, here[0], glyph_obj(g) if g is not None else None)
        agent.log(f'SUPPLY buying {tag} {here[0].text!r} for {unit} (gold {agent.blstats.gold})')
        # recorded BEFORE the steps: a preempting strategy that cuts pickup/pay short must not lose the bookkeeping (_late_purchase)
        self._pending = (tag, here[0].text, unit, letters_before, names)
        inv.pickup(here[0], 1)
        inv.pay_or_drop_unpaid()
        self._pending = None
        if self._after_purchase(tag, here[0].text, unit, letters_before, names):
            self.blocked.pop(key, None)

    def _late_purchase(self):
        """Book a purchase whose pickup/pay a preempting strategy cut short (see buy()): the item is paid by now, or dropped."""
        p = getattr(self, '_pending', None)
        if p is None:
            return
        self._pending = None
        try:
            inv = self.agent.inventory
            inv.items.update(force=True)
            if not (set(inv.items.all_letters) - p[3]):
                return       # nothing new in the pack: the pickup never happened (or the item was dropped again)
            if self._after_purchase(*p):
                self.agent.log(f'SUPPLY late bookkeeping of the {p[0]} bought for {p[2]}')
        except Exception as e:
            self.agent.log(f'SUPPLY late bookkeeping failed: {e!r}')

    def _after_purchase(self, tag, text, unit, letters_before, names=None):
        agent = self.agent
        inv = agent.inventory
        inv.items.update(force=True)
        still_unpaid = [i for i in flatten_items(inv.items) if i.shop_status == Item.UNPAID]
        if still_unpaid:
            agent.log(f'SUPPLY {tag} not bought: still unpaid {[i.text for i in still_unpaid]}')
            return False
        self.bought.append((agent.blstats.time, tag, text, unit))
        if tag == 'lamp':
            self.lamp_letters |= set(inv.items.all_letters) - letters_before
            self.publish_lamps()
        elif tag == 'armor':
            self.armor_letters |= set(inv.items.all_letters) - letters_before
        elif tag == 'instrument' and names:
            new = set(inv.items.all_letters) - letters_before
            if names <= HORN_NAMES:
                self.horn_letters |= new       # the quote only fits a horn that scares (tooled 15 zm, frost / fire 50)
            elif names <= TONAL_NAMES:
                self.tonal_letters |= new      # a flute, harp or bugle: certainly tonal, whatever the pack item's own types
        agent.log(f'SUPPLY {tag} bought price={unit} gold={agent.blstats.gold} (bought so far {len(self.bought)})')
        return True

    def publish_lamps(self):
        """agent._magic_lamp_letters (the wishes lane): the inventory letters of the lamps we paid the magic-lamp price
        for, so the rubbing starts with those (any plain 'lamp' is rubbed in the end)."""
        agent = self.agent
        try:
            items = agent.inventory.items
            live = {letter for letter, item in zip(items.all_letters, items.all_items) if may_be_magic_lamp(item)}
            agent._magic_lamp_letters = self.lamp_letters & live
        except Exception:
            pass

    # -- looking at the shelves ----------------------------------------------------------------------------------

    @utils.debug_log('supply.scan')
    @Strategy.wrap
    def scan(self):
        """Inside a shop (or in its doorway): stand on every shelf square once, so the price of each item is known
        (the tour's check_items does this; the dive, which only passes through Minetown, does not)."""
        agent = self.agent
        bl = agent.blstats
        level = agent.current_level()
        if not jf_config.SUPPLY_BUY or bl.hunger_state >= Hunger.WEAK or not level.shop[bl.y, bl.x] or \
                getattr(agent, '_shop_wish_holding', False):
            yield False
        if jf_config.SUPPLY_SCAN_TOWN_ONLY and level.dungeon_number != Level.GNOMISH_MINES:
            yield False      # the tour's own check_items walks the shelves of a Dlvl 1-4 shop (in its own order, with its own RNG draws)
        if agent.character.prop.hallu or agent.character.prop.blind or agent.character.prop.polymorph or \
                agent._carries_digging_tool() or agent.get_visible_monsters():
            yield False
        first = self.shop_entered.setdefault(self.shop_key(level, bl.y, bl.x), bl.time)
        if bl.time - first > jf_config.SUPPLY_SCAN_TURNS:
            yield False
        dis = agent.bfs()
        unchecked = utils.isin(agent.glyphs, G.OBJECTS, G.BODIES, G.STATUES) & (level.item_count == 0) & \
            (dis > 0) & self.shop_mask_at(level, bl.y, bl.x)
        if not unchecked.any():
            yield False
        yield True
        ys, xs = (unchecked & (dis == dis[unchecked].min())).nonzero()
        i = agent.rng.randint(len(ys))
        agent.go_to(int(ys[i]), int(xs[i]))

    # -- SUPPLY_TOWN: a Minetown visit goes through every shop --------------------------------------------------------

    @utils.debug_log('supply.town')
    @Strategy.wrap
    def town_sweep(self):
        agent = self.agent
        bl = agent.blstats
        level = agent.current_level()
        gl = agent.global_logic
        # Minetown is Mines level 3 or 4 (dungeon.def minetn @ (3, 2)); the filler levels have no doors, altars or
        # fountains (the dive's own test), so those and a shopkeeper in view show the town. Before any of them shows,
        # the first SUPPLY_TOWN_PROBE turns on the level are spent exploring it (the camp would anyway).
        if not jf_config.SUPPLY_TOWN or level.dungeon_number != Level.GNOMISH_MINES or \
                level.level_number not in (3, 4):
            yield False
        if bl.hunger_state >= Hunger.WEAK or agent.prayer_failed or bl.hitpoints < 0.6 * bl.max_hitpoints or \
                agent.character.prop.hallu or agent.character.prop.blind or agent.character.prop.polymorph:
            yield False
        if agent._carries_digging_tool() or gl.dive.digging_tool() is not None or agent.get_visible_monsters():
            yield False
        if gl.minetown_level is not None and gl.minetown_level != level.key():
            yield False   # Minetown was the level above: this filler level has no shops to sweep
        st = self.town.setdefault(level.key(), dict(start=bl.time, done=False, explored=False, logged=False))
        town = gl.minetown_level == level.key() or \
            utils.isin(level.objects, G.DOORS, G.ALTAR, G.FOUNTAIN).any()
        if st['done'] or bl.time - st['start'] > jf_config.SUPPLY_TOWN_TURNS or \
                (not town and bl.time - st['start'] > jf_config.SUPPLY_TOWN_PROBE):
            yield False
        dis = agent.bfs()
        target = None
        for cells in self.shop_components(level):
            ring = self.doorway_cells(level, cells)
            if any(level.was_on[y, x] for y, x in cells) or any(level.was_on[y, x] for y, x in ring):
                continue
            # the interior if the way in is open to the BFS, else the doorway (the shopkeeper stands inside it, and a
            # peaceful monster is no walkable square to the BFS: stepping on the doorway makes him step aside)
            reach = [(int(dis[y, x]), y, x) for y, x in cells if dis[y, x] != -1] or \
                [(int(dis[y, x]), y, x) for y, x in ring if dis[y, x] != -1]
            if reach and (target is None or min(reach) < target):
                target = min(reach)
        no_shops = not self.shop_components(level) and gl.minetown_level != level.key() and \
            bl.time - st['start'] > jf_config.SUPPLY_TOWN_NOSHOP
        if no_shops or (target is None and st['explored']):
            # no shopkeeper after SUPPLY_TOWN_NOSHOP turns in a place with doors/an altar: Orcish Town (mines.des
            # minetn-1, 1 Minetown in 7: the shopkeepers are dead and an orc army holds it) or a level that only looks like
            # a town -- nothing to sweep, and the orcs are the camp's business
            st['done'] = True
            agent.log(f'SUPPLY town sweep done after {bl.time - st["start"]} turns: shops '
                      f'{len(self.shop_components(level))}, bought {len(self.bought)}'
                      + (' (no shopkeeper seen)' if no_shops else ''))
            yield False
        yield True
        if not st['logged']:
            st['logged'] = True
            agent.log(f'SUPPLY town sweep starts on {level.key()} (gold {bl.gold}, {len(self.shop_components(level))} '
                      f'shops known)')
        if target is not None:
            _, ty, tx = target
            key = (level.dungeon_number, level.level_number, ty, tx, 'town')
            try:
                self._walk_to(key, ty, tx)
            finally:
                if (agent.blstats.y, agent.blstats.x) != (ty, tx) and self.blocked.get(key, (0, -1))[0] >= 3:
                    # the way in is shut to us: count the shop as seen
                    level.was_on[ty, tx] = True
            return
        t0 = bl.time
        s0 = agent.step_count
        n0 = len(self.shop_components(level))

        def stop():
            return agent.blstats.time - t0 >= jf_config.SUPPLY_TOWN_EXPLORE or \
                len(self.shop_components(agent.current_level())) > n0
        ran = gl.exploration_strategy(0).until(agent, stop).run(return_condition=True)
        if ran and agent.step_count == s0:
            # it ran without a single action: never spin (the preempt loop asserts after 5 idle rounds)
            st['idle'] = st.get('idle', 0) + 1
            agent.search(1)
            if st['idle'] >= 8:
                st['explored'] = True
        if not ran:
            inside = bool(level.shop[agent.blstats.y, agent.blstats.x])
            if jf_config.SUPPLY_DEBUG:
                d2 = agent.bfs()
                agent.log(f'SUPPLY town: exploration has nothing at {(agent.blstats.y, agent.blstats.x)} inside_shop='
                          f'{inside} reachable={int((d2 != -1).sum())} t={agent.blstats.time - t0}/{stop()}')
            if inside and st.get('waits', 0) < 40:
                # the shopkeeper stands in the way out (the BFS does not walk through a peaceful): let a turn pass
                st['waits'] = st.get('waits', 0) + 1
                agent.search(1)
            else:
                st['explored'] = True

    # -- SUPPLY_SELL: raise the gold for a wanted shelf item we could not pay ---------------------------------------

    @staticmethod
    def buys(stype, cls):
        if not stype:
            return False
        allowed = SHOP_BUYS.get(int(stype), set())
        return allowed is None or cls in allowed

    def plan_sales(self, need, stype, value):
        """The pack items a shop of type `stype` would take, cheapest loss per zorkmid first, or None when they cannot
        cover `need` zm (expected offers) or when letting them go costs more than half the target's value."""
        cands = []
        for item in pack_items(self.agent):
            if not sellable_item(item) or not self.buys(stype, item.category):
                continue
            g = unit_gold(item)
            if g < 1:
                continue
            loss = item_loss(item)
            cands.append((loss / g, item, g, loss))
        cands.sort(key=lambda t: t[0])
        plan, got, lost = [], 0.0, 0.0
        for ratio, item, g, loss in cands:
            if got >= need * 1.15 + 2:
                break
            n = min(item.count, int(math.ceil((need * 1.15 + 2 - got) / g)))
            plan.append((item, n, g * n, loss * n))
            got += g * n
            lost += loss * n
        if got < need or lost > 0.5 * value:
            return None
        return plan

    @staticmethod
    def shop_components(level):
        """The shops of the level: lists of interior squares, one list per connected block (walls separate shops)."""
        interior = level.shop_interior
        seen = np.zeros_like(interior)
        comps = []
        h, w = interior.shape
        for y, x in zip(*interior.nonzero()):
            if seen[y, x]:
                continue
            seen[y, x] = True
            stack, cells = [(int(y), int(x))], []
            while stack:
                cy, cx = stack.pop()
                cells.append((cy, cx))
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        ny, nx = cy + dy, cx + dx
                        if 0 <= ny < h and 0 <= nx < w and interior[ny, nx] and not seen[ny, nx]:
                            seen[ny, nx] = True
                            stack.append((ny, nx))
            comps.append(cells)
        return comps

    def shop_mask_at(self, level, y, x):
        """Boolean mask of the interior of the shop the square belongs to (inside it or in its doorway)."""
        mask = np.zeros_like(level.shop_interior)
        for cells in self.shop_components(level):
            if any(max(abs(y - cy), abs(x - cx)) <= 1 for cy, cx in cells):
                for cy, cx in cells:
                    mask[cy, cx] = True
                break
        return mask

    def shop_key(self, level, y, x):
        """Identifier of the shop the square belongs to (inside it, or in its doorway): (level key, its first interior cell);
        a level can hold several (Minetown 4-5), each with its own scan clock."""
        for cells in self.shop_components(level):
            if any(max(abs(y - cy), abs(x - cx)) <= 1 for cy, cx in cells):
                return (level.key(), min(cells))
        return (level.key(), None)

    @staticmethod
    def doorway_cells(level, cells):
        """The walkable squares next to a shop's interior that are not interior: its doorway."""
        h, w = level.walkable.shape
        inside = set(cells)
        ring = set()
        for cy, cx in cells:
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = cy + dy, cx + dx
                    if 0 <= ny < h and 0 <= nx < w and (ny, nx) not in inside and level.walkable[ny, nx] and \
                            level.shop[ny, nx]:
                        ring.add((ny, nx))
        return sorted(ring)

    @staticmethod
    def shop_type_of(level, cells):
        """The glyph.SHOP id of a shop: the greeting's (level.shop_type), else a general store when its shelves hold
        three or more object classes (the greeting is missed when we come in through a hole or a teleport), else 0."""
        known = [int(level.shop_type[y, x]) for y, x in cells if int(level.shop_type[y, x]) != SHOP.UNKNOWN]
        if known:
            return max(set(known), key=known.count)
        classes = set()
        n = 0
        for y, x in cells:
            for item in level.items[y, x]:
                if item.shop_status == Item.FOR_SALE:
                    classes.add(item.category)
                    n += 1
        return 1 if len(classes) >= 3 and n >= 4 else SHOP.UNKNOWN

    def sale_shops(self, dis):
        """[(distance, (y, x), shop type)]: for each shop of the level of a known type the nearest free (no item),
        reachable interior square -- a costly spot where a dropped item is the shopkeeper's to buy."""
        level = self.agent.current_level()
        out = []
        # the shopkeeper's post is the square inside the door: not a costly spot (nothing dropped there is sold, 'no
        # charge'); level.shop_interior drops it only when the door was seen walkable, so keep off every door's neighbours
        near_door = utils.dilate(utils.isin(level.objects, G.DOORS), radius=1, with_diagonal=True)
        key = level.key()
        for cells in self.shop_components(level):
            stype = self.shop_type_of(level, cells)
            if stype == SHOP.UNKNOWN:
                continue
            free = [(int(dis[y, x]), (y, x)) for y, x in cells
                    if level.item_count[y, x] == 0 and dis[y, x] != -1 and not near_door[y, x]
                    and (key, y, x) not in self.bad_spots]
            if free:
                d, pos = min(free)
                out.append((d, pos, stype))
        out.sort()
        return out

    @staticmethod
    def same_stack(a, b):
        return a.category == b.category and a.glyphs == b.glyphs and a.status == b.status and \
            a.modifier == b.modifier and a.naming == b.naming

    @utils.debug_log('supply.sell')
    @Strategy.wrap
    def sell(self):
        agent = self.agent
        bl = agent.blstats
        inv = agent.inventory
        if not jf_config.SUPPLY_SELL or self.want is None or bl.hunger_state >= Hunger.WEAK or \
                getattr(agent, '_shop_wish_holding', False):
            yield False
        level = agent.current_level()
        if self.want['key'][0] != level.key() or bl.time - self.want['turn'] > 800:
            yield False
        if agent.character.prop.hallu or agent.character.prop.blind or agent.character.prop.polymorph or \
                agent.hands_welded() or agent._carries_digging_tool() or agent.get_visible_monsters():
            yield False
        if any(i.shop_status == Item.UNPAID for i in flatten_items(inv.items)):
            yield False
        # the target is recomputed from the shelves now (a stale want would sell more for an item already bought)
        dis = agent.bfs()
        cands = self.targets(dis)
        if not cands and jf_config.SUPPLY_DOOR:
            cands = self.targets(dis, unreachable=True)    # (the shelf we want is in a shop we cannot walk into just now)
        if not cands or any(c[1] <= bl.gold for c in cands):
            yield False
        prio, unit, d, cy, cx, wnt, citem = cands[0]
        if wnt.tag == 'armor':
            yield False      # (SUPPLY_ARMOR) a few zorkmids of armour are no reason to sell the pack
        w = dict(tag=wnt.tag, price=unit, value=wnt.value, key=(level.key(), cy, cx), text=citem.text)
        price = w['price']
        need = price - bl.gold
        n_sessions, last_session = self.sold_for.get(w['key'], (0, -10 ** 9))
        if need <= 0 or n_sessions >= 3 or bl.time - last_session < 20:
            yield False
        choice = None
        for d, pos, stype in self.sale_shops(dis):
            plan = self.plan_sales(need, stype, w['value'])
            if plan:
                choice = (pos, stype, plan)
                break
        if choice is None:
            if jf_config.SUPPLY_DOOR:
                # a shop that would take the junk but whose door is blocked: stand in its doorway
                for d, door, cells, skey in self.blocked_shops(dis):
                    stype = self.shop_type_of(level, cells)
                    if stype != SHOP.UNKNOWN and self.plan_sales(need, stype, w['value']):
                        yield True
                        self.door_step(door, skey)
                        return
            yield False
        (ty, tx), stype, plan = choice
        yield True
        if (bl.y, bl.x) != (ty, tx):
            key = (level.dungeon_number, level.level_number, ty, tx, 'sell')
            try:
                self._walk_to(key, ty, tx)
            finally:
                if (agent.blstats.y, agent.blstats.x) != (ty, tx) and self.blocked.get(key, (0, -1))[0] >= 3:
                    self.sold_for[w['key']] = (3, agent.blstats.time)
            if (agent.blstats.y, agent.blstats.x) != (ty, tx):
                return
        self.sold_for[w['key']] = (n_sessions + 1, bl.time)
        agent.log(f'SUPPLY sell plan for {w["tag"]} {w["price"]} (gold {bl.gold}) in shop type {stype} at {(ty, tx)}: '
                  f'{[(i.text, n, round(g), round(l, 1)) for i, n, g, l in plan]}')
        budget = 0.5 * w['value']
        lost = 0.0
        for item0, n, g, loss in plan:
            for _ in range(n):
                if agent.blstats.gold >= price:
                    break
                cur = [i for i in pack_items(agent) if self.same_stack(i, item0)]
                if not cur or lost + item_loss(cur[0]) > budget:
                    break
                r = sell_offer(agent, cur[0], accept=True, count=1)
                agent.log(f'SUPPLY sell {cur[0].text!r}: offer={r["offer"]} sold={r["sold"]} '
                          f'uninterested={r["uninterested"]} credit={r["credit"]} only={r["only"]} '
                          f'skipped={r["skipped"]} gold={agent.blstats.gold}')
                if r['skipped'] or not r['sold']:
                    if r['offer'] is None and not (r['skipped'] or r['uninterested'] or r['credit'] or r['only']):
                        # no offer at all: not a costly spot after all (the shopkeeper's post): another square next time
                        self.bad_spots.add((level.key(), ty, tx))
                    break
                lost += item_loss(cur[0])
                self.sold.append((agent.blstats.time, cur[0].text, r['offer']))
            if agent.blstats.gold >= price:
                break
        agent.log(f'SUPPLY sell session done: gold={agent.blstats.gold} price={price} lost={lost:.1f} mpass')
        self.want = dict(w, turn=agent.blstats.time)


# ------------------------------------------------------------------------------------------------ selling (SUPPLY_SELL)
#
# shk.c sellobj / set_cost: dropping an item in a shop (not on the shopkeeper's post) makes him offer base / 2 for it
# (base / 3 with a dunce cap or a low-level Tourist), 3/4 of that for an UNidentified item from one shopkeeper in four
# (m_id % 4 == 0, the same for all his offers); 'Sell it? [ynaq]'. A shop buys only what it stocks (saleable()): a general
# store everything, the others the classes in SHOP_BUYS. Uncursed water and (x:-1) wands are worth 0.

_OFFER = re.compile(r'offers( only)? (\d+) gold pieces? for (?:your|the) ')

# which object classes each shop type (glyph.SHOP ids) buys; None = everything
SHOP_BUYS = {
    1: None,                                              # general store
    2: {nh.ARMOR_CLASS, nh.WEAPON_CLASS},                 # used armor dealership
    3: {nh.SCROLL_CLASS, nh.SPBOOK_CLASS},                # second-hand bookstore
    4: {nh.POTION_CLASS},                                 # liquor emporium
    5: {nh.WEAPON_CLASS, nh.ARMOR_CLASS},                 # antique weapons outlet
    7: {nh.RING_CLASS, nh.GEM_CLASS, nh.AMULET_CLASS},    # jewelers
    8: {nh.WAND_CLASS},                                   # quality apparel and accessories (a wand shop)
    9: {nh.TOOL_CLASS},                                   # hardware store
    10: {nh.SPBOOK_CLASS, nh.SCROLL_CLASS},               # rare books
}

# what the pack loses by letting a type go, in milli-passes (1.0 = 0.001 expected passes per game), from dev/readiness.py v1.2
# weights (a known levitation potion L_potion 0.057 x 0.42 arrivals alive ~ 24) and the castle-entry census (F310); a
# rough table, only the order and the order of magnitude matter. Types not listed are worth DEFAULT_KEEP.
DEFAULT_KEEP = 0.2
KEEP_MPASS = {
    nh.POTION_CLASS: {'levitation': 24, 'healing': 2, 'extra healing': 3, 'full healing': 4, 'gain level': 3,
                      'polymorph': 3, 'speed': 1, 'gain ability': 1, 'enlightenment': 0.5, 'water': 0},
    nh.SCROLL_CLASS: {'teleportation': 6, 'scare monster': 20, 'earth': 8, 'charging': 6, 'genocide': 6,
                      'enchant armor': 2, 'enchant weapon': 1, 'remove curse': 2, 'identify': 1.5, 'magic mapping': 0.3,
                      'blank paper': 0},
    nh.WAND_CLASS: {'digging': 8, 'striking': 6, 'opening': 8, 'locking': 3, 'sleep': 6, 'cold': 6, 'teleportation': 6,
                    'polymorph': 5, 'fire': 4, 'lightning': 4, 'magic missile': 2, 'death': 6, 'cancellation': 2,
                    'wishing': 5000, 'create monster': 0, 'light': 0, 'nothing': 0, 'secret door detection': 0,
                    'undead turning': 0, 'slow monster': 0, 'speed monster': 0.2, 'make invisible': 0, 'probing': 0,
                    'enlightenment': 0},
    nh.RING_CLASS: {'levitation': 25, 'teleport control': 30, 'polymorph control': 15, 'free action': 5, 'conflict': 15,
                    'regeneration': 3, 'protection': 2, 'polymorph': 4, 'teleportation': 2, 'slow digestion': 1,
                    'increase damage': 0.5, 'warning': 0.5},
    nh.AMULET_CLASS: {'life saving': 20, 'reflection': 15, 'magical breathing': 15, 'ESP': 3},
}
SELL_CLASSES = (nh.POTION_CLASS, nh.SCROLL_CLASS, nh.WAND_CLASS, nh.RING_CLASS, nh.AMULET_CLASS)


def base_cost(o):
    c = getattr(o, 'cost', None)
    if c is None and type(o).__name__ == 'Amulet':
        c = 150
    return c


def game_identified(item):
    """The game (not our inference) shows the type: 'potion of healing', 'amulet of life saving'."""
    return ' of ' in (item.text or '')


def _weights(objs):
    return [max(getattr(o, 'prob', 0) or 0, 1) for o in objs]


def item_loss(item):
    """Milli-passes the pack loses per unit if this item goes (expected over its possible types)."""
    table = KEEP_MPASS.get(item.category, {})
    ws = _weights(item.objs)
    tot = sum(ws)
    return sum(w * table.get(o.name, DEFAULT_KEEP) for o, w in zip(item.objs, ws)) / tot if tot else DEFAULT_KEEP


def unit_gold(item):
    """Expected zm one unit fetches from a shopkeeper (0.5 of the base price, 3/8 from one shopkeeper in four when the
    type is not identified; probability-weighted over the possible types)."""
    costs = [(base_cost(o), w) for o, w in zip(item.objs, _weights(item.objs)) if base_cost(o)]
    if not costs:
        return 0.0
    mean = sum(c * w for c, w in costs) / sum(w for _, w in costs)
    return mean * (0.5 if game_identified(item) else 0.469)


def sellable_item(item):
    """Pack items the sale planner may offer: potions, scrolls, wands, rings, amulets that are not in use, not marked by
    the bot (a '#earth' name), not worth nothing (uncursed water, an emptied wand)."""
    if item.category not in SELL_CLASSES or item.equipped or item.shop_status != Item.NOT_SHOP:
        return False
    if item.naming or item.comment:
        return False
    if item.category == nh.POTION_CLASS and all(o.name == 'water' for o in item.objs):
        return False
    if item.category == nh.WAND_CLASS and item.uses and ':-1' in item.uses:
        return False
    if item.is_container() or item.is_possible_container():
        return False
    return True


def sell_offer(agent, item, accept=False, count=1):
    """Drop `count` units of an inventory item in a costly shop square and answer the shopkeeper's offer (accept=False
    declines it and takes the item back). Returns dict(offer, prompts, sold, uninterested, credit, only, skipped):
    offer = the shopkeeper's TOTAL offer for the dropped units, None when he made no clean offer ('offers only N' with
    his short purse sets only=True; 'seems uninterested' sets uninterested; 'cannot pay you at present' sets credit).
    Shared with the id-engine lane (sell-offer price-ID)."""
    res = dict(offer=None, prompts=[], sold=False, uninterested=False, credit=False, only=False, skipped=False)
    inv = agent.inventory
    bl = agent.blstats
    level = agent.current_level()
    try:
        if not level.shop_interior[bl.y, bl.x] or item.equipped or item not in inv.items.all_items or \
                agent.character.prop.hallu or agent.character.prop.blind or agent.character.prop.polymorph or \
                agent.hands_welded() or agent.get_visible_monsters():
            res['skipped'] = True
            return res
    except Exception:
        res['skipped'] = True
        return res
    letter = inv.items.get_letter(item)
    count = max(1, min(int(count), item.count))
    gold0 = bl.gold
    seen = res['prompts']
    msgs = []

    def gen():
        if item.count > 1:
            yield from str(count)
        yield letter
        for _ in range(8):
            obs = agent._observation
            msg = agent.single_message or ''
            if jf_config.SUPPLY_DEBUG:
                agent.log(f'SUPPLY sell_offer frame misc={[int(v) for v in obs["misc"]]} msg={msg!r}')
            if msg:
                msgs.append(msg)
            if obs['misc'][2]:                # --More-- first: 'You drop X.--More--' still has the offer behind it, and
                yield A.MiscAction.MORE       # the yn flag is already set on that frame
            elif obs['misc'][0] or 'Sell it?' in msg or 'Sell them?' in msg or '[ynaq]' in msg:
                # a y/n question: the sale offer, or credit instead of gold. The prompt is also read from its text: castle-entry
                # saw frames where the NLE yn flag was not set for the offer and a generic handler quit it with q
                seen.append(msg)
                if 'Sell it?' in msg or 'Sell them?' in msg:
                    yield 'y' if accept else 'n'
                else:
                    yield 'n'                 # credit offers and anything else
            else:
                return

    # the whole exchange is one atomic operation: the update hooks run when an atom block ENDS, and a preempting strategy raised
    # there (the bug class of B304/B307/B309) skipped the take-back below, leaving a declined ring / potion on the shop floor
    with agent.atom_operation():
        agent.step(A.Command.DROP, gen())
        msgs.append(agent.message or '')
        text = ' '.join(msgs)
        for p in seen:
            m = _OFFER.search(p)
            if m:
                if m.group(1):
                    res['only'] = True
                else:
                    res['offer'] = int(m.group(2))
        res['uninterested'] = 'seems uninterested' in text
        res['credit'] = 'cannot pay you at present' in text or 'in credit' in text
        inv.items.update(force=True)
        res['sold'] = agent.blstats.gold > gold0
        if not res['sold']:
            # the item lies here again as ours ('no charge'): take it back
            try:
                inv.get_items_below_me()
                mine = [i for i in inv.items_below_me if i.shop_status == Item.NOT_SHOP]
                if mine:
                    inv.pickup(mine)
                inv.items.update(force=True)
            except Exception:
                pass
    return res
