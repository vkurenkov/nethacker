# jawfish s28: a stronger dig-diving Valkyrie (val-dwa-law-fem)

This bot is a fork of AutoAscend, by way of DT6A's nethacker, and takes ideas from daglar-dragomirov and nethack_astra.
Every behaviour switch is in `autoascend/jf_config.py`, with a comment saying what it does, why, and what it measured.
s25-s27's READMEs describe the plan of a game: grind on the first levels and in the Gnomish Mines, dig straight down
to the Castle, then cross it with whatever route item the hero carries. This file covers what changed since s27.

## What changed since s27

- **A longer, safer grind before the dive** (`GRIND_XL=8`, `SAFE_GRIND`):
  - the hero now grinds to experience level 8 instead of 7 before digging down;
  - the extra grind ends early, and the dive begins, when:
    - the hero is Hungry and carries little food;
    - the tour turns toward Sokoban (the most dangerous trip of the early game);
    - or 10,000 extra turns have passed;
  - no fountain dips during the extra grind.
  - Why: a stronger hero (more HP, better AC) survives the dive and the Castle better. A plain grind to level 9 killed
    14% of games before the dive; with the stop rules and level 8 the grind costs about as many games as it saves.
- **Castle fixes**:
  - a hero inside the Castle no longer puts a levitation ring back on, which made the chest unreachable and the wand's
    tower look empty (`CFP_INSIDE_OFF`);
  - a cursed, welded weapon at the chest is prayed off instead of giving up on the tower (`INNER_WELD_PRAY`);
  - removing an uncursed ring is no longer mistaken for a cursed one (`RING_REMOVE_FIX`);
  - a levitating hero no longer stalls pushing boulders (`INNER_BOULDER_LEV`);
  - a floating hero digs through the locked back door instead of landing to kick it and waking the eels
    (`LIFT_DOOR_DIG`).
- **Robustness**:
  - the Excalibur errand no longer loops on a staircase it cannot reach (`EXCAL_PATH_GUARD`);
  - a non-UTF-8 byte in a game message or item name no longer raises an error (`DECODE_REPLACE`).

## Evidence

540 fresh pinned games per tree, on two reserved seed blocks never used for design, paired:

| | s28 | s27 |
|---|---|---|
| mean progress | 0.4058 | 0.4055 |
| games reaching Dlvl 30 or deeper | 20 | 19 |
| games with a wand-of-wishing wish | 18 | 15 |
| Castle arrivals | 282 | 287 |
| readiness (expected Castle passes per game, model v1.4.1) | 0.0102 | 0.0075 |
| new exception types | none | |

- Readiness gain: +37%, paired t 1.29. It is not statistically significant.
- Progress is level with s27.
- Hero at the Castle (s28 vs s27):
  - experience level 7.8 vs 7.5;
  - max HP 82 vs 79;
  - experience level 8 or more in 57% of games vs 42%.

## What limits it

- The Castle can only be crossed with a route item: a tonal instrument (about 5% of arrivals truly carry one), a
  lasting lift, or the right wand. A stronger hero converts these routes much better but cannot create one.
- Every game that gets a wand of wishing passes the Castle; most other games cannot.
- Games take about 1.2x as many steps as s27's.
