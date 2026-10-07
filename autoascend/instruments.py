"""Instruments lane (phase 2): more castle arrivals that carry a tonal instrument (horn, flute, harp, bugle).

An instrument is the input of the crusher route (castle_crusher.py: Mastermind on the drawbridge's passtune, the
bridge toggled on the garrison); every one of the 8 tonal types plays it (music.c do_play_instrument), drums, whistles
and the horn of plenty do not. Ground truth of 135 base games (dev/instr_truth.py, JF_TRUTH runs): a tonal instrument
lay on a visited level (Dlvl 1-4, the Gnomish Mines, shop shelves) in 18% of the games and the bot carried one out of
7% -- 11 of them on shop shelves (1 bought: gold 0-35 against quotes of 20-100 zm), 11 on the floor (4 picked up; the
others seen while the dive travelled, never approached, or out of sight), 3 on unexplored Mines levels.

This module holds, behind INSTR_* / INSTRUMENT_* flags (all off in the commit that adds them):

  * INSTR_LOG (logging only; a game plays exactly as without it): 'INSTR ...' lines in the dev bot log -- every
    instrument glyph the map shows (first sighting per square), what the item knapsack says about a floor instrument
    we know (count), and every change of the instruments in the pack with the messages around it.

  * INSTRUMENT_PICK (the pick_strategy layer of global_logic's shop block): a tonal instrument in view on the map -- its
    glyph names the exact type, so a horn of plenty, a drum or a whistle never lures it -- is walked to and taken when the
    pack holds none, at a calm moment (no hostile within 7, HP >= half, not Weak, not levitating), outside shops, within
    INSTRUMENT_PICK_DIST steps, on Dungeons/Mines levels above INSTRUMENT_PICK_MAX_DEPTH. gather_items runs only inside the
    tour's exploration, so an instrument seen while the dive or the Mines camp travels was never approached (truth: 4 of 11
    floor instruments in 135 base games).

  * INSTRUMENT_SHOP (the shop_strategy layer, before buy_instrument): the instrument-only part of the supply lane's shop
    machinery, kept inside this module so that a game without a tonal glyph on a shelf plays exactly as the base does (the
    paired arms can then skip such games): a tonal glyph on a shop square is walked to (the price shows once we stand on it),
    the instrument is bought up to INSTRUMENT_SHOP_MAX zm -- also by a hero who stands inside the shop with a digging tool --
    and when the gold falls short the pack's potions/scrolls/wands/rings/amulets worth least to us are sold to the shop (a
    general store takes them; supply.Supply.plan_sales / sell_offer do the arithmetic) before paying.

  * INSTRUMENT_PREFER: which instrument to take / buy / keep / play when more than one is on offer. The crusher passes 5.9% of
    tooled-horn kits, 2.8% of flute kits and 1.7% of harp kits (cand-l5, metrics F374; a blown horn scares: PASSTUNE_HORN_XORN /
    _PRESS), so a horn outranks a flute, a flute a harp or a bugle (instruments.RANK; unknown candidates count by the mean of
    their tonal types): the knapsack keeps the best one, a better one than the pack's is still picked up or bought, and
    castle_crusher plays the best.

Pure functions below only read the agent (the last observation, the level, the item lists): they never step the
environment, never touch an RNG and never write agent state other than their own `_instr` bookkeeping attribute.
"""
import numpy as np
import nle.nethack as nh

from . import jf_config, jf_log
from . import objects as O
from . import opp_items
from . import supply
from .exceptions import AgentChangeStrategy, AgentFinished
from .glyph import Hunger
from .item import Item, flatten_items
from .level import Level
from .strategy import Strategy

TONAL_NAMES = frozenset(('tooled horn', 'frost horn', 'fire horn', 'wooden flute', 'magic flute', 'wooden harp',
                         'magic harp', 'bugle'))
# instruments that do NOT play the passtune: logged to see how often the look-alike confuses a text match
OTHER_NAMES = frozenset(('horn of plenty', 'leather drum', 'drum of earthquake', 'tin whistle', 'magic whistle'))
HORN_NAMES = frozenset(('tooled horn', 'frost horn', 'fire horn'))

_GLYPH_NAMES = None


