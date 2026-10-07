"""SURV_DIVE_GATE (survival lane, objective B): a food-less hero does not start its dig-dive Hungry or with a young prayer.

The numbers (ledger F462; 64 castle arrivals of the cand-l6c control games, 10 of the jf1500 control): 25% of the castle arrivals carry an
unsafe prayer (P(heard | gap) < 0.8, exact rnz(350)); 13 of those 16 are HUNGER prayers made on the way down by heroes with nothing to
eat (16% of all arrivals), and an unsafe prayer at the castle costs the walk-in about 4.3 points of pass30 (prep lane R524, F448). The
DIVE_PRAYER_GAP gate (gap >= 800) parks the first dig just above 800 turns after the last hunger prayer -- Hungry, Weak within ~100
turns -- and a digging tool that arrives mid-phase (a Mines dwarf's pick) is not gated at all: jf1500 s12 dug Fainting (gap 830),
s5 at gap 801 (Weak 50 turns later), s14 Weak at gap 1699. The dive takes 190-330 turns from the first dig to the castle, so
the hunger prayer lands in the dive and the hero arrives with a prayer 100-300 turns old (P 0.44-0.66).

What the gate does, once, at the first dig (main dungeon, tool in hand, depth <= SURV_GATE_MAX_DEPTH, not a rescue): a hero carrying
less than SURV_GATE_FOOD nutrition that is Hungry or worse holds -- Elbereth, a rest -- until its hunger prayer has been made, and then
until that prayer is SURV_GATE_GAP turns old (so the arrival, ~250 turns later, finds it 550+ old: P(heard) >= 0.88); a hero that is not
Hungry but prayed less than SURV_GATE_GAP turns ago waits for the age. Heroes with food (they eat on the way) and heroes already
past the point (Weak with an unsafe prayer: nothing to wait for) are not held. At most SURV_GATE_MAX turns; hostiles in view: a
one-turn hold (the fight layers above answer them). The wait is on a shallow level, where a hero lives (prep measured ~2.2 arrival
points per 100 turns spent below Medusa; F430: 0.127 deaths per 1000 turns in the Mines, 0.018 on Dlvl 3 at XL5-6).
Reads state, spends game turns only through agent.search / engrave (like prep's PREP_GATE, which waits for gap 800 and holds no
Hungry hero).
"""
from . import jf_config
from .glyph import Hunger
from .level import Level


def _log(agent, msg):
    agent.log(f'SURV_GATE {msg}')


def hold(dive):
    """True when the gate spent this step on a hold turn. Called by DiveLogic.plan_step right before the dive descends."""
    agent = dive.agent
    bl = agent.blstats
    level = agent.current_level()
    st = dive.__dict__.setdefault('_surv_gate', {'done': False, 'start': None})
    if st['done']:
        return False
    if not dive.diving or dive.rescue or agent.prayer_failed or level.dungeon_number != Level.DUNGEONS_OF_DOOM or \
            agent.character.prop.polymorph or dive.in_valley():
        return False
    if bl.depth > jf_config.SURV_GATE_MAX_DEPTH:
        st['done'] = True    # the first dig happened deeper (a fall, a trapdoor): no hold now
        return False
    if dive.digging_tool() is None or level.key() in dive.undiggable:
        return False
    turn = bl.time
    gap = None if agent.last_prayer_turn is None else turn - agent.last_prayer_turn
    food = agent.carried_food_nutrition()
    if food >= jf_config.SURV_GATE_FOOD:
        st['done'] = True
        _log(agent, f'not needed at the first dig: food {food}, hunger {bl.hunger_state}, gap {gap}')
        return False
    if st['start'] is None and not st.get('looked'):
        # one turn to read the hunger state before deciding (a harness hero's poked nutrition shows in the status line a turn late)
        st['looked'] = True
        dive._task('surv gate look')
        agent.search(1)
        return True
    hungry = bl.hunger_state >= Hunger.HUNGRY
    # Weak or worse with a prayer that cannot be heard yet: nothing to wait for (the dive's own prayer rule answers it)
    if bl.hunger_state >= Hunger.WEAK and gap is not None and gap < jf_config.SURV_GATE_UNSAFE_GAP:
        st['done'] = True
        _log(agent, f'not holding: Weak or worse (hunger {bl.hunger_state}) with the prayer {gap} turns old')
        return False
    young = gap is not None and gap < jf_config.SURV_GATE_GAP
    if st['start'] is None:
        if not (hungry or young):
            st['done'] = True
            _log(agent, f'nothing to do at the first dig: hunger {bl.hunger_state}, gap {gap}, food {food}, depth {bl.depth}')
            return False
        st['start'] = turn
        _log(agent, f'start: hunger {bl.hunger_state} gap {gap} food {food} hp {bl.hitpoints}/{bl.max_hitpoints} depth {bl.depth}')
    held = turn - st['start']
    if held > jf_config.SURV_GATE_MAX or not (hungry or young):
        st['done'] = True
        _log(agent, f'over after {held} turns: hunger {bl.hunger_state} gap {gap} food {food}'
                    f'{" (cap)" if held > jf_config.SURV_GATE_MAX else ""}')
        return False
    dive._task('surv gate hold')
    if agent.get_visible_monsters():
        agent.search(1)
        return True
    if dive._rest_elbereth():
        return True
    agent.search(5 if hungry else 20)
    return True


def active(dive):
    """True while a hold is in progress and the hero is in good shape: dive_logic.dig_first then lets fight2 answer what shows up instead of
    digging out of it (the escape-dig is how the first PREP_GATE hold of the prep lane was lost: any monster in view, a newt included, drops
    the hero a level and the wait is over). A hurt hero (HP below SURV_GATE_ESCAPE_HP of its maximum) still escapes."""
    st = getattr(dive, '_surv_gate', None)
    if not st or st['done'] or st['start'] is None:
        return False
    bl = dive.agent.blstats
    return bl.hitpoints >= jf_config.SURV_GATE_ESCAPE_HP * bl.max_hitpoints
