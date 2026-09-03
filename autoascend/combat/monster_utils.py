# heuristic monster types lists
ONLY_RANGED_SLOW_MONSTERS = ['floating eye', 'blue jelly', 'brown mold', 'gas spore', 'acid blob']
EXPLODING_MONSTERS = ['yellow light', 'gas spore', 'flaming sphere', 'freezing sphere', 'shocking sphere']
INSECTS = ['giant ant', 'killer bee', 'soldier ant', 'fire ant', 'giant beetle', 'queen bee']
WEAK_MONSTERS = ['lichen', 'newt', 'shrieker', 'grid bug']
WEIRD_MONSTERS = ['leprechaun', 'nymph']
# hypothesis: treating petrification as an emergency—avoiding bare-contact attacks
# while polymorphed and praying away delayed stoning—preserves productive runs.
PETRIFYING_MONSTERS = ['chickatrice', 'cockatrice']


def is_monster_faster(agent, monster):
    _, y, x, mon, _ = monster
    # hypothesis: using NetHack's movement rate consistently lets combat defend
    # against every monster that can close distance faster than the hero, including
    # soldier ants and jaguars omitted by the old name-based list.
    return mon.mmove > 12


def imminent_death_on_melee(agent, monster):
    if is_dangerous_monster(monster):
        return agent.blstats.hitpoints <= 16
    # hypothesis: retreating from ordinary melee below 13 HP keeps early knights outside one-hit range of armed and high-damage foes long enough to regenerate.
    return agent.blstats.hitpoints <= 12


def is_dangerous_monster(monster):
    _, y, x, mon, _ = monster
    is_pet = 'dog' in mon.mname or 'cat' in mon.mname or 'kitten' in mon.mname or 'pony' in mon.mname \
             or 'horse' in mon.mname
    # 'mumak' in mon.mname or 'orc' in mon.mname or 'rothe' in mon.mname \
    # or 'were' in mon.mname or 'unicorn' in mon.mname or 'elf' in mon.mname or 'leocrotta' in mon.mname \
    # or 'mimic' in mon.mname
    return is_pet or mon.mname in INSECTS


def consider_melee_only_ranged_if_hp_full(agent, monster):
    return monster[3].mname in ('brown mold', 'blue jelly') and agent.blstats.hitpoints == agent.blstats.max_hitpoints
