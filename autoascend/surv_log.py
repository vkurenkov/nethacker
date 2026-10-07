"""SURV_LOG (survival lane, logging only): why does a hero reach Weak / Fainting, and what does it hold and see when it does?

Writes 'SURV ...' lines into the dev bot log (agent.log is a no-op without JF_LOG_DIR: the arena never sees them), only when
jf_config.SURV_LOG is on:

  SURV hunger <old>-><new> ...   every hunger-state change that involves Hungry or worse (glyph.Hunger: 1 not hungry, 2 hungry,
                                 3 weak, 4 fainting): the edible food carried (names, nutrition), the gap since the last prayer,
                                 prayer_failed, diving/rescue, the nearest hostiles (name, distance), HP, the engraving below us
  SURV pray ...                  one line when Agent.pray() starts: hunger, carried food, HP, hostiles
  SURV eat ...                   one line per Inventory.eat() call: what, hunger state

Game identity (the same contract as prep_log.py): note() only READS the agent -- blstats, inventory, the monster tracker's
masks -- and never steps, never calls a strategy, never draws a random number and never writes agent state other than its own
`_surv_log` bookkeeping attribute, which nothing else reads. Every failure is caught (the first 3 are logged as 'SURV error').
Runs with SURV_LOG on replay the flag-off games byte-identically (checked in dev/survival/identity.py).
"""
from . import jf_config  # noqa: F401  (the flag is tested by the callers)
from .glyph import Hunger, MON


def _book(agent):
    book = getattr(agent, '_surv_log', None)
    if book is None:
        book = agent._surv_log = {'hs': None, 'err': 0}
    return book


def _hostiles(agent, limit=5):
    """[(name, chebyshev distance)] of the nearest non-peaceful monsters in the tracker's mask (reads only)."""
    tr = agent.monster_tracker
    mask = tr.monster_mask & ~tr.peaceful_monster_mask
    bl = agent.blstats
    out = []
    for y, x in zip(*mask.nonzero()):
        g = agent.glyphs[y, x]
        try:
            name = MON.permonst(g).mname if MON.is_monster(g) else 'unseen'
        except Exception:
            name = '?'
        out.append((max(abs(int(y) - bl.y), abs(int(x) - bl.x)), name))
    out.sort()
    return [(n, d) for d, n in out[:limit]]


def _food(agent):
    names = []
    for item in agent.edible_carried_food():
        names.append(f'{item.count}x{item.objs[0].name}' if item.count > 1 else item.objs[0].name)
    return names


def _state(agent):
    bl = agent.blstats
    gap = None if agent.last_prayer_turn is None else bl.time - agent.last_prayer_turn
    dive = agent.global_logic.dive
    try:
        cn = agent.inventory.carried_nutrition()
    except Exception:
        cn = None
    return (f'food={_food(agent)} cn={cn} gap={gap} pf={int(bool(agent.prayer_failed))} dv={int(bool(dive.diving))} '
            f'rescue={int(bool(getattr(dive, "rescue", False)))} pet={int(bool(agent.has_pet))} '
            f'hostiles={_hostiles(agent)} eng={(agent.inventory.engraving_below_me or "")[:12]!r}')


def note(agent):
    """Called after every observation update (Agent.update): log the hunger transitions."""
    book = _book(agent)
    try:
        bl = agent.blstats
        hs = int(bl.hunger_state)
        prev = book['hs']
        book['hs'] = hs
        if not book.get('start_logged'):
            # the very first observations: do the welcome / moon / Friday-13th messages ('Watch out!  Bad things can happen on
            # Friday the 13th.', 'You are lucky!  Full moon tonight.') reach the bot? (Luck -1 for good on Friday the 13th: every prayer fails)
            book['start_logged'] = True
            agent.log(f'SURV start msgs={[m[:80] for m in agent._message_history[:8]]} now={agent.message[:100]!r}')
        if prev is None or hs == prev or hs > Hunger.FAINTING or prev > Hunger.FAINTING:
            return
        if max(hs, prev) < Hunger.HUNGRY:
            return
        agent.log(f'SURV hunger {prev}->{hs} {_state(agent)}')
    except Exception as e:  # never raise
        if book['err'] < 3:
            book['err'] += 1
            agent.log(f'SURV error {type(e).__name__}: {str(e)[:120]}')


def note_pray(agent):
    book = _book(agent)
    try:
        agent.log(f'SURV pray hu={int(agent.blstats.hunger_state)} {_state(agent)}')
    except Exception as e:  # never raise
        if book['err'] < 3:
            book['err'] += 1
            agent.log(f'SURV error {type(e).__name__}: {str(e)[:120]}')


def note_eat(agent, item, quaff):
    book = _book(agent)
    try:
        agent.log(f'SURV {"quaff" if quaff else "eat"} {item.text!r} hu={int(agent.blstats.hunger_state)} '
                  f'hostiles={_hostiles(agent, 3)}')
    except Exception as e:  # never raise
        if book['err'] < 3:
            book['err'] += 1
            agent.log(f'SURV error {type(e).__name__}: {str(e)[:120]}')
