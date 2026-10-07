# How jawfish plays: a map of the code

jawfish plays NetHack 3.6.6 (NLE) as a dwarvish Valkyrie (val-dwa-law-fem). It is a fork of AutoAscend, by way of
DT6A's nethacker. A game scores the best milestone it reaches, and dying costs nothing. Depth dominates: Dlvl 12 is
worth 0.21, Dlvl 20 0.38 and Dlvl 29 0.647. So the bot levels up only to XL 7, takes a pick-axe from a Gnomish Mines
dwarf, and digs straight down to the Castle. The release README has the results, the Castle facts and the READINESS
metric. This file shows where each phase lives in the code, how the switches work, and which game rules the plan
rests on. Paths are relative to `autoascend/`.

## Control flow

`bot.py` hands each observation to `arena_adapter.AutoAscendDriver`, which runs `agent.Agent.main()` in its own
thread. `main()` runs `global_logic.GlobalLogic.global_strategy()`: the plan (`current_strategy()`) inside a chain of
`.preempt()` layers. Each layer can interrupt the plan and every layer listed before it, so the last one in the file
has the highest priority. From the bottom up, the chain holds the dwarf hunt, eating, `fight2`, `dig_first`, the
Elbereth rest, the Valley and Castle strategies, the teleport routes, the emergency layer (prayer, then the last
resort), `KNOWN_ITEMS`, the minotaur guard, and finally the Castle trap-door plunge. The plan is AutoAscend's
levelling tour until `DiveLogic.should_dive()`, then `DiveLogic.strategy()`. That is a restartable loop of short
tasks (`plan_step`), so every decision is re-derived from the game state.

## The phases

1. **Grind** (`global_logic.py`: `tour_strategy`, `_grind_level`; `agent.py`: eating, prayer). Explore and fight on
   Dlvl 1, then on Dlvl 3 at XL 5-6 and Dlvl 2 at XL 7, where random monsters stay at difficulty 4 or less. Eat
   corpses, buy food, and space the hunger prayers. Switches: `GRIND_LEVELS`, `WEAK_PRAYER_GAP`,
   `TOUR_FAINT_LONG_TURNS`, `LOWHP_CRIT_XL`, `BUY_FOOD`.
2. **Dive trigger** (`dive_logic.py`: `should_dive`). XL 7, when a Valkyrie becomes intrinsically fast. With a
   digging tool already in hand, the bot also waits until 800 turns have passed since its last prayer, so the
   emergency prayer is ready on the way down. A failed prayer starts a rescue dive down the main stairs. Switches:
   `DIVE_XL`, `DIG_DIVE_XL`, `DIVE_PRAYER_GAP`, `RESCUE_DIVE`, `LATE_RESCUE`.
3. **Pick-axe** (`dive_logic.py`: `hunt_strategy` and the Mines route in `plan_step`). Kill peaceful dwarves for a
   pick-axe or mattock. The grind already hunts them from XL 5. Without a tool, the dive goes down the Gnomish Mines
   and camps on Mines levels 1-4 (up to 8000 turns) until one turns up. Switches: `MINES_ROUTE`, `HUNT_V2` (master
   switch of the hunt), `DWARF_HUNT`, `MINES_CAMP`, `HOME_DIGGER_TURNS`, `GRIND_HUNT_XL`, `EARLY_DETOUR`.
