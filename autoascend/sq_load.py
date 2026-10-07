"""Load lane (27): helpers of the squeeze-cut flags (jf_config SQ_STEP_GUARD / SQ_CUT_RECOVER / SQ_DEAD_DROP).

hack.c test_move refuses a diagonal step when BOTH orthogonal squares are rock (bad_rock: IS_ROCK(typ), i.e. stone, walls, trees,
secret doors/corridors; boulders only in Sokoban) and cant_squeeze_thru() says the pack weighs more than 600 ('You are carrying too
much to get through.', no game time passes).  rockish()/squeeze_cut() are that rule as far as the bot's map shows it, dead_items()
lists the weight nothing in the bot's plans uses (spare armour, crystal balls, spellbooks...), see dev/load/deadload.py for the
offline version and the census of real arrivals (mean 32, median 0, >= 100 in 12.5% of them).
"""
import nle.nethack as nh

from . import power
from . import objects as O
from .glyph import G

try:
    from . import armor_value
except ImportError:   # a tree older than the armour lane (grafted replays of old games): spare armour is then left alone
    armor_value = None

# tools and odd items no route, AC, food or escape plan of the bot uses (weight 100-480 each)
JUNK_NAMES = frozenset(('crystal ball', 'beartrap', 'land mine', 'tinning kit', 'saddle', 'figurine', 'grappling hook',
                        'iron chain', 'heavy iron ball', 'large box', 'chest', 'ice box'))


def rockish(level, y, x):
    """bad_rock() as far as the map shows it: not walkable and a wall or solid stone (a door, trap, water or boulder square is
    not rock: a squeeze beside one is legal; a never-seen square (objects -1) might be floor: no verdict of ours)."""
    h, w = level.walkable.shape
    if not (0 <= y < h and 0 <= x < w):
        return True
    if level.walkable[y, x]:
        return False
    o = int(level.objects[y, x])
    return o in G.WALL or o in G.STONE


def squeeze_cut(level, ny, nx, y, x):
    """The step (ny, nx) -> (y, x) is a diagonal between two rock squares (the weight is not tested here)."""
    return ny != y and nx != x and rockish(level, ny, x) and rockish(level, y, nx)


def dead_items(agent):
    """[(item, count, why)] the pack carries that the bot never uses: an unworn armour piece of a slot whose best piece (by the
    bot's own get_best_armorset) is another one and which is worn there, a junk tool (JUNK_NAMES), spellbooks.  Never a worn or
    wielded item, a container, an unknown-look armour piece (it may be levitation boots or a magic cloak: KEEP_MAGIC_BOOTS)."""
    inv = agent.inventory
    items = list(inv.items.all_items)
    best = inv.get_best_armorset(items=items, allow_unknown_status=True)
    worn_slots = {i.objs[0].sub for i in items if i.equipped and isinstance(i.objs[0], O.Armor)}
    out = []
    for item in items:
        if item.equipped or item.is_container() or item.is_possible_container() or \
                not item.can_be_dropped_from_inventory():
            continue
        o = item.objs[0]
        if isinstance(o, O.Armor):
            if item.is_unambiguous():
                slot = o.sub
                # never a piece kept for a reason beyond its AC: levitation / water walking boots (the castle's passage), speed boots,
                # reflection, magic resistance (armor_value.BONUS), pieces that must not be worn
                try:
                    kept = power.never_wear(item) or power.is_passage_boots(item) or armor_value.never(item) or \
                        armor_value.bonus(item) > 0
                except AttributeError:
                    kept = True   # an older tree lacks one of the helpers: leave the piece alone
                if kept:
                    continue
                if slot in worn_slots and best[slot] is not None and best[slot] is not item:
                    out.append((item, item.count, 'spare armour'))
        elif item.category == nh.SPBOOK_CLASS:
            out.append((item, item.count, 'spellbook'))
        elif all(x.name in JUNK_NAMES for x in item.objs):
            out.append((item, item.count, 'junk'))
    return out


def weight_of(items):
    """Estimated weight of [(item, count, why)] (the heaviest candidate of an unknown look, like Item.weight)."""
    return sum(i.unit_weight(with_content=False) * c for i, c, _ in items)
