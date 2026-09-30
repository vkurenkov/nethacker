# jawfish s25: a dig-diving Valkyrie (val-dwa-law-fem)

This bot is a fork of AutoAscend, by way of DT6A's nethacker. It also takes ideas from daglar-dragomirov and
nethack_astra. All behaviour switches are in `autoascend/jf_config.py`, and the dive's settings are at the top of
`autoascend/dive_logic.py`. Each switch has a comment saying what it does, why, and what it measured. s24's README
covered the plan of a game and why most games stop at Dlvl 29. This file repeats the essentials and adds what we
learned since.

## What changed since s24, and the evidence

s25 is s24 plus 13 fixes. Most of them came from reviewing, one by one, how s24's games died before the Castle. The
two sets of fresh pinned seeds below were never used to design anything. Paired against s24 on the same 450 games:

| | s25 | s24 |
|---|---|---|
| mean progress | +0.019 (paired t 2.41) | |
| deaths by Dlvl 12 | 127 | 146 |
| Castle arrivals | 182 | 173 |
| Castle crossings started / reached the Valley | 17 / 4 | 12 / 0 |
| games past Dlvl 29 | 7 | 6 |

s25 had 0 bot failures. The extra passes are two real Castle crossings (Castle on Dlvl 29, then the trap door into
the Valley on Dlvl 30).

- **Prayers:**
  - `LOWHP_CRIT_XL`: an "HP < 12" prayer at 10 of 58 HP is not low-HP trouble in pray.c, so it heals nothing and
    wastes the prayer. The bot now prays only when pray.c agrees.
  - `TOUR_FAINT_LONG_*`: a long fainting spell prays from a 1200-turn gap instead of waiting for 1600.
- **Stuck dives on Dlvl 2-4** (`STALL_SESSILE`, `STALL_DOWNSEARCH_TURNS`): the bot clears a mold sitting on the
  stairs, and searches for the way down when there seems to be none.
- **Known items** (`KNOWN_ITEMS`): 77 of 171 deaths held a KNOWN teleport scroll, healing potion, or wand of striking
  or sleep that nothing used. The bot now uses them before gambling on unknown items. It never reads a teleport scroll
  on a no-teleport level, and never zaps from its own Elbereth square (see below).
- **Welded cursed weapons** (`WELD_PRAY`, `WELD_HOLD`): an unknown-BUC mattock is two-handed. Once welded, the hero
  has no free hand for Elbereth, and 7 of 10 such games died by Dlvl 20. The bot now prays, or holds until a prayer
  is safe.
- **Shops** (`SHOP_DIG`): the dig-dive sometimes falls into a shop with its pick-axe and sat there for thousands of
  turns. It now digs out after 300 turns if it owes nothing.
- **Medusa's level** (`DEEP_ITEMS`, `DEEP_BLIND_LOOK`). Medusa-3 harness, flag off → on:
  - charging an empty wand of digging: 18 → 34 of 49 passes;
  - blowing an unknown horn that turns out to be frost (it freezes the moat): 21 → 33 of 49;
  - a tooled horn (the ravens flee): 51 → 68 of 127.
  - A blind `:` costs a full turn in 3.6.6, so the bot no longer looks at the floor while blind.
- **At the Castle** (`CL_POTION_EARLY`, `CL_ROUTE`): lift candidates are tried at once, and the hero floats straight
  to a far channel entry. On 45 real lift kits × 10 level variants, passes rose from 28 to 36-37 of 450.

## Why nearly every game stops at or below 0.647 (Dlvl 29)

- The Castle (Dlvl 25-29) is the bottom level of the Dungeons of Doom, so `Can_dig_down` is false there.
- The level is no-teleport, its walls cannot be dug, and a moat surrounds it.
- The Valley below is reached only through the 5 trap doors inside the Castle, or by a level teleport into Gehennom.
- In 20% of games the Castle is on Dlvl 29, and only there does reaching the Valley (Dlvl 30) score higher.
- XL 17 would also score above 0.647, but it needs 640,000 experience points.

## What gets past it

