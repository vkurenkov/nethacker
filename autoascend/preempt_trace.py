"""PREEMPT_TRACE (supply lane, dev tool, off): which code do preempting strategies cut short?

The bug class of ledger F362 (B304, B307, B309): in a multi-step helper the code that follows a `step()` or an
`atom_operation()` block is skipped when a preempting strategy (AgentChangeStrategy) -- or a panic hook (AgentPanic) -- fires in
`update_state()`, which runs at the end of every non-atomic step and at the end of every atom block. This module

  1. logs, once per exception, the code that was cut short:
         PTRACE atom ChangeStrategy by=<the strategy that fired> cut=inventory.drop:784 < global_logic.f:812 < ...
     (`cut` = the nearest frames of bot code outside the step / atom plumbing, innermost first: the helper whose tail did not run),
     so the bot logs of any run rank the helpers whose tails really get skipped, by how often;
  2. fuzzes, to reproduce one such window on demand: an outermost preempt layer (global_logic via agent.run) that fires at the
     end of the chosen helpers' steps / blocks and spends one search turn, as any preempting strategy would:

  JF_CFG='{"PREEMPT_TRACE": true}'                                    # log only
  JF_CFG='{"PREEMPT_TRACE": {"fuzz": {"owner": ["inventory.drop", "inventory.pickup"], "p": 1.0, "skip": 0, "max": 3, "seed": 1}}}'

  owner   module.function names (file stem . function); the hook fires only when the innermost bot frame above the plumbing is
          one of them, i.e. at the exit of THAT helper's own step / block (not of the helpers it calls)
  depth   how many of the nearest bot frames may be the owner (default 1; a step of a walk is played by agent.direction, called
          by agent.move, called by agent.go_to: {"owner": ["agent.go_to"], "depth": 3})
  in      (optional) module.function names of which at least one must be on the call stack too: {"owner": ["agent.go_to"],
          "depth": 3, "in": ["inventory.buy_instrument"]} cuts only the walks of buy_instrument
  mid_walk  (optional, true) fire only at a step of a go_to that has not reached its target yet: the cut walk is left short
  action    (optional) "bump_shk": instead of a search turn the preempting body walks into an adjacent shopkeeper (fires only while
            one is adjacent): reproduces 'Really attack <shopkeeper>?' (ATTACK_GUARD)
  p       probability per exit (default 1.0)      skip   exits of the owners to let pass first (default 0)
  max     how many times at most per game (default 1)      seed   its own RNG (the game's is untouched)

Off (the default) nothing here is imported by the hot paths beyond one flag test, and no game RNG is ever drawn.
"""
import os
import random
import sys

from . import jf_config
from .exceptions import AgentChangeStrategy, AgentPanic
from .strategy import Strategy

# frames that are step / hook plumbing, not the helper whose tail is cut
_PLUMBING = {'f', 'call_update_functions', 'update_state', 'update', 'step', 'atom_operation', '__exit__', '__enter__', 'traced',
             'type_text', '_traced_step', '_traced_exit', 'armed', 'fuzz_hook', 'wrapper', 'inner', '<lambda>', 'context_preempt'}
_PLUMBING_FILES = {'contextlib.py', 'strategy.py', 'preempt_trace.py', 'jf_log.py'}


def cfg():
    c = jf_config.PREEMPT_TRACE
    return c if isinstance(c, dict) else {}


def owner_frames(depth=4, start=None):
    """[(file stem, function, line)] of the nearest `depth` frames outside the plumbing, innermost first."""
    f = start or sys._getframe(1)
    out = []
    while f is not None and len(out) < depth:
        code = f.f_code
        base = os.path.basename(code.co_filename)
        if base not in _PLUMBING_FILES and code.co_name not in _PLUMBING and 'site-packages' not in code.co_filename:
            out.append((os.path.splitext(base)[0], getattr(code, 'co_qualname', code.co_name), f.f_lineno))
        f = f.f_back
    return out


def _by(exc):
    """Name of the strategy that raised the AgentChangeStrategy (its generator's function)."""
    try:
        it = exc.args[1]
        code = getattr(it, 'gi_code', None)
        if code is not None:
            return getattr(code, 'co_qualname', code.co_name)
        return getattr(it, '__name__', str(it))[:40]
    except Exception:
        return '?'