4. **Dig-dive** (`dive_logic.py`: `try_dig_down`, `dig_first`, `elbereth_rest`, `retreat_upstairs`, `weld_hold`,
   `_shop_dig`). Back in the Dungeons of Doom, dig one hole per level, and engrave Elbereth first when hostiles are
   near. Finishing the hole ends most fights (`dig_first` preempts `fight2`). The bot rests only below 60% HP, on
   Elbereth. A wand that lies on the landing square or a few steps away is taken at a calm moment
   (`DIVE_WAND_PICKUP`; engraving with a wand of wishing makes the wish). Switches: `SHELTERED_DIG`, `DIG_ESCAPE`,
   `DIVE_REST`, `CURSED_PICK_OK`, `WAND_FIRST`, `WAND_RESERVE`, `WELD_PRAY`, `WELD_HOLD`, `SHOP_DIG`, `HUNGER_DEEP`,
   `DIVE_WAND_PICKUP`.
   **Excalibur** (`dive_logic.py`: `prep_fountain_dip`, `excal_errand_step`; `EXCAL_PACKAGE`): a lawful hero of XL 5+ who dips her single
   long sword into a fountain gets Excalibur 1 dip in 6 (`fountain.c`), and Excalibur triples the instrument kits' crusher walk-in. The
   dive dips at every fountain within 30 steps (`PREP_EXCAL_DIVE`; HP 70%); a hero holding a tonal instrument also walks, at the dive
   start and by the known stairs, to the fountains of Dlvl 1-6 (`EXCAL_ERRAND*`; XL 7, HP 90%, prayer safe: a released water demon,
   a snake stream or a nymph is survivable only then). Switches: `PREP_EXCAL_DIVE`, `EXCAL_ERRAND`, `EXCAL_ERRAND_INSTR`,
   `EXCAL_ERRAND_FIGHT`, `EXCAL_CALM_FIX`, `EXCAL_WAIT_FIX`, `EXCAL_STEADY`, `EXCAL_DAGGER`, `EXCAL_DEEP_DIST`.
5. **When a fight goes wrong** (`agent.py`: `emergency_strategy`; `known_items.py`; `mino_guard.py`; `opp_items.py`).
   The order is: a prayer if it is safe; then a known escape item (a teleport scroll, a teleport or digging wand, a
   healing potion, a sleep or striking wand); then a last-resort gamble on unknown wands, potions and scrolls. A
   minotaur gets its own plan. Switches: `KNOWN_ITEMS`, `MINO_GUARD`, `LAST_RESORT`, `GENOCIDE_POLICY`, `HORN_SCARE`.