def glyph_names():
    """{object glyph id: type name} for the tonal instruments and their look-alikes (tools are unshuffled in the
    arena's glyph ids: ledger F308 / U306 / U308)."""
    global _GLYPH_NAMES
    if _GLYPH_NAMES is None:
        out = {}
        for otyp, o in enumerate(O.objects):
            if o is None:
                continue
            try:
                name = o.name
                if name in TONAL_NAMES or name in OTHER_NAMES:
                    if O.get_category(o) == nh.TOOL_CLASS:
                        out[int(nh.GLYPH_OBJ_OFF) + otyp] = name
            except Exception:
                continue
        _GLYPH_NAMES = out
    return _GLYPH_NAMES


def glyph_name(glyph):
    try:
        return glyph_names().get(int(glyph))
    except (TypeError, ValueError):
        return None


# lower = better: the crusher's pass rate by type (cand-l5, metrics F374 / R467: tooled horn 5.9%, wooden flute 2.8%, wooden harp 1.7%,
# bugle 1.56% [0.8, 3.2] -- a harp-class find; a frost / fire horn plays the tune and, when its charges are gone or it is improvised
# without a direction, scares like a tooled horn, unmeasured so it ranks just behind the tooled horn). The bugle ties with the harp (the
# lighter one wins the tie in the knapsack).
RANK = {'tooled horn': 0, 'frost horn': 1, 'fire horn': 1, 'wooden flute': 2, 'magic flute': 2,
        'wooden harp': 3, 'magic harp': 3, 'bugle': 3}


def item_rank(item):
    """How good an instrument this item is (lower is better): its own glyph's type when the glyph names one, else the mean over the
    tonal types it may be (an unidentified 'horn': tooled / frost / fire); 9 when it may be none."""
    try:
        names = [glyph_name(g) for g in (item.glyphs or [])]
        if names and all(n in RANK for n in names):
            return float(min(RANK[n] for n in names))
        rs = [RANK[o.name] for o in item.objs if o.name in RANK]
        return sum(rs) / len(rs) if rs else 9.0
    except Exception:
        return 9.0


def pack_best_rank(agent):
    """The best rank among the instruments in the pack (opp_items.is_tonal), None when it holds none."""
    best = None
    try:
        for item in flatten_items(agent.inventory.items):
            if item.shop_status == Item.UNPAID or not opp_items.is_tonal(item):
                continue
            r = item_rank(item)
            if best is None or r < best:
                best = r
    except Exception:
        return 0.0
    return best


class _Book:
    def __init__(self):
        self.sighted = set()      # (level key, y, x, glyph)
        self.known = set()        # (level key, y, x, text)
        self.pack = {}            # letter -> text of the tonal-candidate items in the pack
        self.errors = 0
        self.pack_init = False
        self.pending = None       # the pack set seen on the last observation when it differs from self.pack
        self.pending_n = 0


def _book(agent):
    b = getattr(agent, '_instr', None)
    if b is None:
        b = agent._instr = _Book()
    return b


def _is_tonal_candidate(item):
    try:
        return item.category == nh.TOOL_CLASS and any(o.name in TONAL_NAMES for o in item.objs)
    except Exception:
        return False


def _is_look_alike(item):
    try:
        return item.category == nh.TOOL_CLASS and any(o.name in OTHER_NAMES for o in item.objs)
    except Exception:
        return False


def _task_name(agent):
    try:
        return getattr(agent.global_logic.dive, '_last_task', None)
    except Exception:
        return None


def _knapsack_count(agent, item):
    """What arrange_items / go_to_item_to_pickup would take of this floor item (the item priority's count), or None."""
    inv = agent.inventory
    free_items = [i for i in flatten_items(inv.items) if inv._droppable(i)]
    forced_items = [i for i in flatten_items(inv.items) if not inv._droppable(i)]
    split = agent.global_logic.item_priority.split(free_items + [item], forced_items,
                                                   agent.character.carrying_capacity)
    counts = np.array(list(split.values())).sum(0)
    return int(counts[len(free_items)])


def note(agent):
    """Agent.update calls this on every observation when jf_config.INSTR_LOG is on. Cheap unless an instrument glyph is
    on the map or in the pack; never raises."""
    if not jf_config.INSTR_LOG or not jf_log.enabled():
        return
    try:
        _note(agent)
    except Exception as e:
        b = _book(agent)
        if b.errors < 3:
            b.errors += 1
            try:
                agent.log(f'INSTR error {type(e).__name__}: {str(e)[:200]}')
            except Exception:
                pass


