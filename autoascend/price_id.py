"""Price identification (team member 'price-id'): what an item's base price says about its identity.

NetHack 3.6.6 prices an item by its type's base cost (objects.c oc_cost), so the price a shopkeeper quotes puts
an unidentified appearance into a price group:

  potions  50: booze, fruit juice, see invisible, sickness
          100: confusion, extra healing, hallucination, healing, restore ability, sleeping (and water)
          150: blindness, gain energy, invisibility, monster detection, object detection
          200: enlightenment, full healing, levitation, polymorph, speed
          250: acid, oil
          300: gain ability, gain level, paralysis
  rings   100: adornment, hunger, protection, protection from shape changers, stealth, sustain ability, warning
          150: aggravate monster, cold/poison/shock resistance, gain constitution/strength, increase
               accuracy/damage, invisibility, see invisible
          200: fire resistance, free action, levitation, regeneration, searching, slow digestion, teleportation
          300: conflict, polymorph, polymorph control, teleport control

The knowledge lives where AutoAscend already keeps it: item_manager._glyph_to_price_range (glyph -> (lo, hi) base
price), which possible_objects_from_glyph applies to every item of that appearance (item.objs). Everything that reads
item.objs follows: power.passage_plan's castle try order (a 200 zm potion is levitation 42/124 by generation weight,
a potion outside the 200 group leaves the plan), castle_cross.early_potion, prep_log's readiness estimate.

shk.c (3.6.6), verified for the numbers used here:
  get_cost (buying): base x Charisma factor, x 4/3 for one object in four (oid_price_adjustment: o_id % 4 == 0,
      unidentified items only), x 4/3 again with a dunce cap or a visible Hawaiian shirt / low-level Tourist;
      one rounding (((tmp * mult * 10) / div) + 5) / 10.
  set_cost (selling): base / 2, or base / 3 (dunce cap, shirt, Tourist); for an unidentified item x 3/4 more when
      the SHOPKEEPER's m_id % 4 == 0 (one shopkeeper in four, the same for all his offers).

Only the dev harness uses this module so far (jf_scenario 'price_known'). What price knowledge is worth at the castle
(castle-lift's faithful suite of 45 real lift kits x 10 salts, the classes injected from the true kits): with every
unknown potion/ring/scroll classed, the potion kits quaffed 199 potions instead of 416, with no hallucination, sleep,
blindness or confusion (base 28/18/22/16), and floated at a median turn 9 instead of 22 -- but passes went only
35 -> 39 of 450, because the crossing after the lift loses most floating heroes (minotaurs in the maze, sharks at the
strip). A grind that sells-tests its kit in shops would class about a third of the potions (the shops the grind meets),
so a sell-test strategy was not built.
"""

import nle.nethack as nh

from . import objects as O


def _cost(obj):
    return getattr(obj, 'cost', None)


# ---------------------------------------------------------------------------------------------------------- id-engine API
# Used by the id-engine lane's own code and, as a stable interface, by the supply lane's shop code (agreed on the
# team channel 2026-10-01): what an unidentified item can still be after the price and engrave knowledge in item.objs,
# how route-relevant that is, and how a shopkeeper's sell offer narrows a price group.

# Route-relevant types by class (readiness model + the castle lanes' needs): teleport/polymorph control, levitation and
# water walking, breathing, life saving and reflection, the wands the castle plans use, the scrolls and tools they use
_ROUTE_NAMES = {
    nh.RING_CLASS: ('teleport control', 'polymorph control', 'levitation', 'conflict'),
    nh.AMULET_CLASS: ('amulet of life saving', 'amulet of reflection', 'amulet of magical breathing'),
    nh.WAND_CLASS: ('wishing', 'digging', 'sleep', 'striking', 'opening', 'cold', 'teleportation', 'polymorph', 'death',
                    'fire', 'lightning'),
    nh.SCROLL_CLASS: ('earth', 'scare monster', 'teleportation', 'charging', 'genocide', 'identify'),
    nh.POTION_CLASS: ('levitation', 'polymorph'),
    nh.ARMOR_CLASS: ('levitation boots', 'water walking boots', 'speed boots', 'cloak of magic resistance'),
    nh.TOOL_CLASS: ('magic lamp', 'frost horn', 'fire horn', 'magic harp', 'magic flute', 'magic marker',
                    'bag of holding', 'drum of earthquake'),
}


def _weight(obj):
    p = getattr(obj, 'prob', None)
    return p if p else 1