6. **Medusa's level** (Dlvl 21-28; `dive_logic.py`: the `MEDUSA_*` settings, `deep_items_strategy`;
   `medusa_maps.py`, `medusa_hop.py`). The bot recognises it by its water, and the arrival islands are small. It digs
   from the square with the fewest water neighbours. With a known cold wand, it freezes those neighbours first. With a
   known ring of levitation, it floats to dry land. On Medusa-4's wet islets it steps into a 1-wide moat channel: a
   hero who can't swim crawls out of the water onto a random square next to it (`trap.c drown`), possibly across the
   channel, onto land with a square no moat touches (`MEDUSA_HOP`). While blinded, it holds on Elbereth. Medusa-3
   stays near 40%: a pick-axe hole beside k moat squares floods with 1 - 1/(k+1)^2, and a raven's claw blinds a hero
   in the windows with no Elbereth under him (just after a pit, a flood, or a dust typo: 28% of writes). The harness
   found no significant gain in `MEDUSA_DIG_ORDER`, `MEDUSA_HOP_RESERVE` or `MEDUSA_LAZY_ELB`. Switches:
   `MEDUSA_MAP`, `MEDUSA_FREEZE`, `MEDUSA_LIFT`, `MEDUSA_BLIND_HOLD`, `MEDUSA_HOP`, `COLD_RESERVE`, `DEEP_ITEMS`,
   `DEEP_BLIND_LOOK`, `MEDUSA_NO_RETREAT`.
   Medusa-3's island has a cycle (`medusa_reentry.py`, `MEDUSA_STANDOFF` + `MEDUSA_REENTRY`): hold an Elbereth until a
   window, walk to the '<', climb, rest, and step into the hole dug above: `trap.c fall_through` drops one level further
   one time in four on every entry into a KNOWN hole (a fresh `dighole` always falls exactly one level), so each entry is
   a 1-in-4 skip of her level and otherwise a new random landing on the 18-square island. Census of 616 real dev-seed
   Medusa games (dev/medc2): Medusa-1/2 pass 95%, Medusa-4 85% (13 of 17 harness failures on the south-east islet),
   Medusa-3 75% -- 18 of its 40 deaths on the level above, where the layer used to yield to the fight / dig layers when
   a hostile stood within 3 squares and the dive dug a fresh hole there (no skip chance, 8 exposed turns); and a hero
   with a known wand of digging zapped it at the island (every zap floods 50-75%) instead of cycling. Switches
   `MEDC_ABOVE_GO` (step into the known hole at once) and `MEDC_M3_WAND_LAST` (cycle first, wand last), harness +9 and
   +13 points (real full games, 54 paired Medusa-3 seeds: passes 42 against 35, Castle arrivals 37 against 31); see
   their jf_config blocks. Harness (`dev/medc2`, 610 real arrival kits): Medusa-3 landings below 60% HP
   die 14-75% of the time against 1.4-2.9% at 80%+, and a blind landing doubles the death rate. Measured and dropped
   (null on held-out secrets): holding the Elbereth longer when the '<' is unknown, `MEDB_M3_LOOK`, lane 11's five
   Medusa-4 knobs, `MEDUSA_REENTRY_M4`, an uncapped layer loop (the layer's body ends after 400 actions and the layers
   below get one run: `dig_first` can walk her off the Elbereth; 27% of long games hit it, the passes do not move),
   and `MEDC_REACH_WALK` (kept OFF: a relaxed '<' reachability test, +3 of 94 specs, not significant). On the island
   "You feel like a hypocrite" (-5 alignment, the engraving erased) is mostly a non-flying monster falling into a pit
   the hero dug (`trap.c mintrap`: `madeby_u`), not her swing; a harness hero starts at alignment 0, so Excalibur
   can blast her (`artifact.c touch_artifact`) after a few: real heroes arrive with a record near the cap.
7. **The mazes below Medusa** (`dive_logic.py`: `below_medusa`; `mino_guard.py`). They hold minotaurs, which ignore
   Elbereth. A saved wand of digging is zapped on arrival: one turn instead of about six with the pick. A landing at
   the west edge first listens for the Castle's door sounds. Switches: `WAND_RESERVE`, `WAND_CASTLE_WAIT`,
   `MINO_GUARD`.
