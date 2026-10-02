"""ARMOR_VALUE (armour lane): what a piece of armour is worth beyond its AC.

Inventory.get_best_armorset ranks the pieces of a slot by item.get_ac() alone, so a known pair of speed boots (AC 1) never
replaces iron shoes (AC 2), gauntlets of power (AC 1) never replace leather gloves (AC 1: a tie keeps what is worn), a shield of
reflection (AC 2) never replaces the starting +3 small shield (AC 4), a cloak of magic resistance (AC 1) sits beside a dwarvish
cloak (AC 0) only because it happens to win by one point -- and the wishes lane spends its wishes on exactly these. Measured
(ledger R453, 448 instrument kits at the castle, paired): ARMOR_UP alone 12 -> 18 passes, + a worn gray dragon scale mail
(AC -5.5) 18 -> 27, + worn speed boots (AC -1.2) 18 -> 31: speed matters as much as armour class.

BONUS is in AC points (what a point of AC is worth in the ranking, not in the game): a piece's rank is get_ac() - bonus (lower
wins). NEVER lists the pieces that must not be worn once known: cursed-by-generation or ruinous (levitation boots end a
dig-dive and, cursed, the game's progress; fumbling; a helm of opposite alignment flips the alignment and with it prayer).
The castle code that wants levitation or water walking boots puts them on itself (castle_logic / castle_cross).
"""

BONUS = {
    'speed boots': 8,                       # speed 12 -> 20ish: R453 prices it above a gray dragon scale mail
    'gauntlets of power': 3,                # St 25: +6 damage, +2 to hit
    'shield of reflection': 4,              # reflects the death rays / lightning of liches, soldiers' wands, dragons
    'cloak of magic resistance': 4,
    'cloak of protection': 1,               # MC 3
    'oilskin cloak': 2,                     # an eel's wrap or a hug slips off: the moat and Medusa's lake drown us
    'gray dragon scale mail': 4,            # magic resistance
    'gray dragon scales': 4,
    'silver dragon scale mail': 4,          # reflection
    'silver dragon scales': 4,
    'black dragon scale mail': 2,           # disintegration resistance
    'black dragon scales': 2,
    'orange dragon scale mail': 1,
    'orange dragon scales': 1,
    'blue dragon scale mail': 1,
    'blue dragon scales': 1,
    'green dragon scale mail': 1,
    'green dragon scales': 1,
    'shimmering dragon scale mail': 1,
    'shimmering dragon scales': 1,
}

NEVER = frozenset({'levitation boots', 'fumble boots', 'gauntlets of fumbling', 'helm of opposite alignment', 'dunce cap'})


def _name(item):
    try:
        return item.object.name
    except Exception:
        return None


def never(item):
    return _name(item) in NEVER


def bonus(item):
    return BONUS.get(_name(item), 0)
