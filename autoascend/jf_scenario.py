"""Dev scenario harness hook (dev/scenario.py); a no-op in the arena.

The harness starts a game mid-way (wizard-mode setup: XL, inventory, level teleport to e.g. the castle,
then wizard mode off) and passes the bot state that game should have as JSON in JF_SCENARIO, e.g.
JF_SCENARIO='{"diving": true}'. The arena never sets JF_SCENARIO, so a submission always has
STATE = None and nothing here changes its behaviour.

Keys:
  diving            (default true) the dive phase is on from the first action
  mines_done        (default true) the dive does not take the Mines route
  milestone         a global_logic.Milestone name (e.g. "GO_DOWN")
  last_prayer_turn  what the bot believes about its last prayer (None: never prayed)
  prayer_failed     the bot believes a prayer has failed (god angry)
  form              the polymorph form a setup's wizard #polyself gave us (e.g. "xorn")
  hp_before_poly    [hp, hpmax] of our own form under it
  self_mon          the monster our own form shows as (e.g. "valkyrie"), when a setup polymorphed us first
  poly_control      the setup showed polymorph control (the rings worn now give it)
  identity          {"role": "VALKYRIE", "race": "DWARF", "gender": "FEMALE", "alignment": "LAWFUL"} when the
                    attribute parse can't read them (a polymorphed start)
  medusa_level      [dnum, dlvl] of Medusa's level
  price_known       {"<appearance as displayed>": base price} -- shop price groups learned before (price_id.py)
  crusher_state     {"tune": "EGDDB", "locked_out": true} -- castle-inner replays (dev/replay.py): the game was fed by
                    recorded actions up to the Crusher's lock-out (hero on map (07,08), bridge up behind her), so the
                    fresh Crusher is told what the recording bot knew: the tune, and that crush/lock-out are done
  cfg               {"NAME": value, ...} jf_config switches set for this game only (one run, arms with different switches)
  court_heard       the setup knew the start level has a court (wish_source.scenario_hint: as if its sound had been heard)
  court_entered     ... and that the hero stands in it ('You enter an opulent throne room!')
  tc_intrinsic      the hero has teleport control as an intrinsic AND knows it (a tengu corpse eaten before the bot
                    started: 'You feel in control of yourself.'); spec "intrinsics": ["teleport_control"] gives the
                    property itself (t-route harness kits)
  trap_here         the setup left the hero standing on a deadly trap square she has seen (PET_SWAP_GUARD harness)
  idle_turns        the dive plan does nothing for this many turns (fight2, Elbereth rests and the guards still act): how
                    much of a landing's death is the plan's own doing (dev measurement only)
  demon_vigil       (excalibur lane) true or N turns: the water-demon vigil is on from the first action, as after a real
                    'You unleash a water demon!' (a ^G demon shows no such message, so the vigil never started)
  sleep_room        (DIVE_SLEEPERS tests) the start level counts as a special room entered at the first update, as if
                    "You enter a military barracks!" had been printed (the harness cannot print room entry messages)
"""
import json
import os

_raw = os.environ.get('JF_SCENARIO')
STATE = json.loads(_raw) if _raw else None


def active():
    return STATE is not None


