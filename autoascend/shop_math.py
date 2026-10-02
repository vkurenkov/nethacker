"""Shop price arithmetic of NetHack 3.6.6 (src/shk.c), pure python (no nle import) so it can be unit-tested anywhere.

Supply lane (lane 4). Two directions:

  get_cost()  what a shopkeeper CHARGES the hero for one unit of an object of base price `base`:
      x 4/3 for one object in four while its type is unidentified (oid_price_adjustment: o_id % 4 == 0, so the
        same item always carries it; we cannot see the id, hence `surcharge` is a free flag),
      x 4/3 with a dunce cap, or a Tourist below XL 15, or a visible Hawaiian shirt (no suit / cloak over it),
      x Charisma factor (> 18: 1/2; 18: 2/3; 16-17: 3/4; 11-15: 1; 8-10: 4/3; 6-7: 3/2; <= 5: 2),
      one rounding: (((tmp * mult * 10) / div) + 5) / 10, never below 1.
  set_cost()  what the shopkeeper PAYS for a unit: base / 2 (base / 3 with a dunce cap, a Tourist below XL 15 or a
      visible shirt); for an UNidentified non-gem item a shopkeeper whose m_id % 4 == 0 pays 3/4 of that
      (divisor x 4, multiplier 3), the same for every offer he makes. Gems are a special case, not modelled here.

Facts used (verified in handoff/nethack-3.6.6/src/shk.c get_cost / set_cost / oid_price_adjustment, and against 270
baseline games: magic lamp base 50 quoted 50 / 67 / 75 / 89 / 100 zm, oil lamp base 10 quoted 10 / 13 / 15 / 18 / 20).
"""


def cha_factor(cha):
    """(multiplier, divisor) of the Charisma adjustment in get_cost."""
    if cha > 18:
        return 1, 2
    if cha == 18:
        return 2, 3
    if cha >= 16:
        return 3, 4
    if cha <= 5:
        return 2, 1
    if cha <= 7:
        return 3, 2
    if cha <= 10:
        return 4, 3
    return 1, 1


def get_cost(base, cha, dunce=False, surcharge=False):
    """Price quoted for ONE unit of base price `base` (before any armour/weapon enchantment, before the anger
    surcharge). dunce: a dunce cap, a low-level Tourist or a visible shirt. surcharge: the 1-in-4 unidentified one."""
    mult, div = 1, 1
    if surcharge:
        mult *= 4
        div *= 3
    if dunce:
        mult *= 4
        div *= 3
    cm, cd = cha_factor(cha)
    mult *= cm
    div *= cd
    tmp = base * mult
    if div > 1:
        tmp = (tmp * 10 // div + 5) // 10
    return max(tmp, 1)


def quotes(base, cha, dunce=False):
    """The quotes one unit of this base price can show: normal and surcharged."""
    return {get_cost(base, cha, dunce, False), get_cost(base, cha, dunce, True)}


def quote_fits(base, quote, cha, dunce=False):
    """True when `quote` (price of ONE unit) is a possible get_cost of an unidentified object of base price `base`.
    A +N weapon or armour adds 10 per point to the base before the factors, so callers skip this for those."""
    return quote in quotes(base, cha, dunce)


def set_cost(base, quan=1, cha=None, dunce=False, identified=False, cheap_shk=False):
    """What the shopkeeper offers for `quan` units: base * quan / 2 (/ 3 with dunce); an unidentified item from a
    cheap shopkeeper (m_id % 4 == 0) gets 3/4 of it. Charisma plays no part when SELLING."""
    tmp = base * quan
    div = 3 if dunce else 2
    mult = 1
    if not identified and cheap_shk and tmp > 1:
        mult, div = 3, div * 4
    if tmp >= 1:
        tmp *= mult
        if div > 1:
            tmp = (tmp * 10 // div + 5) // 10
        tmp = max(tmp, 1)
    return tmp


def offers(base, quan=1, dunce=False, identified=False):
    """The offers a shopkeeper can make: normal, and (unidentified only) the cheap shopkeeper's."""
    out = {set_cost(base, quan, dunce=dunce, identified=identified, cheap_shk=False)}
    if not identified:
        out.add(set_cost(base, quan, dunce=dunce, identified=False, cheap_shk=True))
    return out


if __name__ == '__main__':
    # observed in the cand-k baseline msgs: CHA 9 (x4/3): lamp 67 / 89, oil lamp 13 / 18; CHA 11-15: lamp 50
    assert quotes(50, 9) == {67, 89}, quotes(50, 9)
    assert quotes(10, 9) == {13, 18}, quotes(10, 9)
    assert quotes(50, 12) == {50, 67}, quotes(50, 12)
    assert quotes(50, 6) == {75, 100}, quotes(50, 6)
    assert quotes(10, 6) == {15, 20}, quotes(10, 6)
    assert quote_fits(50, 67, 9) and not quote_fits(10, 67, 9)
    # food ration (base 45) at CHA 9 is 60 -> 'only 60 zorkmids per food ration'; unidentified types get 80
    assert get_cost(45, 9) == 60, get_cost(45, 9)
    # a base-100 potion sells for 50, or 38 from a cheap shopkeeper
    assert offers(100) == {50, 38}, offers(100)
    assert offers(100, identified=True) == {50}
    print('shop_math ok')
