"""castle-poly (jf_config CP_*): the random-polymorph route over the castle moat (READINESS route Y) and the
wall-walker forms (route X without control).

WHY (ledger F094, census of the 105 castle arrivals of the cand-g fresh games jf43-60, true kits by a harness reveal):
17 arrivals held a polymorph source (7 wands, all known to the bot; 7 potions; 5 rings), 7 of them at a Dlvl-29 castle
(where a crossing into the Valley = depth 30 = a pass), and none passed. The logs show why:
  * the wand was zapped where the hero landed, in the sealed west maze. Crossing forms came up in 5 of the 7 wand kits
    (crocodile, cobra, queen bee, orc mummy, straw golem), but a handless form can't apply the pick-axe to dig to the
    water ('You can't hold it strongly enough.'), so CFP_RUSH was 'stuck' and fought the land monster next to it until
    the form died (18-50 form HP); castle_logic's walk to the courtyard then dug with the same pick (4 failed digs give
    the whole passage up). Harness cp-base1 (castle-base XL9 kit + a known wand of polymorph (0:6), 21 castle-29 seeds):
    18 of 21 got a crossing form, 1 passed; a 95-HP blue dragon looped 'digging toward (-1, 14)' / 'walking to (0, 6)';
  * a cursed ring of polymorph (put on as a lift test, stuck) polymorphs us every ~100 turns (allmain.c: Polymorph &&
    !rn2(100)): the harness ring kits (pr, 21 seeds) drew 37 crossing forms in 9 games and never crossed -- the passage
    had been given up ('nothing that crosses water') and the forms were in the maze.
polyself.c facts (3.6.6, NLE's own permonst table; $SCR/castlekit/forms.py): Con 17 -> system shock 1 in 10 (rnd(30) HP,
own form only: in a form the form's HP pays), newman 1 in 5 of the rest (XL +-2, HP re-rolled), else a uniform polyok
form: 128 of the 273 cross the moat (fly 55, swim, amphibious or breathless -- mondata.h amphibious() -- or walk walls:
xorn, earth elemental), i.e. 0.34 per zap (fly 0.145, wall-walk 0.005). Form HP d(mlvl,8), time rn1(500,500) x
min(1, XL/mlvl). A form's death returns us to our own form and HP -- in the moat's walled channels that is drowning
(trap.c drown: no land square to crawl to). An eel's wrap drowns flyers too (mhitu.c AD_WRAP: only Swimming or
Amphibious are safe). Any form can zap a wand (zap.c has no hands check); check_capacity refuses when Overtaxed.

CP_POLY (the protocol; castle_power.arrival_step and door_step call it, form_strategy is a preempt layer):
  1. own form with a known wand of polymorph: walk (and dig: we have hands) to the courtyard's test square first, one or
     two steps from the moat and with no water next to it, write Elbereth there, and zap ourselves THERE -- not where
     we land. The kit's lasting lifts (CFP_RUSH pending) still go first.
  2. a form: usable = crosses water (fly/swim/amphibious/breathless), has eyes (an eyeless form is blind the whole
     time), moves (speed >= CP_MIN_SPEED), and -- while the wand can re-roll -- has CP_GOOD_HP hit points. Usable ->
     the crossing (castle_logic's crossing strategy takes a 'floating' hero from the courtyard; form_strategy walks
     a form that is still in the maze to the courtyard without digging, and takes back a passage given up before
     the form came, e.g. from a stuck ring). Not usable -> zap again. A wall-walker -> CFP_XORN.
  3. castle below Dlvl 29 (CP_WALL_REROLL > 0): a plain crossing only reaches the Valley at depth <= 29 (+1 level,
     no pass); a wall-walker passes at any depth (CFP_XORN through the walls, CASTLE_TREASURY, VALLEY_XORN through
     the Valley's rock) -- so up to CP_WALL_REROLL extra zaps look for one before a plain crossing form is taken.
  4. east side (CP_DOOR_REZAP): a form that can't kick the locked back door and has no wand to zap at it zaps itself
     from SAFE_EAST (1 in 5 newman: our own form; most forms have legs) instead of waiting out a 500-1000 turn form;
     a flyer in the doorway steps onto the trap door (LIFT_PLUNGE's '>' drops a flyer through it).
"""