def bases(item):
    """Sorted distinct base prices the unidentified `item` can still have (item.objs after price/engrave knowledge)."""
    return sorted({o.cost for o in item.objs if _cost(o) is not None})


def route_p(item):
    """P(the item is a route-relevant type), by generation weight over the identities item.objs still allows; 1.0/0.0
    for an identified item. Types: _ROUTE_NAMES."""
    names = _ROUTE_NAMES.get(item.category, ())
    objs = item.objs
    total = sum(_weight(o) for o in objs)
    if total <= 0:
        return 0.0
    return sum(_weight(o) for o in objs if getattr(o, 'name', None) in names) / total


def sell_offers(cost):
    """Per-unit offers a shopkeeper can make for an UNidentified item of base price `cost` (shk.c set_cost, no dunce cap,
    not a Tourist): base/2, or 3/8 of it from the shopkeepers whose monster id is divisible by 4 (rounded to nearest)."""
    normal = (cost * 10 // 2 + 5) // 10
    reduced = (cost * 3 * 10 // 8 + 5) // 10
    return {max(normal, 1), max(reduced, 1)}


def learn_offer(agent, item, offer, why='sell offer'):
    """A shopkeeper offered `offer` zorkmids for ONE unit of the unidentified `item`: narrow its glyph's price range to the
    bases that can produce that offer (armour is left alone: its enchantment moves the price by 10 a point). Returns True
    when the knowledge changed."""
    if not item.glyphs or len(item.glyphs) != 1 or offer is None or offer <= 0 or item.category == nh.ARMOR_CLASS:
        return False
    fits = {o.cost for o in item.objs if _cost(o) is not None and offer in sell_offers(o.cost)}
    if not fits:
        agent.log(f'PRICE {why}: offer {offer} fits no base of {[o.name for o in item.objs]}: ignored')
        return False
    return learn(agent, item.glyphs[0], fits, f'{why} {offer}')


def learn(agent, glyph, bases, why):
    """The appearance `glyph` has one of the base prices `bases`: narrow its possible objects. Safe by design -- a
    price that no remaining object of the glyph fits (a misread, or a rule the caller got wrong) changes nothing, and
    a group of bases that isn't contiguous among the glyph's objects (a range would let another price in) keeps the
    old knowledge. Returns True when the knowledge changed."""
    im = agent.inventory.item_manager
    bases = {int(b) for b in bases}
    cands = [o for o in O.possibilities_from_glyph(glyph) if _cost(o) is not None]
    old = im._glyph_to_price_range.get(glyph)
    fits = [o for o in cands if o.cost in bases and (old is None or old[0] <= o.cost <= old[1])]
    if not fits:
        agent.log(f'PRICE {why}: base {sorted(bases)} fits no object of glyph {glyph} (known range {old}): ignored')
        return False
    lo, hi = min(o.cost for o in fits), max(o.cost for o in fits)
    if any(lo <= o.cost <= hi and o.cost not in bases for o in cands):
        agent.log(f'PRICE {why}: base {sorted(bases)} is not a range of glyph {glyph}: ignored')
        return False
    if old == (lo, hi):
        return False
    im._glyph_to_price_range[glyph] = (lo, hi)
    try:
        objs = im.possible_objects_from_glyph(glyph)
    except AssertionError:
        # every object of that price is already known to be another appearance: the price was wrong, undo it
        if old is None:
            del im._glyph_to_price_range[glyph]
        else:
            im._glyph_to_price_range[glyph] = old
        agent.log(f'PRICE {why}: base {lo}-{hi} leaves glyph {glyph} no object: undone')
        return False
    agent.log(f'PRICE {why}: glyph {glyph} base {lo}-{hi} -> {sorted(o.name for o in objs)}')
    return True


def scenario_apply(agent, known):
    """dev harness only (jf_scenario 'price_known': {"cyan potion": 200, "agate ring": 200, ...}): the price groups
    a real game would have learned before the castle. The appearance is resolved to the bot's glyph inside the
    harness game (the same parse the inventory uses)."""
    from .item.item_manager import ItemManager
    for name, base in (known or {}).items():
        try:
            _, glyphs = ItemManager.parse_name(name)
        except Exception as e:   # a typo in a dev spec must not stop the others
            agent.log(f'PRICE scenario: cannot parse {name!r}: {e!r}')
            continue
        for g in glyphs:
            learn(agent, g, {int(base)}, f'scenario {name!r}')
    agent.inventory.items.update(force=True)
