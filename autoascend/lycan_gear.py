"""LYCAN_GEAR (forensics lane, jf_config): fetch what a forced polymorph left on the floor.

A lycanthrope turns into its beast with probability 1/80 per turn (allmain.c); polymon -> break_armor/drop_weapon put the worn body
armour, cloak, helmet, boots, gloves, shield and the wielded weapon on the hero's square (a wolf form even breaks the suit and the cloak),
and were_unload drops the pack's load for a small form.  After 'You return to <race> form' nothing walks back for the pile: the dive never
runs gather_items, the tour only inside its exploration, and the escape digs (wand of digging down at 'Valkyrie is about to die') leave the
level for good.  In the dev corpus 10 of 38 games with a form change end with AC 10 (stripped) and the castle-band rate of the 55 games that
change form is 29% against 55% for clean games (ledger B324).

note_change(agent) is called when a form change or an unload drop happens (the hero stands on the drop square); note_return(agent) when the
hero is human again; strategy(agent) is a layer above the plan and below fight2/eating: back in human form, no hostile within
LYCAN_GEAR_RADIUS, HP >= LYCAN_GEAR_HP, on the same level, at most LYCAN_GEAR_TURNS of human time after the last drop or the return: walk to
the newest drop square, pick the pile up with the item priority (pickup_and_drop_items), wear what is better (wear_best_stuff) and wield the
best melee weapon.  Squares that cannot be reached are struck off; the layer gives up after LYCAN_GEAR_TRIES entries that moved nowhere or
LYCAN_GEAR_SPEND turns spent in it."""
from . import jf_config
from .strategy import Strategy


def _state(agent):
    return getattr(agent, '_lycan_pile', None)


def note_change(agent, why):
    """The gear fell on the hero's square: remember it (level, square, turn)."""
    if not jf_config.LYCAN_GEAR:
        return
    bl = agent.blstats
    level = agent.current_level()
    pos = (int(bl.y), int(bl.x))
    st = _state(agent)
    if st is None or st['key'] != level.key():
        st = agent._lycan_pile = dict(key=level.key(), pos=[], turn=int(bl.time), tries=0, spent=0, legs=0, seen={})
    if pos in st['pos']:
        st['pos'].remove(pos)
    st['pos'].append(pos)
    st['turn'] = int(bl.time)
    agent.log(f'LYCAN_GEAR {why}: gear on the floor at {pos} (depth {bl.depth}), {len(st["pos"])} drop square(s) noted')


def note_return(agent):
    """The hero is human again: the age of the pile counts from now.  The beast spell lasts rn1(500, 500) turns (polyself.c polymon) and a
    higher layer (the form wait) owns every step of it, so this layer is not consulted meanwhile: the first replay round gave the pile up
    after 781 and 707 turns, at the very step the hero turned human."""
    if not jf_config.LYCAN_GEAR:
        return
    st = _state(agent)
    if st:
        st['turn'] = int(agent.blstats.time)


# monsters with passive attacks only (uhitm.c passive(): they hurt whoever hits them) and speed <= 3: no reason to wait for one to leave
PASSIVE_ONLY = ('floating eye', 'blue jelly', 'spotted jelly', 'brown mold', 'yellow mold', 'green mold', 'red mold', 'acid blob', 'shrieker')


def _hostiles(agent, radius):
    """Visible hostiles within radius.  The passive-only ones count only when adjacent: replay jf1103 s4 (floating eyes all over the level)
    never found a quiet moment in 600 turns."""
    bl = agent.blstats
    out = []
    for m in agent.get_visible_monsters():
        d = max(abs(int(m[1]) - int(bl.y)), abs(int(m[2]) - int(bl.x)))
        if d > radius:
            continue
        if d > 1 and getattr(m[3], 'mname', '') in PASSIVE_ONLY:
            continue
        out.append(m)
    return out


def strategy(agent):
    def f():
        st = _state(agent)
        if not jf_config.LYCAN_GEAR or not st or not st['pos']:
            yield False
            return
        bl = agent.blstats
        if agent.character.prop.polymorph:
            st['turn'] = int(bl.time)
            yield False   # still in the beast form: nothing can be picked up
            return
        level = agent.current_level()
        if level.key() != st['key'] or bl.time - st['turn'] > jf_config.LYCAN_GEAR_TURNS or \
                st['tries'] >= jf_config.LYCAN_GEAR_TRIES or st['spent'] >= jf_config.LYCAN_GEAR_SPEND:
            # left the level (stairs, a hole), or too old, or too many idle entries, or too many turns spent: the pile is given up
            agent.log(f'LYCAN_GEAR given up (level {level.key()} vs {st["key"]}, age {bl.time - st["turn"]}, idle {st["tries"]}, '
                      f'spent {st["spent"]})')
            agent._lycan_pile = None
            yield False
            return
        if bl.hitpoints < jf_config.LYCAN_GEAR_HP * bl.max_hitpoints or _hostiles(agent, jf_config.LYCAN_GEAR_RADIUS) or \
                level.shop_interior[bl.y, bl.x]:
            yield False   # fight2, the Elbereth rest and the rest of the stack come first
            return
        pos = st['pos'][-1]
        here = (int(bl.y), int(bl.x))
        if here != pos and (agent.bfs()[pos] == -1 or level.shop_interior[pos[0], pos[1]]):
            # unreachable, or inside a shop: this layer is off in shop interiors (the shopkeeper's business), so a pile in a shop made it
            # walk to the door, hand over, walk back out and so on (replay jf1100 s11: 38 legs, 263 turns, nothing fetched)
            agent.log(f'LYCAN_GEAR: {pos} {"in a shop" if level.shop_interior[pos[0], pos[1]] else "unreachable"}, struck off')
            st['pos'].pop()
            if not st['pos']:
                agent._lycan_pile = None
            yield False
            return
        if here != pos and st['seen'].get(pos, 0) >= jf_config.LYCAN_GEAR_LEGS:
            # a step per entry for ever (a pet in the way, a layer above taking every other step): replay jf850 s4 made 24 one-step legs
            # around a square it could not reach
            agent.log(f'LYCAN_GEAR: {pos} not reached in {st["seen"][pos]} legs, struck off')
            st['pos'].pop()
            if not st['pos']:
                agent._lycan_pile = None
            yield False
            return
        yield True
        t0 = int(agent.blstats.time)
        worked = False
        try:
            if here != pos:
                st['seen'][pos] = st['seen'].get(pos, 0) + 1
            if st['legs'] < 40:
                st['legs'] += 1
                agent.log(f'LYCAN_GEAR: leg {st["legs"]} from {here} to {pos} ({len(st["pos"])} square(s), spent {st["spent"]}, '
                          f'idle {st["tries"]})')
            if here != pos:
                agent.go_to(pos[0], pos[1])
                worked = (int(agent.blstats.y), int(agent.blstats.x)) != here
                return
            worked = True
            below = list(agent.inventory.items_below_me or [])
            agent.log(f'LYCAN_GEAR: on the pile at {pos}: {[i.text for i in below][:8]}')
            st['pos'].pop()
            if not st['pos']:
                agent._lycan_pile = None
            if below:
                agent.inventory.pickup_and_drop_items().run()
            agent.inventory.wear_best_stuff().run()
            agent.wield_best_melee_weapon()
            agent.log(f'LYCAN_GEAR: done, AC {agent.blstats.armor_class}')
        finally:
            # also when go_to / the pickup raised (AgentPanic, AgentChangeStrategy): the budget is charged either way
            st['spent'] += max(0, int(agent.blstats.time) - t0)
            if not worked:
                st['tries'] += 1

    return Strategy(f)