import re

import nle.nethack as nh

from . import jf_config
from .castle_logic import OUTSIDE, WEST_COURTYARD, TRAPDOOR, DOOR, SAFE_EAST, map_char, to_bot
from .exceptions import AgentChangeStrategy, AgentFinished, AgentPanic
from .level import Level
from .strategy import Strategy

M1_FLY, M1_SWIM, M1_WALLWALK = 0x1, 0x2, 0x8
M1_AMPHIBIOUS, M1_BREATHLESS, M1_NOEYES, M1_NOHANDS = 0x200, 0x400, 0x1000, 0x2000
MZ_HUGE = 4
CHARGES_RX = re.compile(r'\((-?\d+):(-?\d+)\)')
# courtyard squares a form walks to (the crossing starts from any of them): the test square first, then its
# neighbours with no water beside them (castle_logic.CastlePassage.INNER), then the corner-side squares
COURTYARD_GOALS = ((1, 7), (2, 7), (1, 8), (2, 8), (1, 9), (0, 7), (0, 8), (0, 9))


def _log(agent, msg):
    agent.log(f'CP {msg}')


def form_info(p):
    """What a polymorph form (permonst) can do at the castle."""
    f1 = int(p.mflags1)
    return dict(name=p.mname, fly=bool(f1 & M1_FLY), swim=bool(f1 & M1_SWIM),
                amph=bool(f1 & (M1_AMPHIBIOUS | M1_BREATHLESS)), wall=bool(f1 & M1_WALLWALK),
                eyes=not (f1 & M1_NOEYES), hands=not (f1 & M1_NOHANDS), speed=int(p.mmove),
                huge=int(p.msize) >= MZ_HUGE, mlvl=int(p.mlevel))


def crosses(info):
    return info['fly'] or info['swim'] or info['amph'] or info['wall']


def on_castle(castle):
    agent = castle.agent
    level = agent.current_level()
    return castle.castle_key is not None and level.key() == castle.castle_key and \
        level.dungeon_number == Level.DUNGEONS_OF_DOOM


def poly_wand(agent):
    from . import castle_power
    return castle_power._poly_wand(agent)


def wand_charges(item):
    """Charges shown in the wand's name ('(0:6)'), else None (unknown)."""
    m = CHARGES_RX.search(item.text or '')
    return int(m.group(2)) if m else None


def can_rezap(castle):
    """A wand of polymorph not known empty, and the zap budget not spent: the wand, else None. (CP_V2: not while a
    form too weak to carry the wand alone is Overtaxed -- zap.c check_capacity refuses the zap at EXT_ENCUMBER.)"""
    wand = poly_wand(castle.agent)
    if wand is None or castle._tries.get('cp_zaps', 0) >= jf_config.CP_MAX_ZAPS:
        return None
    ch = wand_charges(wand)
    if ch is not None and ch <= 0:
        return None
    if jf_config.CP_V2 and castle._tries.get('cp_nozap_form') is not None:
        from . import castle_cross
        form = castle_cross.form_permonst(castle.agent)
        if form is not None and form.mname == castle._tries['cp_nozap_form']:
            return None
    return wand


def verdict(castle, form):
    """('wall' | 'go' | 'stay' | 'reroll' | 'wallroll', info) for our polymorph form (permonst) on the castle."""
    info = form_info(form)
    if info['wall']:
        return 'wall', info
    if not crosses(info):
        return 'reroll', info
    agent = castle.agent
    if can_rezap(castle) is None:
        # nothing to re-roll with: any form that crosses water and moves at all is our best chance
        return ('go' if info['speed'] > 0 else 'stay'), info
    # (CP_V2: the form's birth HP -- its max -- not what a fight left of it: v1 re-rolled a 20-HP succubus bitten to 18)
    hp = agent.blstats.max_hitpoints if jf_config.CP_V2 else agent.blstats.hitpoints
    if not info['eyes'] or info['speed'] < jf_config.CP_MIN_SPEED or hp < jf_config.CP_GOOD_HP:
        return 'reroll', info
    if jf_config.CP_WALL_REROLL and agent.blstats.depth < 29 and \
            castle._tries.get('cp_wall_rerolls', 0) < jf_config.CP_WALL_REROLL:
        # a plain crossing below a castle above Dlvl 29 reaches a Valley at depth <= 29: +1 level, no pass
        return 'wallroll', info
    return 'go', info