def _note(agent):
    b = _book(agent)
    bl = agent.blstats
    level = agent.current_level()
    key = level.key()
    glyphs = agent.glyphs
    names = glyph_names()
    ids = np.fromiter(names.keys(), dtype=np.int64)
    mask = np.isin(glyphs, ids)
    if mask.any():
        for y, x in zip(*mask.nonzero()):
            y, x = int(y), int(x)
            g = int(glyphs[y, x])
            k = (key, y, x, g)
            if k in b.sighted:
                continue
            b.sighted.add(k)
            items = level.items[y, x]
            known = [i for i in (items or []) if _is_tonal_candidate(i) or _is_look_alike(i)]
            agent.log(f'INSTR see {names[g]} at {(y, x)} lvl={key[0]}:{key[1]} cheb={max(abs(y - bl.y), abs(x - bl.x))} '
                      f'shop={int(bool(level.shop_interior[y, x]))} known={[i.text for i in known] or "-"} '
                      f'task={_task_name(agent)}')
    # floor instruments the bot has looked at: price (shelf) or the knapsack's count (floor)
    here_items = None
    try:
        here_items = agent.inventory.items_below_me
    except Exception:
        here_items = None
    for (y, x) in [(int(bl.y), int(bl.x))]:
        for item in (here_items or []):
            if not (_is_tonal_candidate(item) or _is_look_alike(item)):
                continue
            k = (key, y, x, item.text)
            if k in b.known:
                continue
            b.known.add(k)
            cnt = None
            if item.shop_status == Item.NOT_SHOP:
                try:
                    cnt = _knapsack_count(agent, item)
                except Exception as e:
                    cnt = f'err {type(e).__name__}'
            agent.log(f'INSTR here {item.text!r} at {(y, x)} lvl={key[0]}:{key[1]} shop_status={item.shop_status} '
                      f'price={item.price} objs={[o.name for o in item.objs][:4]} knapsack_count={cnt} '
                      f'gold={bl.gold} task={_task_name(agent)}')
    # the instruments in the pack (tonal candidates only; a change counts once it holds for 4 observations in a row: the
    # item list is momentarily cut while a carried bag is checked)
    try:
        inv_items = agent.inventory.items
        if inv_items.all_letters is not None and len(inv_items.all_letters) > 0:
            cur = {}
            for letter, item in zip(inv_items.all_letters, inv_items.all_items):
                if _is_tonal_candidate(item):
                    ex = [glyph_name(g) for g in (item.glyphs or [])]
                    cur[letter] = item.text + (f' [{",".join(n or "?" for n in ex)}]' if ex else '')
            if cur == b.pack:
                b.pending, b.pending_n = None, 0
            else:
                if b.pending == cur:
                    b.pending_n += 1
                else:
                    b.pending, b.pending_n = cur, 1
                if b.pending_n >= 4:
                    if b.pack_init:
                        for letter, text in cur.items():
                            if b.pack.get(letter) != text:
                                agent.log(f'INSTR pack + {letter} - {text} gold={bl.gold} msgs={_recent(agent)}')
                        for letter, text in b.pack.items():
                            if cur.get(letter) != text:
                                agent.log(f'INSTR pack - {letter} - {text} gold={bl.gold} msgs={_recent(agent)}')
                    b.pack = cur
                    b.pack_init = True
                    b.pending, b.pending_n = None, 0
    except Exception:
        pass


def _recent(agent, n=3):
    try:
        return [m for m in list(agent._message_history)[-n:]]
    except Exception:
        return []


# ------------------------------------------------------------------------------------------------ INSTRUMENT_PICK

_TONAL_IDS = None


def tonal_ids():
    global _TONAL_IDS
    if _TONAL_IDS is None:
        _TONAL_IDS = np.array([g for g, n in glyph_names().items() if n in TONAL_NAMES], dtype=np.int64)
    return _TONAL_IDS


def pack_has_tonal(agent):
    """The pack holds an instrument that plays the tune, or may: opp_items.is_tonal, the test INSTRUMENT_KEEP's knapsack keeps by (an
    unidentified 'horn' may be a horn of plenty unless INSTRUMENT_GLYPH lets its glyph decide)."""
    try:
        for item in flatten_items(agent.inventory.items):
            if item.shop_status == Item.UNPAID:
                continue
            if opp_items.is_tonal(item):
                return True
    except Exception:
        return True
    return False


_ALL_IDS = None