def note(agent, kind, exc):
    """Log the cut-short code of `exc` (once per exception object)."""
    if getattr(exc, '_pt_logged', False):
        return
    try:
        exc._pt_logged = True
    except Exception:
        return
    frames = owner_frames(4)
    what = 'ChangeStrategy' if isinstance(exc, AgentChangeStrategy) else 'Panic'
    by = _by(exc) if what == 'ChangeStrategy' else str(exc.args[0] if exc.args else '')[:60]
    agent.log('PTRACE %s %s by=%s cut=%s' % (kind, what, by, ' < '.join('%s.%s:%d' % fr for fr in frames)))


def traced(agent, kind, fn):
    """fn() with the preemption / panic it raises logged (it propagates unchanged)."""
    try:
        return fn()
    except (AgentChangeStrategy, AgentPanic) as e:
        note(agent, kind, e)
        raise


def stack_has(names, start):
    """Some frame above `start` is module.function of `names` (file stem . function, the last qualname part)."""
    f = start
    while f is not None:
        code = f.f_code
        if '%s.%s' % (os.path.splitext(os.path.basename(code.co_filename))[0],
                      getattr(code, 'co_qualname', code.co_name).split('.')[-1]) in names:
            return True
        f = f.f_back
    return False


def adjacent_shopkeeper(agent):
    """(y, x) of a shopkeeper next to the hero, or None."""
    try:
        from .glyph import G
        y0, x0 = int(agent.blstats.y), int(agent.blstats.x)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if (dy or dx) and int(agent.glyphs[y0 + dy, x0 + dx]) in G.SHOPKEEPER:
                    return y0 + dy, x0 + dx
    except Exception:
        pass
    return None


def short_of_target(agent, start):
    """The nearest go_to frame above `start` has not reached its target square (reads the frame's y, x arguments)."""
    f = start
    while f is not None:
        if f.f_code.co_name == 'go_to' and os.path.basename(f.f_code.co_filename) == 'agent.py':
            ty, tx = f.f_locals.get('y'), f.f_locals.get('x')
            if ty is None or tx is None:
                return False
            return (int(agent.blstats.y), int(agent.blstats.x)) != (int(ty), int(tx))
        f = f.f_back
    return False


def fuzz_layer(agent, strat):
    """strat with the fuzzing layer on top (the outermost preempt: it is asked first at every exit), or strat itself."""
    c = cfg().get('fuzz')
    if not c:
        return strat
    owners = set(c.get('owner') or [])
    within = set(c.get('in') or [])
    depth = int(c.get('depth', 1))
    mid_walk = bool(c.get('mid_walk', False))
    action = c.get('action')
    p = float(c.get('p', 1.0))
    skip = int(c.get('skip', 0))
    maxn = int(c.get('max', 1))
    rng = random.Random(int(c.get('seed', 1)))
    st = {'seen': 0, 'fired': 0}

    def fuzz():
        if st['fired'] >= maxn:
            yield False
        fr = owner_frames(depth, sys._getframe(1))
        if not fr or not any('%s.%s' % (a, b.split('.')[-1]) in owners for a, b, _ in fr):
            yield False
        if within and not stack_has(within, sys._getframe(1)):
            yield False
        if mid_walk and not short_of_target(agent, sys._getframe(1)):
            yield False
        target = None
        if action == 'bump_shk':
            target = adjacent_shopkeeper(agent)
            if target is None:
                yield False
        st['seen'] += 1
        if st['seen'] <= skip or rng.random() >= p:
            yield False
        st['fired'] += 1
        agent.log('PTRACE fuzz firing #%d at the exit of %s.%s:%d (seen %d)' % (st['fired'], fr[0][0], fr[0][1], fr[0][2], st['seen']))
        yield True
        if target is not None:
            agent.log('PTRACE fuzz: walking into the shopkeeper at %s' % (target,))
            agent.direction(*target)
        else:
            agent.search(1)

    return strat.preempt(agent, [Strategy(fuzz)])