def drill_pending(castle):
    """castle_cross._poly_drill_pending under CP_POLY (CL_POTION_EARLY's potions wait for it): a form that is making the
    crossing (or walks the walls), or a wand of polymorph that can still re-roll. A form that can't cross with nothing
    left to re-roll it: the potions may lift it."""
    from . import castle_cross
    form = castle_cross.form_permonst(castle.agent)
    if form is not None:
        v, _ = verdict(castle, form)
        if v in ('go', 'stay', 'wall'):
            return True
    return can_rezap(castle) is not None


def _describe(agent, form):
    if form is None:
        return 'own form'
    info = form_info(form)
    tags = [k for k in ('fly', 'swim', 'amph', 'wall', 'huge') if info[k]]
    tags += [] if info['eyes'] else ['eyeless']
    tags += [] if info['hands'] else ['nohands']
    return f'{info["name"]} hp {agent.blstats.hitpoints} speed {info["speed"]} {" ".join(tags)}'


def _zap(castle, wand, why):
    from . import castle_cross, castle_power
    agent = castle.agent
    t = castle._tries
    t['cp_zaps'] = t.get('cp_zaps', 0) + 1
    _log(agent, f'zap {t["cp_zaps"]} ({why}) at {castle._pos()} hp {agent.blstats.hitpoints}/'
                f'{agent.blstats.max_hitpoints} depth {agent.blstats.depth}: {wand.text!r}')
    castle_power._zap_self(castle, wand)
    _log(agent, f'-> {_describe(agent, castle_cross.form_permonst(agent))} ({(agent.message or "")[:70]!r})')


def _overloaded_drop(castle, wand):
    """A small form is Overtaxed by our pack and zap.c check_capacity refuses to zap: keep only the wand (castle_power's
    rule). True: acted."""
    if jf_config.CP_V2:
        return lighten(castle, target=3)
    agent = castle.agent
    t = castle._tries
    if agent.blstats.carrying_capacity < 4 or t.get('cp_drop_at') == agent.blstats.time:
        return False
    rest = [i for i in agent.inventory.items if i is not wand and i.can_be_dropped_from_inventory()
            and i.category != nh.COIN_CLASS]
    if not rest:
        return False
    t['cp_drop_at'] = agent.blstats.time
    t['cp_dropped_pos'] = castle._pos()
    _log(agent, f'overloaded form: dropping {len(rest)} items to zap')
    agent.inventory.drop(rest, smart=False)
    return True


DOOR_WANDS = ('striking', 'digging', 'opening')
UNLOCKERS = ('skeleton key', 'lock pick', 'credit card')


def _weight(item):
    try:
        return int(item.weight())
    except Exception:
        return 10


def _kept(castle):
    """CP_V2: what a lightened form keeps while it can carry it: the wand of polymorph (re-rolls, the door), known wands
    that open the back door (striking / digging / opening), unlocking tools."""
    agent = castle.agent
    wand = poly_wand(agent)
    keep = []
    for it in agent.inventory.items:
        if wand is not None and it is wand:
            keep.append(it)
        elif it.is_unambiguous() and it.category == nh.WAND_CLASS and it.object.name in DOOR_WANDS:
            keep.append(it)
        elif it.is_unambiguous() and it.object.name in UNLOCKERS:
            keep.append(it)
    return keep