def all_ids():
    global _ALL_IDS
    if _ALL_IDS is None:
        _ALL_IDS = np.array(list(glyph_names().keys()), dtype=np.int64)
    return _ALL_IDS


def _pick_state(agent):
    b = _book(agent)
    if not hasattr(b, 'pick_done'):
        b.pick_done = set()       # (level key, y, x): looked at / picked / given up
        b.pick_target = None      # (level key, (y, x))
        b.pick_since = 0
        b.pick_tries = {}
        b.glyph_at = {}           # (level key, y, x) -> instrument type name seen on that square's glyph
        b.shop_looked = set()     # (level key, y, x): shelf squares walked to for their price
        b.shop_tries = {}
        b.shop_blocked = {}       # (level key, y, x) -> turn until which the shelf item is left alone
        b.bought = 0
    return b


def _guarded(agent, planner):
    """Run a read-only planner (_pick_target / _shop_plan). An exception in it is logged and costs the lane one of its five lives for
    the game -- a planner that raised on every observation would otherwise turn into a panic loop -- and the layer then stays out of
    the way. The agent's own control-flow exceptions pass."""
    b = _pick_state(agent)
    n = getattr(b, 'plan_errors', 0)
    if n >= 5:
        return None
    try:
        return planner(agent)
    except (AgentFinished, AgentChangeStrategy, KeyboardInterrupt, SystemExit):
        raise
    except Exception as e:
        b.plan_errors = n + 1
        try:
            agent.log(f'INSTR planner error {planner.__name__} {type(e).__name__}: {str(e)[:200]} ({n + 1} of 5)')
        except Exception:
            pass
        return None


def remember(agent):
    """Agent.update, every observation, when INSTRUMENT_PICK / SHOP / GLYPH is on: keep the type each instrument glyph on the map was
    (a shelf item's text does not say, and the glyph is gone from the screen once we stand on it). Reads only."""
    try:
        _remember_glyphs(agent, _pick_state(agent), agent.current_level().key())
    except Exception:
        pass


def shelf_not_tonal(agent, level, y, x):
    """True when the glyph this shop square showed names an instrument that plays no tune (a horn of plenty, a drum, a whistle):
    INSTRUMENT_GLYPH keeps buy_instrument from paying for one."""
    try:
        g = _pick_state(agent).glyph_at.get((level.key(), int(y), int(x)))
        return g is not None and g not in TONAL_NAMES
    except Exception:
        return False


def _recent_damage(agent):
    """The hero lost HP between two of the dive logic's last observed turns (its _hp_history keeps the last 12): something is hurting
    us or just did. A walk to an instrument is optional and waits for that to be over."""
    try:
        hist = agent.global_logic.dive._hp_history
        return any(b[1] < a[1] for a, b in zip(hist, hist[1:]))
    except Exception:
        return False


