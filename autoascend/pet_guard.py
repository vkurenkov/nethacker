"""PET_SWAP_GUARD (survival lane, forensics F456): do not swap places with the pet while standing on a trap that would kill it.

The mechanism (hack.c domove, 'swap places'): walking into the pet puts the pet on the hero's OLD square; if that square holds a trap the
pet dies in (pit, spiked pit, arrow / dart / falling rock trap, land mine, rolling boulder, fire trap) -- mintrap() answers 2 -- the game says
'You feel guilty about losing your pet like this.' with probability 3/4 and does u.ugangr++, adjalign(-15): the god is angry for the rest
of the game and EVERY later prayer fails (pray.c can_pray: p_type 1; angrygods: 'Thou must relearn thy lessons!' costs a level one time in
three). Forensics (F456): 4 of 879 games (0.5%), three of the four first-prayer failures; in all three replays the hero stood on a trap it
had just triggered or climbed out of ('There is a falling rock trap here.', 'You crawl to the edge of the pit.') and walked into its kitten
or little dog -- the pet is killed at the hero's old square, a turn later. A pet that has seen the trap type escapes 3 times in 4, a young
one has not.

What the guard does: it remembers the squares on which a message says there is a deadly trap under the hero (the 'There is <trap> here.' line
of a look or a pick-up, the trigger messages, 'You crawl to the edge of the pit.'); while the hero is on that square and the step goes into a
pet it spends a search turn instead (the pet wanders off, the next plan steps elsewhere) -- at most PET_SWAP_WAITS turns per square, then the
swap is allowed (a pet that cannot get away must not pin the hero). Traps that merely trap or move the pet (bear trap, web, holes, teleporters)
cost alignment 3 at most and are not covered. A trap the hero never saw trigger or look at is not known to the bot and not covered.

No waiting with a hostile monster within HOSTILE_RADIUS squares (the step may be a flight or a fight position).
Reads messages and the glyph under the target; spends game time only through agent.search.
"""
import re

import numpy as np

from . import jf_config, utils
from .glyph import G

HOSTILE_RADIUS = 3
_KILLER_TRAPS = ('arrow trap', 'dart trap', 'falling rock trap', 'land mine', 'rolling boulder trap', 'fire trap', 'pit', 'spiked pit')
_LOOK = re.compile(r'There is (?:an? )(?:' + '|'.join(_KILLER_TRAPS) + r') here')
_TRIGGER = re.compile(
    r'An arrow shoots out at you|A little dart shoots out at you|a rock falls on your head|You fall into a pit|'
    r'You land on a set of sharp iron spikes|You triggered a land mine|You trigger a rolling boulder trap|'
    r'A tower of flame|You crawl to the edge of the pit')


def _state(agent):
    st = getattr(agent, '_pet_guard', None)
    if st is None:
        st = agent._pet_guard = {'sqs': set(), 'waits': {}, 'noted': 0, 'held': 0}
    return st


def note(agent):
    """Called after every observation update (Agent.update): remember the square of a deadly trap under the hero. Never raises."""
    try:
        st = getattr(agent, '_pet_guard', None)
        if st is not None and st.get('pending_here'):
            st['pending_here'] = False      # dev harness (jf_scenario trap_here): the hero starts on a deadly trap square
            st['sqs'].add((agent.current_level().key(), int(agent.blstats.y), int(agent.blstats.x)))
        msg = agent.message
        if msg and (_LOOK.search(msg) or _TRIGGER.search(msg)):
            st = _state(agent)
            st['sqs'].add((agent.current_level().key(), int(agent.blstats.y), int(agent.blstats.x)))
            st['noted'] += 1
    except Exception:
        pass


def hold(agent, ty, tx):
    """True when the step to (ty, tx) was replaced by a search turn: the hero stands on a remembered deadly trap square and the target
    holds a pet. Called by Agent.move before the step (which then raises AgentPanic, as for any step that did not happen)."""
    st = getattr(agent, '_pet_guard', None)
    if st is None or not st['sqs']:
        return False
    bl = agent.blstats
    sq = (agent.current_level().key(), int(bl.y), int(bl.x))
    if sq not in st['sqs']:
        return False
    if not utils.isin(agent.glyphs[ty:ty + 1, tx:tx + 1], G.PETS).any():
        return False
    y0, x0 = int(bl.y), int(bl.x)
    win = np.s_[max(y0 - HOSTILE_RADIUS, 0):y0 + HOSTILE_RADIUS + 1, max(x0 - HOSTILE_RADIUS, 0):x0 + HOSTILE_RADIUS + 1]
    if (agent.monster_tracker.monster_mask[win] & ~agent.monster_tracker.peaceful_monster_mask[win]).any():
        return False    # a hostile close by: this step may be a flight or a fight position, no waiting
    n = st['waits'].get(sq, 0)
    if n >= jf_config.PET_SWAP_WAITS:
        return False
    st['waits'][sq] = n + 1
    st['held'] += 1
    agent.log(f'PET_GUARD on a deadly trap square at ({bl.y},{bl.x}), the pet is at ({ty},{tx}): wait {n + 1}/{jf_config.PET_SWAP_WAITS}')
    agent.search()
    return True