def lighten(castle, target=1):
    """CP_V2: drop the pack, heaviest first, until our encumbrance (blstats: 0 unencumbered .. 5 overloaded) is at most
    `target`. A small form's capacity is our own x cwt/1450 (weight.c carrycap: a chickatrice ~6, a queen bee 0), so
    everything but the kept items goes at once from Stressed up; only when the kept items alone still stop us moving or
    zapping (Overtaxed+) do they go too, and the wand is then marked unusable for this form. One drop per turn.
    True: dropped this step."""
    from . import castle_cross
    agent = castle.agent
    enc = int(agent.blstats.carrying_capacity)
    if enc <= target:
        return False
    t = castle._tries
    now = agent.blstats.time
    if t.get('cp_lighten_at') == now:
        return False
    keep = _kept(castle)
    cands = [i for i in agent.inventory.items if i.can_be_dropped_from_inventory() and
             i.category != nh.COIN_CLASS and not any(i is k for k in keep)]
    if not cands:
        if enc < 4:
            return False
        cands = [i for i in agent.inventory.items if i.can_be_dropped_from_inventory() and i.category != nh.COIN_CLASS]
        if not cands:
            return False
        form = castle_cross.form_permonst(agent)
        t['cp_nozap_form'] = form.mname if form is not None else None
        _log(agent, f'lighten: the {t["cp_nozap_form"]} form can not carry even the wand (encumbrance {enc})')
    cands.sort(key=lambda i: -_weight(i))
    if enc >= 2:
        drop = cands
    else:
        total = sum(_weight(i) for i in cands)
        drop, acc = [], 0
        for i in cands:
            drop.append(i)
            acc += _weight(i)
            if acc >= 0.5 * total:
                break
    t['cp_lighten_at'] = now
    _log(agent, f'lighten (encumbrance {enc} -> <= {target}): dropping {len(drop)} of {len(cands)} items '
                f'({sum(_weight(i) for i in drop)} wt) at {castle._pos()}: {[i.text for i in drop][:6]}')
    try:
        agent.inventory.drop(drop, smart=False)
    except (AgentChangeStrategy, AgentFinished, AgentPanic):
        raise   # (the strategy framework's own control flow)
    except Exception as e:   # an inventory quirk must not end the route
        _log(agent, f'lighten: drop failed: {e!r}')
        return False
    return True


def lighten_possible(castle, target=1):
    """lighten() would drop something now (or next turn): encumbrance above `target` and droppable items that it may
    drop (the kept ones only from Overtaxed up)."""
    agent = castle.agent
    enc = int(agent.blstats.carrying_capacity)
    if enc <= target:
        return False
    keep = _kept(castle)
    drop = [i for i in agent.inventory.items if i.can_be_dropped_from_inventory() and i.category != nh.COIN_CLASS]
    if enc >= 4:
        return bool(drop)
    return any(not any(i is k for k in keep) for i in drop)


def _launch_step(passage):
    """CP_LAUNCH, own form: one step of castle-lift's on-foot cl_route toward the launch square of the cheapest far
    channel entry. True: acted; 'here': we stand on the launch square (entry and half noted); None: no plan."""
    from . import castle_cross
    t = passage._tries
    if t.get('cp_launch_fail', 0) >= 3:
        return None
    try:
        r = castle_cross.cl_route_step(passage, on_foot=True)
    except (AgentChangeStrategy, AgentFinished, AgentPanic):
        raise   # (a higher layer took over mid-step: smoke cp-smoke4-v2l counted these as route failures)
    except Exception as e:
        _log(passage.agent, f'launch: cl_route_step failed: {e!r}')
        t['cp_launch_fail'] = t.get('cp_launch_fail', 0) + 1
        return None
    if r == 'launch':
        plan = castle_cross.cl_route(passage)
        if plan is not None:
            path, half, _ = plan
            t['cp_entry'] = tuple(int(v) for v in path[-1])
            t['cp_half'] = half
        t['cp_launch'] = tuple(int(v) for v in passage._pos())
        return 'here'
    if r is None:
        t['cp_launch_fail'] = t.get('cp_launch_fail', 0) + 1
        return None
    return True