def _pick_target(agent):
    """('here', (y, x)) when we stand on a tonal item square we have not dealt with, ('walk', (y, x, name, dist)) for the best tonal
    glyph in reach (INSTRUMENT_PREFER: the best type, then the nearest; else the nearest), else None. Reads only. Only while the
    dive runs: the tour's exploration (gather_items) takes what it passes, and acting there only perturbs the game."""
    bl = agent.blstats
    if bl.depth > jf_config.INSTRUMENT_PICK_MAX_DEPTH:
        return None
    level = agent.current_level()
    if level.dungeon_number not in (Level.DUNGEONS_OF_DOOM, Level.GNOMISH_MINES):
        return None
    dive = agent.global_logic.dive
    if not dive.diving:
        return None
    if bl.hunger_state >= Hunger.WEAK or bl.hitpoints < jf_config.INSTRUMENT_PICK_HP * bl.max_hitpoints:
        return None
    st = _pick_state(agent)
    key = level.key()
    here = (int(bl.y), int(bl.x))
    below = agent.inventory.items_below_me or []
    on_here = [i for i in below if i.shop_status == Item.NOT_SHOP and opp_items.is_tonal(i)]
    mask = np.isin(agent.glyphs, tonal_ids())
    if not on_here and not mask.any():
        return None
    ch = agent.character
    if ch.prop.hallu or ch.prop.blind or ch.prop.polymorph or ch.prop.stun or ch.prop.confusion:
        return None
    if bool(int(agent.last_observation['blstats'][nh.NLE_BL_CONDITION]) & getattr(nh, 'BL_MASK_LEV', 0)):
        return None
    if level.shop_interior[here] or level.shop[here]:
        return None
    if _recent_damage(agent):
        return None
    pack_rank = pack_best_rank(agent)
    prefer = jf_config.INSTRUMENT_PREFER
    if pack_rank is not None and not prefer:
        return None
    for m in agent.get_visible_monsters():
        if max(abs(int(m[1]) - bl.y), abs(int(m[2]) - bl.x)) <= 7:
            return None
    if on_here and (key,) + here not in st.pick_done:
        gname = st.glyph_at.get((key,) + here)
        if gname is not None and gname not in TONAL_NAMES:
            st.pick_done.add((key,) + here)       # a horn of plenty, a drum...: not an instrument for the tune
        elif pack_rank is not None and min(item_rank(i) for i in on_here) >= pack_rank:
            st.pick_done.add((key,) + here)       # PREFER: nothing better than what we carry
        else:
            return ('here', here)
    if not mask.any():
        return None
    dis = agent.bfs()
    mask &= (dis > 0) & (dis <= jf_config.INSTRUMENT_PICK_DIST) & ~level.shop_interior & ~level.shop
    for k in list(st.pick_done):
        if k[0] == key:
            mask[k[1], k[2]] = False
    if not mask.any():
        return None
    ys, xs = mask.nonzero()
    best = None
    for y, x in zip(ys, xs):
        y, x = int(y), int(x)
        name = glyph_name(agent.glyphs[y, x])
        r = RANK.get(name, 9)
        if pack_rank is not None and r >= pack_rank:
            continue          # (PREFER only: without it a carried instrument returned above)
        k = (r if prefer else 0, int(dis[y, x]))
        if best is None or k < best[0]:
            best = (k, y, x, name)
    if best is None:
        return None
    _, y, x, name = best
    return ('walk', (y, x, name, int(dis[y, x])))


@Strategy.wrap
def pick_strategy(agent):
    """INSTRUMENT_PICK: walk to a tonal instrument in view and take it (see the module docstring)."""
    if not jf_config.INSTRUMENT_PICK:
        yield False
    target = _guarded(agent, _pick_target)
    if target is None:
        yield False
    yield True
    st = _pick_state(agent)
    level = agent.current_level()
    key = level.key()
    bl = agent.blstats
    kind, data = target
    if kind == 'here':
        st.pick_done.add((key,) + data)
        agent.log(f'INSTR pick: taking what lies here {data}: {[i.text for i in (agent.inventory.items_below_me or [])][:4]}')
        agent.inventory.pickup_and_drop_items().run()
        return
    y, x, name, dist = data
    tk = (key, y, x)
    if st.pick_target != (key, (y, x)):
        st.pick_target = (key, (y, x))
        st.pick_since = bl.time
        st.pick_tries[tk] = 0
        agent.log(f'INSTR pick: walking to {name} at {(y, x)}, {dist} steps (gold {bl.gold})')
    st.pick_tries[tk] = st.pick_tries.get(tk, 0) + 1
    if st.pick_tries[tk] > 8 or bl.time - st.pick_since > 3 * jf_config.INSTRUMENT_PICK_DIST + 40:
        st.pick_done.add(tk)      # could not get there in time (a boulder, a closed door, something in the way)
        agent.log(f'INSTR pick: giving up on {name} at {(y, x)} after {st.pick_tries[tk]} tries')
        return
    agent.go_to(y, x)


# ------------------------------------------------------------------------------------------------ INSTRUMENT_SHOP

SHOP_VALUE = 20.0     # milli-passes an instrument is worth (supply.WANTS): a sale may lose at most half of it


def _remember_glyphs(agent, st, key):
    if agent.character.prop.hallu:
        return      # a hallucinating hero sees a new random object glyph on every square every turn
    seen_any = np.isin(agent.glyphs, all_ids())
    if seen_any.any():
        for y, x in zip(*seen_any.nonzero()):
            st.glyph_at[(key, int(y), int(x))] = glyph_name(agent.glyphs[y, x])


def _shelf_is_tonal(agent, st, key, y, x, item, single):
    """A shop item is an instrument that plays the tune: the glyph this square showed (exact type), else the types its
    quote allows (a 'horn' quoted 15 base is a tooled horn, 50 base frost / fire / plenty)."""
    if item.category != nh.TOOL_CLASS:
        return False
    gname = st.glyph_at.get((key, y, x)) if single else None
    if gname is not None:
        return gname in TONAL_NAMES
    objs = supply.consistent_objs(agent, item)
    return bool(objs) and supply.tonal_share(objs) >= 0.5