8. **The Castle** (Dlvl 25-29; `castle_cross.py`, `castle_logic.py` (`CastlePassage`), `castle_power.py`,
   `castle_treasury.py`). No hole can be dug here. The bot puts on any possible lasting lift at once and drinks
   possible levitation potions on the landing. Then it floats (or, with magical breathing, wades) round the moat to
   the back door (56,08), and drops through the trap door behind it into the Valley. As a xorn, it walks through the
   walls instead. Every unknown ring, potion and amulet gets tried, since dying here costs nothing. The
   `castle_landing.py` and `castle_front.py` plans are switched off. Switches: `CASTLE_PASSAGE`, `CFP_RUSH`,
   `CFP_MB`, `CFP_ZAP`, `CFP_XORN`, `CL_POTION_EARLY`, `CL_ROUTE`, `LIFT_KNOWN_RUSH`, `LIFT_PLUNGE`, `CASTLE_POLY`,
   `POLY_XORN`, `EAST_LATE_DOOR`.
   Once the Crusher has locked the bridge behind the hero, the walk to the wand of wishing is the Crusher's old wand
   leg, or `castle_inner.py` (`CASTLE_INNER`): the throne room, a locked door (32,04)/(32,12) opened with a key, a
   digging wand, a pick-axe or a striking wand (never a kick: it wakes the level), a hallway, a tower door, the chest
   forced with a blade, one zap to name the wand, then `tele_route.py`, while the module holds the chest square (a
   cursed scroll of scare monster lies under the chest). Castle 29 has a second goal, the secret door (38,08) and
   the trap door (40,08). What the hero meets, from a census of 51 real-kit hand-offs: the court has drained west
   along row 08 by then; what is left is 2-3 heavy Elbereth-respecters (trolls, ogres, giants) stuck at the throne
   room's NE corner after objects behind its east wall, about 2 soldiers per hallway (the tower guards, waiting
   behind the locked doors), 2-4 xorns anywhere, and the barracks' soldiers locked in behind (26,05) and (26,11)
   until a giant breaks a door. Awake monsters know where the hero is (`monmove.c:set_apparxy`) and walk straight at
   her, so every turn spent resting or holding brings more of them (at XL 7-10 a rest regenerates 0.2-0.3 HP a
   turn), and a xorn fight costs ~55 HP: the module therefore dashes, and writes an Elbereth the moment a
   wall-walker or a level 8+ respecter arrives next to it. Measured on exactly replayed hand-off states against the
   old leg (three held-out libraries, 199 states): 40 passes (20%, wand in hand 14%) against 59 (30%, wand in hand
   24%), +30 -11, McNemar p 0.004. Resting to 85% HP and holding at the throne-room door, the first form, passed 7 of
   51 real-kit states against 10 for the old leg. Switches: `CASTLE_INNER` (the walk; the values below are its
   measured form), `CASTLE_INNER_GATE`, `CASTLE_INNER_ELB`, `CASTLE_INNER_HOLD`, `CASTLE_INNER_ORDER`, and the
   rejected or neutral `CASTLE_INNER_XORN`, `_SIDE`, `_LOCK`, `_AVOID`, `_CROWD`, `_HORN`, `_EXCAL`, `_ADAPT`.
9. **Wish and teleport-control routes** (`tele_route.py`, `power_route.py`, `power.py`). These work from any level.
   A wand of wishing buys 2 blessed scrolls of charging, a ring of teleport control and 2 cursed scrolls of
   teleportation. Teleport control plus a cursed teleport scroll jumps to the Valley. A second jump from Gehennom
   reaches Dlvl ~45-50 (0.78-0.81). At the Castle, the other plans leave the wand to this route. A throne, a magic
   lamp or a water demon gives ONE wish with no wand behind it (`wish_source.py`, asked through `power.wish_text`).
   `single_wish` then picks the item with the best expected P(pass) for the pack: a ring of polymorph control when the
   pack holds a polymorph source, 2 cursed teleport scrolls when it holds a ring of teleport control, a ring of
   levitation on a Dlvl-29 castle. Harness: 7.8% of lamp wishes pass with this choice, 1.8% with a fixed list. A
   throne is found by the court's sounds (1 wish in 13 thrones, sat on until it vanishes); a lamp is rubbed at a quiet
   moment (a djinni 1 rub in 3; 80% wish when blessed, 20% uncursed).
   The wand route is 7 actions (zap, read the charging scroll, zap, put the ring on, zap, read, read). It can sit
   above the minotaur guard and the emergency layer (`T_ROUTE_TOP`), fire with hostiles in view (`T_ROUTE_FIRE`),
   recharge right after the charging wish (`T_ROUTE_EARLY_CHARGE`), write a dust Elbereth first when something that
   respects it is next to the hero (`ROUTE_ELBERETH`), and refuse a prayer that two or more wishes have made too soon
   (`WISH_PRAYER_HOLD`; `PRAY_BOOKKEEP` keeps the prayer bookkeeping when a layer interrupts the prayer). Found
   items: `T_STACK_BUC` and `T_BLIND_READ` read unknown-BUC teleport scrolls once teleport control is known,
   `T_UNHOLY_PRAY` makes unholy water on a cross-aligned altar for the dip.
   Switches: `WISH_TELEPORT_ROUTE`, `WISH_CHARGING_FIRST`, `WISH_ROUTE_FIRST`, `TC_ROUTE`, `TC_CASTLE_GAMBLE`,
   `LEVELPORT_DEEP`, `T_ROUTE_FIRE`, `T_ROUTE_EARLY_CHARGE`, `T_ROUTE_TOP`, `ROUTE_ELBERETH`, `WISH_PRAYER_HOLD`,
   `PRAY_BOOKKEEP`, `T_STACK_BUC`, `T_BLIND_READ`, `T_UNHOLY_PRAY`, `WISH_SINGLE`, `LAMP_RUB`, `THRONE_SIT`,
   `THRONE_HUNT`.