def arrival_step(passage, cfp_wait):
    """castle_power.arrival_step's polymorph part under CP_POLY (castle_logic.plan_step, the bottom of the preempt
    chain: fight2 / elbereth_rest / the emergency layer act above it), OUR OWN FORM only (form_strategy has the
    forms). False: nothing for the poly route here (the caller goes on); True: acted this step."""
    agent = passage.agent
    t = passage._tries
    from . import castle_cross
    if castle_cross.form_permonst(agent) is not None:
        return False
    if t.get('cp_dropped_pos') is not None and passage._pos() == t['cp_dropped_pos'] and \
            agent.inventory.items_below_me and not t.get('cp_repick'):
        # back in our own form on the pile an overloaded form dropped: take it back
        t['cp_repick'] = 1
        agent.inventory.pickup_and_drop_items().run()
        return True
    wand = can_rezap(passage)
    if wand is None or cfp_wait:
        return False   # (CFP_RUSH: the kit's lasting lifts and the magical-breathing water test go first)
    pos = tuple(int(v) for v in passage._pos())
    at_launch = False
    if jf_config.CP_V2 and jf_config.CP_LAUNCH and t.get('cp_launch') is not None and pos == t['cp_launch']:
        at_launch = True
    elif jf_config.CP_V2 and jf_config.CP_LAUNCH and pos[0] < 57:
        r = _launch_step(passage)
        if r is True:
            passage._set_state('cp: to the far launch square to zap the wand of polymorph there')
            return True
        at_launch = r == 'here'
        if at_launch:
            _log(agent, f'launch square {pos}: entry {t.get("cp_entry")} ({t.get("cp_half")})')
    if not at_launch:
        spot = passage._tspot()
        if pos != spot and not t.get('cp_spot_unreachable'):
            t['cp_approach'] = t.get('cp_approach', 0) + 1
            if t['cp_approach'] > 400:
                t['cp_spot_unreachable'] = 1
                _log(agent, f'test square {spot} not reached in 400 steps: zapping where we are')
            else:
                passage._set_state(f'cp: to {spot} to zap the wand of polymorph there')
                if passage._approach(spot):
                    return True
                t['cp_spot_unreachable'] = 1
    bl = agent.blstats
    near = passage._hostiles_near(1)
    engraving = (agent.inventory.engraving_below_me or '').lower()
    if engraving != 'elbereth' and agent.can_engrave() and not agent.character.prop.blind and \
            t.get('cp_elbereth', 0) < 3:
        # a scared monster doesn't melee us while we zap and look at the form (sea monsters, most land ones)
        t['cp_elbereth'] = t.get('cp_elbereth', 0) + 1
        passage._set_state('cp: Elbereth before the self-zap')
        agent.engrave('Elbereth')
        return True
    if bl.hitpoints < jf_config.CP_ZAP_MIN_HP and not near and t.get('cp_rest', 0) < 300:
        # system shock hits our OWN hit points (rnd(30), 1 zap in 10 at Con 17): no zap from a low pool unless
        # something is at us (then the form's fresh pool is the better bet)
        t['cp_rest'] = t.get('cp_rest', 0) + 1
        passage._set_state(f'cp: resting to {jf_config.CP_ZAP_MIN_HP} HP before the self-zap')
        agent.search(3)
        return True
    _zap(passage, wand, 'first' if not t.get('cp_zaps') else 'own form again')
    return True


def _walk_goal(castle):
    """Where a usable crossing form on land walks: the launch square it was made on (CP_LAUNCH: its entry is one step
    away) or the nearest courtyard square. (bot y, x, map square, kind) or None."""
    agent = castle.agent
    t = castle._tries
    dist = agent.bfs()
    here = tuple(int(v) for v in castle._pos())
    if jf_config.CP_V2 and jf_config.CP_LAUNCH and t.get('cp_launch') is not None and t['cp_launch'] != here and \
            t.get('cp_entry_steps', 0) <= 12:
        y, x = to_bot(*t['cp_launch'])
        if dist[y, x] != -1:
            return y, x, t['cp_launch'], 'launch square'
    best = None
    for spot in COURTYARD_GOALS:
        y, x = to_bot(*spot)
        if spot != here and dist[y, x] != -1 and (best is None or dist[y, x] < best[0]):
            best = (dist[y, x], y, x, spot)
    if best is not None:
        return best[1], best[2], best[3], 'courtyard'
    return None