def _shop_plan(agent):
    """What the instrument shop layer would do now, or None: ('buy', y, x, price, item) | ('sell', y, x, price, item)
    | ('look', y, x). Reads only."""
    bl = agent.blstats
    level = agent.current_level()
    if not level.shop_interior.any():
        return None
    if bl.hunger_state >= Hunger.WEAK or getattr(agent, '_shop_wish_holding', False):
        return None
    ch = agent.character
    if ch.prop.hallu or ch.prop.blind or ch.prop.polymorph:
        return None
    if jf_config.SHOP_WISH:
        from . import shop_wish
        if shop_wish.owes(agent):
            return None
    inv = agent.inventory
    if any(i.shop_status == Item.UNPAID for i in flatten_items(inv.items)):
        return None
    st = _pick_state(agent)
    key = level.key()
    _remember_glyphs(agent, st, key)
    shelf_glyph = np.isin(agent.glyphs, tonal_ids()) & level.shop_interior
    here = (int(bl.y), int(bl.x))
    inside = bool(level.shop_interior[here])
    known = []
    for y, x in zip(*(level.shop_interior & (level.item_count > 0)).nonzero()):
        y, x = int(y), int(x)
        items = level.items[y, x]
        for item in items:
            if item.shop_status != Item.FOR_SALE:
                continue
            unit = supply.unit_quote(item)
            if unit is None or unit > jf_config.INSTRUMENT_SHOP_MAX:
                continue
            if not _shelf_is_tonal(agent, st, key, y, x, item, len(items) == 1):
                continue
            known.append((unit, y, x, item))
    if not known and not shelf_glyph.any():
        return None
    pack_rank = pack_best_rank(agent)
    prefer = jf_config.INSTRUMENT_PREFER
    if pack_rank is not None and not prefer:
        return None
    if agent._carries_digging_tool() and not inside:
        return None        # the shopkeeper bars the door to a pick-axe; inside it, shopping is fine
    for m in agent.get_visible_monsters():
        if max(abs(int(m[1]) - bl.y), abs(int(m[2]) - bl.x)) <= 7:
            return None
    dis = agent.bfs()

    def shelf_rank(y, x, item):
        gname = st.glyph_at.get((key, y, x))
        if gname in RANK:
            return float(RANK[gname])
        rs = [RANK[o.name] for o in supply.consistent_objs(agent, item) if o.name in RANK]
        return sum(rs) / len(rs) if rs else 9.0

    rows = []
    for (unit, y, x, item) in known:
        r = shelf_rank(y, x, item) if prefer else 0.0
        if pack_rank is not None and r >= pack_rank:
            continue          # PREFER: nothing better than what we carry
        rows.append((r, unit, int(dis[y, x]), y, x, item))
    for (r, unit, d, y, x, item) in sorted(rows, key=lambda t: t[:3]):
        if dis[y, x] == -1 or st.shop_blocked.get((key, y, x), -1) > bl.time:
            continue
        if unit <= bl.gold:
            return ('buy', y, x, unit, item)
        if jf_config.INSTRUMENT_SELL:
            return ('sell', y, x, unit, item)
    # a tonal glyph on a shelf whose price we do not know yet: stand on it
    cand = shelf_glyph & (level.item_count == 0) & (dis > 0)
    for k in st.shop_looked:
        if k[0] == key:
            cand[k[1], k[2]] = False
    if pack_rank is not None:
        for y, x in zip(*cand.nonzero()):
            if RANK.get(glyph_name(agent.glyphs[y, x]), 9) >= pack_rank:
                cand[y, x] = False
    if cand.any():
        ys, xs = cand.nonzero()
        i = int(np.argmin(dis[ys, xs]))
        return ('look', int(ys[i]), int(xs[i]))
    return None


