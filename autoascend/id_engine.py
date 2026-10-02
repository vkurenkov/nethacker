"""id-engine lane (team brief v4, lane 6): identification steps outside the scroll-of-identify menu.

power_route.py owns the identify menu (which item a scroll names), the quiet-moment reads of KNOWN identify scrolls
(TC_DIVE_ID / ID_GRIND_READ) and the altar BUC test. This module adds the steps that find out WHICH label is identify
and what else a pack holds, each behind its own jf_config flag (all off by default; ledger I302, F305):

  READ_TEST   read unknown scroll singles at quiet moments until the identify label is known (read.c SCR_IDENTIFY calls
              makeknown before identify_pack, so one read names the type for every later scroll of the label and the
              same read already identifies an item). Ground truth (F305, 90 base games): 17 of 36 castle arrivals still
              held an unread, unknown scroll of identify (21 scrolls); singles are 13-16% identify.
  ID_SELL     price-ID by selling: in a shop that buys the class, drop one unit of each unidentified scroll, ring, wand and
              potion, read the shopkeeper's offer (shk.c set_cost: base / 2, or 3/8 of it from one shopkeeper in four),
              decline, take it back. The offer puts the type in a price group (a 20-zm scroll is identify, a 300-zm ring is
              conflict / polymorph / polymorph control / teleport control). The drop/offer primitive is the supply lane's
              (supply.sell_offer); price_id.learn_offer turns the offer into knowledge.
  ID_BUY_IDENTIFY  a Want for supply's shop-buying strategy: a shelf scroll that is identify (its quote fits only base 20)
              is bought while unknown rings, amulets, wands or boots outnumber the identify scrolls carried.

Risk of reading an unknown scroll, from read.c / explode.c / zap.c (3.6.6), by scroll probability (per 1000 scrolls):
  amnesia 35: forget() blanks this level's map and traps; 1 in 3 forgets rn2(25)% of the discoveries (about 4% of them in
      expectation per read, ~0.14% per read overall) -- harmless for a bot that keeps its own item memory;
  fire 30: explode(dam 2-3) burns each other scroll and potion with chance 1/3 (zap.c destroy_item), rings and wands are
      only destroyed by lightning;
  destroy armor 32: destroy_arm(some_armor()) takes the cloak first, else the body armour, one piece;
  punishment 15: ball and chain (punish); a hard helmet turns the ball's fall through a dug hole into 3 damage;
  create monster 45, teleportation 55 (a random teleport on the level; a CURSED one -- 1 in 8 scrolls are -- is a random
      level teleport: usually up), earth 20 (boulders on the 8 squares around us AND on ours: needs EARTH_BOX, else the
      bot stays boxed for good: cand-i-jf71 s9), scare monster 35 and charging/genocide/stinking cloud (wasted: their
      prompts are declined or answered by GENOCIDE_POLICY).
The reads are therefore limited to: the tour from READ_TEST_XL (or the dive), HP >= 70%, nothing hostile within 7, not
hungry, not afflicted, outside shops and the castle, with EARTH_BOX on, while an unknown ring/amulet/boots/wand worth a
scroll is carried and the identify label is still unknown.
"""

import nle.nethack as nh

from . import jf_config
from . import power_route as PR
from . import price_id
from . import utils
from .exceptions import AgentChangeStrategy, AgentFinished, AgentPanic
from .glyph import G, Hunger
from .level import Level
from .strategy import Strategy


class _State:
    def __init__(self):
        self.next_read_turn = -1
        self.reads = 0
        self.sell_tested = set()   # (level key, glyph) price-tested by a sell offer
        self.sell_nobuy = set()    # (level key, object class) the shopkeeper was 'uninterested' in
        self.sell_fail = 0         # attempts that gave no clean offer (the strategy gives up after ID_SELL_MAX_FAIL)
        self.sells = 0
        self.sell_walks = 0        # calls spent walking to a free shop square (a watchdog)
        self.sell_skips = 0        # consecutive skipped tries
        self.sell_next_turn = -1   # no sell test before this turn (a skipped try waits a few turns)