def _walk_to_courtyard(castle, info):
    """A crossing form in the west maze: to the courtyard (the crossing starts there) by walking -- a form without hands
    can't dig (castle_logic._approach's CASTLE_WEST_DIG gives the passage up after 4 failed digs). True: acted."""
    agent = castle.agent
    t = castle._tries
    if not jf_config.CP_V2 and info['hands'] and not t.get('cfp_nodig') and castle.dive.digging_tool() is not None:
        return castle._approach(castle._tspot())
    goal = _walk_goal(castle)
    if goal is not None:
        y, x, spot, kind = goal
        if (int(agent.blstats.y), int(agent.blstats.x)) == (int(y), int(x)):
            return False
        castle._set_state(f'cp: walking the form to the {kind} {spot}')
        agent.go_to(y, x, max_steps=1)
        return True
    if t.get('cp_explore', 0) >= 6:
        return False
    t['cp_explore'] = t.get('cp_explore', 0) + 1
    castle._set_state('cp: exploring to the courtyard (a form)')
    target = to_bot(*castle._tspot())
    start = agent.step_count
    castle.dive.exploration(None).until(
        agent, lambda: agent.bfs()[target] != -1 or agent.step_count - start > 150).run()
    return True


def _on_water(castle):
    mx, my = castle._pos()
    return map_char(mx, my) == '}' and not castle._dry(mx, my)


def _water_sq(castle, sq):
    return map_char(*sq) == '}' and not castle._dry(*sq)


def _at_launch(castle):
    """CP_LAUNCH: we stand on the launch square with its far entry one step away (still water)."""
    t = castle._tries
    entry = t.get('cp_entry')
    pos = tuple(int(v) for v in castle._pos())
    if entry is None or t.get('cp_launch') != pos or t.get('cp_entry_steps', 0) > 12:
        return False
    return max(abs(entry[0] - pos[0]), abs(entry[1] - pos[1])) == 1 and _water_sq(castle, entry)


def _entry_step(castle):
    """CP_LAUNCH: a usable crossing form on its launch square steps onto the far entry (castle_logic's crossing takes it
    on from the water: committed). True: stepped."""
    if not _at_launch(castle):
        return False
    t = castle._tries
    entry = t['cp_entry']
    t['cp_entry_steps'] = t.get('cp_entry_steps', 0) + 1
    castle._half = t.get('cp_half') or ('north' if entry[1] <= 8 else 'south')
    castle._set_state(f'cp: the form steps onto the moat at {entry} ({castle._half})')
    castle._step_to(*entry)
    return True