10. **The Valley and Gehennom** (`valley.py`, `valley_walk.py`; `dive_logic.py`: `valley_step`, `valley_sneak`,
    `valley_retreat`). The Valley's floor can't be dug, and neither Elbereth nor prayer works in Gehennom. The bot
    walks to the Valley's `>`, digging through its locked secret doors, and digs on below. A xorn walks through the
    rock. Switches: `GEHENNOM_DIVE`, `VALLEY_SNEAK`, `VALLEY_RETREAT`, `VALLEY_XORN`, `VALLEY_LOTTERY`.
11. **Shopping** (`supply.py`, `shop_math.py`; hooks in `global_logic.py`, `item/inventory.py` `buy_food`). Before the
    dive, while the pick-axe is off (a shopkeeper bars the door to one), the bot walks through ~1.3 shops a game. It
    buys what the Castle routes need: a tonal instrument (any of the 8 plays the drawbridge tune), a magic lamp (base
    price 50, a wish 31% of the time when rubbed), a wand quoted at base 500 (wishing or death), a named scroll of
    scare monster. `shop_math.py` is `shk.c`'s price arithmetic (charisma, the 1-in-4 surcharge, dunce cap), which
    turns a quote into the object types it can be; a tool's glyph id in the observation names its exact type. When the
    gold falls short it sells the pack items worth least (potions, scrolls, wands, rings, amulets: a shopkeeper pays
    base/2, 3/8 of base from one in four) and buys. In Minetown (Mines 3-4) it visits every shop, and the tool-less
    Mines camp goes there before it hunts on Mines 1-2. A horn outranks the other instruments (it scares the
    castle's minotaurs: the crusher's `HORN_SCARE`), and a second instrument is bought only while the pack holds no
    certain horn. A magic lamp is kept for the wishes lane (`wish_source.py` rubs it). Lamp, wand and scroll finds
    are small: a tonal instrument is on a visited shelf in 5.8% of games, a magic lamp in 3.3%. Switches:
    `SUPPLY_BUY`, `SUPPLY_KEEP`, `SUPPLY_SELL` (on together), `SUPPLY_TOWN`, `SUPPLY_TOWN_FIRST`, `SUPPLY_DOOR`,
    `SUPPLY_WAND500`, `SUPPLY_SCARE_BUY`.

11. **Identification** (`power_route.py`: `_identify_step`, `_dive_id_ready`, the altar test; `id_engine.py`; `price_id.py`;
    `item/inventory.py`: the wand engrave test). Route items only help when the bot knows what they are, and the
    ground truth of 90 games (`dev/truth.py` + `dev/idtruth.py`) said it did not: 1 of 41 rings and none of the amulets
    were known at the Castle, and half the arrivals still held an unread scroll of identify, because nothing ever
    reads an unknown scroll that is not in a stack. The pieces: the identify menu is paged and ranks rings and
    amulets first (`ID_MENU_PAGES`, `ID_PICK_PRIORITY`, `ID_STACK_SKIP`); known identify scrolls are read in the
    grind when a ring, boots, amulet or wand is worth one (`ID_GRIND_READ`); unknown scroll singles are read at quiet
    moments until the identify label is known (`READ_TEST`, needs `EARTH_BOX`); tools are told apart by their
    glyph ids (`TOOL_GLYPH_ID`: NLE does not shuffle tool glyphs, so a magic lamp, a bag of holding or a frost horn is
    exact on sight); every wand is engrave-tested with text from the first test (`ID_WAND_TEXT_GRIND`,
    `DEEP_WAND_TEST`); shopkeeper offers price-test carried scrolls, rings, wands and potions (`ID_SELL`) and identify
    scrolls are bought (`ID_BUY_IDENTIFY`), both through the supply lane's shop code.
    The 20-zm scroll is identify, the 300-zm ring is conflict, polymorph, polymorph control or teleport control
    (`price_id.py`). Measured on 135 paired games: castle rings known 7% -> 41%, tools 33% -> 100%, wands 64% -> 79%;
    readiness flat (a route ring is carried at only ~8% of the arrivals). `ID_SELL` prices mostly potions in real
    games, and a shelf with identify scrolls shows up in about 7% of them.