@Strategy.wrap
def shop_strategy(agent):
    """INSTRUMENT_SHOP: look at, pay for (selling junk when short) and take a shop's instrument; see the module docstring."""
    if not jf_config.INSTRUMENT_SHOP:
        yield False
    plan = _guarded(agent, _shop_plan)
    if plan is None:
        yield False
    yield True
    st = _pick_state(agent)
    bl = agent.blstats
    inv = agent.inventory
    level = agent.current_level()
    key = level.key()
    kind = plan[0]
    if kind == 'look':
        _, y, x = plan
        st.shop_looked.add((key, y, x))
        agent.log(f'INSTR shop: looking at the instrument on {(y, x)}')
        agent.go_to(y, x)
        return
    _, y, x, price, item = plan
    bk = (key, y, x)
    st.shop_tries[bk] = st.shop_tries.get(bk, 0) + 1
    if st.shop_tries[bk] > 6:
        st.shop_blocked[bk] = bl.time + 1500
        agent.log(f'INSTR shop: giving up on {item.text!r} at {(y, x)}')
        return
    if kind == 'sell':
        if not _sell_for(agent, price):
            st.shop_blocked[bk] = bl.time + 400
            return
        if agent.blstats.gold < price:
            return
    # go to the shelf and pay
    if (agent.blstats.y, agent.blstats.x) != (y, x):
        agent.go_to(y, x)
        if (agent.blstats.y, agent.blstats.x) != (y, x):
            return
    here = [i for i in inv.items_below_me if i.shop_status == Item.FOR_SALE and supply.unit_quote(i) == price
            and _shelf_is_tonal(agent, st, key, y, x, i, len(inv.items_below_me) == 1)]
    if not here:
        st.shop_blocked[bk] = agent.blstats.time + 500
        return
    agent.log(f'INSTR shop: buying {here[0].text!r} for {price} (gold {agent.blstats.gold})')
    inv.pickup(here[0], 1)
    inv.pay_or_drop_unpaid()
    inv.items.update(force=True)
    if pack_has_tonal(agent):
        st.bought += 1
        agent.log(f'INSTR shop: bought price={price} gold={agent.blstats.gold}')
    else:
        agent.log(f'INSTR shop: not bought {here[0].text!r}')
        st.shop_blocked[bk] = agent.blstats.time + 600


def _sell_for(agent, price):
    """Sell the pack items worth least to us in a shop of this level that buys them until the gold covers `price`. True when
    a sale session ran (or the gold already covers it)."""
    sup = agent.global_logic.supply
    bl = agent.blstats
    need = price - bl.gold
    gold0 = bl.gold
    if need <= 0:
        return True
    dis = agent.bfs()
    choice = None
    shops = sup.sale_shops(dis)
    for d, pos, stype in shops:
        plan = sup.plan_sales(need, stype, SHOP_VALUE)
        if plan:
            choice = (pos, stype, plan)
            break
    if choice is None:
        agent.log(f'INSTR shop: nothing to sell for {price} (gold {bl.gold}, shops {[(p, t) for _, p, t in shops]})')
        return False
    (ty, tx), stype, plan = choice
    if (bl.y, bl.x) != (ty, tx):
        agent.go_to(ty, tx)
        if (agent.blstats.y, agent.blstats.x) != (ty, tx):
            return False
    agent.log(f'INSTR shop: sell plan for {price} (gold {agent.blstats.gold}) in shop type {stype} at {(ty, tx)}: '
              f'{[(i.text, n, round(g), round(l, 1)) for i, n, g, l in plan]}')
    budget = 0.5 * SHOP_VALUE
    lost = 0.0
    for item0, n, g, loss in plan:
        for _ in range(n):
            if agent.blstats.gold >= price:
                break
            cur = [i for i in supply.pack_items(agent) if sup.same_stack(i, item0)]
            if not cur or lost + supply.item_loss(cur[0]) > budget:
                break
            r = supply.sell_offer(agent, cur[0], accept=True, count=1)
            agent.log(f'INSTR shop: sell {cur[0].text!r}: offer={r["offer"]} sold={r["sold"]} '
                      f'uninterested={r["uninterested"]} credit={r["credit"]} only={r["only"]} skipped={r["skipped"]} '
                      f'gold={agent.blstats.gold}')
            if r['skipped'] or not r['sold']:
                break
            lost += supply.item_loss(cur[0])
        if agent.blstats.gold >= price:
            break
    agent.log(f'INSTR shop: sale done gold={agent.blstats.gold} price={price} lost={lost:.1f} mpass')
    # nothing sold (a tool shop that buys no potions, a shopkeeper without cash): the caller blocks the shelf for a while instead of
    # trying again a turn later on another square (instr-a6-jf844 s14: six tries, five zorkmids short of a magic flute)
    return agent.blstats.gold > gold0