def form_strategy(dive):
    """CP_POLY preempt layer (above castle_logic's crossing strategy, below CFP_XORN): our polymorph form on the castle's
    west side, on land:
      * usable crossing form: take the passage back if it was given up (a stuck ring's form comes hundreds of turns
        after 'nothing that crosses water'); CP_V2: drop the pack to Burdened first; CP_LAUNCH: on the launch square
        step onto its far entry; in the maze, walk to the launch square / the courtyard (the crossing floats it on);
      * a form that can't make the crossing, and the wand can re-roll: zap again, here."""
    def f():
        castle = dive.castle
        agent = dive.agent
        if not jf_config.CP_POLY or not on_castle(castle) or castle._pos()[0] >= 57 or _on_water(castle):
            yield False
            return
        from . import castle_cross
        form = castle_cross.form_permonst(agent)
        if form is None:
            yield False
            return
        v, info = verdict(castle, form)
        v2 = jf_config.CP_V2
        heavy = v2 and lighten_possible(castle, target=1)
        if v in ('go', 'stay'):
            if castle.given_up and jf_config.CASTLE_PASSAGE:
                castle.given_up = False
                castle._stuck = 0
                _log(agent, f'a {info["name"]} form crosses water: taking the passage back up '
                            f'("{getattr(castle, "_given_up_why", "")}")')
            launch = v2 and jf_config.CP_LAUNCH and _at_launch(castle)
            if castle._pos() in OUTSIDE and not heavy:
                yield False   # castle_logic's crossing strategy (a 'floating' hero in the courtyard)
                return
            if not heavy and not launch and _walk_goal(castle) is None and castle._tries.get('cp_explore', 0) >= 6:
                yield False   # (nowhere to walk: the old layers)
                return
        elif v in ('reroll', 'wallroll'):
            if can_rezap(castle) is None:
                yield False
                return
        else:
            yield False   # a wall-walker: CFP_XORN
            return
        yield True
        steps = 0
        while steps < 300 and on_castle(castle) and not _on_water(castle):
            steps += 1
            form = castle_cross.form_permonst(agent)
            if form is None:
                return   # our own form: castle_power.arrival_step (the launch / test square, the next zap)
            v, info = verdict(castle, form)
            before = agent.step_count
            if v in ('reroll', 'wallroll'):
                wand = can_rezap(castle)
                if wand is None:
                    return
                if _overloaded_drop(castle, wand):
                    continue
                if v2 and int(agent.blstats.carrying_capacity) >= 4:
                    # (dropped this turn already, or nothing left: zap.c would refuse the zap -- wait a move; lighten
                    # marks a form that can't carry even the wand, and can_rezap then ends the re-rolls)
                    agent.search()
                    continue
                if v == 'wallroll':
                    castle._tries['cp_wall_rerolls'] = castle._tries.get('cp_wall_rerolls', 0) + 1
                    why = f'castle {agent.blstats.depth} < 29: a wall-walker wanted, not a {info["name"]}'
                else:
                    why = f'a {_describe(agent, form)} can not make the crossing'
                _zap(castle, wand, why)
            elif v in ('go', 'stay'):
                if v2 and lighten(castle, target=1):
                    continue
                if v2 and lighten_possible(castle, target=1) and \
                        castle._tries.get('cp_lighten_at') == agent.blstats.time:
                    agent.search()   # (the drop's turn: the status line shows the new load next turn)
                    continue
                if v2 and jf_config.CP_LAUNCH and _entry_step(castle):
                    continue
                if castle._pos() in OUTSIDE:
                    return
                if not _walk_to_courtyard(castle, info):
                    _log(agent, f'the {info["name"]} form can not reach the courtyard from {castle._pos()}')
                    return
            else:
                return
            if agent.step_count == before:
                agent.search()

    return Strategy(f)


DIRS8 = ((-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1))


def _dry_land(castle, sq):
    """Land we can stand on next to the moat: castle-map floor or ice, or a walkable square off the map (the mazes)."""
    mx, my = sq
    if 0 <= mx < 63 and 0 <= my < 17:
        return map_char(mx, my) == '.' or (map_char(mx, my) == '}' and castle._dry(mx, my))
    agent = castle.agent
    level = agent.current_level()
    y, x = to_bot(mx, my)
    return 0 <= y < level.walkable.shape[0] and 0 <= x < level.walkable.shape[1] and bool(level.walkable[y, x])


def _outside_land(castle):
    """On dry land outside the castle walls, east of the west courtyard and west of the east courtyard: the strips (map
    rows 0 / 16, x 9..53) -- where castle_logic's crossing is 'committed' and our own form is stranded."""
    pos = tuple(int(v) for v in castle._pos())
    return pos in OUTSIDE and pos not in WEST_COURTYARD and 0 < pos[0] < 57 and _dry_land(castle, pos)


