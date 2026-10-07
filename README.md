# jawfish s27: a dig-diving Valkyrie that prepares for the Castle (val-dwa-law-fem)

This bot is a fork of AutoAscend, by way of DT6A's nethacker, and takes ideas from daglar-dragomirov and nethack_astra.
Every behaviour switch is in `autoascend/jf_config.py`, with a comment saying what it does, why, and what it measured.
s25's and s26's READMEs describe the plan of a game: grind to XL 7 on the first levels and in the Gnomish Mines, dig
straight down to the Castle, then cross it with whatever route item the hero carries. This file covers what changed
since s26.

## What changed since s26 (all measured, paired, on fresh pinned seeds)

- **Castle landing** (the walk from the arrival point to the drawbridge):
  - run past monsters instead of waiting (`LANDING_OUTRUN`);
  - treat a covetous lich differently (`LANDING_LICH`);
  - play a magic flute, magic harp or frost/fire horn at a minotaur (`LANDING_MAGIC`);
  - blow a bugle on the west side (`CL_BUGLE_WEST`);
  - blow the horn again when a scared minotaur comes back (`HORN_REBLOW`).
  - On real arrival kits the drawbridge square is reached 20-25% more often, and minotaur deaths with a bugle fall from 55% to 30%.
- **Excalibur**: dip the long sword at fountains the hero already knows before the dive (`PREP_EXCAL_DIVE`, `EXCAL_PACKAGE`).
  - About half of the Castle arrivals hold Excalibur, against 13% in s26.
  - On the Castle's crusher route it roughly doubles the pass rate of an instrument kit (x1.85, measured on this tree).
- **Medusa's level**:
  - the re-entry trick is allowed more climbs;
  - on Medusa-3 the hero uses a known hole instead of digging a fresh one under attack (`MEDC_ABOVE_GO`);
  - a hero with a pick saves its digging wand, whose zaps flood the island (`MEDC_M3_WAND_LAST`).
  - Medusa-3 passes rise about 11 points. Deaths on Medusa's level, over 540 games, fall from 63 (s26) to 45.
- **Defect fixes**:
  - the Castle crusher no longer walks into the moat on a stale bridge state, and no longer stalls on a refused push;
  - a levitating hero is no longer stuck above the stairs;
  - a hero levitating on a lasting lift eats when hungry;
  - a sleeping barracks is left asleep;
  - the inventory model no longer allows impossible squeezes when the hero carries a bag;
  - two parser crashes are guarded.

## Evidence

540 fresh pinned games per tree, on two reserved seed blocks never used for design:

| | s27 | s26 | base (cand-k) |
|---|---|---|---|
| mean progress | 0.4055 | 0.4043 | 0.3850 |
| Castle arrivals | 282 | 270 | 217 |
| deaths on Medusa's level | 45 | 63 | 102 |
| readiness (expected Castle passes per game, model v1.4) | 0.0070 | 0.0056 | 0.0018 |
| new exception types | none | | |

Readiness counts a pass only when the hero reaches Dlvl 30. The gain over s26 is about +24%, and it is not yet
statistically significant (paired t 0.99).

## What limits it

The bot rarely gets past the Castle:
- the drawbridge route needs a tonal instrument, carried by only 14% of arrivals;
- 19% of Castles hold a lich whose spells end the crusher route;
- when the Castle is on Dlvl 25-28, a hero who drops through its trap doors lands in the Valley of the Dead. The Valley
  floor cannot be dug, so the hero must walk across it to the stairs, or level-teleport out.