def apply(agent):
    """Set the scenario's bot state; called on every agent start (a driver restart re-applies it)."""
    if STATE is None:
        return
    try:
        if STATE.get('cfg'):
            # per-game switch overrides (dev only: the arena never sets JF_SCENARIO), so one queued harness run can hold arms
            # with different switches (the code reads jf_config.NAME at call time)
            from . import jf_config
            for name, value in STATE['cfg'].items():
                setattr(jf_config, name, value)
        from .global_logic import Milestone
        gl = agent.global_logic
        dive = gl.dive
        if STATE.get('diving', True):
            dive.diving = True
            dive.mines_done = bool(STATE.get('mines_done', True))
        if STATE.get('milestone'):
            gl.milestone = Milestone[STATE['milestone']]
        if 'last_prayer_turn' in STATE:
            agent.last_prayer_turn = STATE['last_prayer_turn']
        if 'prayer_failed' in STATE:
            agent.prayer_failed = bool(STATE['prayer_failed'])
        if STATE.get('form'):
            # a setup that polymorphs us (wizard #polyself) ran before the bot saw 'You turn into a ...!', which is
            # how castle_cross.note_message learns the form (the glyph test takes the form's glyph for our own)
            agent._cfp_form = STATE['form']
        if STATE.get('identity'):
            # character.parse fails on a polymorphed hero's attributes ('You are actually a ...'), leaving role,
            # race, gender and alignment unknown (KeyError: None in the cannibalism check, vxw1)
            from .character import Character
            ch = agent.character
            for field, value in STATE['identity'].items():
                if getattr(ch, field, None) is None:
                    setattr(ch, field, getattr(Character, value))
        if STATE.get('self_mon'):
            # ...and character.parse read the form's glyph as our own (the setup polymorphed us first), so
            # prop.polymorph stayed true after the form ended and the dwarf waited it out for good (vxx3 s1)
            from .glyph import MON
            agent.character.self_glyph = MON.from_name(STATE['self_mon'])
        if STATE.get('hp_before_poly'):
            # ...and character.update took the HP it last saw in our own form, before the bot's first step: none
            agent.character.hp_before_poly = tuple(STATE['hp_before_poly'])
        if STATE.get('poly_control'):
            # the setup's wizard #polyself asked 'Become what kind of monster?' before the bot ran
            agent._note_poly_control()
        if STATE.get('medusa_level'):
            dive.medusa_level = tuple(STATE['medusa_level'])
        if STATE.get('castle_known'):
            # a setup that polymorphs us on the castle into a form that can't dig (lift-ready's flyer tests): the
            # castle is recognised by a dig that form can't make -- castle_logic.note_level marks it instead
            dive._scenario_castle = True
        if STATE.get('tc_intrinsic'):
            # note_message learns it from the eating message, which a harness setup never shows the bot
            from . import power_route
            power_route.state(agent).tc_intrinsic = True
        if STATE.get('trap_here'):
            # PET_SWAP_GUARD harness: a wizard-mode wish made a trap under the hero; the bot never saw the message that names it
            from . import pet_guard
            pet_guard._state(agent)['pending_here'] = True
        if STATE.get('idle_turns'):
            # dev only (dive_logic.plan_step): the dive plan idles this many turns, the safety layers still act
            dive._scenario_idle = int(STATE['idle_turns'])
        if STATE.get('sleep_room'):
            # dev only (DIVE_SLEEPERS): the start level is a special room entered at the first update
            dive._sleep_force = True
        if STATE.get('price_known'):
            # price-id: the price groups a real game would have learned in shops before the castle
            # ({"cyan potion": 200, ...}; price_id.scenario_apply)
            from . import price_id
            price_id.scenario_apply(agent, STATE['price_known'])
        if STATE.get('crusher_state'):
            cs = STATE['crusher_state']
            crusher = getattr(dive, 'crusher', None)
            if crusher is not None:
                crusher.tune = cs.get('tune') or 'AAAAA'
                crusher.bridge_open = bool(cs.get('bridge_open', False))
                crusher.toggles = max(1, crusher.toggles)
                crusher.crush_over = bool(cs.get('crush_over', True))
                crusher.hold_over = True
                crusher.locked_out = bool(cs.get('locked_out', True))
                crusher.tries['lockout'] = 1 if crusher.locked_out else 0
                crusher.garrison_known_dead = bool(cs.get('crush_over', True) or crusher.locked_out)
        if STATE.get('demon_vigil'):
            from . import jf_config
            n = STATE['demon_vigil']
            n = jf_config.DEMON_VIGIL_TURNS if n is True else int(n)
            try:
                dive._demon_vigil_until = int(agent.blstats.time) + n
            except Exception:
                dive._demon_vigil_until = 10 ** 9
        agent.log(f'SCENARIO start: {STATE} -> diving={dive.diving} mines_done={dive.mines_done} '
                  f'milestone={gl.milestone.name}')
    except Exception as e:   # a typo in a dev scenario must not kill the agent thread
        agent.log(f'SCENARIO state not applied ({type(e).__name__}: {e}): {STATE}')