def water_strategy(dive):
    """CP_WATER (castle-poly; ledger evidence cp-syn29-v2l): a form's death over the moat returns us to our own form IN
    the water, and a channel has no land to crawl to (trap.c drown -> 'You drown.'): 4 of 21 wand kits drowned that way
    (a 20-HP straw golem bitten twice by the far channel's shark, a 50-HP baby red dragon under a tower xorn and a shark).
      * a form over water below CP_WATER_FRAC of its hit points: onto a dry square next to us if there is one, else the
        wand of polymorph at ourselves now (a fresh HP pool; 1 form in 3 is water-safe -- otherwise the drowning comes
        a turn earlier than it would);
      * a hurt form, or our own form, on the dry strip between the channels (rows 0/16): the wand again there (own form:
        Elbereth first -- the sea monsters in row 1 respect it); the crossing then goes on in the new form."""
    def f():
        castle = dive.castle
        agent = dive.agent
        if not (jf_config.CP_POLY and jf_config.CP_WATER) or not on_castle(castle) or castle._pos()[0] >= 57:
            yield False
            return
        from . import castle_cross
        form = castle_cross.form_permonst(agent)
        bl = agent.blstats
        low = form is not None and bl.hitpoints < jf_config.CP_WATER_FRAC * bl.max_hitpoints
        t = castle._tries
        action = None
        if _on_water(castle):
            if form is None or not low:
                yield False
                return
            dry = [(castle._pos()[0] + dx, castle._pos()[1] + dy) for dx, dy in DIRS8]
            dry = [n for n in dry if _dry_land(castle, n) and not castle._monster_at(*n)]
            if dry:
                action = ('land', min(dry, key=lambda n: (n[1] not in (0, 16), n[0] < 0)))
            elif can_rezap(castle) is not None and int(bl.carrying_capacity) < 4:
                action = ('zap', 'emergency over water')
        elif _outside_land(castle) and can_rezap(castle) is not None and int(bl.carrying_capacity) < 4:
            if form is None and bl.hitpoints >= jf_config.CP_ZAP_MIN_HP:
                action = ('zap', 'own form on the strip')
            elif low:
                action = ('zap', 'hurt form on the strip')
        if action is None:
            yield False
            return
        yield True
        if action[0] == 'land':
            _log(agent, f'form {form.mname} at {bl.hitpoints}/{bl.max_hitpoints} over the water at {castle._pos()}: '
                        f'onto the land at {action[1]}')
            castle._set_state(f'cp: a hurt form onto the land at {action[1]}')
            castle._step_to(*action[1])
            return
        if form is None:
            engraving = (agent.inventory.engraving_below_me or '').lower()
            key = ('cp_strip_elb', tuple(int(v) for v in castle._pos()))
            if engraving != 'elbereth' and agent.can_engrave() and not agent.character.prop.blind and \
                    t.get(key, 0) < 2:
                t[key] = t.get(key, 0) + 1
                castle._set_state('cp: Elbereth on the strip before the self-zap')
                agent.engrave('Elbereth')
                return
        t['cp_water_zaps'] = t.get('cp_water_zaps', 0) + 1
        _zap(castle, can_rezap(castle), action[1])

    return Strategy(f)


def door_step(passage, pos, form):
    """castle_power.door_step under CP_POLY: True: acted this step, None: the old rule decides."""
    from . import castle_power
    if jf_config.LIFT_PLUNGE and pos == DOOR and castle_power.flies(form):
        # a flyer 'floats over' the trap door, but LIFT_PLUNGE's '>' on it plunges a flyer through (do.c dodown on a
        # trap door we have seen: TOOKPLUNGE) -- the old rule waited in the doorway for the form to end
        passage._set_state(f'cp: a {form.mname} steps onto the trap door')
        passage._step_to(*TRAPDOOR)
        return True
    if not jf_config.CP_DOOR_REZAP or passage._door_open() or pos in (DOOR, TRAPDOOR):
        return None
    if castle_power.can_kick(form) or any(passage._usable_wand(i, n) for i in passage._items()
                                          for n in ('striking', 'digging', 'opening')):
        return None
    wand = can_rezap(passage)
    t = passage._tries
    if wand is None or t.get('cp_door_zaps', 0) >= 4 or pos != SAFE_EAST:
        return None   # (castle_power.door_step walks us to SAFE_EAST first)
    if passage._fight_adjacent():
        return True
    t['cp_door_zaps'] = t.get('cp_door_zaps', 0) + 1
    _zap(passage, wand, f'the {form.mname} form can not kick the back door')
    return True
