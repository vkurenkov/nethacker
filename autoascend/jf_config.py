"""Feature switches for A/B experiments.

Dev runs may override them with JF_CFG='{"TOUR_FIXES": false, ...}'; the arena never sets
JF_CFG, so submissions always run these defaults.
"""
import json
import os

# failure-only fixes that can also change the levelling tour's trajectory:
# gas spore near pet, cockatrice-corpse squares, no melee vs passive-damage monsters,
# deadly-status emergency, eat carried food before a hunger prayer below XL 5
TOUR_FIXES = False
# Excalibur dips only at >= 90% HP with a prayer ready (astra); changes the tour
SAFE_DIPS = False
# when Weak or worse with HP > 40, poisonous/acidic corpses are acceptable food
STARVING_EATS = True
# astra's survival layer (Elbereth rest, retreat upstairs) also during the levelling tour
SURVIVAL_IN_TOUR = False

_raw = os.environ.get('JF_CFG')
if _raw:
    for _name, _value in json.loads(_raw).items():
        if _name in globals() and not _name.startswith('_'):
            globals()[_name] = _value
