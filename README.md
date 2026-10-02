# jawfish s26: a dig-diving Valkyrie that prepares for the Castle (val-dwa-law-fem)

This bot is a fork of AutoAscend, by way of DT6A's nethacker, and takes ideas from daglar-dragomirov and nethack_astra.
Every behaviour switch is in `autoascend/jf_config.py`, with a comment saying what it does, why, and what it measured.
s25's README describes the plan of a game: grind to XL 7 on the first levels and in the Gnomish Mines, then dig straight
down to the Castle. This file covers what changed since then.

## Why the Castle

A game scores its deepest level. The Castle (Dlvl 25-29, the bottom of the Dungeons of Doom) caps nearly every bot near
0.647: it cannot be dug through, teleported across or walked around. Its moat, drawbridge, garrison and throne-room court
stop a weak hero. Getting past it needs a ROUTE ITEM:
- a tonal instrument to learn the drawbridge tune by Mastermind, then crush the garrison under the bridge;
- a lasting lift to float to the east back door and its trap doors;
- polymorph control plus a source (a xorn walks through the walls);
- teleport control plus cursed teleport scrolls;
- the Castle's own wand of wishing.

We stopped optimising mean depth directly and optimised READINESS instead: the expected number of Castle passes per game,
measured on real Castle arrival kits replayed in a harness.

## What changed since s25 (all measured, paired, on fresh pinned seeds)

- **Landing**:
  - recognise the Castle at once, route through the west maze to the drawbridge with a replanned maze route, and do not
    stop to rest in the maze;
  - on real arrival kits carrying an instrument, the drawbridge square is reached 54% of the time instead of 25%.
- **Medusa-3**: on the raven island the bot no longer digs into the water. It climbs the up stairs, rests and re-enters
  the hole it dug; a re-entry skips Medusa's level 1 time in 4. Harness, untouched seeds: 65% vs 41% get past Medusa-3.
- **Armour**:
  - wear the armour already carried (`ARMOR_UP`);
  - mattock diggers put their shield back on at the Castle (`MATTOCK_SHIELD`);
  - special pieces such as speed boots and a shield of reflection are valued above their AC (`ARMOR_VALUE`).
  - A forced AC -4 doubles the Castle pass rate of instrument kits in the harness (causal test), so AC matters most at the
    Castle.
- **The Castle's wand of wishing**:
  - a hand-off bug let the bot carry it unzapped for 610 turns;
  - the bot's inventory model could stop at a carried bag after another strategy took over mid-update (`INV_FULL_LIST`).
  - Fixed, that game reaches Dlvl 48.
- **Interrupted actions** (a strategy switch in the middle of a multi-step action skipped its bookkeeping):
  - the lamp-rub loop on an emptied lamp;
  - shop walks counted as failures;
  - a scare-scroll drop note;
  - a ring put on at the moat.
- **Safety**:
  - never answer yes to "Really attack" a shopkeeper, priest or watchman;
  - no shop-shelf walks while blind or hallucinating;
  - an Elbereth rest lasts while the scared pack is still in view.
- **Wishes**: a single wish (lamp, throne) now asks for a tooled horn unless a polymorph source or a teleport-control ring
  is known.
- Smaller route fixes:
  - a levitating hero over the east trap door is let fall into the Valley;
  - the Castle is recognised from a dig that only makes a pit;
  - a polymorph route resumes when a wand is named later.

## Evidence

270 fresh pinned games (seeds never used for design), paired against cand-k's behaviour (the base; s25's own numbers are
within noise of it):

| | s26 | base |
|---|---|---|
| mean progress | 0.4065 | 0.3944 (+0.012) |
| Castle arrivals | 141 | 117 |
| deaths on Medusa's level | 32 | 54 |
| games past Dlvl 29 | 7 | 1 |
| readiness (expected passes per game, model v1.4) | 0.0053 | 0.0020 (t 3.25) |
| new exception types | none | |

Five of the seven passes are found wands of wishing (luck, not readiness). The readiness gain is mostly the landing and
Medusa work. About a third of it is a lucky draw of tooled horns in this sample, so read the real effect as about 2x the
base.

## What limits it

The drawbridge route needs an instrument, and only about 11% of Castle arrivals carry one. Instruments lie on a level the
bot visits before its dive in only 17% of games, and gold limits shop purchases. In the harness, hero strength converts at
the Castle and tactics against single monsters do not, because another killer takes the place of the one removed:
- max HP x1.5 gives x2.5;
- AC -4 gives x2;
- speed boots give x1.7.