def _st(agent):
    st = getattr(agent, '_ideng', None)
    if st is None:
        st = agent._ideng = _State()
    return st


def _log(agent, msg):
    agent.log(f'IDENG {msg}')


def identify_discovered(agent):
    """The bot knows which label is identify (discovered by a read, a price, or the game's discoveries list)."""
    return PR.IDENTIFY_SCROLL in agent.inventory.item_manager.object_to_glyph


def quiet(agent, hp_frac=0.7, hostile_radius=7, allow_shop=False):
    """A moment for a no-risk-to-the-plan action: not hurt, nothing hostile near, fed, unafflicted, not in a shop."""
    bl = agent.blstats
    prop = agent.character.prop
    if prop.blind or prop.confusion or prop.stun or prop.hallu or prop.polymorph:
        return False
    if bl.hitpoints < hp_frac * bl.max_hitpoints or bl.hunger_state >= Hunger.WEAK or bl.carrying_capacity >= 3:
        return False
    level = agent.current_level()
    if level.shop_interior[bl.y, bl.x] and not allow_shop:
        return False
    if int(agent.last_observation['blstats'][nh.NLE_BL_CONDITION]) & nh.BL_MASK_LEV:
        return False
    if PR._hostiles_within(agent, hostile_radius):
        return False
    return True


def _target_worth_a_scroll(agent):
    """An unknown ring, boots, amulet or wand is carried (power_route._id_value_priority at least ID_GRIND_MIN_VALUE)."""
    return any((PR._id_value_priority(agent, i) or 0) >= jf_config.ID_GRIND_MIN_VALUE for i in PR._items(agent)
               if i.category != nh.SCROLL_CLASS)


# ------------------------------------------------------------------------------------------------ READ_TEST

def read_test_item(agent):
    """The unknown scroll to read next, or None. Cheap tests first: this runs on every step of the preempt chain."""
    if not jf_config.READ_TEST:
        return None
    if jf_config.READ_TEST_REQUIRES_EARTH_BOX and not jf_config.EARTH_BOX:
        return None
    bl = agent.blstats
    if bl.experience_level < jf_config.READ_TEST_XL or bl.time < _st(agent).next_read_turn:
        return None
    if identify_discovered(agent):
        return None
    if jf_config.READ_TEST_CLOAK and agent.inventory.items.cloak is None:
        return None   # a scroll of destroy armor takes the cloak first (zap.c some_armor): body armour is spared
    st = PR.state(agent)
    cands = []
    for it in PR.unknown_scrolls(agent):
        g = PR._glyph(it)
        if g in st.read_glyphs or g in st.confuse_glyphs:
            continue
        if PR.known_cursed(it) and PR.TELE_SCROLL in it.objs:
            continue   # a cursed teleport scroll without TC on is a random level teleport (up, off the plan)
        p = PR._p(it, {PR.IDENTIFY_SCROLL})
        if p < jf_config.READ_TEST_MIN_P:
            continue   # a price group that excludes identify (or a label known to be something else)
        # stacks first (a pair of equal labels is identify 46% of the time, a triple 73%: the label probabilities are
        # squared / cubed), then the likelier identify
        cands.append((-min(it.count, 4), -p, it.text or '', it))
    if not cands:
        return None
    level = agent.current_level()
    if level.dungeon_number not in (Level.DUNGEONS_OF_DOOM, Level.GNOMISH_MINES) or \
            bl.depth > jf_config.READ_TEST_MAX_DEPTH:
        return None
    if not _target_worth_a_scroll(agent) or not quiet(agent):
        return None
    cands.sort(key=lambda c: c[:3])
    hook = getattr(PR, 'scroll_read_ok', None)   # t-route's veto (cursed teleport bookkeeping); absent = always ok
    for _, _, _, it in cands:
        if hook is None or hook(agent, it):
            return it
    return None