We measured this by starting a harness hero at the Castle with its REAL kit. Items keep their true identification
state. An earlier harness bug identified BUC-known items and made lifts look 2-4× better than they are.

| Carried at the Castle | P(pass) | How |
|---|---|---|
| wand of wishing | ~1.0 (20/20) | Wish for charging, a ring of teleport control and 2 cursed scrolls of teleportation, then level-teleport: a level below the Castle lands you in the Valley, and a second read reaches Dlvl ~45-50. |
| unidentified ring of levitation, Castle on Dlvl 29 | 0.175 | Float round the moat to the back door (56,08); the trap door (55,08) is behind it. |
| potion of levitation, Castle on Dlvl 29 | 0.06 | Same route. |
| cold wand or frost horn / magical breathing amulet | ~0.01 / 0 of 40 | |
| XL 12-14, AC -10, Excalibur, no helper items | 0 of 40 | The front door. |

Every real-seed pass except the two Castle crossings came from a wand of wishing found early.

## Castle facts that decide a crossing

- **Timing.** Crossings that reach the moat within 30 turns of landing pass 55/167. After 60 turns it is 10/116.
  Throne-room xorns walk through the walls and reach the west channels' tower walls after about 30 turns. Once
  timing is accounted for, HP at the moat entry hardly matters.
- **Sharks.** Each channel's shark homes on the hero and waits at the entry square, and the channels are one square
  wide. The two east sharks swim west along the moat's north and south rows and meet early crossers mid-strip.
- **Levitation.** An uncursed potion of levitation cannot be ended early. Only a blessed one lets `>` bring you
  down. A floating hero does not fall through a trap door and cannot kick a door. A web cancels levitation while it
  holds you.
- **Testing unknown potions** on the landing: hallucination, sleep and blindness from the tests killed nearly every
  game they hit.
- **Minotaurs.** A west-maze minotaur appears in about half of all Castles and usually strikes within 2-9 turns. In
  the dark maze it is first seen 2 squares away.
- **The wand of wishing.** It sits in a chest in one of the four corner towers. The towers connect only through the
  throne room's locked doors (32,04)/(32,12).

## READINESS: measuring preparation when passes are rare

Real passes are about 1-2 per 100 games. We score each game by the state it reaches instead: R = 1 - (1 -
P_anywhere) × (1 - P_reach × P_castle). P_anywhere covers the wish and teleport-control routes. P_castle uses the
per-kit rates above. P_reach is the chance of reaching the Castle alive. The mean over games is the expected number of
passes per game. On it, s24 was about 2× s23, and s25 matches s24: its gains are more arrivals and better Castle
play, which fixed weights don't show.

## Mechanics that cost us time (NetHack 3.6.6 / NLE)

- **Moon phase:** NLE fixes it from the seed (`fix_moon_phase=True`), not the clock.
- **Elbereth:**
  - Hitting an Elbereth-respecting monster while standing on Elbereth costs 5 alignment and erases the engraving
    (mon.c setmangry).
  - Elbereth does not work in Gehennom.
  - Blinded monsters ignore it. A cobra's spit that misses you can blind the monster next to you.
- **Scare monster scroll:** onscary checks it BEFORE the Elbereth exceptions, so it also scares minotaurs and @
  soldiers, and it works in Gehennom. A scroll that has already been picked up once turns to dust when picked up again.
- **Eyewear:** any worn eyewear (lenses included) stops a raven's blinding claw and a cobra's blinding spit.
- **Teleport control and confusion:** a level teleport is random unless rnl(5) == 0. Known-cursed scrolls avoid that.
- **Shop prices:**
  - Sell offers are base/2, or 3/8 of base for 1 shopkeeper in 4 when the item is unidentified.
  - Buy prices carry a 4/3 surcharge on 1 object in 4.
  - Potions at 200 zm are enlightenment, full healing, levitation, polymorph or speed, all safe to drink.
- **Public seeds:** 15 is few. A program tuned on them scores well above its level on fresh seeds. Judge changes by
  paired runs on fresh seeds.
