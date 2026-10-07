"""Survival lane: how much damage can the monsters near us do to a helpless hero?  (SURV_THREAT; KNOWN_ITEMS_BURST)

monst.c's attack dice (mon_attacks.py, generated) give each monster's damage per move; the speed gives its moves per turn
(allmain.c / mon.c mcalcmove: speed / 12 on average); mattacku() hits when 10 + AC + level > rnd(20), +4 to the roll against a helpless
hero (multi < 0).  A fainting spell lasts 10 - uhunger/10 turns (eat.c newuhs), 10-20 in practice, with nothing to stop a monster
that gets to us.  Used by Agent._hunger_threat (SURV_THREAT: pray early only when what stands near could really take the HP we
have) and by known_items (KNOWN_ITEMS_BURST: act before a one-round burst, not after it).  Reads only; draws no random number.
"""
from . import jf_config
from .mon_attacks import MON_ATTACKS

# attacks that never take hit points (theft, seduction, passive-only) or that this model ignores (spells, gaze, engulfing detail)
_NO_HP = {'AD_SITM', 'AD_SEDU', 'AD_SSEX', 'AD_PLYS', 'AD_SLOW', 'AD_BLND', 'AD_CONF', 'AD_STUN', 'AD_SLIM', 'AD_STON',
          'AD_TLPT', 'AD_HALU', 'AD_DREN', 'AD_CNCL', 'AD_CURS', 'AD_LEGS', 'AD_ENCH', 'AD_SAMU', 'AD_WRAP', 'AD_SPEL', 'AD_CLRC',
          'AD_DETH', 'AD_PEST', 'AD_FAMN', 'AD_DISE', 'AD_AXUS', 'AD_POLY', 'AD_WERE', 'AD_SLEE', 'AD_DGST', 'AD_NONE'}
_MELEE = {'AT_CLAW', 'AT_BITE', 'AT_KICK', 'AT_BUTT', 'AT_STNG', 'AT_TUCH', 'AT_TENT', 'AT_HUGS', 'AT_WEAP', 'AT_ENGL', 'AT_EXPL'}


def attack_damage(name, difficulty=None):
    """(average damage of one full round of melee attacks of `name`, level, speed); an unknown name falls back on its difficulty."""
    ent = MON_ATTACKS.get(name)
    if ent is None:
        d = difficulty if difficulty is not None and difficulty >= 0 else 4
        return 2.0 + 1.5 * d, d // 2, 12
    level, speed, diff, attacks = ent
    total = 0.0
    for aatyp, adtyp, n, d in attacks:
        if aatyp not in _MELEE or adtyp in _NO_HP or n <= 0 or d <= 0:
            continue
        avg = n * (d + 1) / 2.0
        if aatyp == 'AT_WEAP':
            avg += 2.5   # the weapon it wields (d6-d8 for most)
        if adtyp == 'AD_SGLD':
            avg *= 0.3   # a leprechaun's d2 claw: it steals the gold and teleports away after the first hit
        total += avg
    return total, level, speed


def hit_chance(ac, level, helpless=True):
    """mhitu.c mattacku: tmp = AC_VALUE(u.uac) + 10 + level (+4 against a helpless hero); a hit when tmp > rnd(20)."""
    ac_value = ac if ac >= 0 else ac / 2.0   # AC_VALUE(ac) = -rnd(-ac) for negative AC
    tmp = ac_value + 10 + level + (4 if helpless else 0)
    return max(0.05, min(0.95, (tmp - 1) / 20.0))


def potential_damage(agent, monsters, horizon=None, helpless=True, elbereth_intact=False, ignores=None):
    """Expected damage over `horizon` turns from the monsters in `monsters` (agent.get_visible_monsters() tuples) if nothing stops them.
    On an intact Elbereth the monsters that respect it count SURV_THREAT_ELB_FACTOR (a dust engraving scuffs 1 turn in 40 + 3 Dex)."""
    bl = agent.blstats
    ac = int(bl.armor_class)
    horizon = jf_config.SURV_FAINT_TURNS if horizon is None else horizon
    total = 0.0
    for m in monsters:
        _, y, x, mon, _ = m
        name = getattr(mon, 'mname', '')
        per_round, level, speed = attack_damage(name, getattr(mon, 'difficulty', None))
        speed = getattr(mon, 'mmove', speed) or speed
        if per_round <= 0 or speed <= 0:
            continue
        moves = speed / 12.0
        dist = max(abs(int(y) - bl.y), abs(int(x) - bl.x))
        approach = max(0.0, (dist - 1) / moves)
        exposure = max(0.0, horizon - approach)
        dmg = per_round * hit_chance(ac, level, helpless) * moves * exposure
        if elbereth_intact and not (ignores is not None and ignores(mon)):
            dmg *= jf_config.SURV_THREAT_ELB_FACTOR
        total += dmg
    return total