11. **Shop wands** (`shop_wish.py`, off). A base-500 wand on a shop shelf (a quote that only wishing or death can make) is
    taken unpaid and engrave-tested in the shop, in one strategy body. A wish goes to the wish route (phase 9), which leaves the
    shop by level teleport: a robbery that costs one alignment point and nothing else unless the shopkeeper is adjacent at the
    jump (he follows), so the test square is 3+ squares from him. Death: the wand goes back, the usage fee (quote/4) is paid from
    gold or sold junk, the door opens again. While anything is unpaid `agent.bfs()` closes the shop's door squares. Switches:
    `SHOP_WISH`, `SHOP_WISH_SELL`.

The rest is AutoAscend's: `strategy.py` (the `Strategy` combinators `preempt`, `condition`, `until` and `every`),
`exploration_logic.py`, `combat/` (`fight2`), `item/`, `level.py`, `glyph/`, `monster_tracker/` and `soko_solver/`.
`jf_log.py`, `jf_scenario.py` and `prep_log.py` are dev-only hooks. They do nothing in the arena.

## Switches

- `jf_config.py` holds the behaviour switches as module constants. The code reads them at call time
  (`jf_config.NAME`), and the values in the file are what ships. Dev runs override them with
  `JF_CFG='{"NAME": value}'`, which the arena never sets. The end of the file derives a few more (`LATE_FIXES`
  turns on `HAZARD_FIXES`).
- `dive_logic.py`'s own constants, at the top of the file, are overridden the same way. `HUNT_V2` is a master
  switch: it turns on eight dwarf-hunt switches.
- Every behaviour change comes in behind a switch that is off in the commit that adds it. With the switch off, the
  bot must replay the previous version byte-identically on pinned seeds. A switch is turned on only after it is
  measured: paired games on fresh seeds, or a harness suite for situations too rare to show up there.
- Each comment says what the switch does and why: the games that failed, and the NetHack source that explains them.
  Then it gives the evidence. `ON (train 3.1): ...` names the measurement that turned a switch on. `Not adopted`,
  `REJECTED`, `parked` or `-- off` mark a switch that stays off, with the reason. The block at the top of
  `jf_config.py` explains the notation: seed names (`jf14 s6`), pinned and paired runs, `sNN`, `cand-X`,
  `train N`, harness runs, and ledger ids. The `dev/` tools it names are in our development repository, not in
  this tree.

## Twelve NetHack 3.6.6 facts the plan rests on

We checked each of these in the 3.6.6 source.

1. **Random monsters scale with your XL as well as depth.** `makemon.c:rndmonst` picks a difficulty between
   depth/6 and (depth + XL)/2. The grind chooses its level by XL to keep that cap at 4. An XL-8 digger on Dlvl 27
   meets no random monster above difficulty 17.
2. **A Valkyrie becomes intrinsically fast at XL 7** (`attrib.c`: `val_abil`, granted by `adjabil`). That is
   `DIVE_XL`. Leaving the grind at XL 6 cost 0.084 on 90 fresh games (s24).