def read_test_step(agent, item):
    st = _st(agent)
    st.reads += 1
    st.next_read_turn = agent.blstats.time + jf_config.READ_TEST_GAP
    p = PR._p(item, {PR.IDENTIFY_SCROLL})
    _log(agent, f'READ_TEST {item.text!r}: P(identify)={p:.2f}, read #{st.reads}')
    PR._read(agent, item, f'read-test of an unknown scroll (P(identify)={p:.2f})')


# ------------------------------------------------------------------------------------------------ ID_SELL: sell offers

SELL_CLASSES = (nh.SCROLL_CLASS, nh.RING_CLASS, nh.WAND_CLASS, nh.POTION_CLASS)
SELL_ORDER = {nh.SCROLL_CLASS: 0, nh.RING_CLASS: 1, nh.WAND_CLASS: 2, nh.POTION_CLASS: 3}
# shknam.c saleable(): the classes each shop type (glyph.SHOP ids) buys; None = everything. The delicatessen buys only
# fruit juice, booze and water, the health food store and the lighting store a few named types: not worth a trip.
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


def _shop_buys(shop_type, cat):
    if shop_type == 0:
        return True   # the type is unknown (no 'Welcome to ...' message seen): try once, 'seems uninterested' tells
    if shop_type not in SHOP_BUYS:
        return False
    buys = SHOP_BUYS[shop_type]
    return buys is None or cat in buys


def sell_candidates(agent):
    """Pack items whose price group a sell offer here would narrow, scrolls first (a 20-zm scroll is identify)."""
    level = agent.current_level()
    bl = agent.blstats
    shop_type = int(level.shop_type[bl.y, bl.x])
    if shop_type != 0 and shop_type not in SHOP_BUYS:
        return []
    st = _st(agent)
    out = []
    for it in PR._items(agent):
        cat = it.category
        if cat not in SELL_CLASSES or it.equipped or it.is_unambiguous() or len(it.glyphs) != 1:
            continue
        if not _shop_buys(shop_type, cat) or (level.key(), cat) in st.sell_nobuy:
            continue
        if (level.key(), it.glyphs[0]) in st.sell_tested or len(price_id.bases(it)) <= 1:
            continue
        if cat == nh.WAND_CLASS and ((it.uses and ':-1' in it.uses) or it.comment == 'EMPT'):
            continue   # a wand with no charge left is worth 0 to a shopkeeper (shk.c getprice)
        if it.comment or it.shop_status != 0:
            continue
        out.append(it)
    out.sort(key=lambda i: (SELL_ORDER[i.category], i.text or ''))
    return out


def sell_id_item(agent):
    """The pack item to price-test next in the shop we stand in, or None (cheap tests first: every step runs this)."""
    if not jf_config.ID_SELL:
        return None
    bl = agent.blstats
    level = agent.current_level()
    if not level.shop_interior[bl.y, bl.x]:
        return None
    st = _st(agent)
    if st.sell_fail >= jf_config.ID_SELL_MAX_FAIL or bl.time < st.sell_next_turn:
        return None
    if not quiet(agent, hp_frac=0.5, hostile_radius=7, allow_shop=True):
        return None
    if not utils.isin(agent.glyphs, G.SHOPKEEPER).any():
        return None
    cands = sell_candidates(agent)
    return cands[0] if cands else None


