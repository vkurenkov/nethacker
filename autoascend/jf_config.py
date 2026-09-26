"""Feature switches for A/B experiments.

Dev runs may override them with JF_CFG='{"TOUR_FIXES": false, ...}'; the arena never sets
JF_CFG, so submissions always run these defaults.
"""
import json
import os

# Fixes that change the levelling tour. Split by WHEN they first change a game:
# LATE: only at a specific hazard (gas spore next to the pet, cockatrice corpse, passive-damage
#   monster, deadly status, empty wand) -- the elite's early game is untouched until then.
# EARLY: prayer at pray.c's critically_low_hp instead of 'HP < 12', eat carried food before a
#   hunger prayer below XL 5 -- these reshuffle games from the first prayer on.
EARLY_FIXES = False
LATE_FIXES = True
# the rarest-hazard subset of LATE_FIXES (gas spore next to the pet, cockatrice-family corpse
# squares, spotted/ochre jelly and gelatinous cube melee): these first fire close to the deaths
# they prevent, so they barely perturb the elite's public trajectories
HAZARD_FIXES = False
# master switch kept for older experiment configs: sets both
TOUR_FIXES = None
# Excalibur dips only at >= 90% HP with a prayer ready (astra); changes the tour
SAFE_DIPS = False
# when Weak or worse with HP > 40, poisonous/acidic corpses are acceptable food
STARVING_EATS = True
# astra's survival layer (Elbereth rest, retreat upstairs) also during the levelling tour
SURVIVAL_IN_TOUR = False
# at critically low HP with no safe prayer and a hostile adjacent: stairs, unknown wands/potions/scrolls
LAST_RESORT = True
# Komershan's verified leader (0.2033 on hidden seeds): dwarves and gnomes skip Sokoban and walk the
# peaceful Mines from Minetown straight to Mines' End (Dlvl 10-13: 0.126-0.26 banked early)
SKIP_SOKOBAN = False
# pray for HP only at pray.c's critically_low_hp (DT6A's 'HP < 12' prays with no trouble to fix: no
# heal, and a failure if the timeout isn't 0), and allow the first prayer from turn 100 (the timeout
# starts at 300; major trouble needs <= 200)
EXACT_PRAYER = False
# minimum turns since the last prayer for a hunger prayer while Fainting (DT6A: 400). Most first prayer
# failures were Fainting prayers 900-1100 turns after the last one (rnz(350) timeout: ~6% fail there,
# ~2% past 1100); a longer gap means fainting longer instead
FAINT_PRAYER_GAP = 1000
# AutoAscend's periodic 'eat corpses' preempt was meant to walk to edible corpses on the level, but
# only_below_me defaults to True, so it only ever eats what lies underfoot; the kills' corpses beside
# us go to the pet (it ate ~40% of the grind's corpses)
EAT_NEARBY_CORPSES = False
# Weak/Fainting with nothing to eat and no safe prayer yet: wait on Elbereth instead of wandering (many
# grind deaths came while fainted: rats, bats, ants; nearly everything on Dlvl 1 respects Elbereth)
FAINT_SHELTER = True
# Fainting prayers by the starvation clock instead of a fixed gap: eat.c kills at uhunger <
# -(100 + 10 * Con) and uhunger drops at most 1 per turn once Fainting (almost not at all while
# fainted), so death is at least 100 + 10 * Con turns after Fainting begins. Pray once the gap is
# FAINT_PRAYER_GAP_LONG (= the Weak rule's gap), or STARVE_MARGIN turns before that deadline whatever
# the gap (the fixed 1000-turn gap could starve a character whose last prayer was an HP one, and it
# prays where rnz(350) still fails ~5.5% of the time; ~2.3% at 1200).
STARVE_CLOCK = True
# give up looking for the Mines entrance after this many turns and go on to Sokoban (0: never)
MINES_SEARCH_TURNS = 3500
FAINT_PRAYER_GAP_LONG = 1400
STARVE_MARGIN = 60
# Weak/Fainting hunger prayers wait for a 1400-turn gap: measured over ~2600 prayers, 900-1399-turn
# gaps failed 3.5-5.4% of the time, 1400-1799 only 1.1% and 1800+ 0.6%. Waiting is survivable because a
# faint lasts 10 - uhunger/10 moves: the observed faint length tells how close starvation
# (uhunger < -(100 + 10 * Con)) really is, and deep Fainting burns only ~0.2 nutrition per turn.
WEAK_PRAYER_GAP = 1400
FAINT_ESTIMATE_MARGIN = 90

_raw = os.environ.get('JF_CFG')
if _raw:
    for _name, _value in json.loads(_raw).items():
        if _name in globals() and not _name.startswith('_'):
            globals()[_name] = _value

if TOUR_FIXES is not None:
    EARLY_FIXES = LATE_FIXES = bool(TOUR_FIXES)
if LATE_FIXES:
    HAZARD_FIXES = True
