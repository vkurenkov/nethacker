# jawfish s24: a dig-diving Valkyrie (val-dwa-law-fem)

This bot is a fork of AutoAscend, by way of DT6A's nethacker. It also takes ideas from daglar-dragomirov and
nethack_astra. All behaviour switches are in `autoascend/jf_config.py`, and the dive's settings are at the top of
`autoascend/dive_logic.py`. Each switch has a comment that says what it does, why, and what it measured. This file
covers the parts that are hard to see from the code.

## Plan of a game

1. Level up on Dlvl 1-4 to XL 7. A Valkyrie becomes intrinsically fast at XL 7. Leaving the grind at XL 6 cost
   -0.084 on 90 fresh games, because the Gnomish Mines trip that follows is deadly without speed.
2. Take a pick-axe from a Mines dwarf, then dig-dive. The bot digs straight down every level, rests on Elbereth,
   and spaces its hunger prayers to respect the prayer timeout.
3. Get past Medusa's level (digging down, or lift items), then dig down to the Castle (Dlvl 25-29).
4. At the Castle, try whatever crossing the carried items allow (next section).

## Why nearly every game stops at or below 0.647 (Dlvl 29)

The Castle is the bottom level of the Dungeons of Doom, so `Can_dig_down` is false there. The level is no-teleport,
and its walls cannot be dug. The Valley below it is reached only through the Castle's trap doors or by a level
teleport into Gehennom. The Castle is at Dlvl 29 in only 20% of games, so 0.647 is the usual ceiling.

What gets past it, measured by starting a harness hero at the Castle with the item (P(pass)):

| Carried at the Castle | P(pass) | How |
|---|---|---|
| wand of wishing | 0.95 | Wish for 2 blessed scrolls of charging, then a ring of teleport control, then "2 cursed scrolls of teleportation". A cursed (or confused) read is a level teleport. With control, a level below the Castle sends you to the Valley (`find_hell`), and a second read in Gehennom reaches Dlvl ~45-50. |
| teleport control + 2 known-cursed teleport scrolls | 0.90 | Same route, from any level. |
| polymorph control + a polymorph source | 0.48 | Become a xorn. Walk through the Castle's walls (castle.des has no NON_PASSWALL) to a trap door, which drops you into the Valley. Phase through the Valley's rock to its down stairs, then dig down in Gehennom. |
| a known lasting lift (levitation ring, water walking boots), Castle at Dlvl 29 | 0.46 | Float round the moat to the back door at (56,08) and drop through the trap door behind it into the Valley, which is Dlvl 30. With the Castle at Dlvl 25-28 the Valley is Dlvl 26-29, still at or under 0.647, and our bot cannot walk out of it alive. |
| XL 12-14, AC -10, HP 150, Excalibur, no helper items | 0 of 40 | The front door. Opening the drawbridge works; holding the doorway against ~50 soldiers, xorns that walk through walls, and dragons does not. |
| the same + 3 identified scare monster scrolls, speed boots, magic resistance | 0.33 | The front door, holding squares covered by scare monster scrolls. |

Our bot's real Castle arrivals are XL 6-10, about 84 max HP, and AC around +1. **Passes are gated by items, not by
strength.** On unselected fresh seeds, every pass so far came from a wand of wishing found early.

## READINESS: measuring preparation when passes are rare

Real passes are too rare for an A/B test to detect: about 3 per 270 fresh games. We score each game by the state
it reaches instead. The value is R = 1 - (1 - P_anywhere) x (1 - P_reach x P_castle), where:

- P_anywhere comes from the routes that work from any level (the first two rows above).
- P_castle comes from the Castle routes.
- P_reach is the chance of reaching the Castle alive from that state, taken from baseline runs. AC at Medusa adds
  about 0.029 per point below 0.

The mean over games is the expected number of passes per game. It is compared on the same fresh seeds between two
bots. s24 roughly doubles s23 on it (0.0033 vs 0.0015 per game, paired t 3.1 over 270 fresh games). s24 also
reaches Castle depth 13% more often and scores +0.020 in progress.

Strength-first preparation was READINESS-neutral and cost progress. Earlier Excalibur cost 0.04-0.06, and an
XP-farming middle game on Dlvl 5-12 cost 0.07. At XL 7-8 and AC 0, the bot cannot farm those levels safely.

## Mechanics that cost us time (NetHack 3.6.6 / NLE)

- NLE fixes the moon phase from the seed (`fix_moon_phase=True`). Full moon, new moon and Friday the 13th come
  from the seed, not the wall clock.
- Hitting an Elbereth-respecting monster while standing on Elbereth costs 5 alignment and erases the engraving
  (`mon.c setmangry`, "You feel like a hypocrite"). This also makes the next prayer riskier.
- With teleport control and confusion, a level teleport becomes random unless `rnl(5)` is 0 ("Oops...").
  Known-cursed scrolls avoid that.
- Cursed gloves or a welded weapon block putting on a ring without using a move. A retry loop there never
  advances the game.
- A box whose lock was forced or kicked open is named "broken chest".
- The 15 public seeds are few. A program tuned on them scores well above its level on fresh seeds (s23: 0.526
  public vs ~0.37 fresh). Judge changes by paired runs on fresh seeds.