def sell_id_step(agent, item):
    """Go to a free interior square, then drop one unit, read the offer, decline, take it back, and learn the price group."""
    try:
        from . import supply
        sell_offer = supply.sell_offer
    except Exception:   # the supply lane is not merged: no shop primitive
        _st(agent).sell_fail = 10 ** 6
        return
    bl = agent.blstats
    level = agent.current_level()
    st = _st(agent)
    dis = agent.bfs()
    free = level.shop_interior & (level.item_count == 0) & (dis != -1)
    if not free.any():
        st.sell_fail += 1
        return
    if not free[bl.y, bl.x]:
        # watchdog: a walk that does not end in a test (a blocked path, a shopkeeper in the way) gives up after 40 calls
        st.sell_walks += 1
        if st.sell_walks > 40:
            st.sell_walks = 0
            st.sell_fail += 2
            _log(agent, 'ID_SELL: no free square reached after 40 moves')
            return
        ty, tx = min(zip(*free.nonzero()), key=lambda p: dis[p])
        agent.go_to(ty, tx)
        return
    st.sell_walks = 0
    st.sell_tested.add((level.key(), item.glyphs[0]))
    cat = item.category
    text = item.text
    bases_before = price_id.bases(item)
    try:
        res = sell_offer(agent, item, accept=False, count=1)
    except (AgentPanic, AgentChangeStrategy, AgentFinished):
        if jf_config.PREEMPT_SAFE:
            # F362: the offer was cut short (supply.sell_offer is one atomic block, so the item is back in the pack but its parse
            # went with the exception): not tested after all, ask again at the next quiet moment
            st.sell_tested.discard((level.key(), item.glyphs[0]))
        raise
    except Exception as e:   # a failing shop primitive must not repeat on every step
        st.sell_fail += 1
        _log(agent, f'ID_SELL {text!r}: sell_offer failed {e!r}')
        return
    if res.get('skipped'):   # a monster in view, not a costly square, ...: nothing was dropped, try again in a few turns
        st.sell_tested.discard((level.key(), item.glyphs[0]))
        st.sell_next_turn = bl.time + 5
        st.sell_skips += 1
        if st.sell_skips >= 12:
            st.sell_fail += 1
            st.sell_skips = 0
        return
    st.sells += 1
    if res.get('uninterested'):
        st.sell_nobuy.add((level.key(), cat))
        _log(agent, f'ID_SELL {text!r}: the shopkeeper is uninterested in class {cat}')
        return
    offer = res.get('offer')
    if offer is None:
        st.sell_fail += 1
        _log(agent, f'ID_SELL {text!r}: no clean offer {res}')
        return
    changed = price_id.learn_offer(agent, item, offer, why='ID_SELL')
    agent.inventory.items.update(force=True)
    _log(agent, f'ID_SELL {text!r}: offer {offer} (bases were {bases_before}) -> '
                f'{"narrowed" if changed else "no change"}')


# ------------------------------------------------------------------------------------------------ ID_BUY_IDENTIFY

def identify_wanted(agent):
    """More unknown rings, amulets, boots or wands worth a scroll are carried than identify scrolls (cap ID_BUY_MAX)."""
    targets = sum(1 for i in PR._items(agent) if i.category != nh.SCROLL_CLASS and
                  (PR._id_value_priority(agent, i) or 0) >= jf_config.ID_GRIND_MIN_VALUE)
    have = sum(i.count for i in PR.known_identify(agent))
    return targets > have and have < jf_config.ID_BUY_MAX


def register_wants():
    """Append the identify Want to the supply lane's registry (EXTRA_WANTS) when that lane is merged; a no-op else."""
    try:
        from . import supply
        if any(w.tag == 'identify' for w in supply.EXTRA_WANTS):
            return True

        def test(agent, item, gobj, unit):
            return item.category == nh.SCROLL_CLASS and \
                {o.name for o in supply.consistent_objs(agent, item)} == {'identify'}

        def need(agent):
            return bool(jf_config.ID_BUY_IDENTIFY) and identify_wanted(agent)

        supply.EXTRA_WANTS.append(supply.Want('identify', 2, lambda: jf_config.ID_BUY_CAP, test, need, 15.0))
        return True
    except Exception:
        return False


register_wants()


# ------------------------------------------------------------------------------------------------ the preempt layer

def strategy(agent):
    """Preempt layer (global_logic): one quiet-moment identification action per call."""
    def plan():
        try:
            it = read_test_item(agent)
            if it is not None:
                return 'read', it
            it = sell_id_item(agent)
            if it is not None:
                return 'sell', it
        except Exception as e:   # a readiness check must never break the preempt loop
            agent.log(f'IDENG check failed: {e!r}')
        return None

    def f():
        if plan() is None:
            yield False
            return
        yield True
        p = plan()   # (the inventory may have been re-parsed since the condition ran)
        if p is None:
            return
        kind, item = p
        if kind == 'read':
            read_test_step(agent, item)
        else:
            sell_id_step(agent, item)

    return Strategy(f)