3. **Dwarves are peaceful to a dwarf, and 37.5% carry a digging tool.** `makemon.c:peace_minded` makes dwarves and
   gnomes peaceful to a dwarvish hero (the race's love mask in `role.c`). `makemon.c:m_initweap` gives a dwarf a
   pick-axe 1 time in 4 and a mattock 1 in 8. A melee hit angers the target before it does damage
   (`uhitm.c:hmon_hitmon` -> `wakeup` -> `mon.c:setmangry`). So the kill costs alignment (-1, then the dwarf's
   malign of -12) but never the Luck -1 that `mon.c:xkilled` charges, half the time, for killing a monster that is
   still peaceful.
4. **Elbereth guards only the square you stand on, and not against everyone.** In `monmove.c:onscary`, @ (humans
   and elves), minotaurs, shopkeepers, guards, and blind or peaceful monsters ignore it, and it does nothing in
   Gehennom. A scroll of scare monster on the square has none of those exceptions. Attacking a monster that
   respects your Elbereth while standing on it, in melee or with a zap, costs 5 alignment (1d5 when yours is 5 or
   less). It also erases the engraving (`mon.c:setmangry`, "You feel like a hypocrite").
5. **Engraving fails often.** `engrave.c:doengrave` garbles each letter of a dust engraving 1 time in 25. It adds
   1 in 11 when blind, 1 in 7 when confused, 1 in 4 when stunned and 1 in 2 when hallucinating. A dust Elbereth
   comes out wrong 28% of the time, and while hallucinating it comes out whole only 0.3% of the time
   (`ELBERETH_FUTILE`). Per `engrave.c:freehand`, a welded two-hander (or a welded weapon plus a cursed shield)
   leaves no free hand to engrave with (`WELD_HOLD`).
6. **Prayer has narrow conditions.** In `pray.c:can_pray`, major trouble is fixed only when the prayer timeout is
   200 or less, Luck and alignment are not negative, and the god is not angry. A prayer made too soon costs 3 Luck
   and angers the god (`pray.c:prayer_done`), so the prayers after it fail too. A successful prayer resets the
   timeout to `rnz(350)` (`pray.c:pleased`), whose long tail fails ~4% of major-trouble prayers made even 1100
   turns later. Low HP is trouble only at 5 HP or less, or at most max/5 at XL 1-5, max/6 at XL 6-13, and max/7 at
   XL 14-21 (`pray.c:critically_low_hp`). A prayer above that line heals nothing (`LOWHP_CRIT_XL`). At Luck 0 and
   away from an altar, the god fixes the worst trouble, and the other major ones at most half the time
   (`pray.c:pleased`). Weak hunger (`TROUBLE_STARVING`, 9) outranks a welded two-hander
   (`TROUBLE_UNUSEABLE_HANDS`, 2). Every wish adds `rn1(100, 50)` to the timeout (`zap.c:makewish`, "the gods
   take notice"), so a prayer after two wishes fails about half the time and after three nearly always
   (`WISH_PRAYER_HOLD`).
7. **Where holes can be dug, and when they flood.** `dungeon.c:Can_dig_down` is false on a dungeon's bottom level
   (the Castle) and on hard-floor levels (the Valley: `gehennom.des` FLAGS). `Can_fall_thru` keeps the Castle's trap
   doors working, and `trap.c:fall_through` sends them to the Valley. Under `dig.c:fillholetyp`, a hole dug next to
   k moat squares floods with probability k/(k+1), with pools counting a third. A pick-axe rolls this twice (once
   for the pit and once for the hole, `dig.c:dig` -> `dighole`), and a wand of digging rolls it once. A hole we dig
   drops exactly one level (`dig.c:digactualhole`; only an existing trap door or hole can fall further,
   `trap.c:fall_through`). A hero in water who can't swim, fly or breathe it crawls out to a random square among the
   eight around the water square that has no monster and is no diagonal squeeze (`trap.c:drown`,
   `hack.c:crawl_destination`); the square she stepped from always qualifies, so a step into a 1-wide channel cannot
   drown her and lands her on the far bank with probability n_far / (n_far + n_near).
8. **Minotaurs.** `mkmaze.c:makemaz` puts 0-2 minotaurs (`rn2(3)`) in each filler maze between Medusa and the
   Castle, and `sp_lev.c:fill_empty_maze` puts 0-1 per MAZEWALK in the Castle's mazes. They ignore Elbereth
   (`onscary`), and every monster attack, hit or miss, interrupts digging (`mhitu.c`: `hitmu`, `missmu` ->
   `stop_occupation`), so a pick-axe hole can't be finished beside one. A scroll of scare monster stops them, and
   they don't follow you up the stairs.
9. **Who follows you off a level.** `dog.c:keepdogs` takes along every adjacent monster for which
   `mondata.c:levl_follower` holds: pets, a shopkeeper chasing you, and `M2_STALK` monsters that aren't fleeing,
   such as soldiers and trolls. They follow up or down stairs and through holes and trap doors. Minotaurs and
   soldier ants are not stalkers.
10. **Teleport scrolls.** In `read.c:seffects`, an uncursed, unconfused scroll of teleportation teleports you
    within the level (`teleport.c:scrolltele`). That fails on no-teleport levels: every Medusa variant, the Castle
    and the Valley (`medusa.des`, `castle.des`, `gehennom.des` FLAGS). A blessed one asks "Do you wish to
    teleport?" first. A cursed or confused read is a level teleport (`teleport.c:level_tele`), which only Sokoban,
    the endgame and the Amulet stop. With teleport control, asking for any level below the Castle from the Dungeons
    of Doom lands you in the Valley (`find_hell`). While blind, you can still read a scroll whose label you have
    seen (`read.c:doread`).

11. **A dwarf digs a hole in 2 + 4 calls, and a dig can never run under a shield.** `dig.c:dig` adds
    `10 + rn2(5) + abon() + spe - erosion` to the effort every call and, for a dwarvish hero, then DOUBLES the whole
    effort (`Race_if(PM_DWARF)`): a pit (> 50) after 2 calls, the hole (> 250) after 4 more once the digging
    restarts in the pit (the pit stage clears the digging level), about 5 game turns a level; a pick-axe and a mattock
    dig at the same speed, and `apply` wields the tool inside its own move. An adjacent hostile stops the occupation
    after every call (`allmain.c: monster_nearby`). A two-handed tool is refused under a shield (`wield.c:wield_tool`)
    and a shield under a two-handed weapon (`do_wear.c:canwearobj`); a small shield has delay 0, so wearing or taking
    it off is one move, as is wielding a weapon. So a mattock digger's shield is off for every dig, but the dig is a
    small part of the exposure: above Dlvl 20, 14 of 595 monster hits landed inside a dig window in 186 harness dives
    (SHIELD_FIGHT wears it for the melee that causes the rest).
12. **A fall into water soaks the whole pack.** `trap.c:drown` calls `water_damage_chain(invent)`: every carried
    item, worn or not, is spared with probability (Luck + 5)/20 (25% at Luck 0), otherwise a scroll fades to blank
    paper, a potion dilutes (twice: plain water), and an iron item rusts one level (3 at most) unless it is
    rustproof or blessed and `rnl(4)` is 0. A worn piece then gives `a_ac + spe - min(erosion, a_ac)` AC
    (`hack.h:ARM_BONUS`). Only iron rusts: iron shoes (AC 2) and the dwarvish iron helm (2) do, high boots (2), mithril
    and the wooden small shield do not. A confused scroll of enchant armor is the only repair. Nothing protects the pack
    in the pack, and dropped pieces fall with the hero only one time in three (`dokick.c:impact_drop`). A flooded
    Medusa crossing costs about 1.9 AC at the Castle (harness: 1-2 falls +1.88 AC, 3+ falls +3.0 AC) and about one
    scroll and two potions per fall.
