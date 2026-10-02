"""Feature switches for A/B experiments.

Dev runs may override them with JF_CFG='{"TOUR_FIXES": false, ...}'; the arena never sets
JF_CFG, so submissions always run these defaults.
"""
import json
import os

# Reading the evidence in these comments:
#  - 'jf14 s6' (or 'jf14-s6') = seed 6 of the 15-seed set with secret 'jf14'; 'public s4' = seed 4 of the arena's
#    15 public seeds; a run name may come first ('base4-jf14 s6', 'cmp-main jf41 s3'). 'Pinned' games run with
#    NetHack's wall clock fixed (dev/run_pinned.py), so a seed replays the same game and two configs can be compared
#    game by game ('paired'). 'Fresh' seed sets had not been used to design anything.
#  - Scores are the arena's progress score, 0-1, set by the best milestone reached (death costs nothing):
#    Dlvl 12 = 0.21, Dlvl 20 = 0.38, Dlvl 25 = 0.47, Dlvl 29 = 0.647. 'x vs y' is usually with the change vs
#    without it, and 'a -> b' between numbers is before -> after.
#  - 'sNN' = our submission NN, 'cand-X' = a submission candidate, 'train N' (runs 'tNN') = a merge round,
#    '<name> lane' = the team work stream behind a flag, 'guard' = a regression A/B against the base bot of the time.
#  - 'harness' / 'suite' = dev/scenario.py games that start a hero mid-game (e.g. on the castle level with a real
#    game's kit). Ids like A027, B017, F070 and R096 refer to the team's internal experiment ledger (not in this repo).
#  - 'panics' = errors the bot catches and recovers from (a stuck loop shows as thousands of them); 'steps' are
#    actions sent to the game, 'turns' are game turns. C names (pray.c, rnz(350), ...) are NetHack 3.6.6's.
#  - XL = experience level, BUC = blessed/uncursed/cursed status, TC = teleport control, MR = magic resistance,
#    MB = magical breathing, LR = the last resort (LAST_RESORT below); Dlvl, HP and AC as in NetHack.

# Fixes that change the levelling tour (the pre-dive early game, mostly an XP grind on Dlvl 1-3).
# Split by WHEN they first change a game:
# LATE (ON): only at a specific hazard (gas spore next to the pet, cockatrice corpse, passive-damage
#   monster, deadly status, empty wand) -- the elite's early game is untouched until then (the elite:
#   DT6A's AutoAscend fork, which this bot builds on).
# EARLY (off): prayer at pray.c's critically_low_hp instead of 'HP < 12', eat carried food before a
#   hunger prayer below XL 5 -- these reshuffle games from the first prayer on.
EARLY_FIXES = False
LATE_FIXES = True
# the rarest-hazard subset of LATE_FIXES (gas spore next to the pet, cockatrice-family corpse
# squares, spotted/ochre jelly and gelatinous cube melee): these first fire close to the deaths
# they prevent, so they barely perturb the elite's public trajectories. Effectively ON: the end of this
# file sets it whenever LATE_FIXES is on, as it is by default.
HAZARD_FIXES = False
# master switch kept for older experiment configs: sets both
TOUR_FIXES = None
# Excalibur dips only at >= 90% HP with a prayer ready (astra); changes the tour
SAFE_DIPS = False
# when Weak or worse with HP > 40, poisonous/acidic corpses are acceptable food
STARVING_EATS = True
# astra's survival layer (Elbereth rest, retreat upstairs) also during the levelling tour (astra = nethack_astra,
# another NetHack agent this bot takes ideas from)
SURVIVAL_IN_TOUR = True
# the last resort (LR; LAST_RESORT_DIG, DESPERATE_PRAYER_GAP and the LR_* flags refine it): at critically low HP with
# no safe prayer and a hostile adjacent, gamble -- the stairs we stand on (down also banks depth), then unknown wands
# zapped at the attacker, unknown potions, unknown scrolls. The game is usually lost here, and death costs nothing.
LAST_RESORT = True
# Komershan's verified leader (0.2033 on hidden seeds): dwarves and gnomes skip Sokoban and walk the
# peaceful Mines from Minetown straight to Mines' End (Dlvl 10-13: 0.126-0.26 banked early)
SKIP_SOKOBAN = False
# pray for HP only at pray.c's critically_low_hp (DT6A's 'HP < 12' prays with no trouble to fix: no
# heal, and a failure if the timeout isn't 0), and allow the first prayer from turn 100 (the timeout
# starts at 300; major trouble needs <= 200)
EXACT_PRAYER = False
# minimum turns since the last prayer for a hunger prayer while Fainting (DT6A: 400). Most first prayer
# failures were Fainting prayers 900-1100 turns after the last one (rnz(350) timeout: ~6% fail there,
# ~2% past 1100); a longer gap means fainting longer instead
FAINT_PRAYER_GAP = 1100
# AutoAscend's periodic 'eat corpses' preempt was meant to walk to edible corpses on the level, but
# only_below_me defaults to True, so it only ever eats what lies underfoot; the kills' corpses beside
# us go to the pet (it ate ~40% of the grind's corpses)
EAT_NEARBY_CORPSES = False
# Weak/Fainting with nothing to eat and no safe prayer yet: wait on Elbereth instead of wandering (many
# grind deaths came while fainted: rats, bats, ants; nearly everything on Dlvl 1 respects Elbereth).
# OFF: calibrated against the frozen s13 on the same 60 games (jf14/jf16/jf25/jf26) the shelter +
# starvation clock + 1400-turn Weak gap regime scored 0.207 vs s13's 0.251; with the three reverted
# (the other fixes kept) 0.252. Sheltering stops the hunt/eat loop that keeps the grind fed.
FAINT_SHELTER = False
# Fainting prayers by the starvation clock instead of a fixed gap: eat.c kills at uhunger <
# -(100 + 10 * Con) and uhunger drops at most 1 per turn once Fainting (almost not at all while
# fainted), so death is at least 100 + 10 * Con turns after Fainting begins. Pray once the gap is
# FAINT_PRAYER_GAP_LONG (= the Weak rule's gap), or STARVE_MARGIN turns before that deadline whatever
# the gap (the fixed 1000-turn gap could starve a character whose last prayer was an HP one, and it
# prays where rnz(350) still fails ~5.5% of the time; ~2.3% at 1200).
STARVE_CLOCK = False
# give up looking for the Mines entrance after this many turns and go on to Sokoban (0: never)
MINES_SEARCH_TURNS = 3500
# buy food in shops (never while carrying a digging tool) until carrying BUY_FOOD_UNTIL nutrition
BUY_FOOD = True
BUY_FOOD_UNTIL = 2400
# give up an item for sale after 3 walks toward it failed (a shopkeeper in the path), for 2000 turns
# ON (train 3.1): grind-food 43a08fa, replay-verified loop fix (base4-jf14 s6 paced 1500 turns at a shop)
BUY_FOOD_GIVEUP = True
# with at least FOOD_FIRST_MIN nutrition carried, eat instead of hunger-praying below FOOD_FIRST_GAP turns
# (0: off). Off: the 20 games where it fired (mostly the grind, on found food) fell 5.11 -> 3.97 in total --
# DT6A's reserve (eat only when no safe prayer) saves riskier Fainting prayers later.
FOOD_FIRST_MIN = 0
FOOD_FIRST_GAP = 1400
# from this XL the grind detours to the Mines (level PICK_TRIP_LEVEL, PICK_TRIP_TURNS at most) for a dwarf's
# pick-axe and keeps it (0: off)
PICK_TRIP_XL = 0
PICK_TRIP_LEVEL = 2
PICK_TRIP_TURNS = 2500
# a tool-less trip ends once the character reaches this XL (0: never): see _pick_trip_active
PICK_TRIP_END_XL = 0
# a tour headed for a shallower main-dungeon level (the grind, after a trip) explores for up staircases
# only: after its trip, pt6-public seed 9 fell through a trap door to Dlvl 4, took that level's unexplored
# '>' to Dlvl 5 and met soldier ants at XL 7 (the old rule takes any unexplored staircase, 50/50)
UPWARD_RETURN = False
# from this XL the Dlvl 1 grind moves to Dlvl GRIND_DEEP_LEVEL (0: never)
GRIND_DEEP_XL = 0
GRIND_DEEP_LEVEL = 3
# no Excalibur dips while carrying a digging tool (a dip's silent curse welds the sword and locks the pick out)
# ON (train 3, A027): no Excalibur dips while carrying a digging tool
NO_DIP_WITH_TOOL = True
# the grind's main-dungeon level by XL, {min XL: Dlvl} (empty: Dlvl 1 throughout; overrides GRIND_DEEP_*):
# e.g. {5: 3, 7: 2} keeps the random-monster cap (depth + XL) / 2 at 4 from XL 5 (global_logic._grind_level)
# train 3 (early-game A027): XL 5-6 grind on Dlvl 3, XL 7 on Dlvl 2 (cap 4): prayers 12.2 -> 7.2/game, grind losses 10 -> 5
GRIND_LEVELS = {5: 3, 7: 2}
# the tour skips to its next milestone after this many turns within 8 squares of one spot on one level
# (0: never). Stalls held 12 of 90 games for 1500-14000 turns, fainting through hunger prayers.
TOUR_STALL_TURNS = 1500
# STARVE_CLOCK's settings (above; FAINT_PRAYER_GAP_LONG acts only with it). STARVE_MARGIN also serves STARVE_DEADLINE
# (below) while no faint has been measured: pray this many turns before the worst-case starvation turn
FAINT_PRAYER_GAP_LONG = 1400
STARVE_MARGIN = 60
# Weak hunger prayers wait for this gap (DT6A/s13: 1200). Measured over ~2600 prayers, 900-1399-turn
# gaps failed 3.5-5.4% of the time, 1400-1799 only 1.1% and 1800+ 0.6% -- but 1400 lost more games
# to fainting than it saved from failed prayers (see FAINT_SHELTER).
WEAK_PRAYER_GAP = 1200
# corpses older than this (turns since the kill) are not eaten (AutoAscend: 50; tainting starts above 50)
CORPSE_MAX_AGE = 30
# STARVE_DEADLINE (and STARVE_CLOCK): pray once the nutrition estimated from the last faint's length is within this
# margin of eat.c's starvation line -(100 + 10 * Con)
FAINT_ESTIMATE_MARGIN = 90
# Gehennom (dive_logic.valley_step, valley_sneak, valley_retreat, gehennom_escape): walk the Valley of the Dead
# to its '>' (fixed map in valley.py), digging through its three locked secret doors with the pick-axe; never
# pray (pray.c: the god can't help there and may get angry) or rely on Elbereth (onscary: Inhell) in Gehennom;
# the Valley's '<' only as the retreat to the castle's east edge (the castle mode rests and drops back through
# the trap door behind the back door); a wand of digging zapped down as the escape; dig-dive below. Everything
# keys on dnum == 1 (Gehennom), which no game reached before the castle passage (msgs byte-identical on vs off).
GEHENNOM_DIVE = True
# Castle passage (castle_logic.py): on the castle level (the dig-dive's floor) walk to the west courtyard,
# try every ring/potion that may be levitation (or freeze the moat with a cold ray), float round the moat
# to the back door (56,08) and drop through the trap door behind it into the Valley (castle depth + 1).
# Dying on the castle level costs nothing: the castle is as deep as a dig can go.
# ON (train 3): fires only on the castle level, where the score is banked (A018 neutral); power/gehennom build on it
CASTLE_PASSAGE = True
# engulfed: wield the best melee weapon before fighting out (a dig-diver is swallowed with its pick-axe)
ENGULF_WIELD = False
# a Hungry (or worse) dive walks to fresh edible corpses within DIVE_EAT_RADIUS (BFS steps) and eats them
DIVE_EAT = False
DIVE_EAT_RADIUS = 8
# LAST_RESORT: a known wand of digging is zapped down first (an escape that also banks a level)
# ON (train 3): castle A018 guard neutral (+0.004); harness 8 of 10 escapes
LAST_RESORT_DIG = True
# fight2 on an Elbereth square: its -100 on every attack and its 'wait' bonus assume the engraving scares what is
# next to us. With an @ (human/elf) or minotaur adjacent it doesn't: fight it (see combat/fight_heur.py
# at_ignorer_adjacent; base4-jf16 s4 waited 5 turns in its dig pit while two Green-elves hit it 65 -> 12 HP)
# ON (train 3.2, dive-safety A060): guard vs base5 neutral (0.4212 vs 0.4230, 38/45 identical); harness Big Room
# 34 -> 40/42, @ group 13 -> 14/14; base4+t31+base4arm: 18/135 games waited on Elbereth under @ attack, 15 died to
# that monster kind
AT_ELBERETH_FIX = True
# with AT_ELBERETH_FIX: melee priority bonus on the ignorer while an Elbereth could be (re)written here -- once it
# is dead the engraving holds everything else off again and the dig resumes (0: no focus)
AT_FOCUS = 10
# with AT_ELBERETH_FIX: the dig out gives way to the fight for an ignorer this many steps away (1: adjacent only)
AT_DIG_RADIUS = 2
# LAST_RESORT: pray at critical HP beside a hostile once this many turns have passed since the last prayer
# (0: off; the ordinary low-HP prayer waits 500)
# ON (train 3): castle A038 guard neutral (-0.002); harness (2 Grey-elves, hero at 12/72 HP): deaths 9/10 -> 3/10
DESPERATE_PRAYER_GAP = 250
# LAST_RESORT: zap each unknown wand once (one still unknown after a zap at a monster is no attack wand)
# ON (train 3): with DESPERATE_PRAYER_GAP (castle A038)
LR_WAND_ONCE = True
# --- power: what the character carries to the Castle (power.py) ---
# Unidentified boots of the magic appearances (combat/jungle/hiking/mud/buckled/riding/snow) are 2/7 levitation
# or water walking, the Castle's moat crossing. The bot never picked them up (get_best_armorset skips ambiguous
# armour, and ItemPriority's unknown-status branch is dead: the parser maps UNKNOWN to UNCURSED); 26 of 90
# base-* games walked over a pair. Keep them unworn for castle_logic; never wear levitation/fumble boots.
KEEP_MAGIC_BOOTS = False
# BOOTS_KEEP (off, kit-builder): KEEP_MAGIC_BOOTS's goal with a lighter touch. KEEP_MAGIC_BOOTS lost 0.02-0.03 twice
# (unpinned A/Bs, A008/R066): every pair went ahead of the healing potions, the food and the thrown weapons. Here one
# pair per look that may still be levitation or water walking boots (price groups and knowledge rule the others out),
# after the food and the thrown weapons; never worn before the castle (castle_cross/castle_logic try them there).
# Evidence (true names from the seeds' appearance maps, ledger F070): 6 of 75 dev cmp-main games walked over real
# levitation or water walking boots and carried none to the castle (jf14 s6, jf40 s1/s11/s13, jf42 s0/s10).
BOOTS_KEEP = False
# a known wand of wishing keeps rnd(3) - 1 charges after the engrave-test wish (51 of 3158 games got one):
# zap them (power.wish_text: gray dragon scale mail, then an amulet of life saving worn at once, then a ring of
# levitation for the Castle, then speed boots). ON (coordinator, train 2): it fires only in wish games (~1%).
SPARE_WISHES = True
# a wished-for object is not formally identified (zap.c makewish: 'p - a granite ring'): name its appearance
# after the wish (power.learn_wished). Without it SPARE_WISHES wished for an amulet of life saving again and
# again and never wore one (base5-public s4, base5arm-jf16 s5), and castle_logic wished 3 rings of levitation,
# never put one on and then zapped the empty wand until a minotaur came (pwc-dp10 jf14-s14)
# ON (train 3.3, power B013): a wished-for object is recognised by its appearance (SPARE_WISHES never wore its
# amulet of life saving)
WISH_LEARN = True
# scrolls that may be scare monster are never dropped by arrange_items (a heavy armour swap dropped all light
# loot and picked it up again: 250 of 3158 games turned one to dust), a scroll we dropped is never picked up
# again, and a dust event names the scare monster label (power.scare_scrolls for castle/gehennom)
SCARE_KEEP = False
# while diving, ItemPriority keeps food and then the passage candidates (potions/rings that may be levitation,
# ...) ahead of the thrown weapons: 23 of 90 base games dropped potion types for good, mostly for daggers
# and the dive's pick-axe/mattock
KEEP_POTIONS = False
# inside a shop that buys them, drop each unknown potion/ring/candidate boots, read the shopkeeper's offer
# (base/2, or 3/8 of it) and decline: the price group narrows levitation to 1 of 5 potions / 1 of 7 rings.
# PROTOTYPE, keep off: in power-sell1-jf16 a ring's offer worked (100 -> the 200 zm group) but no potion
# offer was captured, and one game (s13) looped with 4114 tracebacks before dying.
SELL_PRICE_ID = False
# --- power: the post-castle campaign (castle_power.py, hooks in castle_logic; inert before the castle) ---
# on the castle's landing square: engrave-test unknown wands, drop every scroll that may be scare monster (the
# minotaurs of the west maze killed 27 of 61 real kits, most before any item was tried), then try the
# passage plan right there instead of after the walk to the courtyard
# ON (train 3.3, power castle set)
CASTLE_ARRIVAL_DRILL = True
# polymorph forms that fly/swim/breathe water cross the moat (P 0.2 per random polymorph); a known wand of
# polymorph is zapped at ourselves until one comes up; forms wait for their end at the door/trap door
# ON (train 3.3, power castle set)
CASTLE_POLY = True
# on the castle's west side an Elbereth-ignorer (minotaur, @) within 2: drop every scroll that may be scare monster
# and hold on the pile, striking what stays next to us (dive_logic.gehennom_scare's hold loop)
# ON (train 3.3, power castle set; acts from depth 25 on the main line, same score in the inertness replay)
CASTLE_SCARE = True
# castle: rest before/while crossing one square in from the moat, never on the courtyard's moat edge
# ON (train 3.3, power castle set)
CASTLE_EDGE_REST = True
# castle: go round by the south half when a sea monster was seen lately in the north half's west column (and
# back out of a column whose next square a monster holds); the choice is made in the west courtyard only
CASTLE_SEA_SWITCH = False
CASTLE_SCARE_HOLD = 1500   # turns at most on the pile while an Elbereth-ignorer is about
CASTLE_SCARE_DEPTH = 25    # from this depth on the main line (castle or the mazes right above it); a diggable
                           # level is dug down from the pile (scared monsters don't interrupt a dig)
# castle (castle_logic): dig straight east from the west maze into the courtyard instead of exploring for the
# maze's single join (the maze walls outside the castle map are diggable)
# ON (train 3.3, power): castle arrival kit suite 0/61 -> 3/61 crossings with the castle set; acts only on the castle
# level (score banked)
CASTLE_WEST_DIG = True
# castle: no retreat up the castle's '<' while the passage is on (it leads onto Medusa's level next to her
# when she is castle-1: 2 of 61 real kits 'petrified by Medusa' in pwc-dp1)
# ON (train 3.3, power castle set)
CASTLE_NO_RETREAT = True
# --- castle-breach: getting past the castle with the kits the dive brings (castle_logic, castle_power, dive_logic) ---
# Harness (castle-real-all, 61 real kits x 4 level-generation salts = 244 games, train 3.6 = 4103a5a): 8/244 pass,
# 8/84 among the 21 kits that hold a passage item or a polymorph source. Crossing attempts (courtyard -> moat) die in
# the moat ring's NW channel (map x 0 rows 1-5 + row 0 x 0-8, one square wide) or on the courtyard corner (0,6): 21 of
# ~40 attempts (brx-base-all3/all4), a shark waiting hidden at (0,5)/(1,5)/(0,4) biting 5d6 up to twice per our move
# while we trade blows over the water; every attempt that got past it reached the east courtyard.
# BREACH_PROBE: before the first lift is tried in the west courtyard, stand on the moat-ring corner of our half ON FOOT
# and search (detect.c mfind0: a search finds a hidden eel/shark next to us): fight what shows from dry land, step back
# to TEST_SPOT (no water next to it) to rest below BREACH_PROBE_HP, and only set off once BREACH_PROBE_QUIET searches
# in a row found nothing (at most BREACH_PROBE_BUDGET turns). A lasting lift found earlier (a ring put on where we
# landed) is taken off for the rests.
BREACH_PROBE = False
BREACH_PROBE_QUIET = 8
BREACH_PROBE_BUDGET = 300
BREACH_PROBE_HP = 0.6
# a probe older than this many turns is repeated (shorter) before the next item that may lift us
BREACH_PROBE_STALE = 25
# BREACH_WANDS: engrave-test the unknown wands on a bare west-courtyard square (2,8) before the passage plan is given up:
# the arrival drill tested them on the landing square, inside the pit of our castle-detecting dig, where the engrave
# test's look ('There is a pit here.  You see no objects here.') refused every wand and marked it tried -- jf14-s0 gave
# the castle up ('nothing that crosses water') holding an untested wand of cold (brx-smoke1)
BREACH_WANDS = False
# BREACH_RESUME: a passage given up for want of a way across ('nothing that crosses water', 'stranded') resumes when one
# turns up later (a wand named by a zap at a monster, a lift from a last-resort quaff, a crossing polymorph form)
BREACH_RESUME = True
# BREACH_COLD_FIRST: with a known wand of cold (or frost horn) and only untested potions/amulets left, freeze the west
# channel first (a ray freezes ~3 squares; the ice has no water beside it) and try the potions at the strip's east end
# on Elbereth: a lift then only has to cover the 13-square east channel (an uncursed potion lasts 11-150 turns, the whole
# way round takes ~56 at our speed). Kits: 4 of 61 carry a wand of cold, 2 of them with a potion of levitation
BREACH_COLD_FIRST = False
# BREACH_LEVWARN: 'You float slightly lower.' (5 turns left of a potion's lift): quaff another known potion of
# levitation, else don't start a water stretch from land, and over water make for the nearest dry square
BREACH_LEVWARN = False
# BREACH_SIDESTEP: floating into the west channel with a sea monster in its first one-square-wide square ((0,4) north:
# 42 attack actions there in the baseline, the commonest block), back onto the corner and wait up to 4 turns for it to
# come out after us onto one of the two squares off the corner, then pass it by the other (both lead into the column)
BREACH_SIDESTEP = False
# BREACH_NOWAIT: on the castle level (passage active) don't wait out blindness or hallucination (a potion of blindness:
# 250-450 turns, hallucination 600-800) before going on with the passage plan -- confusion and stun (short, and a
# confused step can land in the moat) are still waited out
BREACH_NOWAIT = False
# BREACH_PLUNGE: a flying polymorph form on the (55,08) trap door presses '>' (do.c dodown: a seen trap door takes a
# flyer through with TOOKPLUNGE; only levitation refuses) instead of waiting up to 3000 turns for the form to end
BREACH_PLUNGE = False
# BREACH_SPOT: the west courtyard's item-test square (1,7) under a boulder (giants carry and drop them) moves to the
# nearest free inner square, and a levitating hero goes round a boulder (or breaks it with the pick) instead of pushing
# it without leverage: brx all-flags jf14-s14 explored 4000 turns toward a buried (1,7); baseline jf14-s14~1 gave up
# 'courtyard square (1, 7) not reachable'; smoke jf14-s14~3 pushed the corner's boulder 80 times and gave up
BREACH_SPOT = False
# BREACH_RUSH: a lasting lift (ring, boots, a wished ring) rests in the west courtyard before the crossing only below
# BREACH_RUSH_HP (was 85%), and never with a land hostile within 4 -- the moat is the escape from the maze's monsters
# (2 squares into the channel nothing on land reaches us); the rest happens on the strip instead (rest stop below 80%,
# Elbereth). brx-t2-mino ring kits 4/24: most died at the landing or in the courtyard rest (jf16-s6~2: gnome king)
BREACH_RUSH = False
BREACH_RUSH_HP = 0.35
# BREACH_BYPASS: floating round the moat with every closer square held by a monster, step sideways to an equally close
# free square whose next step is free instead of attacking (east channel mouth: a sea monster on (61,5) is passed by
# (62,5) -> (61,6); the baseline attacked it from (62,4) 31 times in 434 harness games)
BREACH_BYPASS = False
# BREACH_MINO: an adjacent minotaur (or another Elbereth-ignorer of level 10+) at the castle depth: zap what may stop it
# at any HP, best first -- a known wand of sleep/death, teleportation (zap.c u_teleport_mon works on noteleport levels:
# rloc), polymorph (at IT: the kit's wand of polymorph was zapped at ourselves below 60% HP and minotaurs killed
# public-s0 in 3 of 4 salts), then striking/fire/cold/lightning/magic missile, then each unknown wand once (the old
# rule waited for HP < 90%: minotaurs take 30-50 HP a turn, 26 of 84 target games died to one)
BREACH_MINO = False
# BREACH_PILE: on a scroll of scare monster that works (CASTLE_SCARE hold, castle recognised), use the hold: zap wands
# (BREACH_MINO's order) at an Elbereth-ignorer in a straight line up to 8 squares away, and try the passage plan's rings,
# amulets, boots and wishes right there (the hold rested up to 1500 turns and tried nothing: 22 of 84 target games died
# 'before any try', several after 100-700 turns on or near a pile)
BREACH_PILE = False
# BREACH_DOOR: at the back door (57,08) -- the giant eels start at (57,07)/(57,09), both next to it -- stand on Elbereth
# while opening it (a scared eel lets go: F030), re-engraving after each kick (dokick.c u_wipe_engr(2), and its
# wake_nearby wakes them); 3 of ~40 crossing attempts drowned there
BREACH_DOOR = False
# a hunger prayer from this gap (instead of FAINT_PRAYER_GAP / WEAK_PRAYER_GAP) when a hostile within
# THREAT_RADIUS can reach us while Fainting, or while Weak with at most THREAT_WEAK_MARGIN nutrition left
# (0: off). 9 of 10 Dlvl-1 deaths in the base runs were fainted next to ordinary monsters at gaps 950-1110.
# ON (train 3.2, grind-food A047/A058/t32 -- one bundle measured together, so this line recurs on each flag it set):
# 90 games 0.4025 vs 0.3964; in-lane losses 6 vs 10, failed prayers 3 vs 7 (was: 0)
THREAT_PRAYER_GAP = 1000
THREAT_RADIUS = 5
THREAT_WEAK_MARGIN = 15
# a hostile of at least this difficulty is a threat (99: none, i.e. this trigger is off; was: 4). Set in train 3.2
# (grind-food A047/A058/t32): 90 games 0.4025 vs 0.3964; in-lane losses 6 vs 10, failed prayers 3 vs 7
THREAT_MIN_DIFFICULTY = 99
# the difficulty trigger only from this gap (0: THREAT_PRAYER_GAP)
THREAT_DIFF_GAP = 0
# this many walking hostiles within THREAT_RADIUS count as a threat (99: never; with THREAT_MIN_DIFFICULTY also 99, a
# threat is an Elbereth-ignorer, our HP below THREAT_HP_FRAC, or THREAT_NO_ELBERETH's case; was: 2). Set in train 3.2
# (grind-food A047/A058/t32): 90 games 0.4025 vs 0.3964; in-lane losses 6 vs 10, failed prayers 3 vs 7
THREAT_MIN_COUNT = 99
# ... or our HP below this fraction (a faint on a smudged Elbereth took a 90-HP XL7 to 49 in one faint)
# ON (train 3.2, grind-food A047/A058/t32): 90 games 0.4025 vs 0.3964; in-lane losses 6 vs 10, failed prayers 3 vs 7 (was: 0.5)
THREAT_HP_FRAC = 0.75
# ... or Fainting with no intact Elbereth under us and, within THREAT_NE_RADIUS, a walking hostile of difficulty >=
# THREAT_NE_MIN_DIFFICULTY or speed > 12, or any two walking hostiles
# ON (train 3.2, grind-food A047/A058/t32): 90 games 0.4025 vs 0.3964; in-lane losses 6 vs 10, failed prayers 3 vs 7 (was: False)
THREAT_NO_ELBERETH = True
THREAT_NE_RADIUS = 3
THREAT_NE_MIN_DIFFICULTY = 3
# DIVE_THREAT_GAP (verified-tier 'never faint' lane; 0 = off): the hunger-threat prayer above also while diving (the
# Mines pick trip and camps included), from this gap. Without it the dive has no threat rule: Fainting beside a hostile
# it waits for the plain 1100-turn Fainting gap. s23 on 18 sets (270 games): 198 fainting windows outside the grind
# killed 30 (15%) -- 25% of those that began under 900 turns after the last prayer (an HP prayer reset the clock) -- vs
# 559 grind windows killing 19 (3.4%) with the threat rule. rnz(350): a major-trouble prayer fails 8.5% at an 800-turn
# gap, 5.4% at 1000
DIVE_THREAT_GAP = 800
# find the kill square of our melee/thrown kills from the attack itself, and of pack kills from the corpse
# glyph, when the glyph-disappearance test misses it (27% of kills: their corpses were never eaten)
# ON (train 3.2, grind-food A047/A058/t32): 90 games 0.4025 vs 0.3964; in-lane losses 6 vs 10, failed prayers 3 vs 7 (was: False)
CORPSE_TRACK = True
# walk to fresh (<= CLAIM_MAX_AGE turns) edible corpses within CLAIM_DIST steps and eat them, before the pet
# ON (train 3.2, grind-food A047/A058/t32): 90 games 0.4025 vs 0.3964; in-lane losses 6 vs 10, failed prayers 3 vs 7 (was: False)
CLAIM_CORPSES = True
CLAIM_DIST = 3
CLAIM_MAX_AGE = 15
# LIZARD_KEEP (ON, verified-tier): keep one lizard corpse (10 weight, never rots) as the stoning cure -- not eaten off
# the floor or from the pack as food; emergency_strategy eats it when Stoned (eat.c: a lizard corpse fixes petrification;
# a prayer is the only other cure the bot has). s23, 360 pinned games: 4 'petrified by a chickatrice' deaths (Mines and
# castle), 2 of them in games that had eaten lizard corpses before (jf50 s4, jf54 s1); 57 lizard corpses eaten, 0 kept
LIZARD_KEEP = True
# ARMOR_UP (off, verified-tier; strength for Medusa -- F067: AC +4/0/-4/-8 -> 14/15/18/22 of 30 falls pass): s23's 123
# castle arrivals (360 games) had median AC 0; 28 wore no body armour and 36 carried unworn armour -- mostly the Mines
# dwarves' kit ('a dwarvish mithril-coat', 'a pair of iron shoes', 'a dwarvish iron helm'). BUC is not the reason
# (item_manager treats unknown BUC as uncursed); the dig-dive never runs gather_items, so wear_best_stuff never sees
# what the Mines trip picked up. With the flag:
#  - the dive runs wear_best_stuff every 25 turns with no hostile within 6 (not levitating); a tie keeps what is worn;
#  - a known scroll of enchant armor (not known cursed) is read while every worn piece is +3 or less (7 were carried
#    unread by 5 of the 123 arrivals).
# (Excalibur: fight2's melee already wields the best known weapon -- Excalibur over the pick-axe -- in fights.)
# MEASURED (armour lane, R423, 186 real dig-start kits of cand-k replayed by dev/digsuite.py, base 008ef20 vs ARMOR_UP, paired
# by kit, PREP_LOG): AC at Medusa -0.42 +-0.11 (140 kits, t -3.8), AC at the castle -0.31 +-0.15 (70 kits, t -2.1), carried-unworn
# AC per castle arrival 0.47 -> 0.12, castle arrivals 84 vs 79 of 186 (n.s.), depth >= 25 reached 128 vs 127, 26 wear passes in
# 60 kits cost 3 turns each (max 10) and no HP; what is left is blocked by a known-cursed worn piece (0.6 AC) or not in the pack.
# ARMOR_UP also logs 'ARMOR_UP slot ...' / 'ARMOR_UP wear pass done: AC n' lines.
ARMOR_UP = True
# eat poisonous corpses (not only when Weak) at HP >= max(POISON_EATS_MIN_HP, 60%) during the tour
POISON_EATS = False
POISON_EATS_MIN_HP = 40
# carry up to this many lichen/lizard corpses as a food reserve instead of eating them off the floor while not
# Weak (0: off)
LICHEN_RESERVE = 0
# the Dlvl 1 grind ends (DIVE_XL) only fed: Not Hungry within DIVE_FED_GAP turns of the last hunger prayer, or
# carrying >= DIVE_FED_FOOD nutrition; else it waits for the next hunger prayer (at most DIVE_FED_MAX_WAIT turns)
DIVE_FED = False
DIVE_FED_GAP = 500
DIVE_FED_FOOD = 400
DIVE_FED_MAX_WAIT = 2000
# longer hunger-prayer gaps in the tour only (0: WEAK_PRAYER_GAP / FAINT_PRAYER_GAP): with FAINT_GUARD(_IDLE)
# holding Elbereth through faints, rnz(350) fails 2.3% of prayers at a 1200 gap, 1.8% at 1400, 1.0% at 1700
# ON (train 3.2, grind-food A047/A058/t32): 90 games 0.4025 vs 0.3964; in-lane losses 6 vs 10, failed prayers 3 vs 7 (was: 0)
TOUR_WEAK_PRAYER_GAP = 1700
# ON (train 3.2, grind-food A047/A058/t32): 90 games 0.4025 vs 0.3964; in-lane losses 6 vs 10, failed prayers 3 vs 7 (was: 0)
TOUR_FAINT_PRAYER_GAP = 1600
# per-XL tour gaps [[min_xl, weak_gap, faint_gap], ...] (the highest min_xl <= XL wins; overrides TOUR_*)
TOUR_GAPS_BY_XL = []
# the low-HP prayer only at pray.c's critically_low_hp (EXACT_PRAYER's HP rule without its turn-100 first prayer)
LOWHP_EXACT = False
# LOWHP_CRIT_XL (ON, grind-audit): from this XL on (0: off) the low-HP prayer waits for pray.c's critically_low_hp
# (HP <= 5, or HP * 5 <= maxHP at XL 1-5, HP * 6 <= maxHP at XL 6-13). DT6A's 'HP < 12' rule prays at 10-11 HP of a
# 54-58 max: pray.c sees no trouble, so the prayer only pats us on the head (a weapon glow; 1 time in 3 the golden
# glow heals) and resets the timeout, and the real emergency one HP band later has no prayer left. cand-g fresh sets
# (270 pinned games, jf43-60): 3 such prayers at XL 5+, 2 died within 10 turns -- jf46 s8 prayed at 11/58 beside a
# homunculus ('Your long sword softly glows'), fell to 8 HP and the last resort's unknown potions put it to sleep;
# jf49 s2 prayed at 10/54 beside a gnomish wizard's wand of striking. Below XL 5 the old rule stays (LOWHP_EXACT's
# XL-1 skips were inconclusive, R109).
# Validated (grind-audit bundles GA-B2/GA-B3, 270 fresh pinned games each vs cand-g, ledger R191/R196): first to fire in
# 3 games, +0.97 / +0.81 net (jf46 s8 0.037 -> 0.507, jf49 s2 0.051 -> 0.554). Adopted at 5 in s25.
LOWHP_CRIT_XL = 5
# TOUR_FAINT_LONG_TURNS (ON, grind-audit; 0 = off): in the tour, a Fainting spell this many turns old prays from gap
# TOUR_FAINT_LONG_GAP instead of waiting for TOUR_FAINT_PRAYER_GAP (1600). eat.c: a faint lasts 10 - uhunger/10 turns
# and starts on a conscious turn with rn2(20 - uhunger/10) >= 19, so deep into a spell (uhunger ~ -100) we lie fainted
# ~90% of the time in 20-30-turn faints; the dust Elbereth under us wears (allmain.c: 1/(40 + 3 Dex) per turn) and
# the next monster gets a whole faint of free hits. cand-g fresh sets: 335 tour fainting spells, 7 ended in death, 5
# of them 430-540 turns into the spell (jf47 s5, jf49 s3, jf51 s1, jf55 s1, jf59 s14; killed at gaps 1392-1610 by a
# hobgoblin, rothe, giant rat, little dog, werejackal) -- two of them fainted at the very moment the 1600 gap came.
# Replaying the 335 spells with this rule (350 turns, gap 1200): it fires in 115, catches those 5, and costs ~0.8
# expected extra prayer failures (rnz(350): a Fainting prayer fails 2.3% at gap 1200, 1.3% at 1600) -- net ~+4
# games per 270. Short spells keep the long gap (their faints are short and their risk low: 0 of 7 deaths).
# Validated (GA-B2/GA-B3, ledger R191/R196): tour fainting deaths 7 -> 2 per 270, tour losses 39 -> 33, tour prayer
# failures 14 = 14 (99 faint-long prayers, 1 failed); first to fire in 69 games (net +1.49 in GA-B2, -0.20 in GA-B3,
# i.e. chaos around a small gain). Adopted at 350 / 1200 in s25.
TOUR_FAINT_LONG_TURNS = 350
TOUR_FAINT_LONG_GAP = 1200
# --- grind-audit: dives stuck on one level (dive_logic._stall_*; STALL_SESSILE and STALL_DOWNSEARCH_TURNS ON) ---
# cand-g fresh sets (270 pinned games): 10 of 231 planned dives stayed 1500+ turns on Dlvl 1-4 and 6 of them died
# there -- the dive hunger prayer every ~900 turns fails sooner or later (ledger F090). The BFS never enters a boulder
# square nor the square of a monster fight2 won't melee (molds, floating eyes, gas spores, blobs, jellies; also
# remembered out of sight), so one of those in a corridor or on the stairs walls the way off for good.
# STALL_SESSILE: the stairs we need are cut off (or a hostile sessile monster sits on them): hit what blocks the way --
# molds, lichens, blobs, cold/spotted jellies in melee at >= 50% HP; a floating eye only blind, blindfolded or with a
# thrown missile; a gas spore only at >= max(40, 60%) HP with nothing tame or peaceful next to it and not in
# Minetown. cand-g jf49 s10: a yellow mold on Dlvl 3's '<' (a gas spore beside it) held the XL-7 dive's way to the
# Mines 2500 turns, then a dive hunger prayer failed; jf45 s13 starved in a corridor between floating eyes and gas
# spores; jf43 s10 spent 9400 dive turns on Dlvl 1 behind a floating eye in the '<' room's only corridor
# Validated with the thresholds below (GA-B3, ledger R196): dives stalled 3000+ turns on Dlvl 1-4 6 -> 1 per 270 (with
# STALL_DOWNSEARCH); at STALL_MIN_TURNS 500 (GA-B2) it fired on 7 cut-offs of 501-670 turns that resolved by themselves
# (net -1.26), none of which fire at 1500. Adopted (ON) in s25.
STALL_SESSILE = True
# STALL_BOULDER: ...or boulders: push the first boulder on the way (hack.c moverock: it moves on unless rock, a wall,
# another boulder or a monster is behind it). cand-g jf44 s12 stood 6000 turns in a doorway between four boulders
# (the BFS reached 1 square), praying every 909 turns until an orc-captain came
# Not validated: jf44 s12's four boulders all have rock behind them in the push direction (the push can't help); pushing
# in the Mines untested. Keep off.
STALL_BOULDER = False
# the way cut off this long first: detours turn up -- ga-b1 jf43 s14 acted at 113 turns, ga-b2 jf46 s1 / jf48 s1 at
# 570-670 turns, each a game the base finished on its own; the stalls this is for lasted 2000-19000 turns
STALL_MIN_TURNS = 1500
STALL_MAX_TRIES = 12        # attempts on one blocker before leaving it alone for 300 turns
STALL_STAIRS_WAIT = 20      # a mold/jelly (speed 0) on the stairs this long: it never leaves
STALL_STAIRS_WAIT_MOVER = 400  # ...a floating eye, gas spore, lichen or blob: they drift off in time
# STALL_DOWNSEARCH_TURNS (0: off): no '>' seen on a main-line level after this many turns of the dive trying to
# descend: search the walls next to the largest unseen region (HIDDEN_SEARCH2's _search_toward_void) instead of
# AutoAscend's nearest-first search. cand-g jf55 s12 never saw Dlvl 2's '>' (the east half of the map blank) in 9000
# grind and 6000 dive turns, then a hunger prayer failed
# Validated (GA-B2/GA-B3, ledger R191/R196): first to fire in 4 games, +0.50 net (jf55 s12 0.051 -> 0.554, the others
# equal). Adopted at 1000 in s25.
STALL_DOWNSEARCH_TURNS = 1000
STALL_DOWNSEARCH_MAX_DEPTH = 10
# CAMP_HUNGER_GAP (0: off, grind-audit): a tool-less planned dive at depth <= CAMP_HUNGER_MAX_DEPTH (the Mines camp,
# the tool-less Mines descent after it, a dive stuck on Dlvl 2-4) prays for hunger from this gap -- Weak and Fainting
# -- once it has made one hunger prayer in the dive, holding Elbereth meanwhile (the faint guard; idle only while
# Fainting, never with a dwarf to hunt in view). E2's DIVE_FAINT_PRAYER_GAP 850 keeps the first cycle. cand-g fresh
# sets: dive hunger prayers at gaps < 1000 failed 20 of 220 (9.1%), 0 of 70 at 1000-1300 (rnz(350): 7.5% at 900,
# 2.3% at 1200); at depth <= 12 12 of 261 failed and nearly every failure ended the game at 0.05-0.12 -- tool-less
# camps pray every ~905 turns (jf60 s5: 907, 909, 909, 909, 907 after its camp) and the risk compounds (ledger F093).
# NOT validated -- keep off (GA-B3 vs GA-B2, ledger R196): the shallow dive prayer failures halve (12 -> 7 per 270), but the
# Elbereth holds through the longer Fainting waits cost games: the bundle with it -0.0046 vs without (t -0.76), the 18
# games where it fired first -0.70 (4 better / 6 worse), 9 of 34 games with camp holds died within 300 turns of one.
# jf60 s8: a non-hunger prayer reset the clock without fixing hunger and the camp held Fainting 550 turns on Elbereth
# until a smudge let a red naga hatchling, a lizard and a kobold in. Untested fixes: only after a hunger prayer; a
# spell-age cap like TOUR_FAINT_LONG_TURNS.
CAMP_HUNGER_GAP = 0
CAMP_HUNGER_MAX_DEPTH = 12
# hunger-prayer gaps while diving at depth >= DIVE_GAP_MIN_DEPTH (0: WEAK_PRAYER_GAP / FAINT_PRAYER_GAP)
DIVE_WEAK_PRAYER_GAP = 0
DIVE_FAINT_PRAYER_GAP = 850
DIVE_GAP_MIN_DEPTH = 3
# the Weak and Fainting hunger-prayer gap while diving with a digging tool (0: the rules above); see
# agent._dive_tool_hunger_gap
# ON (train 3.3, dive-safety A061): first dive hunger cycle prays from gap 850; guard vs base6 +0.011 (flag fired in
# 4 games, +0.175, none worse); harness 13/14 vs 7/14
DIVE_TOOL_HUNGER_GAP = 850
# HUNGER_DEEP (ON, strong-dive): the dive at depth >= HUNGER_DEEP_DEPTH (the castle included, not Gehennom) never
# goes hungry on purpose. cmp-main (99e4eb7, 90 pinned games): 15 games died while fainting, 12 of them in the dive,
# 6 at the castle (a fainted hero on the moat's edge is a shark's or a xorn's) -- e.g. jf42 s12 carried a tripe
# ration and an apple to its death: castle.crossing_strategy and fight2 (monsters are always in view there) sit above
# eat_from_inventory in the preempt chain; jf16 s11 fainted 180 turns at gaps 912-1088 waiting for the 1100 Fainting
# gap (DIVE_TOOL_HUNGER_GAP covers only the first dive cycle); jf42 s6 dug from Dlvl 7 to 25 while Weak with no
# food and no safe prayer (an HP prayer had just reset the timeout) and died fainted there. So, deep in the dive:
#  1. eat carried food as soon as Hungry, above fight2 and the castle crossing, while nothing hostile is adjacent
#     and we are not levitating (agent.eat_deep);
#  2. hunger prayers at Weak or Fainting from HUNGER_DEEP_GAP in every cycle (a prayer at 850 fails ~7.5% vs ~3.9%
#     at 1100 (rnz(350)), a faint beside a deep monster far more often);
#  (a castle camp that gave the crossing up keeps the long gaps: its score is banked, and every 850 gap fails ~8%)
HUNGER_DEEP = True
HUNGER_DEEP_DEPTH = 10
# ...on the castle level only (the default): on the way down HUNGER_DEEP only shifted meal times by a few turns, which
# reshuffled every game below Dlvl 10 (cand-c: 10 such games, net -0.79 of pure chaos); at the castle the score is
# banked and a fainted crosser is lost
HUNGER_DEEP_CASTLE_ONLY = True
HUNGER_DEEP_GAP = 850
# HUNGER_HOLD (with HUNGER_DEEP; off): Weak or Fainting with no food and no prayer due yet -> dig no deeper (hold on an
# Elbereth) until one is due (dive.try_dig_down). Off: the score is the deepest level, and digging on while fainting
# banks levels -- jf42 s6 held on Dlvl 19 for ~100 turns and died fainted there (0.365), while the base game dug on
# fainting and reached its Dlvl-25 castle (0.466).
HUNGER_HOLD = False
# without STARVE_CLOCK: a Fainting prayer whatever the gap when the faint-length hunger estimate nears starvation
# ON (train 3.2, grind-food A047/A058/t32): 90 games 0.4025 vs 0.3964; in-lane losses 6 vs 10, failed prayers 3 vs 7 (was: False)
STARVE_DEADLINE = True
# Fainting just after a paralysis ended ('You can move again'): pray from this gap (0: off)
# ON (train 3.2, grind-food A047/A058/t32): 90 games 0.4025 vs 0.3964; in-lane losses 6 vs 10, failed prayers 3 vs 7 (was: 0)
STARVE_UNMEASURED_GAP = 1100
# measure a faint from its own screen (not the last update), and not at all after an interrupted counted search
# ON (train 3.2, grind-food A047/A058/t32): 90 games 0.4025 vs 0.3964; in-lane losses 6 vs 10, failed prayers 3 vs 7 (was: False)
FAINT_MEASURE_FIX = True
# log corpse bookkeeping (kills recorded, corpses we stand on and their known age); diagnostics only
CORPSE_DEBUG = False

# robustness (loops and stalls):
# path() walks the BFS distances back obeying the BFS's own diagonal rule (a door entered diagonally was
# retried 90 times in one jf26 game): only changes a path that would have failed
PATH_DIAG_FIX = True
# fight2 lets go of monsters it has faced this many turns without contact, a kill or damage (asleep, immobile,
# out of reach), or after FIGHT_STALL_MOVES consecutive moves among <= 3 squares (the dance), for
# FIGHT_IGNORE_TURNS or until they come adjacent / anything hurts us (0: off; < 0: log only)
# ON (train 2) at 150 in the dive (the tour keeps FIGHT_STALL_TOUR_TURNS): robustness b2 guard 0.3480 vs 0.3479
FIGHT_STALL_TURNS = 150
FIGHT_STALL_MOVES = 30
FIGHT_IGNORE_TURNS = 300
# in the tour (the Dlvl 1 grind) only stalls this long are broken, and not by the dance trigger
FIGHT_STALL_TOUR_TURNS = 400
# the same in the Valley of the Dead only (GEHENNOM_DIVE; used while FIGHT_STALL_TURNS is 0)
VALLEY_FIGHT_STALL_TURNS = 25
# walking through known traps (AutoAscend's search relent, the dive's cut-off stairs, TRAP_LAST_RESORT) never
# enters polymorph/fire/sleeping gas/magic/anti-magic/rust traps, nor trap doors/holes/level teleporters in the tour
# ON (train 2): robustness b2 guard; +0.14 over the 2 games it fired in (b1)
SAFE_TRAP_WALK = True
# exploration with nothing left but searching, while unexplored ground lies beyond a known trap: walk through
# (the safe kinds of) traps at once instead of after ~80 visits' worth of searching one square
# ON (train 2): robustness b2 guard (dive only, after TRAP_RESORT_MIN_TURNS on the level)
TRAP_LAST_RESORT = True
TRAP_RESORT_MIN_TURNS = 1000   # ...once the dive has spent this long on the level
# remember where molds/jellies/floating eyes/gas spores sit and keep the BFS off those squares while they are out of
# sight (a mold on an item pile looks like the pile from afar: check_items looped on it for thousands of turns)
SESSILE_MEMORY = True
# go_to() re-plans to its real target after a path is blocked mid-way (its loop variables overwrote the target,
# so the next round aimed at the blocked square: 'end point is no longer accessible' and a strategy restart)
GOTO_TARGET_FIX = True
# the panic-loop breaker closes a square for 100 turns, not for the rest of the game (the failing moves are
# usually ours: a bear trap, a web; a permanent forbid boxed a Mines dive in for 5000+ turns)
TEMP_FORBID = True
# boxed in by diagonal squeezes while carrying > 600: drop to 550 for a while (a corridor bend held a grind 8000 turns)
UNSQUEEZE = True
UNSQUEEZE_TURNS = 30   # boxed in on one square this long first (the dive only)
# SQUEEZE_KEEP (ON, kit-builder): under UNSQUEEZE's 550 cap ItemPriority's order keeps daggers and food ahead of the
# light kit, and the pile is never picked up again: 6 squeezes in ~630 recent games (5 in Mines corners) dropped 4-26
# items each -- cmp-main jf41 s13 a wand of cold, a wand of digging and a ring, jf42 s6 a ring of polymorph control and
# wands of lightning and striking. With the flag the cap keeps wands, rings and amulets (3-20 each) and known potions
# of levitation/healing and scrolls of teleportation right after the weapon, armour and digging tool
SQUEEZE_KEEP = True
SQUEEZE_KEEP_CAP = 590   # hack.c cant_squeeze_thru: > 600 carried; the weight estimate takes the heaviest candidate
# after 3 failed use_container attempts on a floor container, leave that square's containers alone (a take-out
# menu that never matched was retried 45,453 times in one game)
# ON (train 2): the take-out loop (robustness B004) hit jf14 s0 in the train-2 smoke run: 11399 panics and 317k
# steps; with the fix 152 panics and 36k steps
CONTAINER_LOOP_FIX = True
# climbing out of a branch (or on the tool quest), known trap doors and holes stay closed: the stairs-cut-off walk
# stepped onto them again and again (base-jf26 s14 fell 42 times in 10k turns climbing out of Mines' End)
CLIMB_NO_FALL = True
# no fight2 moves while we are still in a pit (each try costs a turn and the attacker hits for free)
PIT_AWARE_FIGHT = True
# held by a bear trap: move-attempt diagonally (every diagonal attempt counts, 1 in 5 orthogonal ones: hack.c trapmove)
BEARTRAP_ESCAPE = True
# Lycanthropy (466 of 3158 dev games were infected; uncured Dlvl-1 lycanthropes died ~21% per 1000
# turns): detect 'You dream that you feel feverish' and were changes, never eat our were family's corpses
# (cannibalism: Luck -2..-5, the next prayer fails -- public s13, jf25 s10), treat a were form's HP as
# a buffer (no HP prayers/last resort for it: jf16 s11 and jf25 s9 spent their hunger prayer on the
# rat's HP and starved), and drop the load a rat can't carry so it can eat (public s4 starved Overloaded
# with 5 food items)
LYCAN_FIXES = True
# no lycanthropy cure prayer while Hungry without food (wait for the Weak hunger prayer; see cure_disease)
LYCAN_CURE_WAIT = False
# were_unload drops a were form's load whenever Overtaxed or worse, not only when Weak with food to eat
# t35: jf16 s6 0.602 -> 0.051 (a 9-HP were form dropped all 20 items on Dlvl 3 and never went back for them), jf14 s12
# and arm-jf25 s0 -0.040 each -- off
LYCAN_UNLOAD_ALWAYS = False
# Weak/Fainting in the tour with no prayer due and a monster within FAINT_GUARD_RADIUS: hold on Elbereth
# instead of fighting (dive_logic.faint_guard; fainted melee deaths were 8 of 18 Dlvl-1 grind deaths)
FAINT_GUARD = True
FAINT_GUARD_RADIUS = 4
# with FAINT_GUARD: also hold on Elbereth with nothing in view, from FAINT_GUARD_IDLE_WEAK turns into Weak and
# while Fainting, until the prayer is due (monsters arriving during a faint get no conscious turn to react to)
# ON (train 3.2, grind-food A047/A058/t32): 90 games 0.4025 vs 0.3964; in-lane losses 6 vs 10, failed prayers 3 vs 7 (was: False)
FAINT_GUARD_IDLE = True
FAINT_GUARD_IDLE_WEAK = 30
# the reactive guard also in the rescue dive after a failed prayer (no idle hold there: the dive must go on)
FAINT_GUARD_RESCUE = False
# one-action hold strategies (Elbereth rest, water demon vigil, faint shelter/guard) repeat while their own
# condition holds, instead of letting one step of a lower strategy run between two hold actions
# (dive_logic._hold_loop)
# ON (train 3.2, grind-food A047/A058/t32): 90 games 0.4025 vs 0.3964; in-lane losses 6 vs 10, failed prayers 3 vs 7 (was: False)
HOLD_LOOP = True
# ... only after a failed prayer (the rescue dive): the tour's holds keep their old behaviour
HOLD_LOOP_RESCUE = False
# dev only (never set in the arena): the Nth tour hunger prayer is treated as failed, turning games into rescues
SIM_RESCUE_PRAYER = 0
# Water demon vigil fixes (dive_logic.water_demon_vigil): step off the fountain before engraving (the dip
# leaves us on it: 'You can't write on the fountain!', so the vigil never held), hold while a demon is
# within DEMON_VIGIL_RADIUS (not 2) for DEMON_VIGIL_TURNS. 74 of 975 dipping games released a demon, 22
# of them died within 300 turns.
DEMON_FIX = True
DEMON_VIGIL_RADIUS = 5
DEMON_VIGIL_TURNS = 400
# fight2 never melees a floating eye we can see (the exploration stall breaker's attack-all mode did: 401
# paralysis events in 223 dev games, 35 games died frozen)
FEYE_FIX = False
# no Excalibur dips during a water demon's vigil window (the bot went back to the fountain next to the demon)
DEMON_NO_REDIP = True
# the last resort (unknown wands/potions/scrolls) yields to the Elbereth rest while everything close respects
# Elbereth and we are on one or can engrave (a zap erased it, a bounced ray / potion of sickness killed at 2-3 HP)
LR_ELBERETH = False
# weak-role lane (DT6A's Tourist leader, GRIND_DESPERATE_PRAYER_GAP 200; 0: off): the tour's own desperate prayer --
# critically low HP, a hostile adjacent, no prayer yet failed and at least this many turns since the last one ->
# pray before the unknown-item gambles (and before LR_ELBERETH). The dive has DESPERATE_PRAYER_GAP (depth >= 5, only
# when Elbereth is futile); the tour had nothing but the 500-turn HP rule, then the gambles: on fresh jf43-60 (E2)
# 26 of 72 early deaths fired the gambles first (the tour's quaffs put jf46 s8 to sleep beside a homunculus), and
# rnz(350) still answers a prayer ~55% of the time 200 turns on, ~77% 400 turns on (pray.c: timeout <= 200)
WR_GRIND_PRAYER = 0
# weak-role lane (DT6A's Tourist and vlomshakov's Healer leaders): no floor look (':') while blind in the dive -- in 3.6.6
# a blind look is a real move (invent.c look_here returns !!Blind) that reads no dust engraving; see
# inventory._blind_look_skip
WR_BLIND_LOOK = False
# the Elbereth rest never hides from a lone monster one blow kills (difficulty <= 2, not fast), at any HP
REST_FIGHT_WEAK = False
# never kill a gas spore whose blast reaches any @, a shop's squares (its shopkeeper may be out of view) or anything in
# Minetown; its melee is filtered out of fight2 (throws already skip it). Explosion damage from our kill is our
# attack on every peaceful in the 3x3 (explode.c): 3 of the 4 murders in 16 recent runs came from it (cmp-main
# jf40 s12: two watchmen in Minetown, Luck -4, prayers held, died fainting 0.075; cmp-main jf41 s5 and base10arm
# jf16 s11: shopkeeper Wonotobo). Before it was turned ON it had been tested only in the gc-h4 bundle (rejected as a
# whole, R032).
SPORE_SAFE = True
# a floating eye is hit blindfolded (blindfold/towel on, F-attack, off again), else by a throw, else as before
# ON (train 3.4, grind-combat A063): blindfold/towel on before meleeing a floating eye (jf16 s12 replay: no freeze,
# no rock-mole death)
FEYE_BLIND = True
# FEYE_TELE: once telepathic ('You feel a strange mental acuity.'), fight2 no longer melees a floating eye it can see
# (the FEYE_FIX filter: only blindfolded -- FEYE_BLIND with a towel/blindfold carried -- or as the stall breaker's safe
# last resort). An eye's corpse always gives telepathy (eat.c: level 2 > rn2(1)), which is the one thing an eye kill
# is worth; after that each swing is a 2-in-3 freeze of d(lvl+1,70) turns whenever the eye survives the blow
# (uhitm.c passive). cmp-main (99e4eb7, 90 pinned games): 320 melee eye kills, 80 freezes in 20 games, 48 of them
# after telepathy; all 7 freeze deaths in cmp-main + cmp-s22 (jf40 s4/s14, jf42 s8, jf41 s11) came after
# telepathy (a jackal pack, a rock mole, a hill orc ate the frozen XL6-7 grinder).
FEYE_TELE = True
# ...boxed in by an eye (no step to take): Elbereth to make it flee; still boxed after this many turns: hit it anyway
# (at full HP, fed, alone; see agent.fight2)
FEYE_TELE_BOXED = 150
# a missile/wand/ray hit breaks the Elbereth holds (rest, faint guard/shelter, demon vigil) and fight2's
# wait-on-Elbereth for RANGED_BREAK_TURNS turns: fight2 then closes in on a weak shooter or leaves its line
# ON (train 3.4, A063): a hold breaks when shot/zapped from range; guard vs base7 on 45 amd64 games 0.446 vs 0.415,
# grind deaths 5 -> 1
RANGED_ON_ELB = True
RANGED_BREAK_TURNS = 8

# the item split keeps the digging tool right after the melee weapon, before the armor set: it came after the
# armor, so a heavy armor pickup could push it out -- base8-public s11 took a splint mail on Dlvl 3 and dropped its
# pick-axe (and a food ration), the dive never knew the spot, camped tool-less in the Mines and died there (0.075;
# its castle is at Dlvl 28)
# ON (train 3.5): t35/t36 public s11 kept its pick at that drop step (0.075 -> 0.602 / 0.466), no other game changed by it
TOOL_KEEP_FIRST = True
# the faint guard (and its idle hold) also in a tool-less dive that is not a rescue -- the Mines camp waits
# thousands of turns for a dwarf's pick like the grind waits for XP, but fainted unguarded among the Mines' hostiles:
# base8 tool-less camps fainted 2-23 times, and all 6 died there (large dog, soldier ant, gargoyle, gray unicorn)
# t35/t36: arm-jf25 s5 +0.187, but arm-jf16 s11 0.602 -> 0.126 (held Weak on Elbereth instead of eating and taking the
# dwarf's pick base8 took) and it fired in a deep tool dive in were form (digging_tool() None) -- off
CAMP_GUARD = False
# a welded two-hander (a cursed dwarvish mattock the dive applied: 13% of dwarves' weapons are cursed) leaves no free
# hand, so no Elbereth for the rest of the dive: base5-8 tool dives with a welded mattock scored 0.28-0.39 (4-5 per 90
# games) vs 0.49-0.52 without. pray.c counts it as major trouble (TROUBLE_UNUSEABLE_HANDS: welded and !freehand())
# and fix_worst_trouble uncurses the weapon, so the dive prays for it once WELD_PRAY_GAP turns have passed since the
# last prayer (a major-trouble prayer fails when rnz(350) > gap + 200: 3.9% at 1100). The base8 welds came 806-2431
# turns after the last prayer, all within 3 turns of the dive start
# t36: uncursed the mattock in 3 of 4 welded games, but jf16 s8 0.602 -> 0.445 and s10 0.353 -> 0.206 (the spent
# prayer), arm-jf14 s8 +0.015 -- so it stayed off after t36 until s25 turned it ON together with WELD_HOLD
# (dive-audit lane, below: WELD_HOLD's comment has the evidence)
WELD_PRAY = True
WELD_PRAY_GAP = 1100
# engraving (Elbereth, wand engrave-tests) follows engrave.c freehand(): a welded one-handed weapon (a cursed pick-axe the
# dive applied) beside an uncursed shield still leaves a hand to write with; hands_welded() counted any shield, so such a
# dive dug on without Elbereth (Valkyries start with a small shield)
# ON (train 3.6): replay base8-jf14 s6 (pick-axe welded at the dive start, small shield worn): Elbereth 8x vs 1x, d24 -> d25
FREEHAND_FIX = True
# no retreat up the stairs from the level below Medusa's (or below an unvisited level at Medusa depth): they come out on
# her '>' beside her, and her gaze stones us -- base9-public s3 dug past Medusa-26 at 17/78 HP, landed on 27 by its '<',
# retreated up and was 'petrified by Medusa' (8 such deaths in ~700 dev runs); CASTLE_NO_RETREAT covers the castle only
# once it is recognised
# ON (train 3.6): replay base9-public s3 no longer climbs onto Medusa's '>' (lived 740 more turns on the castle level)
MEDUSA_NO_RETREAT = True
# teleport control's "To what level do you want to teleport?" was answered ESC (agent.update's generic text-prompt
# branch), which cancels the teleport after the level teleporter is already used up. With control, from the Dungeons
# any level past the castle is find_hell() = the Valley (castle+1: 0.507-0.691, above anything short of a castle
# crossing) and from Gehennom level 50 exactly (the top of the progress table) or the vibrating-square level when
# shallower (teleport.c level_tele): answer 50 in those two dungeons. Only reachable with teleport control (2 of 360
# recent games), so dominant and ON by default.
LEVELPORT_DEEP = True
# a wand of wishing -> Gehennom's bottom-1 (tele_route.py): wish 1 = a ring of teleport control (worn), wish 2 = '2 cursed
# scrolls of teleportation' (the wand is wrested for its last charge if needed), then read one anywhere in the Dungeons
# (-> the Valley, castle+1) and one in the Valley (-> the vibrating-square level, Dlvl ~44-52: 0.78-0.81). Harness
# lp-e2e: TC ring + a cursed scroll read on Dlvl 12 -> the Valley (Dlvl 26). Harness wr-unknown/wr2-unknown (XL 6 on Dlvl 3
# with an unidentified wand of wishing): 12/12 into Gehennom, 10/12 to Dlvl 44-51. ON: it only acts with a wand of wishing.
WISH_TELEPORT_ROUTE = True
# WISH_CHARGING_FIRST (castle-front lane, research F076): a wand of wishing's first wish is '2 blessed scrolls of
# charging'; the route's wishes then zap the wand down to (x:0), and one scroll is read on it before any wrest.
# mkobj.c: spe = rnd(3), recharged = 0; read.c recharge(): lim 3 for wishing, a blessed charge sets spe to 3 when
# spe < 3, and a second recharge explodes it. So c + 2 wishes instead of c: a 1-charge wand (1 in 3) got only the
# teleport-control ring before (tele_route.py).
WISH_CHARGING_FIRST = True
# ROUTE_GLOVES_FIX (front-strong lane, ON): cursed gloves or a welded weapon block the teleport-control ring without
# using a move ('You cannot remove your gloves to put on the ring.'), and the route's ring step retried forever (fs7-k6
# s9: 385k steps after the castle wand; any wand-of-wishing game with cursed gloves). Then the next wish is a blessed
# scroll of remove curse, read at once; with no wish left the step yields instead of looping.
ROUTE_GLOVES_FIX = True
# FRONT_DOOR (castle-front lane, research F076, castle_front.py): a castle kit whose lift plan gave up and that holds a
# known wand of striking or opening goes in by the front -- a boulder pushed onto the drawbridge span (or a cold ray),
# the bridge destroyed/lowered from (03,08), the soldiers held at (04,08) as they come over the span one at a time,
# then along row 08 to the throne room. The castle depth is already scored: a death here costs nothing.
FRONT_DOOR = False
# FRONT_V3 (front-strong lane, castle_front.py; needs FRONT_DOOR): the front door for a strong kit. After the bridge
# opens we hold the west maze's mouth (-2,10) -- the only square from which the courtyard's single exit (-1,10) is
# the one castle-side neighbour (sp_lev.c walkfrom carves odd cells; the diagonals are wall), no water beside it --
# with Elbereth rests against the court, a known scroll of scare monster dropped there, a scroll of taming when 2+
# are next to us; then in along row 08 (back to the mouth when badly hurt west of the hallway), and on to the wand:
# the locked door (32,04)/(32,12), a hallway, the corner towers; the chest under the burned Elbereth and the cursed
# scare monster scroll is forced open, the wand taken and engrave-tested (the wish: WISH_TELEPORT_ROUTE).
FRONT_V3 = False
# PASSTUNE_CRUSHER (ON; castle-redteam lane, ledger F104, castle_crusher.py + passtune.py): a castle kit that carries a
# tonal instrument (horn, flute, harp, bugle -- 7 of 105 true castle kits) learns the drawbridge's passtune by
# Mastermind (music.c: the span (05,08) in our 3x3, feedback 'N tumblers click and M gears turn'; passtune.Solver ~5.2
# plays, max 7) from (04,07)/(04,09) on Elbereth, then toggles the bridge: closing it kills every non-flyer, non-
# wall-walker on the span or the portcullis (dbridge.c do_entity: drowned or crushed, the kill is ours), opening it
# crushes whatever swims under the span. From that square nothing inside is in line with us and the @ soldiers must
# stand on the span to reach us (speed 10 vs our 12-16: we close first). Once quiet, in along row 08 (FRONT_V3's
# walk-in; a lure back to the crusher when 2+ come): castle 29 -> the secret door (38,08) -> trap door (40,08); other
# depths -> a tower chest's wand of wishing, named by one zap for WISH_TELEPORT_ROUTE. Runs above the crossing: at a
# castle on 25-28 a lift gives one level, the tower wand a pass.
PASSTUNE_CRUSHER = True
PASSTUNE_MAX_PLAYS = 25        # Mastermind plays before giving up
PASSTUNE_REST_HP = 0.5         # below this share of HP: close the bridge, rest on Elbereth on the crusher square
PASSTUNE_RESUME_HP = 0.8       # ...up to this share, then open it again
PASSTUNE_QUIET = 100           # game turns with nothing on (or dying on) the bridge before we walk in...
PASSTUNE_MAX_SPELL = 800      # ...or this many turns at the crusher in one spell (the court and the woken barracks
                              # keep trickling out: harness rt-smoke1 s1 crushed 62 in 1500 turns, never quiet)
PASSTUNE_MAX_STEPS = 3000      # crusher-phase steps at most
PASSTUNE_C29_TRAPDOOR = True   # castle 29: the trap door (40,08) beyond the secret door; else the tower wand
PASSTUNE_LURES = 12           # times the walk in turns back to the crusher for 2+ crushable monsters in view
# INSTRUMENT_KEEP (ON; castle-redteam, for PASSTUNE_CRUSHER): keep one tonal instrument through pack squeezes
# (ItemPriority: after the food, ahead of the unknown potions/scrolls/wands) and buy a cheap one in a shop when we carry
# none. cand-g fresh (270): 29 games picked one up (24 on Dlvl 1-4), 9 reached the castle, 7 still carried it (7/105
# arrivals); 11 more saw one and never took it (9 in shops at 16-67 zm), 5 of them reached the castle -> at most
# 14/105 arrivals with one. A pre-castle change: it reorders pack squeezes (HORN_KEEP's on90a jf47 s0 lesson).
INSTRUMENT_KEEP = True
# ROUTE_RING_SWAP (ON; castle-redteam): WISH_TELEPORT_ROUTE takes one ring off (not a known-cursed one) when both ring
# fingers are busy, to put the ring of teleport control on. Without it the route logged 'both ring fingers busy'
# every turn and never moved: rt-ik-smoke jf73 s1 took the castle's wand of wishing through PASSTUNE_CRUSHER,
# wished the TC ring and the scrolls, and sat there wearing two lift-test rings until a xorn killed it.
ROUTE_RING_SWAP = True
INSTRUMENT_BUY_MAX = 70         # zm at most for a shop instrument (bugle/tooled horn 15, flutes 12-36, harps 50 base)
PASSTUNE_PULL = False         # after the first quiet, one more spell from (04,08) on row 08 (rt-a1c/a2c: +0-6 kills, a
                              # shark death at (04,08), passes 3/20 and 2/20 vs 4 and 2 without: off)
PASSTUNE_LOCKOUT = True       # close the bridge behind us from (07,08) on the way in
# PASSTUNE_SCARE_WALKIN (off; crusher-walkin lane, for PASSTUNE_CRUSHER): in the throne room (past the lock-out,
# where there is no way back to the crusher square), a known scroll of scare monster is dropped before fighting an
# Elbereth-ignorer (@ or minotaur) -- monmove.c onscary checks a scroll on our square BEFORE the human/minotaur
# exclusions (F104), so it keeps a soldier or sergeant off us the same way Elbereth keeps the rest of the court off.
# Evidence: R217's cand-k full games -- both real walk-ins (castle 25, full HP) died to one 9 and 42 turns after
# entering the throne room, with no defence in that spot but the blow. See crusher-walkin's harness numbers below
# before turning this on.
PASSTUNE_SCARE_WALKIN = False

# --- castle-gate lane (2026-10-01 readiness program; harness census: dev/census.py JF_CENSUS, runs cg-*) ---
# PASSTUNE_SWEEP (off; for PASSTUNE_CRUSHER): the lure train. What the crusher leaves alive for the walk-in is not the
# court's trickle: (a) most castles wake their 36 barracks soldiers (a lich/demilich in the court casts the undirected
# spell AGGRAVATE MONSTER every move within 7 squares of us, mcastu.c MGC_AGGRAVATION + monmove.c dochug; 62 of 75 castle-
# crush-a games show 'You feel that monsters are aware of your presence', ledger F313/F318) and a court giant smashes the
# barracks doors; greedy m_move keeps the army jammed on the barracks' WEST wall while we stand at (04,07) and releases
# it the moment we are east of x=26 -- 21 of the 47 baseline walk-in deaths (112 real kits, runs/cg-kcrush-base) were
# @ soldiers in the first turns inside the throne room; (b) M2_COLLECT/JEWELS court monsters (ogres, trolls, giants,
# ettins) stick at the throne room's east wall for hundreds of turns, drawn by the storerooms' objects behind it (F317).
# So when the quiet test passes (garrison dead) the hero walks along row 08 to the throne room's first square (27,08) --
# bridge still DOWN -- looks, and as soon as a hostile castle monster is within PASSTUNE_SWEEP_RANGE (or closing in) runs
# back (speed ~16 vs the soldiers' 10) to (04,07); the crush loop kills the whole train on the span/portcullis, then the
# next sweep (up to PASSTUNE_SWEEPS). The bridge is closed behind the hero at (07,08) on the way out (SEAL: a west-bank
# minotaur/@ cannot follow him in) and re-opened there on the way back. A sweep that finds nothing coming for
# PASSTUNE_SWEEP_WAIT turns is the verified quiet that replaces the 100-turn timer: the hero stays sealed in at (27,08) and
# the hand-off to castle-inner is made from there ('CRUSH M:handoff'; locked_out is True, the bridge is up).
PASSTUNE_SWEEP = False
PASSTUNE_SWEEPS = 8            # trains at most
PASSTUNE_SWEEP_RANGE = 6       # a hostile castle-side monster this close (Chebyshev) to the hero starts the run back
PASSTUNE_SWEEP_QUIET = 25       # quiet turns (no kill, nothing on the bridge) before the FIRST sweep, once the garrison is dead (hazard at the crusher square is ~8% of games per 100 turns after T+100, and a 1100-turn session starves)
PASSTUNE_SWEEP_QUIET_TRAIN = 45 # ...and before each later one: the last train's stragglers are still walking in (sweep 2 of a smoke met them in the antechamber: 80 -> 25 HP in 7 turns)
PASSTUNE_SWEEP_START_HP = 0.9  # HP share a sweep needs to leave (the crusher loop's own resume level is 0.8)
PASSTUNE_SWEEP_WAIT = 8        # turns at (27,08) with nothing coming before the room counts as quiet
PASSTUNE_SWEEP_REST = 0.9        # sealed in at (27,08) with nothing coming: rest on Elbereth to this share of HP before the hand-off
PASSTUNE_SWEEP_REST_TURNS = 250  # ...for at most this many turns from the start of the wait
PASSTUNE_SWEEP_HP = 0.6        # below this share of HP a sweep turns back to rest at the crusher square
PASSTUNE_SWEEP_STEPS = 160     # steps one sweep may take before it is given up
PASSTUNE_SWEEP_SEAL = True     # close the bridge behind us at (07,08) on the way out (west-bank pursuers cannot follow), re-open it there on the way back
# PASSTUNE_FOUNTAIN_STEP (off): the antechamber's fountain (10,08) is on the walk-in's row and cannot hold an Elbereth (engrave.c
# doengrave: 'You can't write on the fountain!'); a hero that stops there with a monster within 2, hurt, or hurt in the
# last 3 turns steps to a free neighbour first. Evidence: sweep smoke jf90-s8 (xorn, 8 hits on the fountain), 4 more
# games with the message, ledger F326.
PASSTUNE_FOUNTAIN_STEP = True
# PASSTUNE_TRICK (off): the bridge as a minotaur trap. The maze's minotaur (19 of the 112 baseline kits died to one at the crusher
# square, 8 of them later than T+45, i.e. after the garrison was dead) and random Elbereth-ignoring @ (elf-lords, Woodland-
# elves, T+7..T+60) walk straight up to a hero standing on the west bank, Elbereth or not (monmove.c onscary). With the
# garrison crushed and the bridge down, a pest first seen 3..7 squares away makes the hero walk over the span to (07,08);
# m_move heads for us across the bridge, and the tune closes it on the span or the portcullis (dbridge.c do_entity:
# every non-flyer, non-wall-walker there dies). Then the bridge is re-opened from (07,08) (the sweep's 'return').
PASSTUNE_TRICK = False
PASSTUNE_TRICKS = 3            # tricks at most
PASSTUNE_TRICK_TURNS = 25      # turns one trick may take before it is given up
# PASSTUNE_DOORS (off; needs PASSTUNE_SWEEP and a digging tool): the second kind of train. After a quiet look the 7-8 tower guards
# (@, soldiers: they ignore Elbereth) are still behind the locked doors (32,04)/(32,12), pressing toward us in the 1-wide
# hallways; the walk-in meets them one by one with no way back (@ soldiers killed 21 of 47 baseline walk-ins). Sealed in at
# (27,08) the hero digs each door open from the square under it (pick-axe: silent, a dwarf breaks it in ~4 turns; no kick: a
# kick wakes the barracks, dokick.c wake_nearby), on an Elbereth, waits PASSTUNE_DOOR_WAIT turns for the guards, and runs
# back to the bridge with them behind it, exactly like a sweep.
PASSTUNE_DOORS = False
PASSTUNE_DOOR_WAIT = 30        # turns under an open door waiting for the guards (they walk ~20 squares from the hallway's west end)
PASSTUNE_DOORS_ARMY = False       # ...also on a side whose barracks door is open: the first visit under the door releases the awake army (about 15-30 soldiers
                              # file out along row 05/11 toward the hero and he runs the 25 squares to the bridge with them behind him: the first soldier or two
                              # reach him near the exit (a pincer at (27..28,07)), speed 10 vs his 16; est. 30 HP)

# PASSTUNE_TAME_CONF (off; castle-gate, ledger I312 item 5): a CONFUSED scroll of taming is an 11x11 area effect (read.c SCR_TAMING:
# bd = confused ? 5 : 1, m_at() in the box, no line of sight): every monster inside that fails resist() is tamed, a human
# (soldiers, MR 0) made peaceful (dog.c tamedog sets mpeaceful before its is_human refusal), xorns (MR 20) 4 in 5. At the crusher
# square at crush_over the box holds 1.6 xorns, 2.3 @, 3 sea monsters on average (census, runs/cg-x4-base, boxcount.py).
# Needs a KNOWN scroll of taming (not cursed) and a KNOWN potion of confusion or booze in the pack: quaffs, reads the next turn,
# waits the confusion out on the Elbereth (a confused hero only improvises: no tune). One use per game, at the quiet decision.
PASSTUNE_TAME_CONF = True
# PASSTUNE_TAME_MINO (off): the same quaff + confused read, but at once when a hostile minotaur is in view within 7 squares
# (the maze minotaur kills 19% of the base games before crush_over; Elbereth does not stop it; MR 0, so the scroll tames it
# for certain if it is inside the box). The go is spent: nothing is left for the quiet decision.
PASSTUNE_TAME_MINO = True
# PASSTUNE_PET_GUARD (off; for PASSTUNE_TAME_CONF/MINO): no bridge toggle (open, close to rest, lock-out, sweep seal/re-open) while a
# tame or peaceful monster stands on the span or the portcullis square, or hides under the raised span (after a taming read, one
# search turn reveals an adjacent eel/shark). 100 pet-kill messages in 63 of 448 taming-arm games (alignment -15, Luck -1 each:
# every prayer then fails, pray.c): opening 31, closing on the portcullis 27+13, our own blow 13.
PASSTUNE_PET_GUARD = True
PASSTUNE_PET_WAIT = 5             # turns a toggle waits for the bridge to clear at most (never while a hostile is within 2 or HP < 0.6)

# PASSTUNE_HORN_XORN (off; castle-gate, ledger F347): the xorns (2-4 per castle) converge on the hero and kill 10% of the
# base games and 21% of the sweep arm; the bridge cannot kill them and a dust Elbereth holds them only while the hero stands
# on it. A tooled horn (or a drum) improvised scares everything within distu < XL*10 that fails resist() (xorn MR 20: 4 in 5)
# for ~25 of its moves; a fleeing monster with room to move away does not attack. Horn kits die to minotaurs half as often
# as flute/harp kits (13 vs 30/32 of ~138, runs/cg-x4-base; the existing HORN_SCARE guard) -- this extends the same tool to
# xorns: blow when one is in view within PASSTUNE_HORN_RANGE (at most every PASSTUNE_HORN_GAP game turns, PASSTUNE_HORN_MAX
# times) and once on the Elbereth at the quiet decision before the walk-in.
PASSTUNE_HORN_XORN = True
PASSTUNE_HORN_RANGE = 7
PASSTUNE_HORN_GAP = 18
PASSTUNE_HORN_MAX = 12
PASSTUNE_HORN_PRESS = True   # ...and, inside the castle (x >= 7), whenever 2+ hostiles stand within 4 squares: soldiers (MR 0) flee a horn too

# Never dig or zap digging down on a staircase (rescue agent, 78a30e1; ported by hand for train 2): the square
# under '@' is unknown on arrival, so _diggable_spot took the arrival '<' for floor, and a wand of digging
# zapped there only says 'The beam bounces off the stairs' -- the dive zapped again until the wand was empty
# (6 of 90 baseline games, up to 5 charges = 5 levels each; jf16/5, jf27/1).
WAND_STAIRS_FIX = True

# SHOP_GUARD (pick-hunt lane): BUY_FOOD picks up nothing for sale while we have teleportitis without teleport
# control -- base4-jf14 s10 ate a leprechaun on its grind ('You feel very jumpy.'), picked up a food ration in a
# Dlvl-3 shop and teleported out before paying it ('You escaped the shop without paying!'): Keystone Kops, then the
# shopkeeper and his wand of striking killed the XL-8 dive; and the dive fetches no dwarf's pile in a shop.
# ON (train 3.1): no shop pickups with uncontrolled teleportitis, no pile fetch in a shop (jf14 s10: teleported out
# unpaid, killed by the shopkeeper)
SHOP_GUARD = True
# SHOP_SIGN_FIX: a locked door with any engraving in front of it that isn't one of our Elbereths is a closed shop
# (shknam.c stock_room engraves "Closed for inventory" in dust outside every locked shop door; nothing else is
# engraved at doors). The fuzzy 'closedforinventory' match missed a worn sign: cmp-main jf41 s3 read
# '?c?c  ??r ir?? ?', kicked the door open ("How dare you break my door?") and the shopkeeper killed the XL-7
# grinder (0.051). 6 broken shop doors in ~6000 games of all runs.
SHOP_SIGN_FIX = True

# --- valley-run (the Valley of the Dead with real castle-arrival kits: XL 7-10, 55-114 HP, AC -8..+10) ---
# VALLEY_SPRINT (off, REJECTED -- no signal): the Valley walk never stops to fight what it can outrun
# (dive_logic._valley_sprint): only adjacent monsters faster than us (bats) and the one on the next square of the way
# are attacked; the way is the cheapest by a router that charges unseen graveyard squares and dangerous monsters;
# up to 4 climbs of the '<' for a new landing square when the way on is through a dangerous monster; the landing
# wields the weapon; a door is dug as soon as nothing is next to us; the '>' is taken at once with hostiles in view;
# rest only below 45% HP; graveyard sleepers stay out of fight2 (the VALLEY_GRAVE_FILTER rule).
# Evidence (valley-real suite, 61 real castle kits started in the Valley, 3000 turns): past the '>' 0/61 in every
# arm -- base (train 3.6) median life 59 turns, v1 (4983dcc, vr-sprint1) 31, v2 (70412c3, vr-sprint2) 26; v2 got 4
# games out of the landing zone (1 to the temple) vs 2 for base. The landing kills: first hit ~3 turns after the
# fall (vampire bats, 44% of them vampires in bat form that rise again at full HP), then mummies.
VALLEY_SPRINT = False

# --- valley-exit ---
# VALLEY_FORT (off, testing): the Valley's residents all home in on us (monmove.c set_apparxy: a monster that can see
# knows our square, no line of sight needed) and an XL-8 kit can't trade blows with them: vx-base (valley-real, 61
# real kits) 0/61 past the '>', 41 dead in the Valley (median ~40 turns: 2-6 vampire-bat-type biters within ~3 turns
# of the fall, then giant/ettin mummies). A scroll of scare monster still works in Gehennom (onscary: only Elbereth
# has the Inhell exception) and a scared monster never melees (dochug: mattacku only if !scared). So on landing walk
# to the '<' (1-13 steps from every landing square), drop the scroll there (or, unknown, every scroll that may be one:
# 12 of the 61 kits truly carry one) and strike from that square whatever comes next to us, with the climb at hand;
# leave for the walk once no hostile has been in view for a while and HP is back, and come back to it to heal
# (dive_logic.valley_fort). Only acts in the Valley.
VALLEY_FORT = False
# LANDING_GUARD (off, testing; castle_landing.py): the castle landing -- a minotaur (or another big Elbereth-ignorer) at
# the castle depth gets the best known wand (beams and cold; other rays only with room to die out before a bounce),
# a frozen one is struck instead, known healing is quaffed at 60% HP beside it (one of its turns takes 30-50 HP), and
# CASTLE_SCARE drops its scrolls at 4 squares instead of 2. Inert before depth 25 on the main line.
LANDING_GUARD = False

# --- castle-landing (the first ~30 turns on the castle for a kit-holder: mino_guard.py, dive_logic.landing_listen) ---
# Harness facts behind these (ledger F101; castle-lift's faithful lift10 suite, 45 real lift kits x 10 salts, arm
# cl-t10-fix = 37/450): a minotaur meets 178/450 games and kills 106 in every castle-lift arm; 6/176 pass with one vs
# 31/274 without; its first blow comes a median 6-9 turns after the landing, and 80 of the 106 first saw it at distance
# <= 2 (the west maze is dark: infravision shows it only down a straight corridor). 35 of the 106 held a real stopper.
# LANDING_MINO_FLOAT: MINO_GUARD stays in scope while we float (levitation, water walking, magical breathing) over LAND:
# a minotaur reaches a floating hero in the west maze as well as a walking one. Before, _in_scope() dropped out for any
# floating hero (meant for the moat, where no walker reaches us), and castle_cross's rush just meleed it: 18 minotaur
# deaths in cl-t10-fix came after the lift worked, on the way to the moat (cra-jf25-s11~1: floated at +6, minotaur at 5
# squares at +12, meleed from +14, dead at +20 with an unknown wand of slow monster and a scroll of taming unused).
# Over water it still stays out; digging (a pit, a hole) is skipped while levitating (dig.c: can't reach the floor).
LANDING_MINO_FLOAT = False
# LANDING_MINO_CASTLE: the minotaur protocol on the castle (recognised, or a castle-likely landing: Dungeons, depth >= 25,
# landed at bot x <= 9, and a door sound heard or the first WAND_CASTLE_WAIT turns not over -- castle arrivals hear the
# soldiers' doors within 3 turns, 101/101, filler mazes have no doors):
#  - no recognition dig and no zap of a wand of digging down in the fight: Can_dig_down is false on the castle, both only
#    make a pit (cg-jf55-s6: 'MINO zapping a wand of digging down' at +0 beside the minotaur, 70 -> 26 HP, 'the wand dug
#    only a pit'), and the pit keeps us there (2-5 turns to climb out; vision.c shows only the 8 neighbours from it);
#  - unknown scrolls are read at an ADJACENT minotaur where teleports don't work (step 11 read them only where they do):
#    scare monster (read.c: every monster on a seen square flees, untimed -- in the dark maze that is an adjacent one),
#    taming (maybe_tame on the 8 neighbours; MR 0 never resists) and genocide still save us. After CASTLE_SCARE's
#    drop gamble when that one is pending (a pile of k maybe-scare scrolls is k chances in one turn, a read one);
#  - a pile that doesn't scare it is known at its first blow (a scared monster never melees: dochug !scared) instead
#    of digging on under its blows (cm-jf41-s9~3: 'MINO dig out (on a scroll of scare monster)' 69 -> 10 HP).
# Kits: taming scrolls cm-jf41-s9 / cra-jf25-s11 lost 10 of 20 games to minotaurs with the scroll unread.
# MEASURED (ledger R203; lift10 450 paired vs the flags-off baseline = castle-lift's cl-t10-fix, 450/450 identical):
# LANDING_MINO_FLOAT + LANDING_MINO_CASTLE + LANDING_SCARE_KEEP1 (ld1-mino): passes 35 vs 37 (+0/-2), minotaur deaths
# 106 -> 99; 47 castle reads in 43 games, 3 minotaurs tamed ('The neighborhood is friendlier.': cm-jf41-s9 lived
# 206-924 turns instead of 2-9, none passed); 35 fake piles caught at the first blow. The drop-first ordering and the
# fresh-pile read spend turns on ~7% gambles where the base zapped an unknown wand of cold (cra-jf14-s0~1), and
# KEEP1 held back the one real scare label (cra-jf14-s14~5; see SCARE_READ_ID). Keep off.
LANDING_MINO_CASTLE = False
# LANDING_SCARE_KEEP1 (with LANDING_MINO_CASTLE and CASTLE_SCARE): the castle's drop gamble keeps one unknown scroll back
# for LANDING_MINO_CASTLE's read: a read one is also taming or genocide (P ~ p_scare + p_taming + p_genocide) where the
# dropped one is only scare monster (P = p_scare), and the fight lasts a second turn more often than not.
LANDING_SCARE_KEEP1 = False
# LANDING_EAR: at a castle-likely landing (Dungeons, depth >= 25, below a known Medusa, landed at bot x <= 9) the dive
# doesn't dig its recognition pit; it writes Elbereth and listens for up to LANDING_EAR_WAIT turns, and a door sound
# ('You hear a door open' / '... crash open': the castle's soldiers, 101/101 castle arrivals within 3 turns, 1/185
# filler mazes) recognises the castle at once. Silence: the dive digs as before. castle-lift's CL_SENSE did this for
# kits with lifts to test (known_rush_strategy 'listen'); this is every kit, and the recognition is the castle plan's
# (its arrival drill, lift tries, TC gamble) as well as MINO_GUARD's. The recognition dig costs a median 6 turns and
# leaves us in its pit (cg-jf44-s6~1: 'You are still in a pit' when the minotaur came at +6, dead at +7).
# MEASURED (ledger R203, lift10 450 paired vs the flags-off baseline): it does what it is for -- 431/450 castles
# recognised by ear at +1..+3 (11 silent: fainted, deaf), pits 391 -> 6 games, deaths before the first item try
# 94 -> 54, first try +6 -> +3, moat median 33 -> 24, moat within 30 turns 54 -> 68 -- but passes 32 vs 37
# (+11/-16). The saved kits are the weak ones and the early crossers die later: deaths after reaching the strip
# 16 -> 26, sharks there 6 -> 17. The NE/SE sharks start at (57,0)/(57,16), home in on us along rows 1/15 at about a
# square a turn and meet an early crosser mid-strip (cra-jf16-s14~7: known ring, strip at +27 with 101 HP, five bites
# at (22,0), dead); late crossers meet them at the west end. It only moves the shark fight. With WISH_ROUTE_FIRST off
# it also exposes the castle's wish race (the wish kit 8/10). Repeated on main 21bb946 with castle-lift's CL_STRIP (no
# strip rest stop with a shark on our tail) + WISH_ROUTE_FIRST + SCARE_READ_ID (ld3-ear, 449 paired): 31 vs 36
# (+9/-14); CL_STRIP alone 33 vs 36 (+0/-3). Keep off until the crossing has an answer to the sharks.
LANDING_EAR = False
LANDING_EAR_WAIT = 4
# LANDING_CRUSH_FIRST (castle-entry): a kit with a tonal instrument (the crusher armed: PASSTUNE_CRUSHER, an instrument in
# the pack, the tune not yet known, not given up, not afloat) walks out of the west maze to the crusher square BEFORE it
# tests anything: castle_cross.rush_strategy (the CFP/CL lift tests -- unknown rings, amulets and potions, the moat jumps and
# routes) and castle_power.arrival_step's lift steps stand down (the wand engrave tests stay: 2 turns each). The tests resume
# once the crusher is done or has given up. castle-k-instr-x4 base (448 instrument kits, 396 recognise the castle, 115 reach
# the square): the games that ran such tests reached it 23% of 316, those that did not 54% of 80; on the moat route 7% of 70.
LANDING_CRUSH_FIRST = True
# LANDING_QUIET_TESTS (castle-entry): the castle's arrival lift tests (unknown rings, amulets, boots: castle_cross.rush_strategy's
# 'lift' step and castle_power.arrival_step's drill) wait while a monster is within 2 squares on dry land, as the potion tests
# already do (_on_foot_blocked). Census of 168 minotaur-seen landings (JF_CENSUS): 151 of 208 ring/amulet tests ran with a
# hostile within 2 squares (a minotaur at 2 in several), 7 HP lost in the 3 turns after; the usual layers (fight2, Elbereth rests,
# MINO_GUARD) get the turn instead.
LANDING_QUIET_TESTS = False

# --- SHOP_WISH (castle-entry; shop_wish.py; ledger F334/F314) ---
# A wand of wishing on a shop shelf: the bot never has the 667-889 zm it is quoted (median gold 47), but wishing and death are the
# only base-500 wands (shk.c get_cost: no other wand base can produce such a quote), one in two each. Inside a general store of the
# Dungeons of Doom the bot walks onto the shelf squares that show a wand (so the quote appears), takes a base-500 one UNPAID
# (pickup needs no gold), engrave-tests it on a free shop square (engrave.c: a usage fee goes on the debit, the wish is granted),
# and the wish route (tele_route: ring of teleport control + 2 cursed scrolls of teleportation) leaves by LEVEL TELEPORT: a robbery
# (do.c goto_level -> check_special_room(TRUE) on the OLD level -> rob_shop: alignment -1, Kops near the stairs), harmless once we
# are gone unless the shopkeeper is next to us (he follows), so the test square is >= 3 squares from him. Death: the usage fee
# (quote/4) is paid from gold or from junk sold to the shopkeeper (SHOP_WISH_SELL) and the wand goes back on the shelf.
# While anything is unpaid in the pack agent.bfs() closes the shop's door squares (walking out with a bill is robbery) and
# Inventory.pay_or_drop_unpaid() keeps the session's wand.
# Harness (dev/shopwish_scenario.sh, secret jf289, XL 6 Valkyrie, general stores on Dlvl 2-11, commit 4 of this lane): a wand of
# wishing on the shelf converted 21 of 21 (Dlvl 45-50, Valley reached, 8-35 turns from the take to the jump; the shopkeeper came
# along in at least 4 of the 21, all tiny shops with no test square 3+ from him -- after the pass, so it costs survival, not the
# pass); a wand of death with gold for the fee 12 of 12 (take, test, wand back, fee paid, door open, ~7 turns), with junk to sell
# 11 of 11 (2-3 sales); a shelf with no base-500 wand: nothing taken, panics 38 against 45 with the flag off (8 games each).
# The session is ONE body (shop_wish._session): agent.preempt() gives the layers below a preempting body the next action, so one
# action per call let the grind's wand_engrave_identify test the unpaid wand first (no record, door shut for good).
# OFF until the lane's merge request is accepted.
SHOP_WISH = True
SHOP_WISH_SELL = True      # (read with SHOP_WISH) sell junk to the shopkeeper when the usage fee of a wand of death is more than the gold
# WISH_ROUTE_FIRST: on the castle a wand of wishing is WISH_TELEPORT_ROUTE's while the route still wants a wish
# (charging, the teleport-control ring, the cursed scrolls): castle_logic._plan drops its own 'wish' step (castle_power's
# arrival drill reads that plan) and CL_POTION_EARLY's potion tests wait (castle_cross._wish_route_pending), for at most
# WISH_ROUTE_FIRST_TURNS after the recognition. tele_route zaps only with no monster at all within 3, so it skips ticks,
# and the passage spent the wand in one: castle-lift (ledger F103) saw the drill wish for a ring of levitation on the
# landing ('power drill: trying wish ... where we landed'), the level teleport (0.78-0.81) lost for a float in the west
# maze. Main passes the lift suite's wish kit 10/10 by timing only; recognised at +2 (LANDING_EAR) it lost 2 of 10.
# The passage's moves wait too (castle_logic.plan_step, castle_cross.rush_strategy): the west dig opened a wall to a
# minotaur before the teleport-control ring was on (ld3w-ear-wr cra-jf14-s14~3). wish10 (the wish kit x 10 salts):
# 10/10 with it, with and without LANDING_EAR (EAR without it 8/10); flags off 10/10. Inert without a wand of wishing
# at the castle.
WISH_ROUTE_FIRST = True
WISH_ROUTE_FIRST_TURNS = 100
# SCARE_READ_ID: a read scroll that says 'You hear maniacal laughter' (or 'sad wailing', read confused or cursed) is
# scare monster (read.c SCR_SCARE_MONSTER; nothing else prints them) and isn't auto-identified: the naming prompt that
# follows ('Call a scroll labeled X:', docall) names its label -- remember it as power.note_dust_prompt does for a scroll
# that turned to dust. Lift suite cra-jf14-s14~5: power_route read one of 3 KO BATE at +1 ('maniacal laughter in the
# distance'), the castle's scare drop then gambled on its other labels, and with LANDING_SCARE_KEEP1 held the 2 real ones
# back (dead to the minotaur; the base's gamble pile happened to include them: 'The minotaur turns to flee', pass).
SCARE_READ_ID = True
# VALLEY_XORN (valley-exit; dive_logic.valley_xorn): a wall-walking polymorph form in the Valley (castle-first-pass's
# CFP_XORN crosses the castle as a xorn) phases through the Valley's rock to its '>' (gehennom.des: NON_DIGGABLE but no
# NON_PASSWALL) and goes down; the Gehennom dig-dive goes on below (a xorn keeps its weapon and hands). Acts only in
# the Valley in a wall-walking form.
# ON (e1d198e + this): real arm jf16 s0 pinned 0.691/D30 -> 0.723/D33; xornkit_salted 14: 5 Valley arrivals all exit
# (D34 x4, D31) vs all dying at D30 off; identity off/on until 2 turns after the Valley arrival; crash-clean (vxk-on6,
# id-t5-on) -- the turn-30000 DRIVER hang is a harness-only artifact (#polyself before the first attribute parse).
VALLEY_XORN = True

# --- valley-walk (valley_walk.py; VALLEY_WALK off, VALLEY_LOTTERY ON): the Valley on foot for a castle-crossing kit ---
# VALLEY_WALK (off, testing): one strategy owns every Valley move (above fight2, valley_sneak, the Valley retreat/fort
# and gehennom_escape/scare): the '>' when reachable (down at once), a door's dig square (clear the neighbours, dig),
# else one step along the cheapest way (unseen graveyard squares, sleepers, awake monsters and the squares next to
# awake monsters cost extra); fight only what blocks that step, a monster faster than us next to us (bats) or anything
# when boxed in. A monster that moves can't melee in the same action (monmove.c dochug), so walking away from the
# slow undead takes few blows. valley-real base: 0/61 exits, median life 59 turns (F052).
VALLEY_WALK = False
VALLEY_WALK_GRAVE_COST = 4      # extra step cost of a graveyard square not yet seen empty (a sleeper to cut through)
VALLEY_WALK_SLEEPER_COST = 6    # ...of a square with a sleeper seen on it
VALLEY_WALK_ADJ_COST = 2        # ...of a square next to an awake hostile (x3 for a dangerous one)
VALLEY_WALK_RETREAT_BELOW = 0.4  # hurt with an awake hostile next to us and the '<' close: climb to heal
VALLEY_WALK_RETREAT_REACH = 20
# VALLEY_WALK_HOLD: on landing stand on the '<' first (1-13 steps from every landing square) and fight the landing
# crowd with the climb at hand (bats and mummies never follow up, monst.c M2_STALK); walk once no hostile has been in
# view for HOLD_QUIET turns at HOLD_LEAVE HP, or after HOLD_MAX turns
VALLEY_WALK_HOLD = False
VALLEY_WALK_HOLD_QUIET = 10
VALLEY_WALK_HOLD_LEAVE = 0.7
VALLEY_WALK_HOLD_MAX = 150
VALLEY_WALK_CLIMB_BELOW = 0.5
# invisible (no hero glyph on our square): don't stop to fight the bats -- close monsters move at random and swing at
# guessed squares (monmove.c m_move / set_apparxy); keep walking. Part of VALLEY_WALK: inert while that is off.
VALLEY_WALK_INVIS_WALK = True
# VALLEY_LOTTERY (ON): in the Valley without teleport control, a level teleport is a free roll --
# teleport.c random_teleport_level() from depth V: 1 in 5 nothing, else uniform over 1..V-1 and V+1..V+3, so
# P(deeper) = 0.8 * 3 / (V + 2) (~8%) per read, and a trip up costs nothing the score has banked (an XL-8 kit's walk
# out is ~0/61). A scroll of teleportation level-teleports when read cursed or confused (read.c; noteleport doesn't
# stop level_tele). So: read known cursed teleport scrolls; with known ones, get confused (a known potion of
# confusion/booze, a cursed confuse monster stack, or a known scroll of magic mapping -- on the nommap Valley it
# confuses for rnd(30) turns) and read them; read the unknown scrolls (unconfused: a confused genocide kills us) to
# find the teleport stack (identified by 'A mysterious force prevents you from teleporting!'), magic mapping ('Your
# mind is filled with crazy lines!') and the cursed teleports among them; VALLEY_LOTTERY_QUAFF: with known teleport
# scrolls and no confusion source, quaff unknown potions (confusion/booze ~8% each). At a quiet moment (no awake
# hostile next to us) or below VALLEY_LOTTERY_DESPERATE HP. Real kits: 28 of 46 dev castle kits carry teleport scrolls.
VALLEY_LOTTERY = True
VALLEY_LOTTERY_MAX_READS = 30
VALLEY_LOTTERY_QUAFF = True
VALLEY_LOTTERY_MAX_QUAFFS = 20
VALLEY_LOTTERY_DESPERATE = 1.0   # read/quaff even with an awake hostile next to us below this HP fraction (1.0: always)
# confused, read the unknown scrolls too (a teleport one is a ticket; a confused genocide kills us, ~3.5% a scroll)
VALLEY_LOTTERY_CONFUSED_UNKNOWN = True
VALLEY_LOTTERY_MAX_XL = 11      # stronger characters keep their walk (a roll goes up 3 times in 4)
# quaff the unknown potions for confusion before reading the unknown scrolls (then every unknown teleport scroll read
# confused is a ticket instead of being identified and spent)
VALLEY_LOTTERY_CONFUSE_FIRST = False

# --- castle-first-pass (CFP_*, castle_cross.py): get off the castle's west landing onto the moat before it kills us ---
# CFP_RUSH: on the castle's west side a LASTING lift (known lev ring/boots, then unknown rings, then unknown magic
# boots) goes on at once, above fight2/elbereth_rest/the scare hold, and a floating hero digs straight from the maze
# to (-1,2)/(-1,14) and floats onto the moat ring's west column at (0,1)/(0,15) (9 water squares to the dry strip
# instead of 14 from the courtyard corner). Over the moat no walker reaches us. Pinned-clock cfp-p2-jf16 s0: a ring
# of levitation in the kit, dead 25 turns after landing (master lich + elf-lord) with the ring never tried.
# ON in the train-4 candidate with CFP_MB/CFP_ZAP/CFP_XORN/POLY_XORN: the set of the first real castle pass (ledger
# R082/R083: arm jf16 s0 0.691, Dlvl 30); all act only on the castle level (POLY_XORN: a polymorph-control prompt at
# depth 25+).
CFP_RUSH = True
# CFP_MB (with CFP_RUSH): magical breathing walks the moat bottom (trap.c drown: 'But you aren't drowning. You touch
# bottom.'); an unknown amulet is put on in the lift phase and water-tested by the step off the dug launch square (no
# MB: we crawl back out onto it); a confirmed amulet or an amphibious/breathless polymorph form counts as floating for
# castle_logic's crossing. cfp-p2-jf25 s3's kit held an amulet of magical breathing and a skeleton key, never used.
CFP_MB = True
# CFP_ZAP: what blocks the way round the moat gets the best known wand first -- teleportation, striking (beams), then
# sleep/lightning/fire/cold/magic missile rays only where the ray can't bounce back (castle_logic zapped only striking)
CFP_ZAP = True
# CFP_XORN (with POLY_XORN, power-route): before CASTLE_POLY's self-zap put on the rings that may be polymorph control
# (the lift test took them off), stop zapping once we are a wall-walker, and as a xorn walk through the castle's walls
# (no NON_PASSWALL in castle.des) along the walled north corridor to a trap door (40..55,08): trap.c fall_through on
# the stronghold is find_hell(), the Valley. cfp-v1-arm jf16 s0 zapped its wand of polymorph 6 times into random forms
# with the ring of polymorph control in its pack (taken off by the lift test).
CFP_XORN = True
# CFP_PRUSH (with CFP_RUSH): potions that may lift us are quaffed one square west of the dug launch square (-1,2)/
# (-1,14) on Elbereth, not in the courtyard: a potion's 10-149 turns then start 2 moves from the moat with 9 water
# squares to the strip (14 from the courtyard), and no walk through the maze. Potions go before the magical-breathing
# water test (the dunk dilutes them: cfp-g1-arm cfpi-s1 turned its diluted potion of levitation into water).
# OFF in the train-4 candidate: castle-real-all 1/61 with it vs 2/61 without (t4-real-on, cfp-cra-prush): the rush to the
# launch square walks/digs through the maze on foot, and jf25-s0 met a troll there instead of quaffing its potion of
# levitation at the courtyard's TEST_SPOT (which crosses and passes without it)
CFP_PRUSH = False
# CFP_INVIS (with CFP_RUSH): on the castle, before the lifts, go permanently invisible with a KNOWN wand of make
# invisible (zapped at ourselves: zap.c 'ordinary' -> HInvis FROMOUTSIDE) or ring of invisibility (a worn mummy wrapping
# blocks it and comes off first): monmove.c set_apparxy makes a monster that can't see us guess our square each time we
# move (ours 1 time in 3, else a random accessible neighbour), so sharks, eels and minotaurs land ~40-55% of their melee
CFP_INVIS = False
# CFP_DUEL (with CFP_RUSH): on the dug launch square with a LASTING lift (known levitation ring/boots, water walking
# boots), the sea monsters are fought from land before we float out: the sharks (awake, speed 12, 5d6, starting at
# (5,0)/(5,16) in the west channels) track us and wait hidden at the water square nearest us, so every launch met the
# channel's shark and then bled under its bites over the 9 water squares (NW channel: 14 shark deaths of 40 failed
# crossings, ledger F065). From land a shark bites alone (no xorn reaches the launch square: court xorns can't cross the
# moat), we step back off the water's reach to rest below half HP, and we go only at 90% HP after 5 quiet turns.
CFP_DUEL = False
# CFP_EEL: the east eels at the back door. On foot and held by a sea monster (castle_logic's crossing), write Elbereth
# instead of hitting the holder (a scared holder lets go: monflee -> release_hero; its next touch would drown us);
# in front of the locked door (57,08) fight a sea monster in view next to us before the next kick (kicks wake them and
# wipe Elbereth). A potion's lift must be waited out before the kick, so potion kits kick every time: castle-c2 seed 3
# drowned at the door the turn it crashed open (the eel at (57,07) wrapped it; the bot hit back twice).
# ON (castle-only): harness eel drownings 6 -> 2 over 56 paired games, door test 21/28 vs 20/28; identical on the 61
# real castle kits (castle-real-all: never fired), crash-clean (ledger R097/R099).
CFP_EEL = True

# --- lift-ready: the kit's lifts known before the castle and used at once ---
# WAND_ENGRAVE_TEXT (ledger B016): the wand engrave test writes an 'x' at the text prompt instead of leaving it empty.
# engrave.c keeps the message of striking / slow monster / speed monster / magic missile / sleep+death / cold in
# post_engr_text and prints it only after the text is written; an empty prompt says '<wand> glows, then fades.' and
# nothing else. 90 s23 games ran 130 engrave tests and never once named one of those wands (0 'ice cubes', 0 'bugs',
# 0 'riddled', 0 'unsuccessfully fights'): the real castle-29 kit amd cfpe-s0 carried its wand of cold to the castle
# untested-looking and gave up there at once. Only a DUST wand reaches the 'add to the current engraving' prompt, so a
# burning/engraving wand (fire, lightning: the flash would blind us; digging) keeps the old empty answer -- they name
# themselves before the prompt anyway. The test answers 'n' and writes 'Elbereth' (wipes our finger's 'x', leaves a
# working Elbereth). DIVE ONLY (strong-dive's cand-b: a text engrave in the grind reshuffled nearly every game from
# T~700 and made the paired comparisons unpaired): the grind keeps the empty answer (byte-identical), and once diving
# inventory.wand_text_retest tests each wand the grind left unnamed once more, at a quiet moment.
WAND_ENGRAVE_TEXT = True
# LIFT_PLUNGE (castle_cross.plunge_strategy): on a castle trap door (40..55,08), not levitating, press '>' (do.c dodown:
# a seen trap door plunges us, flyers included; only levitation, being held or a huge form refuse). amd cfpf-s4 (real
# castle-29 game): an earth-elemental form 'don't fit through' at (40,08), the form died there and the dwarf stood on
# the trap door with 45 HP until the xorns killed it. A huge form zaps the wand of polymorph again or waits it out.
LIFT_PLUNGE = True
# LIFT_POLY_PICKY (castle_power.unusable_form / _repoly_step): on the castle's west side a polymorph form that 'crosses
# water' but can't make the crossing zaps the wand of polymorph again: an eyeless form (blind for its whole life --
# global_logic waited it out: amd cfph-s6's black light stood 43 turns, harness lift-fly1 s0 300 turns), a sessile one
# (brown mold, mmove 0: amd cfpf-s1), or one that can't apply the pick through the maze walls ('You can't hold it
# strongly enough.': amd cfpf-s4's energy vortex spent 740 turns in the west maze). 48% of the 278 polyok forms fly,
# swim, breathe water or walk walls (monst.c), and a form's death only returns us to our own form.
LIFT_POLY_PICKY = False
# LIFT_COLD (castle_cross.cold_strategy): the short cold route. castle_logic's starts at the courtyard corner and goes
# all the way round (28 moat squares; a ray freezes 2-4, a wand has 4-8 charges less the engrave test: harness cold1
# 0/36, real cfpi-s1 stranded at (3,0)). Instead: dig to (-1,0)/(-1,16) beside the end of moat row 0/16, freeze it
# eastward from the ice front (9 squares to the dry strip), walk the strip, freeze (54..62,row) (9 squares) and dig east
# into the east maze, which joins the east courtyard: 18 squares, ~6 rays. An object on a moat square (the corpse of an
# eel our ray killed) counts as ice.
LIFT_COLD = False
# LIFT_POTION_HP (castle_logic.plan_step): below this fraction of max HP, rest on the test square's Elbereth before
# quaffing the next potion that may be levitation (0 = off): a levitation potion floats us straight into the west
# channel (shark, eels, the tower wall's xorns). cmp-main jf40-s5 quaffed its potion of levitation at 29/71 HP and died
# two squares in.
LIFT_POTION_HP = 0
# LIFT_DOOR_RAYS: a known wand of fire / lightning / cold opens the castle's locked back door too (zap.c zap_over_floor:
# the door burns / splinters / shatters and the ray stops there), from afar (CFP_ZAP) or in front of it -- no landing to
# kick, no wait for a potion's levitation to end. cmp-main jf41-s9 waited at the door with a wand of lightning (0:6)
# until a minotaur came.
LIFT_DOOR_RAYS = True
# LIFT_KNOWN_RUSH (castle_cross.known_rush_strategy): a KNOWN lasting lift (ring of levitation, levitation boots known
# not cursed, water walking boots, an amulet of magical breathing) goes on the moment we land where castle arrivals land
# (Dungeons, depth >= 25, below a known Medusa, bot x <= 9), before the recognition dig (+3..+7 turns and a pit);
# levitation confirms the castle by its first door sound (within 3 turns in 101/101 castle arrivals, CFP_SENSE), and
# comes off again after 4 silent turns. Then CFP_RUSH floats us to the moat. cmp-main jf16-s0 floated only at +11 on
# its third ring and died at +15.
LIFT_KNOWN_RUSH = True
# LIFT_EARLY_RINGS (with LIFT_KNOWN_RUSH): with no known lasting lift, the kit's unknown rings that may be levitation
# (up to 3) are tried at the castle-likely landing before the recognition dig -- CFP_RUSH tries them right after it
# anyway; one that floats us is listened on like a known one
LIFT_EARLY_RINGS = False
# LIFT_NEAR_WATER (castle_cross._near_launch): a floating hero's way onto the moat by the estimated turns -- the fixed
# launch squares (-1,2)/(-1,14), the moat column straight east when level with it, or (level with the courtyard, rows
# 6-10) straight east into the courtyard and round its corner -- instead of always the fixed launch square
# (cmp-main jf42-s2 dug 4 squares south with five fights, 43 turns, one step from the courtyard's join)
LIFT_NEAR_WATER = False
# WORN_KEEP (item.can_be_dropped_from_inventory, ledger B019): a worn ring, amulet or blindfold is never in a drop list.
# arrange_items tried to drop the worn ring of teleport control (TC_WEAR put it on) with 'D': 'You cannot drop something
# you are wearing.' passes no game time, so its loop spun ~700 steps per game turn (turn-inactivity panics) -- 850
# castle turns in 20 wall minutes (strong-dive's sd-id-C public-s7~1); any worn accessory the item split doesn't want
# (TC_WEAR, CFP's kept rings, SPARE_WISHES' amulet) can start it
WORN_KEEP = True

# --- castle-lift (CL_*, castle_cross.py): use the kit's real lift before the castle's west side kills us ---
# CL_POTION_EARLY (castle_cross.early_potion, in CFP_RUSH's plan after the lasting lifts and the polymorph-control zap):
# on the castle's west side, not floating, a potion that may be levitation is quaffed WHERE WE STAND at the first quiet
# moment (no monster glyph within 3, 4 for a known one; HP >= 50%, 70% for a known one; not next to water; not blind,
# hallucinating, confused or stunned), on Elbereth, instead of only at castle_logic's TEST_SPOT after the walk through
# the west maze. A potion that floats us hands over to the rush (dig/float straight onto the moat's west column).
# Why (castle-lift census, 105 cand-g castle arrivals x true kits): 13 held a real potion of levitation and 10 never
# quaffed it -- the walk to the courtyard loses to the preempt layers (scare-pile holds, Elbereth rests, fights, poly
# escapes): jf43 s14 (castle 29) lived 1377 turns with it untried and found it by a LAST RESORT quaff at 1 HP; jf53 s3
# held a KNOWN potion of levitation and sat 90 turns on a scare pile. 38 of 73 arrivals with unknown potions never
# quaffed one (20 of them alive 50+ turns). The tests wait while castle_power's polymorph drill is still running (a known
# wand of polymorph: castle-29 benchmark cfpf-s4 quaffed between two self-zaps and lost base's poly pass).
# Result (faithful lift suite dev/scenario.py kit_type_faithful, 45 real castle kits x 10 level salts, 450 games): alone
# 29 passes vs 28; with CL_ROUTE 37 (and 35 in a replicate) -- see CL_ROUTE. The tests make 42 of 450 heroes
# hallucinate (26 of them within 22 turns of the landing), and waiting that out (600-800 turns) kills 35 of the 42; with
# BREACH_NOWAIT the tests and the crossing go on (145 crossings vs 131) but the passes stay 36 vs 36 -- the hallucinated
# crossings die in the west channel like the others.
CL_POTION_EARLY = True
# CL_ROUTE (castle_cross.cl_route, in CFP_RUSH's floating branch): a floating hero's way from the west maze onto the moat
# is planned over the maze's real structure -- mkmaze.c carves cells at odd level coordinates (map (even x, even y)),
# pillars (odd, odd) are always wall, the boundary column x = -1 is wall but for the courtyard exit (-1,10) -- with dig
# costs, to the moat square whose rest of the west channel is cheapest (water moves x 0.75), sea monsters seen by an
# entry costing extra; a known wand of digging with a charge to spare tunnels a straight run of 2+ walls in one zap; a
# form that can't swing the pick walks to (-1,10) and floats onto (0,11). The old rows-first dig to (-1,2)/(-1,14)
# took 11-54 turns (median ~20) from 'floating' to the first moat square in the harness's potion kits (cm-jf40-s5~2:
# 7 digs up the pillar column x = -5), turns a potion's 10-149 of lift can't spare. Entries far from the courtyard's
# channel mouths (0,5)/(0,11) are preferred: the west sharks home in on us and settle at the water square nearest us
# (monmove.c m_move), and crossings entering at (0,5) passed 2 of 38 vs (0,1) 11 of 18. Known webs are routed round (a
# web drops Levitation while it holds -- trap.c float_vs_flight -- and castle_logic then gave the passage up); polymorph
# forms keep castle_power's way. Result with CL_POTION_EARLY (lift suite, 450 games): 37 passes vs 28 (paired +20/-11;
# 35 in a replicate); per kind (landing deaths / crossings / moat within 30 turns / passes): potions 95/69/23/14 vs
# 93/46/12/12 of 250, rings 38/31/25/12 vs 38/32/21/7 of 80. Castle-29 full-game benchmark (76 pinned seeds, 40
# arrivals, few holding a lift): 1 pass as base, landing deaths 10 vs 13.
CL_ROUTE = True
# CL_MB_ROUTE (with CL_ROUTE and CFP_MB): the unknown amulet's magical-breathing water test (castle_cross.rush_strategy)
# walks cl_route's maze-aware way on foot to the chosen far entry and dunks there, instead of the rows-first dig to the
# fixed launch squares. Census: the 4 real MB amulets of the cand-g arrivals were never tried (the test waits for the
# potions: a dunk dilutes them; CL_POTION_EARLY clears them sooner). Not adopted: in a bundle with CFP_DUEL,
# BREACH_LEVWARN and LIFT_COLD the lift suite fell to 27 passes from 35 (rings 11 -> 6), and the MB kits stayed 0 of 20.
CL_MB_ROUTE = False
# CL_LAUNCH (with CL_ROUTE; castle_cross.cl_launch_plan, first in CFP_RUSH's plan while not floating): with unknown rings
# or potions that may be levitation left, walk/dig ON FOOT cl_route's way to the land square next to the chosen far
# channel entry, write Elbereth there, and try the lifts on that square; a lift steps straight onto the water.
# Harness lift suite (cl-t10-*, 45 real kits x 10 salts): crossings entering the moat within 30 turns of the landing
# pass 59/157 at the far entries vs 12/82 after 60 turns (the throne room's xorns reach the west towers after ~30
# turns); a potion found in the maze burned ~15 of its 10-149 turns afloat on the way; 26 floating heroes died on the
# launch square fighting the channel's shark, which a hero on Elbereth scares off (monmove.c distfleeck: monflee).
# Not adopted: with BREACH_NOWAIT the lift suite gave 31 passes vs 35 for CL_POTION_EARLY + CL_ROUTE -- more crossings
# (135 vs 120) but later ones: the walk to the launch square costs the turns the early potion saves.
CL_LAUNCH = False
# CL_STRIP (castle_logic._rest_stop): a lasting lift doesn't stop to rest on the dry strip (rows 0/16) while a sea
# monster is on its tail (bit us within 3 turns, or shows within 2): taking the ring off and writing Elbereth costs two
# turns of bites; afloat we outrun a shark (12 vs 12 + intrinsic Fast). Early crossings (moat <= 30 turns after the
# landing) in the harness lift suite died on the strips 30 times, sharks and eels 22 of them (cl-t10-rt/pe/launch).
# Not adopted: CL_STRIP + CL_SENSE + CL_EAST_WAIT on top of CL_POTION_EARLY + CL_ROUTE gave 35 passes vs 37 (more heroes
# reached the strips, 82 vs 69, and more died there: sharks 14 and eels 6 vs 6 and 2).
CL_STRIP = True
# CL_SENSE (with LIFT_KNOWN_RUSH; castle_cross.known_rush_strategy 'listen'): at a castle-likely landing (Dungeons, depth
# >= 25, bot x <= 9, below a known Medusa) with lifts to test (unknown rings, potions that may be levitation), listen up
# to LIFT_LISTEN turns for the castle's door sounds instead of the recognition dig; a sound recognises the castle at once
# (the dig takes +6 turns median and leaves a pit). castle-first-pass CFP_SENSE: a door sound within 3 turns in 101 of
# 101 castle arrivals, 1 of 185 filler maze levels. Silence: the dive digs as usual. Not adopted (see CL_STRIP): the
# landing's minotaur deaths only moved later (killed before any try 38 -> 14, after trying or afloat +16/+11).
CL_SENSE = False
# CL_EAST_WAIT (castle_logic._door_step): afloat on a potion at the back door, when it is open, or on the trap door:
# '>' once (a blessed potion lets us down), else wait for the lift to end at SAFE_EAST (59,08) instead of hovering over
# the trap door (55,08), where the castle's own monsters reach us through the hall's walls. cl-t10-rt: 4 of the 13
# east-side deaths hovered on (55,08) (xorns x2, a fire elemental, a red naga). Not adopted (see CL_STRIP): east-side
# deaths 18 vs 16 -- the east courtyard's own visitors (the east maze's minotaur, leocrottas) find us at SAFE_EAST.
CL_EAST_WAIT = False
# EAST_LATE_DOOR (price-id; castle_logic._east_float_wait, castle_cross.door_zap_from_afar): afloat on a potion's timed lift
# on the castle's east side, leave the locked back door (56,08) shut: no wand zap, key or kick at it while we float,
# '>' once (a blessed potion lets us down at will: potion.c I_SPECIAL), then wait at SAFE_EAST (59,08) for the lift to
# end (an uncursed potion lasts 10-149 turns and can't be ended). On foot, CFP_ZAP opens the door from SAFE_EAST's row
# out of the eels' reach and we walk (58,8) -> (57,8) -> (56,8) onto the trap door (55,08). An open door (or one opened
# before) is not entered while we float (as CL_EAST_WAIT).
# Why: a door opened while we float lets us drift over the trap door, where we hover until the lift ends (potion.c: only
# a blessed potion sets I_SPECIAL, which '>' ends; trap.c: a trap door doesn't trigger under Levitation; dokick.c: no
# kick afloat without a brace square): the hall fills from the castle (xorns, earth elementals through the walls) and
# from the courtyard through the open door. Harness east scenarios (price-id east/suite2: castle-base XL 8, 55/80 HP,
# floating on a fresh uncursed potion at the courtyard's east column (62,08), cand-i flags, seeds 0-59): base 58/120 --
# with a wand of striking the door was zapped open at once, 23/60 passed and 35 of the 37 deaths hovered in the hall;
# with no tool 35/60 -- vs EAST_LATE_DOOR 77/120 (38/60, 39/60; no hall deaths). CL_EAST_WAIT (its wait starts at
# (57,08), next to the eels) 37/60 vs 32 and 39 on seeds 0-29; BREACH_DOOR on top 78/120 (no gain). Castle-lift's
# faithful lift suite (potion kits, paired): neutral -- full price knowledge 16 = 16 (+2/-2, 23 firings), base 11 vs 13
# (+2/-4, 12 firings): real crossings reach the east with less lift left (median 36 turns) and few kits open the door
# afloat; pooled, 11 hall hoverers passed 4 and 29 courtyard waiters 22 (ledger R205). Left over: ~1/3 of the scenario
# heroes still die during the courtyard wait (the east maze's minotaurs via (63,06), dragons, giants).
EAST_LATE_DOOR = True
# CL_FLEE (with CL_ROUTE): floating with an Elbereth-ignorer on land within 5 (a minotaur: 3d10/3d10/2d8 a turn, it can't
# enter the water), cl_route takes the nearest water: the mouth penalty x0.2 and the channel length x0.3. Harness lift
# suite: minotaurs are the top killer of floating heroes before the moat (cl-t10-rt: 18 of 112 afloat-stage deaths).
# Not adopted: 440 of 450 games identical with it, 36 passes vs 35 -- a floating hero rarely sees the minotaur in time
# (79 of 106 minotaur deaths saw it first at distance <= 2 and lived a median 2 turns more).
CL_FLEE = False
# CL_BUGLE_WEST (opp_items.bugle_ok, main's idea): BUGLE_SCARE's bugle is also blown at a minotaur on the recognised castle
# level while we are on its west side (maze or west courtyard, not yet on the moat). The bugle wakes the castle's
# soldiers and turns them hostile (music.c awaken_soldiers), but they are walled in (raised drawbridge, towers opening
# inward, locked barracks and secret doors), and a minotaur flees it with no timer (R176: 14/20 vs 1/20). Note: 0 of
# the 105 cand-g castle arrivals carried a bugle (ItemPriority keeps horns, drums and cameras, not bugles). Lift suite
# with a bugle added to every kit (225 games an arm): minotaur deaths 55 -> 46, passes 17 -> 18; parked until the
# dive keeps bugles.
CL_BUGLE_WEST = False

# --- power-route (TC_*, power_route.py): teleport control + a level-teleport trigger from what the dive carries ---
# TC_ROUTE (ON): learn which ring gives teleport control from the game's prompts ('Where do you want to be
# teleported?' / 'To what level do you want to teleport?' with one unknown ring worn) and the tengu message, identify
# by reading (the identify menu picks rings, then teleport scrolls' BUC, wands, potions), and jump as soon as TC and a
# SURE trigger are in hand: a cursed scroll of teleportation read unconfused, or a level teleporter (teleport.c:
# confused answers to the level prompt are random 4 times in 5). From the Dungeons that lands in the Valley (castle+1),
# from Gehennom on Dlvl 50 or the vibrating-square level (LEVELPORT_DEEP). Evidence: the 61 real castle kits held a TC
# ring 4 times and a teleport scroll 34 times (4 cursed); jf16-s14 (Dlvl-29 castle, base3) carried the TC ring, a cursed
# teleport scroll and 4 identify scrolls, and died 13 turns after landing with all of it unused.
# ON (merge c44fe78): 45-game guard, dive-only version, pooled ~+0.025 (public 0.5112 vs base10 0.5023, jf14 0.4387 vs
# 0.4243, jf16 0.4611 vs 0.4094; ledger R079); harness designed kit pr-tca7b 4/7 into the Valley (Dlvl 30).
TC_ROUTE = True
# the castle once the lift plan has given up (castle_logic.given_up): dying there costs nothing and an uncontrolled level
# teleport only goes up, so read-identify, put rings that may give TC on, and pull every teleport trigger
TC_CASTLE_GAMBLE = True
# with TC known and only uncursed teleport scrolls: get confused (a stack that confused us before -- a cursed confuse
# monster scroll -- or a known potion of confusion/booze) and read one: controlled 1 time in 5
# (rnl(5) at Luck 0), else a random level (the score keeps the deepest). In Gehennom (the Valley kills an XL-8 hero in
# ~60 turns), on the castle, or from TC_LOTTERY_DEPTH down
TC_LOTTERY = True
TC_LOTTERY_DEPTH = 10
# with TC known: dip the teleport scrolls into known unholy water (potion.c H2Opotion_dip curses the whole stack: every
# scroll becomes a sure controlled jump); at the castle's end state also into water of unknown BUC (1 in 8 unholy,
# plain water blanks them)
TC_DIP = True
# a ring known (or proven by a TC prompt) to give teleport control goes on and stays on: a level teleporter stepped on
# anywhere in the Dungeons is then the Valley (6% of games step on one)
TC_WEAR = True
# identify by reading outside the castle at quiet moments (no hostile within 6, HP >= 60%, not Weak): known identify
# scrolls and unknown stacks of 2+ while unknown rings/wands/potions or a teleport scroll of unknown BUC are carried
TC_DIVE_ID = True
# drop carried rings/potions/scrolls/amulets of unknown BUC on a known altar of the current level (the grind's Dlvl 1-3
# hold ~90% of the kit's scrolls and potions: 25 of 90 base10 games stood on an altar there); the bot picks them up again
TC_ALTAR = True
# ALTAR_PICKUP (ON, kit-builder; ledger B017): TC_ALTAR's drop runs in the dive, which has no pickup step (gather_items is
# the tour's), so the bot walked away from the pile: 24 of 75 dev cmp-main games and 18 of 86 castle-29 games left their
# unknown potions/rings/scrolls/amulets on an altar (426 dropped, 76 ever picked up; true identities from the seeds'
# appearance maps: 6 potions of levitation, a ring of levitation, 8 healing potions, 4 known teleport scrolls on the dev
# sets; jf14 s2's Dlvl-26 kit kept 2 scrolls and no potion or ring). With the flag: the dropped items are picked up again
# in the same step, a pickup cut short is retried from the altar while we stay on its level, and scrolls that may be
# scare monster stay out of the drop (pickup.c: a scare monster scroll picked up once turns to dust the next time)
ALTAR_PICKUP = True
# ...a cut-short pickup is retried for at most this many turns after the drop
ALTAR_PICKUP_TURNS = 300
# try on (and take off) unknown rings whose BUC is known not cursed, at a quiet moment of the dive: a levitation ring
# names itself ('You start to float in the air!') -- a certain lift for the castle and Medusa's islands
TC_RING_TEST = True
# ID_MENU_PAGES (t-route; off): the identify menu's page count comes from the screen. power_route._identify_step looked
# for '(1 of 2)' in agent.single_popup, but agent.get_message_and_popup cuts the popup at that marker, so the pick was
# always made on page 1 of a menu that usually has two (the not-fully-identified pack in class order: amulets, weapons,
# armor, food, scrolls, potions, rings, wands, tools). The rings (value 160) and wands on page 2 were never picked: on
# the fresh sets s25-jf79..96, 82 of 107 identify picks took a scroll, potion or wand while an unidentified ring was
# carried (idpicks.py); jf79 s6 read 5 identify scrolls and never named its ring of teleport control (the harness
# reveal of the seed's looks: opal ring), and of 28 real TC rings held without a wish on 720 fresh games only 3 became
# known. With the flag the menu is paged through ('>'), the best item over all pages is chosen, and '<' goes back to
# its page before the letter.
ID_MENU_PAGES = False
# ID_PICK_PRIORITY (t-route; off): which item an identify pick names (power_route._id_value). Base order: unknown rings
# 160, a known teleport scroll of unknown BUC 95, unknown scroll stacks 60-83, wands 45, potions ~41, amulets 30, armor
# 25. With the flag: unknown rings 200+ (teleport control, levitation and polymorph control first), unknown boots 190
# (2 of the 7 random boot looks are lifts, levitation and water walking, and 1 is speed), unknown amulets 170 (life
# saving, reflection, magical breathing; strangulation is 13.5% and must stay off), unknown wands 150 (the engrave test
# leaves sleep/death, teleportation/cancellation/make invisible and the no-message wands apart), a known teleport
# scroll's BUC 120 (a cursed one is the T route's ticket), then the old values for potions and scrolls. READINESS
# weighs a known piece above an unknown one (TC 1.0 vs 0.11, polymorph control 1.0 vs 0.3, wishing 0.95 vs 0.76, a
# known lasting lift 0.10 vs 0.083), and KNOWN_ITEMS / MINO_GUARD use only known escape wands and amulets.
ID_PICK_PRIORITY = False
# --- t-route lane (2026-10-01 readiness program; power_route.py / tele_route.py; harness T-kits in dev/scenarios/t-route) ---
# Census (ledger F309; 990 real games, true identities from per-seed appearance maps): a TC ring is picked up in 3.9% of
# the games without a wish and named in 0.4%; a teleport scroll in 48.6% (known cursed 2.0%); a level teleporter is
# stepped on in 7.6% (two thirds in the Gnomish Mines, where a request for any deeper level clamps to Mines' End), never
# with TC worn; the 8 real wand-of-wishing games passed 8 of 8 through tele_route. So TC and a SURE second trigger
# (teleport.c: a cursed scroll read unconfused, or a level teleporter) are what a pass needs, and they rarely meet.
# T_STACK_BUC (off): remember what our own unconfused read of a teleportation stack taught about the rest of it (read.c
# SCR_TELEPORTATION: only a cursed or confused read calls level_tele(); a level prompt, or a random level change with no
# TC, means CURSED -- every scroll left is a sure ticket; a position prompt or 'A mysterious force...' means not
# cursed). cursed_tele_scrolls() then counts the rest of such a stack.
T_STACK_BUC = True
# T_BLIND_READ (off; needs TC worn): a teleportation stack whose BUC we do not know is read once at a quiet moment. With TC
# on every outcome is a prompt (level prompt = cursed: jump to the Valley, the rest of the stack is the second jump;
# position prompt = not cursed: ESC, one scroll spent), never a random teleport. A random stack is cursed 1 time in 8
# (mkobj.c blessorcurse(4)); the base bot waited for a BUC word that only an altar test gives (2.0% of games).
T_BLIND_READ = True
T_BLIND_TRIES = 2          # reads of one stack that settle nothing (a refused read) before it is left alone
# T_UNHOLY_PRAY (off): with TC known and >= 2 teleportation scrolls that are not sure tickets, a potion of water and a known
# CROSS-ALIGNED altar on the level: drop the water on the altar and pray. pray.c prayer_done: on an altar of another
# alignment the prayer's outcome is irrelevant -- p_type 0 (too soon), 1 (Luck < 0, angry god) and 2 (good standing) all call
# water_prayer(FALSE), which turns every potion of water on the altar to unholy water ('glow black'); the price is the
# god's anger (Luck -3, prayer timeout up, one time in three a lost level, one in three random curses) -- paid back by the
# pass the unholy water buys: potion.c H2Opotion_dip curses the WHOLE scroll stack (TC_DIP; harness U4 45/45), i.e. two
# sure tickets. Census (F309): water held in 38% of games, a cross-aligned altar seen in 33%, a cursed water in 1.5%.
T_UNHOLY_PRAY = True
# T_ROUTE_FIRE (off; t-route, tele_route.py): WISH_TELEPORT_ROUTE zaps and charges even with a monster in view within 3
# squares (it used to wait for none at all: a sleeping soldier, a peaceful or one behind a door stalled the route, and on a
# tower square or a castle landing the fight does not end); the 121-zap wrest loop of an empty wand still waits. The route
# is ~6-9 game turns, ends in a level teleport and wins more than a fight does.
T_ROUTE_FIRE = True
# T_ROUTE_EARLY_CHARGE (off; t-route): read the wished blessed charging scroll on the wand as soon as it is in hand instead of
# after a zap that says 'Nothing happens' -- read.c recharge() sets a wand of wishing below 3 charges to 3 (the wish for the
# scrolls spent one, so it is 0-2): ring, scrolls and a spare wish are then certain, and the route is a constant 7 actions
# (zap, read, zap, put on, zap, read, read) instead of 6-9 with a wasted empty zap in two thirds of the wands.
T_ROUTE_EARLY_CHARGE = True
# T_ROUTE_TOP (off; t-route): the wish route also sits at the TOP of the preempt chain (above the minotaur guard, KNOWN_ITEMS and
# the emergency layer), except while a safe emergency prayer is due. W-suite wW1 (base, 112 real castle arrivals + an identified
# wand of wishing (0:2)): 91 pass, 12 of the 21 failures are 'killed by a minotaur' in 2-24 turns -- mino_guard's plan ran
# instead of the route, which needs 6-9 turns, and a won fight is not a pass.
T_ROUTE_TOP = True
# PRAY_BOOKKEEP (off; t-route, agent.pray): write last_prayer_turn / prayer_failed even when a higher-priority layer interrupts the
# prayer's step() after the game has run it. T_ROUTE_TOP made this common (the wished ring is recognised during the prayer's
# updates and the route becomes ready): ts-w4all wW1 jf81 s1 prayed for hunger at gap 852 ('Tyr is displeased'), the bookkeeping
# was skipped, and the bot prayed again 3 turns later: 'Thou hast angered me', killed by the wrath of Tyr. Needed with T_ROUTE_TOP.
PRAY_BOOKKEEP = True
# ROUTE_ELBERETH (off; t-route): the wish route writes a dust Elbereth first when something that respects it stands next to us and nothing
# that ignores it does (not in Gehennom; onscary(): all but @, minotaurs, shopkeepers/guards, blind and peaceful monsters). 3.6.6 erases it
# only when WE attack (mon.c setmangry), not for a targetless wand zap or a read, and a scared monster makes no melee attack (dochug:
# !scared). Costs one move per writing (1 letter in 25 is garbled: 72% whole), at most 2 tries per square and 5 per route. wW1 (112 real
# castle arrivals + an identified wand): the 15 failures of T_ROUTE_FIRE+TOP are 5 minotaurs (it cannot help) and 9 troll/naga/worm/tiger/
# crocodile/lich/horse/scorpion deaths in 3-11 turns with no Elbereth under the hero because the route sits above the layers that write one.
ROUTE_ELBERETH = True
# WISH_PRAYER_HOLD (off; t-route): no safe-to-pray answer while the wishes granted so far have probably pushed the prayer timeout past
# 200. zap.c makewish() does u.ublesscnt += rn1(100, 50) for EVERY wish ('the gods take notice'); pray.c can_pray() fixes a major trouble
# only with ublesscnt <= 200, so a prayer after the 2nd wish fails about half of the time and after the 3rd nearly always -- Luck -3
# (each later wish fails 3 times in 5 and burns its charge), an angry god, rndcurse, a lost level, and no invulnerability while the
# minotaur hits ('You begin praying to Tyr.  The minotaur hits!'). Estimate: 100 per wish, less one per turn; held above 150 for a
# non-urgent prayer (hunger) and above 240 for a critically-low-HP one (a coin flip after two wishes still beats certain death).
# Evidence: wp14 W14-weak (Weak with hunger): the 4 seeds that prayed after ONE wish were 'satisfied'; s0 and s4 prayed after two:
# 'Thou art arrogant' / 'Thou hast angered me' + black glow, the wand drained by failed wishes (s4: 50 zaps at (1:0)); wW1 real castle
# arrivals with the route flags: 7 games prayed at HP 2-11 after 2-3 wishes, 1 of the 7 worked.
WISH_PRAYER_HOLD = True
# polymorph control's 'Become what kind of monster?' (polyself.c) was answered ESC = a random form; on the castle answer
# 'xorn' instead: it walks through walls (M1_WALLWALK; castle.des has no NON_PASSWALL) to the trap doors behind the
# back door and falls through into the Valley (castle-first-pass moves the form; jf16-s7's Dlvl-29 kit holds a ring of
# polymorph control). ON in the train-4 candidate (the xorn pass set, see CFP_RUSH).
POLY_XORN = True

# STAIR_BOULDER_FIX (ON, power-route; ledger B009): a boulder on the staircase dive_logic._take_stairs wants. The BFS
# never enters a boulder square, so it pushed the boulder from next to the stairs; with a wall behind it 'You try to
# move the boulder, but in vain.' takes no game time and the dive spun there (jf14 s4: ~300k steps on Mines 2 with a
# pick-axe and a wand of digging in the pack, then a soldier ant; 0.075 vs 0.602). After a failed push the boulder is
# broken (pick-axe/mattock applied at it, or a known wand of striking), else pushed from a side with floor behind it,
# else the stairs are left alone for STAIR_BOULDER_WAIT turns
# ON (R096): jf14 s4 0.075 -> 0.602 (pick-axe breaks the boulder on Mines 2's '<'); flag off byte-identical on 3 pinned
# seeds; 45-game guard fired only there, 0 unexpected exceptions / driver restarts.
STAIR_BOULDER_FIX = True
STAIR_BOULDER_WAIT = 300

# MINO_GUARD (minotaur lane, mino_guard.py; ON): a minotaur in view (the filler mazes between Medusa and the castle,
# the castle's west maze) -- a known way out first: a wand of digging down, the up stairs (no M2_STALK: it never
# follows), teleportation/polymorph/sleep zapped at it, a wand or scroll of teleportation on ourselves, a scroll of
# genocide ('minotaur'), a scroll of scare monster dropped under us; then death / sleep-or-death next to us, cold,
# unknown wands at it, unknown scrolls where teleports work; the emergency prayer still first at low HP; and no rest
# on a level where one was seen. cmp-main: minotaurs killed 23 of 90 games; 3 of the 7 dev-set maze deaths carried a
# known item that ends the fight in one action (jf14 s0 genocide, jf16 s10 teleport scrolls, jf41 s13 teleport wand).
MINO_GUARD = True
# STOPPER_FIX (ledger B018, minotaur lane; ON): castle_power's deep escape picks the unknown wand to zap at an
# Elbereth-ignorer by what its possible types would do to THAT monster (resistances: sleep, cold/fire/shock, death vs
# undead/demons/nonliving; the MR roll for sleep/polymorph/slow) net of the chance a ray bounces back onto us; no wand
# worth it -> no zap. mm-g3-jf14 s6: a {sleep, death} wand zapped at a master lich bounced and slept us (then killed).
STOPPER_FIX = True

# SOKOBAN_TRIP (off, power-route): when the grind would hand over to the dive, run the tour's Sokoban milestones first
# (dive_logic._sokoban_trip): 4 random rings + 4 random wands + the prize (bag of holding / amulet of reflection) --
# the ingredients the castle and teleport-control routes lack (TC ring in 4 of 61 real castle kits)
SOKOBAN_TRIP = False
SOKOBAN_TRIP_TURNS = 8000

# ROBUST_FIXES (ON, verified-tier lane; ported from eL1fe's dag engine): four loops/asserts that freeze deep games.
#  - item_manager.parse_name: objnam.c xname shows dragon scales as 'set of <color> dragon scales' (plural 'sets of
#    ...'); the parser knew only '<color> dragon scales' and asserted on every look at them. Dragons die from Dlvl ~20
#    on, so it hits exactly the deep games: 12 dev games in PANIC loops at Dlvl 19-29 (c8-pub g2 3034 panics on Dlvl
#    19, s7d-pub g10 1351 on Dlvl 28, shop-jf26 g14 612 on the Dlvl-29 castle level).
#  - exploration_logic.check_altar: LOOK shows no altar where the map remembered one (misread glyph, stale map):
#    forget it instead of asserting (the strategy retried it every step).
#  - inventory.wear/takeoff: canwearobj/select_off refuse without a turn -- a welded two-hander ('You cannot do that
#    while holding your weapon.' for suits/shirts, 'You cannot wear gloves over your weapon.'; neither marks the
#    weapon cursed, so hands_welded() never learns it), a foot in a bear trap / stuck in the floor, slippery fingers.
#    The refusal asserted (or passed for success: 'Your foot is trapped!') and wear_best_stuff retried it forever
#    (the 'turn inactivity' guard then passes one turn per 200 steps). The refused slot now waits (1000 turns
#    welded, 20 otherwise).
#  - explore1's door kicking: a shopkeeper in view means a closed shop's door; a digger that fell into a closed
#    shop sees the shopkeeper before level.shop knows the room (no entry greeting), and kicking its door open from
#    inside is fatal.
ROBUST_FIXES = True
# BOX_TRAP_SAFE (ON, gen-audit): a trap found on a box/chest ('You find a trap on the large box!  Disarm it?') is
# left alone -- answer n and never #loot that square (lock.c: opening a trapped box sets the trap off too). trap.c
# untrap: a disarm fails when rnd(75 + depth/2) > Dex + XL, ~75% for an XL-5 Valkyrie, and chest_trap's gas cloud is
# poisoned(..., 15): 1 in 15 instant death. Fresh-set cmp-main (s23): 6 of 90 games found a box trap, 5 set it off
# on the disarm; jf45 s8 died at T6166 on Dlvl 3 ('A cloud of noxious gas billows from the large box.', 53/53 HP).
BOX_TRAP_SAFE = True
# BOX_FORCE (item-yield lane, off): during the levelling tour, pry open the locked boxes and chests we have found with
# #force and loot them. Why: mksobj() locks a large box or chest 4 times in 5, and nothing outside the castle code ever
# opened one ('Hmmm, it turns out to be locked.', then the box was left for good). Ground truth (dev/truth.py reads the
# game's own object lists; ledger F110; 90 games jf79-84, main 6056954): the Dlvl 1-4 grind levels held 140 containers,
# 99 locked; the bot saw 118 and opened 32. Their 373 objects hold 165 wands, rings, amulets, potions and scrolls (1.8 per
# game), of which the bot took 26; the floors of the same levels gave it 355. Among them: a ring of teleport control
# (jf80 s3), a ring of polymorph, an amulet of magical breathing, a wand of teleportation, 5 scrolls of teleportation.
# How (lock.c doforce/forcelock): a wielded blade pries with a success chance of 2x its large-monster damage die per turn
# (dagger 6%), and each turn breaks the blade when rn2(1000 - spe) > 992 - 10 x erosion: ~0.7% per turn, so a +0 dagger
# breaks before the lock gives in ~10% of the time. So only a spare blade is used -- known uncursed or blessed, not the
# weapon in hand, never a long sword (the starting dagger, in practice) -- and forcing stops when none is left. fight2
# re-wields the best melee weapon before any melee. Before prying, the box is checked for traps BOX_FORCE_TRAP_CHECKS more
# times (#untrap finds a box trap with chance 10/(31 - XL): ~40% at XL 5-7, so one check misses most) and a trap found is
# left alone as BOX_TRAP_SAFE does. Not in shops (breaking a shop box's lock is charged), not while diving, not with
# hostiles within BOX_FORCE_CLEAR, below BOX_FORCE_MIN_HP, Weak, blind, confused, stunned, hallucinating, levitating or
# polymorphed, not on a square with several containers or where a box trap went off. Log lines 'BOX_FORCE ...'.
BOX_FORCE = False
BOX_FORCE_TRAP_CHECKS = 4       # extra #untrap checks before prying (with the one before the lock was found: 5 in all)
BOX_FORCE_MAX_TRIES = 4         # #force commands per box (each is up to 50 turns: lock.c gives up after 50)
BOX_FORCE_CLEAR = 6             # no hostile within this many squares
BOX_FORCE_MIN_HP = 0.6          # of max HP
BOX_FORCE_MAX_DIST = 60         # BFS steps to walk to a known locked box

# WARM_JIT (ON, verified-tier lane): compile utils.bfs (the one lazily compiled numba kernel) while the sandbox starts the
# bot instead of inside a game action. The arena times each act() with the evaluator's own action timeout (the hub
# verifier picks its own; a timeout scores the episode 0), but bot startup gets max(30 s, timeout) (arena/sandbox.py).
# Cold, the first bfs() is the slowest action of every game: 2.3 s on an idle machine, the per-game max action time of
# the 180 cmp-main0 games is median 4.4 s, 45% > 5 s, max 11.0 s (15 games in parallel). Game-identical (bfs is pure).
WARM_JIT = True

# opp-items lane (opp_items.py): three small levers from items the dive already meets (ledger F080) --
# GENOCIDE_POLICY and HORN_SCARE (both ON), TENGU_EAT (parked, off).
# GENOCIDE_POLICY: every genocide prompt gets an answer by what we know of the scroll (read.c do_genocide: a cursed
# scroll gives the same species prompt but sends in 4-6 of the named monster). Class prompt (only a blessed scroll
# asks it) -> 'H'; species prompt: a minotaur within 5 -> 'minotaur'; BUC known not cursed (the display, or the same
# stack's first read said 'Wiped out') -> 'minotaur', then raven/xorn/giant eel/shark; BUC unknown -> 'giant eel'
# (real: the castle moat's and Medusa's eels; reversed: stranded eels flee and waste away, mon.c minliquid), 'newt'
# with water within 3 squares or a proven-cursed stack, 'minotaur' on the castle (banked) or for a lone scroll at
# castle depth. Before, agent.update ESCaped it (jf14 s0 wasted one of two genocide scrolls on Dlvl 2; a cursed one
# then sends in 4-6 random monsters). A known genocide scroll proven not cursed is read at once (the levels below
# don't exist yet: fill_empty_maze makes no genocided minotaurs). Harness (A083): 2 unknown uncursed -> 'Wiped out all
# giant eels' then 'all minotaurs' 9/9; cursed -> 'Sent in some giant eels' 9/9, no deaths from them.
GENOCIDE_POLICY = True
# GENO_EXTRAS (ON, with GENOCIDE_POLICY; verified-tier, from the r/nethack research F085; mechanism-only, rare): the blessed
# (class) prompt answers 'L' first on the castle level and in Gehennom (covetous master liches teleport next to the castle
# landing and drive the Valley pile-ups); 'H' (the mazes' minotaurs) stays first above; never 'h' (dwarves: our race).
# (Tried and dropped: a known cursed scroll reverse-genociding 'wraith' for XL / 'tengu' for teleport control -- harness
# geno-rev, 4/4 'Sent in some wraiths.', but the dig-dive digs away from the fleeing wraiths: no corpse eaten, no XL,
# 2 of 4 dead in the mazes below; it would need a hunt-and-eat mode.)
GENO_EXTRAS = True
# HORN_SCARE (needs MINO_GUARD): a tooled horn or any drum makes every minotaur in range flee (music.c
# awaken_monsters: MR 0 never resists, monflee with no timer) -- mino_guard blows it at first sight, before any wand
# or scroll, then digs while it flees (a cornered one next to us: step out of its reach; blown again when it comes
# back or hits us); an unknown horn (tooled 5/11, frost 2/11, fire 2/11, plenty 2/11) is a gamble after the known
# stoppers, its ray (if any) aimed at the minotaur or down the longest free line; an expensive camera in line within
# 2 squares blinds it and makes it flee 3 times in 4 (uhitm.c flash_hits_mon; weaker: a blind monster walks at
# random). Also answers the 'Improvise?' prompt the castle's horn test never answered (cmp-main0-jf44 s0: 'n' went
# to the tune prompt, 'Never mind'). Harness (A084, minotaur next to the medusa+1 landing, 14 maze + 6 castle
# landings): escaped down horn 0 -> 14/20, drum 1 -> 13/20, camera 0 -> 6/20. Real (cand-f cfg, jf43-48): fired in 4
# of 90 games, jf43 s7 0.445 -> 0.466 (a drum at a Dlvl-24 maze minotaur, dug on to the castle), the rest equal.
HORN_SCARE = True
# BUGLE_SCARE (ON, with HORN_SCARE; verified-tier, from the r/nethack research F085): a bugle is a scare instrument too --
# music.c awaken_soldiers (3.6.6): every non-mercenary within distu < XL*10 that fails resist(TOOL_CLASS) flees with no
# timer (minotaurs, MR 0, never resist; no onscary check in this path), the same reach as a tooled horn. It also wakes
# every mercenary on the level and makes it hostile, so never on the castle level (barracks) nor with a peaceful
# watchman/soldier in view (opp_items.bugle_ok). Bugles are the commonest instrument in our dives.
BUGLE_SCARE = True
# HORN_KEEP (off): once diving, keep one horn / drum / camera in the pack (ItemPriority). Instruments are rarely shed (3
# drop messages in 180 cmp-main games) and a keep reorders a shed: on90a jf47 s0 (Mines, diving) kept one of two
# horns, dropped a second looking glass instead, and the whole game reshuffled (0.602 -> 0.117, chaos not cause).
HORN_KEEP = False
HORN_REFRESH = 15          # turns a flee (or a blow in range) holds before the horn is blown again, unless it attacks
# TENGU_EAT (parked, R159: EV <= 0): in the dive, hit a HOSTILE tengu next to us (HP >= 60%, nothing else close) and
# eat a fresh tengu corpse within 6 steps when not Satiated: eat.c cpostfx picks one of poison res / teleportitis /
# teleport control, then givit(): TC 6/12 -> 1/6 per corpse (a corpse 1 kill in 2, corpse_chance). Peaceful tengu
# (lawful: ~85% of them for our lawful Valkyrie, makemon.c peace_minded) are left alone: a peaceful kill is Luck -1
# half the time. Hostile mid-dive tengu meet ~1.6% of games; the fight costs 10-25 HP at the dive's start.
TENGU_EAT = False
TENGU_CORPSE_AGE = 25      # a tengu corpse older than this is left (CORPSE_MAX_AGE is 30)
# CASTLE_TREASURY (ON; castle_treasury.py, imported from vlomshakov f84a81b -- elite scan F075): a wall-walker on the
# castle (CFP_XORN / POLY_XORN) first walks through the walls to the four tower cells (castle.des $place: one holds a
# chest with the wand of wishing, locked 4 times in 5), opens it (key / #force with a sword / kick), takes the wand
# and names it by one zap -- that wish and the rest are WISH_TELEPORT_ROUTE's (a wall-walker may run the route with
# this flag on): TC ring + cursed teleport scrolls read on the castle -> Valley -> Dlvl ~50 (0.78-0.81) instead of
# the trap door's Valley (0.691). Budgets 240 actions / 400 turns, HP >= 45%. Their ascension wish list is not
# imported (it switched our teleport route off).
CASTLE_TREASURY = True

# ROBUST_FIXES2 (ON, robustness-audit lane): stalls found by a census of the botlogs of 5456 unique dev games
# (1047 of them since s23; $SCR/robust). Each piece acts only where the old code asserted or spun without a turn.
#  - dive_logic.go_to_mines: the Mines branch sits on another level; follow_level_path_strategy walked the whole
#    stair path in one go and asserted when the first staircase was cut off (a trap door dropped us into an unexplored
#    corner of a known level, a boulder or a peaceful on the stairs). The assert repeated every few steps: 9 of 217
#    recent seeds, 20-1950 panics, up to 10k turns (s23 cmp-main-jf45 s2: 1950 panics and ~1000 turns on Dlvl 4,
#    26k steps; jf40 s1 1315 panics on Dlvl 2). Now one staircase at a time via _take_stairs (it waits out
#    peacefuls, breaks boulders), exploring for a way when cut off, as fetch_digging_tool and tool_quest already do.
#  - agent.move: 'You are carrying too much to get through.' (hack.c test_move: a diagonal squeeze with more than
#    600 weight) passes no turn. The BFS squeezes by our own weight estimate, which misses unknown weights, so the
#    same diagonal step was planned again (s23 cmp-main-jf46 s10: 1986 refusals, 1902 panics, 250 turns on Dlvl 3).
#    The refusal now turns squeezing off until our estimate drops below what it was or SQUEEZE_REFUSED_TURNS pass
#    (short: when the squeeze is the only way on, the bot retries it once per window instead of ~8 times a turn);
#    'Your body is too large to fit through.' (a big polymorph form) likewise, for SQUEEZE_REFUSED_TURNS. And
#    _take_stairs' last step from a neighbour onto the stairs skips a refused squeeze (gen-audit ga-e1-jf46 s3: 9374
#    refusals, 238k steps on Mines 1 until the camp gave that '>' up).
#  - inventory.get_items_below_me: 'You are physically incapable of picking anything up.' (pickup.c: notake(), e.g.
#    a garter snake form from a zapped wand of polymorph) asserted on every look (cand-f jf43 s11: 329 panics over
#    535 turns on the Dlvl-28 castle level); now the pile is treated as not listable, like the other refusals.
#  - item_manager.parse_name: 'heavy iron ball' / 'iron chain' (BALL_CLASS / CHAIN_CLASS, no appearance) matched no
#    object and the category check asserted on every look at a punishment ball (lift runs: 618 panics over 630 turns
#    on Dlvl 4, 383 on the Dlvl-29 castle level) -- READ_TEST reads unknown scrolls, so punishment gets likelier.
#  - exploration_logic.open_neighbor_doors: a locked door next to us with the legs too wounded to kick
#    (agent._no_kick_until) was chosen again and again -- 'This door is locked.' passes no turn -- until the legs
#    healed (rf2-jf47 s9: 52 turn-inactivity asserts in 50 turns on Dlvl 13; 5 older seeds, ~25 each). Kicking-only
#    doors now wait for the legs.
#  - SESSILE_MEMORY (dive): the '#terrain' view (check_terrain) shows no monsters, so the memory now skips it; before,
#    a remembered mold next to us looked 'seen empty' at every terrain check and was dropped until the next look.
#  - agent.main watchdog (general): the 'turn inactivity' guard fired WATCHDOG_STREAK times within WATCHDOG_WINDOW
#    turns -> the forced turn becomes a counted search of WATCHDOG_WAIT turns (NetHack stops it when a monster comes),
#    and so does every further assert while they keep coming (loop mode):
#    a spinning strategy then costs ~10 steps per game turn instead of 200-700 (B019's castle drop loop: 502,857
#    steps, 837 s wall for 1000 turns in cand-d/e jf40 s0 -- 1M steps truncate a game). Games without such a streak
#    are unchanged.
ROBUST_FIXES2 = True
SQUEEZE_REFUSED_TURNS = 100
WATCHDOG_STREAK = 5
WATCHDOG_WINDOW = 30
WATCHDOG_WAIT = 20

# GRIND_SESSILE (off, robustness-audit lane; ledger B020): a mold/jelly/floating eye/gas spore we bump into ('Monster on
# a next tile') is remembered in the grind too (SESSILE_MEMORY runs only while diving), and the grind forgets it once
# seen empty from next to it (not in the '#terrain' view, which shows no monsters). Out of sight such a square shows
# the item under the monster, so the grind's paths went back to it: cmp-main-jf43 s10 alternated two F on Dlvl 1 for
# 14.5k turns (2444 panics, 138 faints, 0.037 -> 0.466 with the flag). Every 'Monster on a next tile' blocker in 7 debug
# replays of cand-f loop games was such a monster (green/red/yellow mold, acid blob, floating eye, gas spore).
# NOT a rare fix: grinds bump into molds often, so it reshuffles ~40% of games: 120 pinned games (cand-f + it and
# ROBUST_FIXES2 vs cand-f, jf40/42-48) 50 diverged at its first firing, mean -0.006 there; pooled -0.002 (t -0.09);
# early deaths 39 vs 39, D>=25 62 vs 63.
GRIND_SESSILE = False
# PREP_LOG (off; readiness lane, logging only): write a 'PREP {json}' state line into the dev bot log at turn
# checkpoints (every 2500 turns) and on each new deepest level of every dungeon branch -- blstats, the inventory as the
# game shows it, the bot's item knowledge (P(item is a lift / TC ring / wand of wishing ...)), intrinsics, the last
# prayer. prep/readiness.py turns those lines into the READINESS metric. prep_log.py only reads state (never steps,
# never draws a random number); runs with it on replay the flag-off games byte-identically. A no-op in the arena
# (agent.log writes nothing without JF_LOG_DIR).
PREP_LOG = False

# ---------------------------------------------------------------------------------------------------------------------
# PREP track (prep lane, all off): a better-prepared character at the castle -- measured by READINESS (prep-metric's
# readiness.py: expected passes implied by the state at castle arrival, from the team's harness evidence) with the
# progress score and early deaths as guardrails. Today (cand-g, 270 fresh pinned games jf43-60) castle arrivals are
# XL 7 / AC 0 (median), 12 of 87 carry Excalibur, 5 know a lift; a strong Valkyrie reaches the castle at XL 12-14 /
# AC <= -10 with Excalibur (ledger F084, R172, F085).
# RESULT (ledger R173, R178, R180, F087): every arm below is READINESS-neutral or worse and costs 0.04-0.07 progress on
# fresh seeds. Pass potential is item-bound (teleport control + known-cursed teleport scrolls, polymorph control + a
# polymorph source, a known lift when the castle is at Dlvl 29); strength (XL, HP, Excalibur) is worth ~0 at the castle
# for this bot, and only AC helps -- by getting past Medusa.
#
# PREP_EXCAL_XL: the lowest XL for a fountain dip (0 = the old 7). fountain.c dipfountain grants Excalibur to a lawful
# XL >= 5 hero dipping a single long sword 1 time in 6 (a fountain dries up 1 dip in 3, so ~3/8 per fountain). The bot
# waited for XL 7 (SAFE_DIPS' water-demon caution) -- but E2's DIVE_XL 7 starts the dive at XL 7 and NO_DIP_WITH_TOOL
# stops all dips once a pick is carried, so cand-g made Excalibur in 22 of 270 fresh games vs s23's 60 (same seeds).
# From XL 5 the grind's Dlvl-3 XL 5-6 stretch dips too. Excalibur (+d5 to-hit, +d10 damage, drain resistance while
# wielded) is the one piece a strong castle kit cannot drop (R172: 0/30 Valley exits without it, level drain).
# MEASURED (R173, XL 5 vs cand-g, 90 fresh pinned games jf43-48): Excalibur made 39 vs 8, but progress -0.058 (t -2.2)
# and READINESS Cprep -0.0045 (t -2.9), Cx -0.0005 (t -1.1): 7 water demons in 262 dips killed 5 XL 5-6 dippers (AC -4 demons summon more),
# water moccasins 3 more. Keep 0.
PREP_EXCAL_XL = 0
# PREP_EXCAL_DIVE: the dive dips for Excalibur at every fountain it sees within PREP_EXCAL_DIST steps on a Dungeons level
# (dive_logic.prep_fountain_dip), and the tour-style dips (dip_for_excalibur) are no longer stopped by NO_DIP_WITH_TOOL:
# the digging tool (or bare hands) goes in hand before every dip, so the dip's silent curse (fountain.c rnd(30) == 16,
# NO_DIP_WITH_TOOL's reason: a welded sword locks the pick out) can't weld the sword; the starting sword's BUC is known,
# so a curse shows and get_best_melee_weapon never wields it again. Conditions: HP >= 70%, not Weak, no hostile within
# PREP_EXCAL_CALM squares, no released water demon about. The dig-dive passes ~20 levels; the Oracle level (Dlvl 5-9)
# alone has 4 fountains (P(Excalibur) ~ 1 - (5/8)^4 = 85% when all are reached).
# MEASURED (R178, vs cand-g, 90 fresh pinned games jf43-48): Excalibur carried at castle arrival 22 of 41 vs 5 of 36,
# READINESS -0.0002 (t -0.4, neutral), progress -0.037 (t -2.45): the pre-pick dips on Dlvl 2-4 reshuffle the Mines
# trip. Off.
PREP_EXCAL_DIVE = False
PREP_EXCAL_DIST = 30
PREP_EXCAL_CALM = 7
# PREP_MID: the XP-earning middle game. With a digging tool in the pack (the way out), each main-line level from
# PREP_MID_MIN_DEPTH to PREP_MID_MAX_DEPTH is explored fully (the tour's explore1: items picked up and worn, fountains
# dipped, fights fought) while XL < PREP_MID_XL, up to PREP_MID_TURNS turns per level and until turn PREP_MID_TURN_CAP;
# then the dig-dive goes on as before. A level is left at once (dig_first digs out) at a danger: HP below
# PREP_MID_ESCAPE_HP, PREP_MID_CROWD+ hostiles within 6, a boss kind, anything that fights through Elbereth (@ humans
# and elves, minotaurs), or a monster of difficulty above XL + PREP_MID_DIFF. Why: castle arrivals are XL 7 / HPmax 77
# / AC 0 (s23 median, ledger F084); a strong castle kit is XL 12-14 / AC -10 / Excalibur (R172, F085), and astra's
# real dwarven Valkyrie mapped every level to reach the castle at XL 12 / AC -10 by T21.6k.
# MEASURED (R180, with PREP_EXCAL_DIVE + ARMOR_UP vs cand-g, 90 fresh pinned games jf43-48): castle arrivals XL 8 vs 7,
# HPmax 82 vs 77, AC unchanged; 1 death per 10k turns on the band for ~+0.5 XL per game (Elvenking, elves, wolves,
# wargs, leocrotta, gargoyle...); early deaths 37 vs 25, progress -0.070 (t -3.15), READINESS -0.0003 (neutral). At
# XL 7-8 / AC ~0 Dlvl 5-12 spawns are too strong to farm and too weak to level on (as DIVE_SUPPLY R081, F042). Off.
PREP_MID = False
PREP_MID_MIN_DEPTH = 5
PREP_MID_MAX_DEPTH = 12
PREP_MID_XL = 10
PREP_MID_TURNS = 1500
PREP_MID_TURN_CAP = 30000
PREP_MID_ESCAPE_HP = 0.4
PREP_MID_CROWD = 3
PREP_MID_DIFF = 2
# PREP_DIVE_PICKUP: the dig-dive picks up the rings, wands, amulets, potions and scrolls it sees within PREP_PICKUP_DIST
# steps (Dungeons/Mines levels down to PREP_PICKUP_MAX_DEPTH, above Medusa; no hostile within 7, HP >= 60%, not Weak,
# never in a shop; arrange_items' item priority decides what stays -- dive_logic.prep_dive_pickup). The dive never ran
# item pickup, so a castle kit is ~all from the Dlvl 1-3 grind (cand-g castle arrivals: 0.9 rings, 4.6 potions, 5.4
# scrolls, 1.8 wands, 5 of 87 with a known lift). Each unknown potion is levitation 4.2% of the time, each ring
# levitation or teleport control 1/28 each, each wand cold 4% -- and the castle's lift plan tries unknown ones.
# MEASURED: the dig-dive lands and digs within a few turns and almost never has such an item in view (1 level with any
# candidate in a whole jf43 s0 game, 40+ steps away), so this adds ~nothing. Off.
PREP_DIVE_PICKUP = False
PREP_PICKUP_DIST = 12
PREP_PICKUP_MAX_DEPTH = 20
# CP_POLY (castle-poly, castle_poly.py; needs CASTLE_POLY): the random-polymorph castle route (READINESS Y). Census F094:
# 17 of the 105 cand-g castle arrivals (jf43-60) held a polymorph source (7 wands, all known to the bot; 7 potions; 5
# rings), 7 at a Dlvl-29 castle, none passed: the wand was zapped where we landed and every crossing form it drew
# (crocodile, cobra, queen bee, orc mummy, straw golem) stayed in the west maze -- a form without hands can't dig to the
# water -- fighting until it died; a stuck ring's forms came after the passage was given up. With CP_POLY the wand is
# zapped on the courtyard's test square (one step from the moat's mouths), forms that can't make the crossing
# (no water movement, eyeless, speed < CP_MIN_SPEED, HP < CP_GOOD_HP while the wand can re-roll) are re-rolled, a
# usable form in the maze walks (no digging) to the courtyard and takes a given-up passage back.
CP_POLY = False
CP_MIN_SPEED = 6        # slower forms (molds, jellies, mimics, floating eyes: speed 0-3) re-roll
CP_GOOD_HP = 20         # form HP below this re-rolls while the wand has charges (a shark bites 5d6)
CP_ZAP_MIN_HP = 31      # own-form HP for a self-zap with nothing next to us (system shock: rnd(30) of OUR HP)
CP_MAX_ZAPS = 12        # self-zaps per castle visit (the wand runs dry first: 4-8 charges)
# CP_WALL_REROLL: castles above Dlvl 29 (a crossing reaches a Valley at depth <= 29: +1 level, no pass): up to this many
# extra zaps for a wall-walker (xorn / earth elemental: CFP_XORN + VALLEY_XORN pass at any depth; 0.5% per zap) before
# a plain crossing form is taken
CP_WALL_REROLL = 0
# CP_DOOR_REZAP: on the east side a form that can't kick the locked back door and has no door wand zaps the wand of
# polymorph at itself from SAFE_EAST (newman 1 in 5; most forms have legs) instead of waiting out a 500-1000 turn form
CP_DOOR_REZAP = False
# CP_V2 (needs CP_POLY): v1's paired harness (real census poly kits x 6 salts, 102 games per arm) was 0 passes vs 1 off.
# Its logs: (1) small forms carry ~nothing (weight.c carrycap x cwt/1450: a queen bee 0) -- a 39-HP queen bee sat
# Overloaded 5 turns in the courtyard until a minotaur came, a chickatrice looped 'You can't do that while carrying so
# much stuff' (zap.c check_capacity refuses at Overtaxed); (2) CFP's own self-zap (_poly_now, when an unknown ring 'may
# be polymorph control') still fired where we landed; (3) CP_GOOD_HP judged the current HP, re-rolling hurt flyers.
# V2: a usable form drops its pack (heaviest first) to Burdened at most -- an amphibious form can't climb out of the
# water above that (hack.c domove SLT_ENCUMBER) -- keeping the wand of polymorph, door wands and unlocking tools while the
# form can carry them; CFP's landing self-zap defers to CP; a form is judged by its birth HP (max_hitpoints).
CP_V2 = False
# CP_LAUNCH (needs CP_V2 and CL_ROUTE's planner): in our own form walk/dig castle-lift's cl_route to the launch square of
# the cheapest FAR channel entry ((0,1)/(0,15): castle-lift's harness crossings passed 11/18 and 8/19 from there vs 2/38
# from the courtyard mouth (0,5), where the west sharks settle), write Elbereth and zap there; a usable crossing form then
# steps straight onto that water square and castle_logic's crossing takes it on.
CP_LAUNCH = False
# CP_WATER (needs CP_POLY; castle_poly.water_strategy): a form's death over the moat returns us to our own form IN the
# water and the channels have no land to crawl to -- cp-syn29-v2l (21 castle-29 wand kits): 4 drowned so (a 20-HP straw
# golem bitten twice by the far channel's shark, a 50-HP baby red dragon under a tower xorn + a shark). Below
# CP_WATER_FRAC of its HP a form over water steps onto dry land next to it, else zaps the wand again (1 form in 3 is
# water-safe); on the dry strip (rows 0/16) a hurt form or our own form zaps again (own form on Elbereth).
CP_WATER = False
CP_WATER_FRAC = 0.5
# DEEP_ITEMS (ON, deep-arrivals, ledger F095; dive_logic.deep_items_strategy): on Medusa's level, the kit's scare and
# cure items before the next dig or Elbereth. cand-g's 45 Medusa deaths on fresh jf43-60 were mostly the pick-only
# flood lottery and the Medusa-3 raven swarm (M3 passes 41% vs its 0.54-0.57 flood-only ceiling, F074), but 7 of them
# held an item that answers the swarm and never used it: a KNOWN scroll of scare monster (jf53 s2 raven, jf52 s5
# snakes, jf59 s5), a bugle (jf58 s7), an unknown horn (jf47 s0, jf47 s12, jf59 s12: tooled 5/11, frost 2/11), two
# unicorn horns through raven blindness (jf53 s2), two scrolls of charging beside an empty wand of digging (jf59 s5).
#  - blind: a unicorn horn not known cursed (apply.c use_unihorn: an uncursed one fixes blindness ~65% of the time)
#    -- a raven's claw re-blinds for d6 per hit, and a blind dust Elbereth holds 1 time in 3 (engrave.c);
#  - hostiles pressing (one adjacent, two within 2, or blind and hurt): a scare instrument (music.c: a tooled horn,
#    a drum or a bugle makes every MR-0 monster within ~XL*10 distu flee with no timer -- ravens, snakes, eels) blown
#    again after HORN_REFRESH turns or a hit; an unknown horn is improvised, its ray (a frost or fire horn) aimed at
#    a moat neighbour (frost: 'The water freezes', a flood roll less; the horn is then MEDUSA_FREEZE's cold source);
#  - a KNOWN scroll of scare monster dropped on the square we are about to dig (or, blind and hurt, where we stand):
#    monmove.c onscary counts a scroll on the square for every monster but Rodney/minions/Angels/Riders, and unlike
#    a dust Elbereth the pit doesn't delete it (dig.c del_engr_at only removes engravings). We rest on it while blind
#    or below DEEP_ITEMS_REST_UNTIL HP (at most DEEP_ITEMS_REST_MAX turns, and not while something still hurts us),
#    then dig from it;
#  - anywhere in the dive, at a quiet moment: a scroll of charging (not known cursed) on a known wand of digging that
#    is known empty or down to 1 charge (read.c recharge: blessed 4-8 charges, uncursed 1-8; each zap on Medusa's
#    level is one flood roll instead of the pick's two).
DEEP_ITEMS = True
DEEP_ITEMS_REST_UNTIL = 0.6
DEEP_ITEMS_REST_MAX = 150
DEEP_ITEMS_UNIHORN_TRIES = 3   # unicorn horn applications per blind spell
# DEEP_BLIND_LOOK (ON, deep-arrivals, F095): WR_BLIND_LOOK's floor-look skip while blind in the dive, at depth >=
# DEEP_BLIND_LOOK_DEPTH only. 34 of cand-g's 45 fresh Medusa deaths spent 3-12 of their last 50 turns on blind ':'
# looks (invent.c look_here returns !!Blind: a whole turn, and no dust engraving is read), so each blind Elbereth
# cost two turns. WR_BLIND_LOOK everywhere was neutral (R183: the Mines' blind moments reshuffle games); its Dlvl>=21
# subset was 6 better / 4 worse, net +0.23 over 46 diverged games. Deep only, a game is unchanged until its first blind
# moment below Dlvl 20.
DEEP_BLIND_LOOK = True
DEEP_BLIND_LOOK_DEPTH = 21
# RAVEN_GAP (off, deep-arrivals, F095): on Medusa-3, before a fresh pit on the chosen dig square, stay on our intact
# (read-back) Elbereth while a raven is within RAVEN_GAP_RADIUS, at most RAVEN_GAP_MAX turns per square. Why: the pit
# deletes the engraving (dig.c del_engr_at) and a flood (1 - 1/(k+1) per roll, k >= 1 everywhere on the island) puts
# us on a fresh square with none, and a raven next to us then gets a free round -- 8 of cand-g's 13 raven deaths were
# first blinded in the round right after a flood's crawl-out (jf46 s9, jf47 s0, jf45 s7, jf56 s12, jf58 s7, jf59 s6)
# or in the fresh pit (jf47 s4). Ravens flee an Elbereth (monflee rnd(10), 3 in 10 rnd(100)) and fly off; a raven 4+
# squares away needs 2+ turns to come back (speed 20).
RAVEN_GAP = False
RAVEN_GAP_RADIUS = 3
RAVEN_GAP_MAX = 12
# PARKED (harness, F097): M3 pick-only 20 -> 18 of 49 with RAVEN_GAP -- waiting lets ravens gather, and the flood
# lottery, not the ravens, caps Medusa-3.
# DEEP_WAND_TEST (off, deep-arrivals, F097 follow-up): WAND_ENGRAVE_TEXT's quiet-moment dive test also takes wands that
# were never engrave-tested at all (inventory.wand_retest_wanted). 18 unknown wands at cand-g's 171 Medusa arrivals had
# no engrave test (jf53 s1, jf55 s7 uranium, jf47 s4 marble...); digging (5.5% of wands) names itself on the test and
# cold (4%) says 'ice cubes' -- the flood-reducers that lift Medusa-3 in the harness (charging an empty wand of digging
# 18 -> 34 of 49, a frost horn 21 -> 33 of 49). Small (~1 flood-reducer per 270 games), cheap.
DEEP_WAND_TEST = False

# ---------------------------------------------------------------------------------------------------------------
# dive-audit lane (2026-09-30; ledger F092): a death-by-death review of cand-g's 53 fresh deaths at max depth 5-20
# (cand-g = s24 = 6ec6675, 270 pinned games jf43-60). Every flag below is ON (adopted in s25).
# Measured together (da-all3: 270 fresh pinned games, these four and WELD_PRAY on vs cand-g): +0.0127 mean progress
# (paired t 2.12), deaths at max depth 5-20 41 vs 53, castle arrivals 91 vs 87. By the flag that acted at the first
# divergence: KNOWN_ITEMS +0.52 over 45 games, WELD_PRAY/WELD_HOLD +1.14 over 10, SHOP_DIG +1.21 over 6,
# ELBERETH_FUTILE +0.55 over 7.
#
# KNOWN_ITEMS (known_items.py): in mortal danger while diving, use the KNOWN item that ends it -- a scroll of
# teleportation, a wand of teleportation at ourselves, a wand of digging down, a potion of full/extra healing, a wand
# of sleep / striking / cold / fire at the attacker -- before emergency_strategy's last resort gambles on UNKNOWN ones.
# 77 of the 171 cand-g deaths with an inventory log (prep-metric's PREP_LOG twins, jf43-54) held a known escape or
# attack item they never used (~30 scrolls of teleportation, ~15 wands of striking): the last resort only tries unknown
# wands, potions and scrolls; fight2 zaps only rays (never striking, never sleep); nothing reads a known teleport scroll.
# Examples: jf45 s14 (a mumak: 79 -> 43 -> 15 -> dead, a known wand of sleep and a blessed scroll of teleportation in
# the pack), jf52 s9 (a soldier ant while blind, 2 uncursed scrolls of teleportation), jf54 s14 (killer bees while
# blind: a scroll of teleportation, wands of cold and fire), jf49 s7 (stuck to a giant mimic: a scroll of teleportation),
# jf48 s8 (a soldier: a scroll of teleportation). Danger = a hostile next to us and either critically low HP (the last
# resort's own trigger) or a burst: we lost at least our remaining HP over the last KNOWN_ITEMS_BURST_TURNS turns and
# are below KNOWN_ITEMS_BURST_FRAC of max HP -- a mumak, soldier ant or elf-lord takes 20-40 a turn, so jf45 s14 went
# 43 -> 15 -> dead without ever being inside the last resort's window. A due emergency prayer always goes first.
KNOWN_ITEMS = True
KNOWN_ITEMS_BURST_TURNS = 2
KNOWN_ITEMS_BURST_FRAC = 0.5
KNOWN_ITEMS_RAY_RUN = 6      # free squares behind the target before a sleep/fire/lightning ray is safe from its bounce
#
# WELD_HOLD (with WELD_PRAY): welded to a cursed two-hander while diving (the first apply of a dwarvish mattock of
# unknown BUC: 14% of dwarves' weapons are cursed) -> no free hand, so no Elbereth for the rest of the dive (engrave.c
# freehand), and the Valkyrie's pick-axe skill starts Unskilled. cand-g: 10 of 197 diggers welded a mattock, mean 0.270
# vs 0.510 for the rest; 7 of the 10 died at Dlvl <= 20 (vs 12 of 185): jf43 s13 (a jaguar, 2 hits in 10), jf47 s10
# (an ice troll), jf48 s10 and jf53 s9 (a quasit, killer bees), jf50 s7 (a troll), jf56 s5. Two others got the mattock
# uncursed by a later Weak/HP prayer (pray.c fix_worst_trouble: TROUBLE_UNUSEABLE_HANDS is major trouble). WELD_PRAY
# (off after t36: it prayed only once WELD_PRAY_GAP had passed, and the dive dug on welded until then -- jf48 s10 and
# jf50 s7 welded at gaps 864 and 805 and died 65 and 60 turns later, Dlvl 8 and 11) is now ON, paired with a hold: while
# welded, not deeper than WELD_HOLD_MAX_DEPTH, the dive neither descends nor digs out (dig_first) until WELD_PRAY's
# prayer frees the hands, a prayer fails or comes without freeing them (a Weak prayer fixes hunger first: pray.c ranks
# TROUBLE_STARVING above TROUBLE_UNUSEABLE_HANDS), or WELD_HOLD_MAX_WAIT turns pass; fight2 and the emergency prayer act
# as usual. Pinned replays of the 8 welded cand-g games (19b5f85, WELD_PRAY + WELD_HOLD): 0.262 -> 0.394 mean; jf43 s13
# 0.206 -> 0.466, jf47 s10 0.379 -> 0.554, jf48 s4 0.393 -> 0.647, jf53 s9 0.126 -> 0.445, jf56 s5 0.292 -> 0.466;
# jf50 s7 0.161 -> 0.051 and jf48 s10 0.075 -> 0.075 held on after a hunger prayer left the weld (now ends the hold).
WELD_HOLD = True
WELD_HOLD_MAX_DEPTH = 12
WELD_HOLD_MAX_WAIT = 1500
#
# SHOP_DIG: fell into a shop with a digging tool while diving -- its shopkeeper holds the door against a pick
# (shk.c shk_move: badinv, satdoor) and the dive never digs in a shop, so the game sat there until it starved or was
# killed: jf46 s13 (9324 turns on Dlvl 14, starved to a barrow wight), jf50 s6 (4210 turns on Dlvl 8), jf60 s6 (3135
# turns on Dlvl 9), jf43 s8 (4229 turns on Dlvl 18); 64 shop landings in the 270 games. A hole in a shop floor costs
# nothing without a bill (shk.c shopdig(1) grabs the pack only with billct or debit) and nothing falls with us from an
# empty square (dokick.c impact_drop: goods on the hole's square are stolen, the shopkeeper chases us): so, with
# nothing unpaid in the pack and no diggable square outside the shop within reach, dig down from an empty shop square.
# Pinned replays of the 4 stalled games (19b5f85): jf46 s13 0.292 -> 0.602, jf50 s6 0.075 -> 0.445, jf60 s6 0.098 ->
# 0.445, jf43 s8 unchanged. Only after SHOP_DIG_AFTER turns inside the shop: 60 of the 64 shop landings walked out
# within 30-230 turns, and digging at once there only reshuffled those games (da-all1 jf43-48: 17 firings, net -0.12).
SHOP_DIG = True
SHOP_DIG_AFTER = 300
#
# ELBERETH_FUTILE: no Elbereth while hallucinating (agent.can_engrave): engrave.c garbles every letter 1 time in 2 while
# hallucinating besides the dust's 1 in 25, so 'Elbereth' comes out whole ~0.3% of the time and each try is a turn
# handed to whatever is attacking. cand-g jf49 s12 (a black light's blast on Dlvl 11) engraved 6 times in 6 turns under a
# soldier ant, 63 -> 0 HP (replay: 0.206 -> 0.507); 5 of 270 games were killed while hallucinating. The first version
# also blocked it while stunned (1 in 4 per letter, ~7% whole): 30 stunned blocks in da-all2's 270 games, no gain.
ELBERETH_FUTILE = True
#
# --- arrivals-2: the tool-less Mines trip (cand-i census: 44 of 420 fresh games die in the Mines before any pick) ---
# SQUEEZE_DIAG (logging only, off): while diving, every 100 turns in the Gnomish Mines (elsewhere only when it matters),
# log the carried weight and what the BFS reaches with and without diagonal squeezes (hack.c cant_squeeze_thru: > 600
# carried refuses a diagonal step between two rock/wall squares), plus the distance to the level's '<' and '>' both
# ways. Replay-only diagnostics: it reads the agent and runs two uncached BFS, nothing else.
SQUEEZE_DIAG = False
# SQUEEZE_OUT (ON): UNSQUEEZE's drop to the squeeze cap (agent.unsqueeze: worn/wielded/digging tool first, then
# SQUEEZE_KEEP's wands/rings/amulets and known lifts/heals/teleports) also on a Mines level where the weight cuts the
# dive off from part of the level -- not only when boxed in on <= 5 squares. SQUEEZE_DIAG replays of 60 cand-i games
# (jf51/61/66/67, byte-identical): the pack weighs > 600 in 67% of the Mines samples (median 737; the tool-less trip
# keeps the grind's loot, a pick adds 100-120), so every diagonal squeeze of a Mines cave is a wall; 15 of the 60
# games had a Mines level whose staircase was reachable only by squeezing (F1), a squeeze-only region with a
# staircase still unknown (F2) or a pocket (F3), and 9 of those 15 died in the Mines. jf51 s10 held its pick 11,000
# turns on Mines 4 with the '<' behind a squeeze (-1 vs 26 steps with one), jf51 s11 sat 20,000 turns in an
# 11-square Mines-1 pocket (79-727 squares with squeezes), jf61 s0's camp never found Mines 1's '>' behind a squeeze
# region and died there after 8000 turns (fainting, a failed prayer, a fire ant). Checked every SQUEEZE_OUT_EVERY
# turns once this visit to the level has lasted SQUEEZE_OUT_TURNS, twice in a row before the drop.
SQUEEZE_OUT = True
SQUEEZE_OUT_TURNS = 2000  # ...only once this visit to the level has lasted this long (guard a2-g1: 100 fired in 8 of
                          # 90 games, 0 better / 4 worse -- transient cut-offs; a2-g3: 1000 still fired in jf48 s5, whose
                          # camp found its '>' 290 turns later; the Mines deaths sat 3,000-18,000 turns)
SQUEEZE_OUT_EVERY = 50
SQUEEZE_OUT_MIN = 15      # F2: squares reachable only by squeezing
# RETURN_DIG (ON): climbing out of the Mines with a digging tool (dive_logic.return_to_main_dungeon), the '<' has been
# unreachable or unknown for RETURN_DIG_TURNS -> tunnel toward it (or toward the nearest large unexplored area) with the
# tool, one square per call (dive_logic._return_dig/_dig_toward; never in Minetown, never a shop wall). SQUEEZE_OUT can't
# free these: worn armour + the tool are the 'essentials' and often weigh > 540 alone. cand-i: 164 dives took a pick in
# the Mines and 39 needed >= 300 turns to get back to the main dungeon; 5 never did and died there -- jf66 s10 (Mines 2's
# '<' never found in 18,000 turns after a trap-door fall), jf51 s7 (a trap door in the 1-wide passage to the '<',
# CLIMB_NO_FALL, 6,700 turns), jf65 s0 (trap door, 9,600 turns), jf44 s1, jf66 s2; SQUEEZE_OUT replay jf61 s0 got its pick
# and then sat 10,500 turns on Mines 1 below a '<' reachable only by squeezing (plate/mithril + pick > 600).
RETURN_DIG = True
RETURN_DIG_TURNS = 1000   # cut off, and on the level (this visit), this long: 125 of 164 cand-i pick returns took < 300
                          # turns, 20 more < 1000; the stuck ones sat 1,500-18,000
# TRAP_OUT (ON): a Mines staircase still cut off while SAFE_TRAP_WALK has the safe traps open (dive_logic._trap_out):
# after TRAP_OUT_TURNS rust and anti-magic traps become walkable too (UNSAFE_TRAPS kept them shut for good; for a
# Valkyrie a rust trap corrodes one iron item, an anti-magic field drains unused Pw), after TRAP_OUT_FALL_TURNS and
# climbing without a digging tool, trap doors and holes too (CLIMB_NO_FALL shut them for good; a seen one is escaped 1
# time in 5, a fall costs one Mines level). SQUEEZE_DIAG replays: cand-i jf53 s4's camp sat 8,700 turns in a Mines-3
# pocket shut by an anti-magic trap ('You feel your magical energy drain away' on the way in), died fainting; jf69 s9
# (7,700 turns: trap door + rust + anti-magic), jf68 s0 (2,900: anti-magic + trap door), jf68 s2 (14,000 turns on
# Mines 2, 'known trap doors/holes stay closed (CLIMB_NO_FALL)'), all Mines deaths.
TRAP_OUT = True
TRAP_OUT_TURNS = 1000       # on the level this visit (guard a2-g1: 300 turns fired in games that were not stuck for long)
TRAP_OUT_FALL_TURNS = 2000
#
# --- camp-food: the tool-less Mines trip eats its own kills (ledger F108) ---
# CAMP_EAT (off): while diving in the Gnomish Mines (the tool-less trip and its camp, and a pick-holder on its way back
# out), walk to the fresh corpses of our kills and eat them whenever not Satiated, as the tour's CLAIM_CORPSES does, and
# record the kill squares with CORPSE_TRACK there too. Both are tour-only otherwise, so the dive eats only a corpse it
# happens to stand on. a2-g4 (420 fresh pinned games jf43-70): 219 tool-less Mines trips, 664k turns; we kill 16.8
# monsters per 1k turns, whose edible corpses (the rules below; mon.c corpse_chance) hold ~900 nutrition per 1k; we ate
# ~390 of it underfoot and left ~505 per 1k turns, about half of what the trip burns (its hunger prayers: 0.58 per 1k).
# 160 Fainting spells there: the hunger cycle before each left 686 nutrition of our uneaten kills on average, and all 7
# tool-less fainting deaths left 300-2500 -- jf48 s6 an owlbear (700) killed while Hungry, then fainted to death by a
# scorpion; jf50 s2 a crocodile, a jaguar and a lizard, then a failed gap-898 hunger prayer; jf53 s2 four rothes and a
# winter wolf, then an HP prayer reset its prayer clock. Only a quarter of that food came from kills made while Hungry or
# worse (3 of the 7 deaths made none), so the walk does not wait for hunger. (DIVE_EAT, R019/R036: every dive, Hungry
# only, no kill tracking -- neutral in train 2.) One-seed replays of the 8 Mines fainting deaths (cf-on1, pinned):
# faints 86 -> 2, corpse nutrition eaten 226 -> 465 per 1k Mines turns, hunger prayers 0.47 -> 0.36 per 1k; 4 of the 8
# got a pick and reached Dlvl 22-26 (0.075-0.117 -> 0.408-0.507), 2 did worse (jf48 s6 0.179 -> 0.117 and jf66 s2
# 0.117 -> 0.075: later fights in reshuffled games).
# The pet: gone by the dive in nearly every game (it ate 2 of the trips' ~3,200 expected edible kill corpses in a2-g4).
# Guard (fresh pinned sets jf97-114, 270 games, fa9fdea + CAMP_EAT vs main a1b6670 defaults; ledger R218):
# progress +0.0057 (se 0.011, t 0.52; 9 sets up, 9 down; 140 games identical, 0 failures); in the 143 tool-less Mines
# trips Fainting spells 111 -> 68, faint messages 435 -> 224, hunger prayers 0.47 -> 0.36 per 1k trip turns (median
# gap 1198 -> 1400), prayer failures 7 -> 3, trip deaths 25 -> 21 (fainting deaths 10 -> 7), tools 110 -> 116; Mines
# deaths 33 -> 27, but castle arrivals 105 -> 102 (the extra survivors died deeper); READINESS Cx +0.0000 (t 0.02).
# Meals took 7.3% of the trip's turns vs 7.7% before (they replace underfoot meals and fainting). The mechanism works;
# the score gain is below what 270 games can see.
# The meal: agent._is_corpse_editable as everywhere (never a dwarf -- cannibalism for a dwarf hero, eat.c
# maybe_cannibal; no poisonous or acidic corpse unless Weak with HP > 40 (STARVING_EATS); no were, cockatrice,
# mimic, bats, dogs/cats; none older than CORPSE_MAX_AGE); a stack of two same-kind corpses (merged age) is left.
# The walk: at most CAMP_EAT_DIST BFS steps (known traps, water and peacefuls closed; none while the BFS has traps open
# after a stuck dive), to a kill at most CAMP_EAT_MAX_AGE turns old whose square shows that corpse right now (most
# kinds leave one only 1/4-1/2 of the time), off shop squares and known traps, and worth CAMP_EAT_MIN_NUT; not while a
# peaceful dwarf worth hunting is in view or a digging tool is being fetched (unless Weak: a dwarf walks off with a
# pick-axe), nor levitating, blind, hallucinating or polymorphed. A walk that finds nothing to eat on arrival (a stack,
# a pet's meal) drops the kill's record, so it is not repeated.
CAMP_EAT = False
CAMP_EAT_DIST = 6
CAMP_EAT_MAX_AGE = 20       # + the walk stays under CORPSE_MAX_AGE (30) at the meal
CAMP_EAT_MIN_NUT = 20       # killer bees, soldier ants (5) and giant ants (10) are not worth a walk (a floating eye is:
                            # telepathy)
CAMP_EAT_MIN_HUNGER = 1     # glyph.Hunger: 1 = Not Hungry (anything but Satiated), 2 = Hungry
#
# --- medusa-supply: flood reducers carried to Medusa's level (ledger F109) ---
# DIG_WAND_THRIFT (0 = off): above Medusa's level, with a pick-axe or mattock to dig with, the known wand of digging
# keeps its charges for Medusa's level (a zap rolls dig.c fillholetyp once, the pick twice) and the mazes below it
# (WAND_RESERVE's arrival zap against their minotaurs). WAND_RESERVE already holds WAND_FIRST's zap until an
# emergency (HP < WAND_RESERVE_HP with a hostile within 2), but two of dig_first's escapes zapped past it:
#  1 (level 1+): never a zap with a level follower next to us. dog.c keepdogs takes every adjacent M2_STALK monster
#    that isn't fleeing (mondata.c levl_follower) down the hole with us, and it lands next to us again: the zap buys
#    nothing and the next level's escape zaps again. KNOWN_ITEMS already refuses its zapdown then (jf47 s10's ice
#    troll followed three holes). cand-i-jf55 s6: soldiers followed 8 zaps Dlvl 10-17 until 'Nothing happens';
#    cand-i-jf60 s8: 9 zaps Dlvl 15-23; s25-jf93 s7: a homunculus followed 5 zaps Dlvl 9-13 (HP 41/102 kept the
#    emergency on), and the game drowned on Medusa-3 digging with its mattock beside the empty wand. The same for any
#    hostile next to us within DIG_WAND_THRIFT_CHAIN turns of our last escape hole (a follower we can't name: that
#    replay's homunculus showed as an unseen 'unknown' and emptied the wand again), and for an emergency made only by
#    a lichen, newt, shrieker or grid bug (combat WEAK_MONSTERS: cand-i-jf55 s6's replay zapped at a newt at 25/79).
#  2 (level 2): an @ within 2 (_melee_ignores_elbereth; a minotaur still gets the zap) or a bite with no Elbereth to
#    be had zaps only in WAND_RESERVE's emergency, like WAND_FIRST: until then fight2 fights it, as a diver without
#    the wand does. 29 of the 63 pick-holder zaps above Medusa were a single Woodland/Green/Grey-elf, were@, nurse or
#    soldier within 2 at full HP; 8 of those games later ran the wand dry on Medusa's level (cand-i-jf44 s7, jf66 s12:
#    drowned / ravens after 2-3 floods) or in the mazes below it (cand-i-jf45 s4, jf62 s1, jf66 s7: minotaurs).
# Census (720 fresh pinned games s25-jf79..96 + cand-i-jf43..72, $SCR/msupply): 456 Medusa arrivals; a usable flood
# reducer at 23 of 119 Medusa-3 and 16 of 119 Medusa-4 arrivals, nearly all wands of digging (pass 65% vs 46% without
# on M3, 81% vs 61% on M4); Medusa zaps 90: 50 holes, 35 floods, 5 empty. Pick-less dives (the wand is their only
# digging tool: 68 dig-downs, 55 escapes, 15 last resorts) and the last resort / KNOWN_ITEMS / mino_guard are unchanged.
DIG_WAND_THRIFT = 0
DIG_WAND_THRIFT_CHAIN = 10   # turns after an escape hole in which a hostile next to us counts as a follower
#
# --- bug-hunter: loops and stalls that waste whole games (ledger B023+) ---
# EARTH_BOX (off): boulders on every side and nothing else in reach -> push one out (agent.unbox_boulders). read.c
# SCR_EARTH (uncursed) drops a boulder on each of the 8 squares around us and one on our own square; the BFS never
# enters a boulder square, so the bot sees its own square as the whole level and stays there for good: every task
# after that ('descend', 'tool quest', 'home level: search for its digger') finds no target and searches in place. The
# dive's TC_DIVE_ID reads unknown scroll stacks at quiet moments, and the last resort reads unknown scrolls. A digging
# tool does not help as coded: the boulder under us makes dig.c dig_check refuse the hole ('There isn't enough room to
# dig in here'). Fresh sets (2490 games, 1421 unique, 15 earth reads): cand-i-jf71 s9 (XL-7 dive on Dlvl 2: boxed
# 42,000 turns, starved, 0.051), cf-mb-jf105 s8 (a pick-axe in hand, Dlvl 3: 24,000 turns, starved, 0.051),
# cand-k-jf80 s6 (Dlvl 4: 2,400 turns, killed there, 0.075), cand-k-jf96 s7 (Dlvl 27, a mattock in hand: 7,100
# turns, killed there, 0.554), a2-g4-jf44 s12 (Dlvl 3: boxed 4,800 turns, then died on Dlvl 4, 0.051). In jf71 s9
# the boulders west and east of us had open floor behind them: one push frees the way (hack.c moverock: a boulder
# moves on unless rock, a wall, iron bars, another boulder or a monster is behind it, and not diagonally through a
# doorway; a refused push takes no time). Rule: boxed (the BFS reaches <= EARTH_BOX_REACH squares with 2+ boulders
# next to them, or 1 square beside a boulder; the same pocket for EARTH_BOX_WAIT turns) -> push the boulder whose
# square, once open, reaches the most ground; else break one with a digging tool (dig.c: a pick applied at a boulder
# breaks it in a few turns); else, boxed on one square with every neighbour rock or a boulder the game refused to move
# (pray.c TROUBLE_STUCK_IN_WALL, a major trouble: the god teleports us out), pray once it is safe. A first version
# (reach <= 4, one boulder enough, 5 turns) fired in an ordinary Dlvl-3 walk of jf96 s7 (a monster held a corridor).
EARTH_BOX = False
EARTH_BOX_REACH = 4           # boxed: the BFS reaches at most this many squares (cand-k-jf96 s7's first push left a
                              # 2-square pocket in a maze corridor, boulders at both ends)
EARTH_BOX_WAIT = 20           # the same pocket this many turns first (a pet or monster in the way moves on by itself)
EARTH_BOX_PRAY_GAP = 1000     # the stuck prayer: at least this many turns since the last prayer (rnz(350) tail)
# TRAP_CHOKE (off): a known trap of a kind the BFS never walks (agent.UNSAFE_TRAPS stay shut even when AutoAscend
# relents on traps, SAFE_TRAP_WALK) can seal the only way between us and every staircase of the level, for good: the
# tour has no trap fallback at all (TRAP_LAST_RESORT is dive-only), and the dive's opens only the safe kinds. Fresh sets:
# cand-i-jf70 s5 (Dlvl 1 grind: an anti-magic field just inside the only door of a dead-end corridor it had explored;
# 342,000 turns in that corridor with the '>' in view, 267 prayers, starved at XL 5, 0.029) and cand-i-jf66 s4 (Dlvl 1:
# a rust trap on the only square in front of a room's only door; 70,000 turns in the two rooms behind it, starved,
# 0.037); both replay byte-identically on main 6056954. For a Valkyrie without magic resistance an anti-magic field only
# drains energy (trap.c ANTI_MAGIC: drain_en; 1d4 HP with MR), and a rust trap rusts one iron item. Rule (main dungeon,
# checked every 25 turns): every known staircase of the level unreachable, but reachable with the TRAP_CHOKE_MILD kinds
# open, for TRAP_CHOKE_TURNS -> the BFS walks those kinds on this level; still cut off after TRAP_CHOKE_HARD_TURNS and
# the TRAP_CHOKE_HARD kinds reconnect -> those too (a burnt scroll or a nap beats starving). Polymorph traps never.
TRAP_CHOKE = False
TRAP_CHOKE_TURNS = 500
TRAP_CHOKE_HARD_TURNS = 3000
# SESSILE_LOOP (off): ledger B020's grind loop -- a path through the square of a mold/jelly/floating eye/gas spore
# (fight2 never melees them; out of sight the square shows what lies under it) ends in 'Monster on a next tile', the
# strategy restarts, and the next path goes the same way. GRIND_SESSILE (off) remembers every such blocker at the first
# bump, which fixes the loop but reshuffles ~40% of games (R164). This remembers a square only after
# SESSILE_LOOP_BUMPS bumps within SESSILE_LOOP_TURNS (the tour only; the dive has SESSILE_MEMORY). Fresh sets (1421
# unique games): 175 with 20+ such panics in the tour, 49 with a 500+ turn burst, 0 in the dive; cand-k-jf79 s9 (1572
# panics, 13,000 turns in one corner of Dlvl 1, starved, 0.037), cf-mb-jf105 s7 (947 panics, a red mold, starved at
# XL 4, 0.024), da-all3-jf43 s10 (3033 panics over 28,000 turns).
SESSILE_LOOP = False
SESSILE_LOOP_BUMPS = 8
SESSILE_LOOP_TURNS = 400
#
# --- chokepoint: fight a pack from a corridor (chokepoint.py) ---
# CHOKEPOINT (off, being measured): when a pack comes at us (CHOKE_MIN_NEAR melee hostiles within CHOKE_NEAR_RADIUS or
# CHOKE_MIN_VIEW within CHOKE_VIEW_RADIUS) and we stand in the open, fight2 walks to a known square within CHOKE_STEPS
# that the pack can reach through at most CHOKE_MAX_FACING of its neighbours (a straight corridor, a Mines passage, the
# corridor square outside a door, the room square inside the door the pack comes through) and holds it, so the pack
# meets us one or two at a time (mon.c monnear: melee needs an adjacent square; doorways stop only movement).
# Multi-monster fights are a killer in every band (F090: 12 of 36 grind deaths were XL5-6 pack fights; F092: Mines camp
# combat, @ crowds, soldier ants, killer bees). Details and the exclusions in chokepoint.py.
CHOKEPOINT = False
CHOKE_LOG = False           # logging only: 'CHOKE census' lines with what CHOKEPOINT would do (no behaviour change)
CHOKE_MIN_NEAR = 2
CHOKE_NEAR_RADIUS = 5
CHOKE_MIN_VIEW = 3
CHOKE_VIEW_RADIUS = 8
CHOKE_TRIVIAL_XL = 4        # from this XL level-0 kinds (jackals, sewer rats, kobolds, goblins) don't count
CHOKE_MAX_FACING = 2        # neighbours the pack can come through (with the square itself blocked) ...
CHOKE_DETOUR = 6            # ... counting routes at most this much longer than the monster's straight-line distance
CHOKE_MAX_THREATS = 6       # (cost bounds: monsters and candidate squares looked at per decision)
CHOKE_MAX_CANDIDATES = 16
CHOKE_STEPS = 4             # the farthest chokepoint we walk to (BFS steps) with nothing next to us
CHOKE_RETREAT_STEPS = 2     # ... with 2+ adjacent (or 1 adjacent and 3+ near): stepping away costs a swing each step
CHOKE_PRIORITY = 25         # the approach step beats melee (16) and pickups (15), not a good wand zap or Elbereth
CHOKE_HOLD_PRIORITY = 0.5   # on the chokepoint: wait for the pack (below every attack)
CHOKE_HOLD_TURNS = 15       # a hold with no contact this long ends ...
CHOKE_COOLDOWN = 60         # ... and the trigger rests this long (unless something is next to us)
CHOKE_SHOT_TURNS = 5        # shot at from afar with nothing next to us this long: no hold (archers keeping away)
CHOKE_LOG_EVERY = 5         # log throttle while a decision repeats
CHOKE_FROM_TURN = 0         # dev replays: CHOKEPOINT acts only from this turn (log-only before it)
#
# --- supply lane (lane 4, supply.py + shop_math.py): what the bot carries to the Castle, bought in shops ---
# The base bot walks through ~1.3 shops per game and buys food only (plus a tonal instrument up to INSTRUMENT_BUY_MAX).
# Ledger F304: the MAGIC LAMP costs base 50 (objects.c; oil lamp 10), so a shop 'lamp' quoted 50 / 67 / 75 / 89 / 100 is
# magic; cand-k jf79-96: 11 of 270 games stood on one at 50-89 zm and bought none, 4 of them with enough gold. Rubbed once,
# a random lamp gives a wish 31% of the time (mkobj.c: 25% blessed / 50% uncursed / 25% cursed; potion.c djinni_from_bottle).
# Instruments: all 8 tonal types play the drawbridge tune (lane 1); a 'horn' of base 15 is a tooled horn, base 50 is frost /
# fire / plenty (2/3 tonal); the old cap of 70 skipped harps (67-89) and frost/fire horns (67-100).
# SUPPLY_BUY (off): the Supply.buy strategy -- before BUY_FOOD in the preempt chain -- walks to the best affordable wanted
# shelf item and pays: tonal instrument (one, if the pack has none) first, then magic lamps (up to SUPPLY_LAMP_N); BUY_FOOD
# waits until the shop's shelves were all looked at (SUPPLY_SCAN_TURNS at most) so food never spends the gold they need.
# A shelf item is classified by the glyph on the map (tools are unshuffled in NLE's glyph ids: ledger F308) and by its quote
# (shop_math.py, shk.c get_cost). Log lines: 'SUPPLY seen ..', 'SUPPLY buying ..', 'SUPPLY lamp bought price=.. gold=..'.
# A horn comes first (castle-gate R344/F347: horn kits meet the castle's minotaurs with HORN_SCARE and die half as often,
# 13/136 against 30/140 with a flute): a certain tooled horn (15 zm) outranks a frost / fire horn, then the rest; a second
# instrument is bought only while the pack holds no certain horn (a horn of plenty is the one 'horn' that plays no tune).
# MEASURED (ledger R355, S2: BUY+KEEP+SELL only, jf79-80, 30 games paired with cand-k): progress +0.048 [-0.014, +0.110],
# castle arrivals alive 13 vs 11, Cx +0.0019 [-0.0004, +0.0055], 0 shopkeeper incidents, 0 new exceptions; the footprint is the
# ~1.3 shop visits of a game. Expected size (F320 + truth, 120 games): a tonal instrument on a visited shelf in 5.8% of
# games and a magic lamp in 3.3%, the base already buying about half of the instruments it sees: ~+2 points of tonal
# carry at the castle and ~+3% of games with a certain magic lamp (the wishes lane's replay of 11 lamp sightings: 3 bought).
SUPPLY_BUY = True
SUPPLY_LAMP_BUY = True        # (read with SUPPLY_BUY) buy magic lamps
SUPPLY_LAMP_MAX = 140         # highest unit price paid for one (CHA <= 5: 100; with the surcharge 133)
SUPPLY_LAMP_N = 2             # lamps wanted in the pack (each is its own 31% wish)
SUPPLY_INSTR_BUY = True       # (read with SUPPLY_BUY) buy a tonal instrument when the pack has none
SUPPLY_INSTR_MAX = 140        # highest unit price paid for one (harp / frost horn / fire horn: base 50 -> 50 .. 133 at CHA <= 5)
SUPPLY_SCAN_TURNS = 400       # BUY_FOOD waits at most this long inside a shop whose shelves are not all checked
# SUPPLY_WAND500 (read with SUPPLY_BUY): a shelf wand quoted at base 500 is wishing or death (objects.c, prob 5 each): half are
# wands of wishing, and an engrave-test of one is a wish. cand-k wand census (metrics lane, ledger F314): the bot engrave-tests
# 0.68 wands a game, 1.1% were wishing, 4 of 4 such games passed. Quotes 500 x charisma x 4/3: 667-1000 zm (CHA 6-10), up to
# SUPPLY_WAND500_MAX; SUPPLY_SELL will sell nearly the whole pack for it (value 450 milli-passes).
SUPPLY_WAND500 = True
SUPPLY_WAND500_MAX = 1400
# SUPPLY_SCARE_BUY (read with SUPPLY_BUY): a shelf scroll the game NAMES scare monster, up to SUPPLY_SCARE_N in the pack (castle-gate:
# the strongest crusher-square item, monmove.c onscary checks a scroll on our square before the @ and minotaur exclusions;
# castle-entry rank 2). Only a scroll shown by name: 1 in 8 of the price-100 group is scare monster, too costly to buy blind.
SUPPLY_SCARE_BUY = True
SUPPLY_SCARE_N = 2
SUPPLY_SCARE_MAX = 220
# SUPPLY_KEEP (off): ItemPriority keeps up to SUPPLY_LAMP_N possible magic lamps in the pack (right after the food, before
# the tonal instrument and the unknown potions/scrolls/wands), and never lets them go through a pack squeeze.
SUPPLY_KEEP = True
# SUPPLY_SELL (off, needs SUPPLY_BUY): when the best wanted shelf item costs more than the gold we carry (Supply.want), sell
# the pack items that are worth least to us for that gold (potions, scrolls, wands, rings, amulets; lowest loss per zorkmid
# first, never the equipped, never the marked '#earth' scrolls) to a shop on the level that buys them -- a general store takes
# all (shk.c sellobj / set_cost: base/2, 3/8 of base from 1 shopkeeper in 4 for unidentified types) -- then Supply.buy pays.
# The loss table (supply.KEEP_MPASS) is in milli-passes from readiness v1.2's weights; the sale is refused when the items
# cost more than half the target's worth (instrument 20, lamp 10, wand500 450). The bot's gold is median 47 at XL 7 while a pack at T10k
# holds 4.4 unknown potions, 5.3 scrolls, 1.3 wands, 0.9 rings (~700 zm at sale prices).
SUPPLY_SELL = True
# SUPPLY_TOWN (off, needs SUPPLY_BUY): on Minetown (a Mines level where a shopkeeper was seen, glyph-derived
# global_logic.minetown_level), with no digging tool (a shopkeeper bars the door to a pick-axe), the camp's transit becomes a
# visit: walk into every shop whose shopkeeper was seen (a known shop component nobody has stood in) and explore the town
# (global_logic.exploration_strategy, which opens the doors but never kicks them in the Mines) for SUPPLY_TOWN_EXPLORE turns
# at a time, up to SUPPLY_TOWN_TURNS in all; Supply.scan stands on each shelf square, buy / sell / BUY_FOOD act as they
# find things. cand-k jf79-96: 70 of 270 games reach Mines level 3 or 4 (Minetown), 25 enter Izchak's, 32 any town shop; the
# camp skips the town on purpose (no dwarf hunting there: the Watch) and only passes through it.
# S1 (ledger R340, jf79-81, 45 games, BUY+KEEP+SELL+TOWN+TOWN_FIRST): progress -0.030 [-0.088, +0.029], arrivals alive 10 vs 16,
# games reaching Mines 3-4 14 vs 9 (as built) but no purchase; on the same two sets S2 (no TOWN) scored +0.048 against S1's +0.008:
# OFF -- it doubles the Minetown shop reach (~+3 points of games that see a lamp) for a drift the data cannot call zero.
SUPPLY_TOWN = False
SUPPLY_TOWN_TURNS = 900
SUPPLY_TOWN_EXPLORE = 150
SUPPLY_TOWN_PROBE = 150       # turns on a Mines level 3-4 spent exploring before a door, altar, fountain or shopkeeper shows
SUPPLY_TOWN_NOSHOP = 400      # turns in a town-like Mines level with no shopkeeper seen after which the sweep ends (Orcish Town)
# SUPPLY_TOWN_FIRST (off, with SUPPLY_TOWN): the tool-less Mines camp goes down to Mines level 3 without hunting on levels 1-2
# (dive_logic.camp_step: no dwarf search on the way down), so Minetown (Mines 3 or 4) is visited in every game that camps.
# cand-k: 162 of 270 games enter the Mines, only 70 reach Mines 3 -- 92 found their pick-axe (or died) on levels 1-2 first.
# No dwarf is hunted on Mines levels 1-2 while the camp heads down (dive_logic._hunt_allowed): a pick-axe taken there would
# bar the shop doors (a shopkeeper does not let a digging tool in) and end the trip before it began; levels 1-2 are searched
# on the way back up, as before.
SUPPLY_TOWN_FIRST = False
# SUPPLY_DOOR (off, needs SUPPLY_BUY): a shop whose interior the BFS cannot reach -- the shopkeeper stands at his post just
# inside the door while we are away, and a peaceful monster is no walkable square to it -- is approached through its
# doorway: Supply.buy walks to the door of the shop holding a wanted shelf item we can pay for and Supply.sell to the door of
# a shop that would take our junk, and each lets a turn pass there (at most SUPPLY_DOOR_WAITS per shop) until he steps
# aside. Why: the magic lamp is in Izchak's lighting store, which buys only candles and lamps, so the gold comes from
# another shop and the bot has to walk back in (wishes lane's jf86 s9 replay: sold the wand at the general store, never
# returned for the lamp).
SUPPLY_DOOR = True
SUPPLY_DOOR_WAITS = 30
SUPPLY_DEBUG = False          # logging only: every frame of a sale ('SUPPLY sell_offer frame ...')

#
# --- id-engine lane (2026-10-01; ledger I302, F305): make the bot KNOW its route items. All flags OFF in the commit that
# adds them (flag-off replays the base byte-identically). Ground truth (F305: 90 base games jf79-84, JF_TRUTH=1, dev/idtruth.py):
# at the castle 1 of 41 rings, 0 of 10 amulets, 28 of 65 wands (game-known; 39 bot-known), 23 of 216 scrolls (86 bot-known),
# 0 of 7 levitation potions and 0 of 3 magic lamps are identified; 17 of 36 castle arrivals still hold an UNREAD scroll of
# identify (21 scrolls, 0 known), and 41 of the 51 identify-menu picks of the 90 games went to scrolls (5 to rings).
#
# ID_STACK_SKIP: a scroll stack that has just been read and opened the identify menu IS identify (read.c SCR_IDENTIFY calls
# makeknown before identify_pack), but the bot's item list is stale during the menu: the stack still scores as an unknown
# scroll stack (value 73) and the pick names it (8 of 51 picks; the pick only learns the stack's BUC). With the flag a
# scroll of the glyph being read is worth 0 in the menu.
ID_STACK_SKIP = False
# ID_GRIND_READ: power_route._dive_id_ready reads KNOWN scrolls of identify (price-identified, discovered, or a stack the
# bot already named) only once the dive has begun, so a game carries them through the whole 12,000-turn grind (jf84 s1 knew
# its scroll 'q' was identify from a Dlvl-2 shop quote at t6160 and read it at t9050 on Dlvl 3; F305: 33 identify scrolls
# at the dive start of 72 games, 0 known). With the flag the same quiet-moment rule (no hostile within 6, HP >= 60%, not
# Weak, not in a shop) also applies in the tour from XL ID_GRIND_XL -- known identify scrolls and unknown stacks of 2+ as
# in the dive -- but only while a pick worth a scroll is carried (an unknown ring, boots, amulet or wand whose
# _id_value_priority is at least ID_GRIND_MIN_VALUE): otherwise the scroll waits for the dive start, when everything
# the grind found is there to choose from. Unknown singles wait for READ_TEST.
ID_GRIND_READ = False
ID_GRIND_XL = 3
ID_GRIND_MIN_VALUE = 150
# TOOL_GLYPH_ID: NLE reports every object glyph as GLYPH_OBJ_OFF + objects[otyp].oc_descr_idx (winrl.cc shuffled_glyph),
# and o_init.c shuffle_all() permutes oc_descr_idx only inside rings, amulets, potions, scrolls, wands, spellbooks and the
# magic-appearance armour groups. Tools are not shuffled, so tools that read alike in words have DIFFERENT glyph ids:
# lamp {oil lamp, magic lamp}, bag {sack, oilskin sack, bag of holding, bag of tricks}, horn {tooled, frost, fire, horn of
# plenty}, flute, harp, drum {leather drum, drum of earthquake}, whistle {tin, magic}, candle. objects/utils.py
# possibilities_from_glyph returned every tool with the glyph's description; with the flag it returns the glyph's own tool,
# so item.objs is exact on sight (inventory via inv_glyphs, floor squares via glyphs). Only data the arena passes to act()
# (coordinator ruling 2026-10-01). F305: 3 magic lamps and 4 bags of holding reached 36 castles unidentified.
TOOL_GLYPH_ID = True
# ID_WAND_TEXT_GRIND: WAND_ENGRAVE_TEXT (the engrave test writes an 'x' so engrave.c prints post_engr_text: striking 'The wand
# unsuccessfully fights your attempt to write!', sleep/death 'The bugs stop moving!', cold 'ice cubes', magic missile 'riddled
# by bullet holes', slow/speed monster) runs in the dive only: the grind answers the text prompt empty ('glows, then fades':
# nothing learned) and the dive re-tests once at a quiet moment -- wands picked up during the dive are not re-tested. F305:
# 65 wands at 36 castle arrivals, 28 game-known, 39 bot-known; striking 13 carried, 9 known. With the flag the first test
# in the grind already writes text (engrave.c doengrave: a dust wand writes 'Elbereth' in the same action).
ID_WAND_TEXT_GRIND = False
# ID_WAND_REFINE / ID_DIVE_HOLD (power_route.py; off): spend identify scrolls on rings and amulets, not on what the engrave
# test already narrowed. ID2 (R316): 100 identify picks went to ring 34, scroll 27, wand 17, potion 14, amulet 8; of the 58
# picks on a wand, potion or scroll 22 were followed by a ring or amulet picked up LATER, 18 of which stayed unknown to the
# end; 14 of the 27 castle arrivals with an unknown ring had used up their identify scrolls (picks 1-4) on lesser things.
# ID_WAND_REFINE: an engrave-TESTED wand (fewer than 12 candidates left) is worth 30 + 120 x P(route wand) in
# power_route._id_value_priority when its candidates mix route and other types (the silent five hide opening; the vanish
# trio hides teleportation) and 45 when they do not (sleep or death), so it no longer counts as a target worth a scroll
# (ID_GRIND_MIN_VALUE) or outbids an amulet; an untested wand keeps 150.
ID_WAND_REFINE = False
# ID_DIVE_HOLD: known identify scrolls are held in the early dive too (depth < ID_HOLD_DEPTH) until an unknown ring, boots,
# amulet or untested wand is carried -- the grind's rule (ID_GRIND_READ) -- and read at any target from ID_HOLD_DEPTH down,
# where the dive passes through quickly and a new ring is unlikely.
# Evidence: only ID5 (jf350, 15 games, ledger R348): the 6 identify picks went to 3 rings and 3 wands, none to a scroll (ID2:
# wand 4, ring 3, scroll 3 of 10; base: 4 scroll picks of 4); two of the 5 unnamed TC rings of ID2 were picked up after the
# game's identify scrolls had been read on other items, which is the case this holds scrolls for. Too few games to see more.
ID_DIVE_HOLD = False
ID_HOLD_DEPTH = 10
# READ_TEST (id_engine.py; needs EARTH_BOX, see READ_TEST_REQUIRES_EARTH_BOX): read unknown scroll singles at quiet moments
# until the identify label is known. F305: 17 of 36 castle arrivals (47%) and 31 of 72 dive starts still held an unknown
# scroll of identify (singles: 13-16% of the unknown singles are identify); one read names the label for every later scroll and
# identifies an item at once. The risks (read.c, explode.c, zap.c; table in id_engine.py's docstring): destroy armor 3.2%,
# fire 3.0% (burns 1/3 of the other scrolls and potions), punishment 1.5%, create monster 4.5%, a cursed teleportation
# scroll 0.7%, earth 2.0% (boxes the bot in without EARTH_BOX), amnesia 3.5% (harmless: ~0.14% of the discoveries per read),
# scare monster/charging/genocide wasted. Conditions per read: the tour from XL READ_TEST_XL or the dive, depth <=
# READ_TEST_MAX_DEPTH, HP >= 70%, nothing hostile within 7, not Weak/afflicted/levitating/in a shop, an unknown ring,
# boots, amulet or wand worth a scroll in the pack (ID_GRIND_MIN_VALUE), P(identify) >= READ_TEST_MIN_P by generation
# weight among what the price knowledge still allows, READ_TEST_GAP turns between reads; power_route.scroll_read_ok
# (t-route's veto hook) is asked when it exists.
# Evidence (ID2 = this flag with the id-engine set, 135 paired truth games vs base: jf79-84 + fresh jf350-352; ledger R316,
# R339, F346): castle rings known 7% -> 41%, unknown scroll labels known 19% -> 45%; AC +0.3 at the dive start (fresh sets) and
# 0 at the castle; games ending at max depth <= 11 32% -> 27%; 2 of 103 reading games ended within 300 turns of a read (both
# create-monster groups at XL5); readiness itself is flat (pooled Cx +0.0005 t 0.49, G_total +0.0004 t 0.48; fresh-only Cx
# -0.0015 t -0.67). The knowledge feeds t-route (power_route.tc_known, TC_ROUTE) and the wishes lane's single_wish (p_tc,
# p_src from Item.objs), but a route ring is carried at only ~8% of the castle arrivals.
READ_TEST = False
READ_TEST_XL = 4
READ_TEST_MAX_DEPTH = 12
READ_TEST_MIN_P = 0.10
READ_TEST_GAP = 15
READ_TEST_REQUIRES_EARTH_BOX = True
# READ_TEST_CLOAK (off): READ_TEST only while a cloak is worn. Destroy armor (3.2% of scrolls; 14 armour pieces in the 258
# reads of ID2) takes the cloak first (do_wear.c/wizard.c some_armor: cloak, else body armour, then helm/gloves/boots/shield
# each replace it with chance 1/4), so with a cloak on the body armour (mithril AC 5) is spared 42% of the time instead of
# being the victim 42% of the time. Cost: games without a cloak (~45%) read nothing until they wear one.
READ_TEST_CLOAK = False
# ID_SELL (id_engine.py; needs the supply lane's supply.sell_offer, else it does nothing): price-ID by selling. In a shop that
# buys the class the bot drops one unit of each unidentified scroll, ring, wand and potion (one try per level and
# appearance), reads the shopkeeper's offer (shk.c set_cost: base / 2, or 3/8 of it from one shopkeeper in four for an
# unidentified item), declines and takes it back; price_id.learn_offer narrows the glyph's base-price range. F305: shop
# quotes narrowed only 5-10% of the carried unknown appearances (a quote needs the same appearance on a shelf), a sell
# offer prices every carried type in any shop that buys its class (the bot walks through ~1.3 shops per game).
# Evidence (ID5, jf350, 15 games, ledger R348): 41 appearances priced in 8 games (27 potions, 10 scrolls, 2 wands, 2 rings),
# 0 exception types, no shopkeeper trouble, 5 watchdog give-ups, 20 'uninterested' answers (one try per level and class);
# harness (id-sell preset): every offer narrows to the right group (20-zm scroll = identify exactly).
ID_SELL = False
ID_SELL_MAX_FAIL = 6
# ID_BUY_IDENTIFY (needs supply.EXTRA_WANTS): buy a shelf scroll that is identify (its quote fits only base 20: 20-36 zm)
# while unknown rings/amulets/boots/wands (ID_GRIND_MIN_VALUE) outnumber the known identify scrolls carried (at most
# ID_BUY_MAX), paying at most ID_BUY_CAP per scroll. F305: identify-priced scrolls were on a shelf in 8 of 60 games.
# Evidence: harness (id-buy preset) buys both, reads them and names the ring and the amulet; ID5 jf350 (15 real games, R348):
# one shelf identify scroll seen (27 zm, gold 46), not bought -- Supply.buy gives up while a hostile monster is in view.
ID_BUY_IDENTIFY = False
ID_BUY_CAP = 60
ID_BUY_MAX = 3
#
# --- arrivals (lane 8, 2026-10-01): more live castle arrivals -- Medusa's level, the mazes below it, the landing ---
# Base f414e9e (= cand-k): of 165 games alive at Medusa's depth 115 reach the castle (M1 80%, M2 81%, M3 42%, M4 70%;
# ledger F307); 112 live arrivals, 48 of them die within 40 turns of the landing (23 to minotaurs).
# MEDUSA_HOP (off; medusa_hop.py, dive_logic._hop_action): on Medusa's level, standing on land with no dry square
# (Medusa-4's wet islets: 71% of its falls), walk to a launch square and step INTO a 1-wide moat channel that joins the
# land to land with a dry square (no moat in the 3x3: a hole there cannot flood, dig.c fillholetyp). trap.c drown(): a
# hero in water who can't swim crawls out to a random square among the 8 around the water square that hack.c
# crawl_destination accepts (land, no monster, no diagonal squeeze between rocks) -- the origin square among them, so
# the step never drowns -- and when the channel touches a second stretch of land the crawl lands there with probability
# n_far / (n_far + n_near). The cost is the soaking (scrolls blank, potions dilute, iron rusts), what every flood of the
# dig lottery costs too (a pick-axe hole beside k moat squares floods with 1 - 1/(k+1)^2). Harness probe (dive-medusa
# kit, M4 islet 9 -> the NE hut across the channel at map (69,6)): 5 of 6 landed across, the 6th back on the origin.
# MEDUSA_HOP_MAX steps into water per Medusa level; MEDUSA_HOP_COST the most expected tries (sum of 1/p over the
# channels of the chain) a chain may cost; a longer one (up to MEDUSA_HOP_COST_WET) only from land whose driest square
# has MEDUSA_HOP_WET_K or more moat neighbours (a pick-axe hole there floods with 1 - 1/(k+1)^2 >= 94% per try);
# MEDUSA_HOP_WALK the farthest launch square (BFS steps).
# Measured (harness dive-medusa kit XL8 HP80 AC0, secret jf410, pass = next level; ledger R312/R335 and R317):
#  - MEDUSA_HOP on Medusa-4: 87/97 = 90% against 55/97 = 57% (gained 33, lost 1); the 43 cand-k games that met Medusa-4,
#    replayed in full: castle arrivals 30 -> 39. Inert on Medusa-1/2/3 (byte-identical). Recommended ON.
#  - MEDUSA_HOP_RESERVE on Medusa-3 (n=102): 43 against 40 (n.s.); MEDUSA_LAZY_ELB: 38 against 40; MEDUSA_DIG_ORDER: 46
#    against 40 (p 0.26). Medusa-3 is capped by the flood lottery (~48-55% for a pick-axe) and the ravens' blinding.
# MEDUSA_HOP_RESERVE (off, needs MEDUSA_HOP): where no chain of channels leads to dry land (Medusa-3's raven island, whose
# neighbour island is wet too), hop to the neighbouring land once our own is down to squares with MEDUSA_HOP_RESERVE_OWN
# or more moat neighbours and the other has one with at most MEDUSA_HOP_RESERVE_THEIRS (as seen now, floods counted);
# at most MEDUSA_HOP_RESERVE_MAX such hops a level. Why: Medusa-3's island has four k = 1 squares in one chain (one flood
# makes the rest k = 2) and 18 squares in all; flood-only Monte Carlo (pick-axe, 4 tries): 48% on the island, 67% with the
# next island's two isolated k = 1 squares. The harness's Medusa-3 deaths by drowning (15 of 35 failures at AC 0) came with
# 77/80 HP: the island ran out. Result: the drownings turn into raven deaths (52 of 59 failures), 43/102 against 40/102.
# MEDUSA_LAZY_ELB (off): on Medusa's level the dig engraves Elbereth before every dig phase even with nothing in range
# (dive_logic._elbereth_before_digging_escape); with the flag only when something Elbereth stops is within
# ELBERETH_DIG_RADIUS (or after a pit wiped one we wrote). In the harness half of the Medusa-3 passes (22 of 43) finished
# before the first raven attack (first attack: median turn 5-7, a first attempt takes ~8 actions), so the action saved
# before the pit is a larger share of the window. Result: 38/102 against 40/102 -- the first blinding comes where no
# Elbereth stands (55% right after a flood and crawl-out, 18% just after a pit, the rest a dust typo or too late), not
# from the pre-dig write.
MEDUSA_LAZY_ELB = False
MEDUSA_HOP_RESERVE = False
MEDUSA_HOP_RESERVE_MAX = 2
MEDUSA_HOP_RESERVE_OWN = 2
MEDUSA_HOP_RESERVE_THEIRS = 1
MEDUSA_HOP = True
MEDUSA_HOP_MAX = 14
MEDUSA_HOP_COST = 2.0
MEDUSA_HOP_WET_K = 3
MEDUSA_HOP_COST_WET = 4.5
MEDUSA_HOP_WALK = 14
#
# --- medusa lane (phase 2, 2026-10-02): Medusa's level and the mazes below it (medusa_reentry.py; ledger I322, F368, F383, R457) ---
# MEDUSA_REENTRY + MEDUSA_STANDOFF (both off; RECOMMENDED ON TOGETHER, nothing else is needed): Medusa-3 -- the raven island,
# where the arrival region and the '<' are one 18-square island with a moat neighbour on every square, 30 ravens and a couple
# of nymphs -- is a flood lottery for a digger (dig.c fillholetyp: a hole is dry with 1/(k+1)^2, 1/4 at the best squares, and
# every flood is a drowning risk): the base passes 44% of the harness games (101/229 on five secrets). This policy never digs
# there. It climbs the '<' (ravens have no M2_STALK, they never follow) and goes back down through the hole we dug above:
# trap.c fall_through() (walking onto a known hole, or '>' on it) drops one level further with probability 1/4 (newlevel++
# while !rn2(4)), unlike the FIRST fall through a freshly dug hole (dig.c digactualhole: exactly one level, ledger F306). So
# every re-entry is a 1-in-4 skip of Medusa's level outright, else a fresh random landing on the island and another climb. The
# first climb finds the hole we fell through only if the known map reaches it; otherwise the dive digs a new hole beside the
# '>' (the stairs we came up by are avoided), one step from the '>' for every later entry. EVIDENCE (harness dive-medusa, XL8
# HP80 AC6 pick-axe, Medusa-3 seeds, paired by seed against 008ef20; Medusa-3 is 7 of the first 45 real base games): the final
# tree on UNTOUCHED secrets jf752 29/44 (66%) vs base 13/44 (30%), +18 -2, and jf753 26/35 (74%) vs 17/35 (49%), +12 -3; pooled
# 55/79 (69.6%) vs 30/79 (38.0%), exact sign p < 0.0001, paired difference +31.6 points (95% CI +18.7 to +44.6). On the
# development secrets jf750+jf751 (used to tune): 74/109 (67.9%) vs 52/109 (47.7%), +39 -17, p 0.005. COSTS: a median 340 turns
# a Medusa-3 game (base 29), ~330 of them on the island and ~100 above it; 9% of the games die within a few turns of reaching
# the level above (an awake pack at its '>': elf-lords, soldiers, vampires), and the pick-axe is stolen by a nymph in ~3% of
# them (a stolen digging tool ends the plan). MEDUSA_REENTRY_MAX climbs a game; the '<' must be within MEDUSA_REENTRY_STEPS BFS
# steps; the level above is rested on to MEDUSA_REENTRY_REST of max HP (at most MEDUSA_REENTRY_REST_MAX turns, and sight is
# waited for, MEDUSA_REENTRY_BLIND_MAX) before an entry; a recorded hole farther than MEDUSA_REENTRY_HOLE_STEPS steps is not
# walked to; the layer eats the pack's food itself when Hungry (it loops above the dive's eaters) and gives way when Weak with
# nothing to eat. MEDUSA_REENTRY_M4 also uses it on Medusa-4's wet islets (not measured; off).
MEDUSA_REENTRY = True
MEDUSA_REENTRY_FLOODS = 0       # climb only after this many floods on the island (0: at once); lower than that the dive digs
MEDUSA_REENTRY_HP = 0.5         # ...or below this share of max HP (climb whatever the flood count)
MEDUSA_REENTRY_SCARE = True     # Elbereth before the walk to the '<' when two ravens are next to us and it is 2+ steps away
MEDUSA_REENTRY_LOOP = 400       # actions the layer takes in a row before it hands control back (see reentry_strategy)
MEDUSA_REENTRY_MAX = 10
MEDUSA_REENTRY_STEPS = 8
MEDUSA_REENTRY_COMMIT = 3        # a walk this near the '<' is finished, not held, when the window closes
MEDUSA_REENTRY_REST = 0.9
MEDUSA_REENTRY_REST_MAX = 400
MEDUSA_REENTRY_TOTAL = 2500     # the standoff and the cycle give up this many turns after the first landing on Medusa's level
MEDUSA_REENTRY_BLIND_MAX = 60   # turns waited above for sight to return before the hole is entered blind
MEDUSA_REENTRY_HOLE_STEPS = 40
MEDUSA_REENTRY_M4 = False
# MEDUSA_STANDOFF (off; medusa_reentry.py; the walk half of the policy above): on Medusa-3's island hold an intact Elbereth (read
# back every step while we can see) and let the walk to the '<' start only when a WINDOW is open: sight, HP >= MEDUSA_STANDOFF_HP
# of max and no hostile within max(MEDUSA_STANDOFF_WINDOW, steps to the '<' + 2) squares (hostiles are counted within
# MEDUSA_STANDOFF_RADIUS); at most MEDUSA_STANDOFF_MAX turns a landing (MEDUSA_STANDOFF_MAX_OK once sighted with the HP),
# MEDUSA_STANDOFF_TRIES engravings a square. Why: the island's ravens do not thin out (harness: 200 turns on Elbereth, full HP at
# the end, 2-9 ravens within 9 squares throughout -- a scared raven flees rnd(10) turns, one time in seven rnd(100) (monmove.c
# distfleeck), but the level holds 30 of them), the hold itself is safe (an intact Elbereth: no raven bit in 200 turns), and a
# walk begun at a window loses 2.2 HP on average against 8.0 HP and 4x the turns for one begun at the cap. What kills is the
# landing next to the flock: a raven's claw (AD_BLND) hits AC 6 about 95% of the time, so one round of contact blinds, and a
# blind dust Elbereth is written whole 34% of the time (engrave.c: 1 letter in 11 garbled when blind on top of 1 in 25) against
# 72% sighted. The fixes that mattered, each from a death pattern of the harness logs (F383): the walk goes round the monsters
# (MEDUSA_REENTRY_AROUND; the old step hit the raven standing on the path, nine turns running, 69 -> 16 HP), a blind hold writes
# again only when hurt (MEDUSA_STANDOFF_REFRESH 0; a refresh every 30 turns replaced a standing Elbereth by one that holds 1 time
# in 3), and the give-up 'hurt on an intact Elbereth' no longer fires on the hit taken in the turn that wrote it
# (MEDUSA_STANDOFF_HURT_STRICT). Tried and NOT adopted: a hold cap of 60 turns plus rest to 70% (wn10a, jf750 33/52 vs 37/52).
MEDUSA_STANDOFF = True
MEDUSA_STANDOFF_MAX = 250       # turns a landing is held while we are blind or below MEDUSA_STANDOFF_HP (the hold is the rest)
MEDUSA_STANDOFF_MAX_OK = 250    # ...and once we see and have the HP: the walk starts at the latest then, window or not
MEDUSA_STANDOFF_REFRESH = 0     # blind: write the Elbereth again after this many turns without a hurt (0: only when hurt; was 30)
MEDUSA_REENTRY_AROUND = True    # the walk to the '<' goes round the monsters (an Elbereth when the way is taken) instead of hitting them
MEDUSA_STANDOFF_HURT_STRICT = True   # "hurt on an intact Elbereth" (the hold gives up) only when it stood intact at the observation before too
MEDUSA_STANDOFF_RADIUS = 12
MEDUSA_STANDOFF_WINDOW = 4
MEDUSA_STANDOFF_HP = 0.7
MEDUSA_STANDOFF_TRIES = 6
# DIVE_WAND_PICKUP (off; dive_logic.dive_wand_pickup; ledger F334 of t-route): the dig-dive takes a wand that lies on its
# landing square or in view within DIVE_WAND_DIST BFS steps, at a calm moment (no hostile within 7, HP >= 60%, not Weak,
# not in a shop) -- DIVE_WAND_RINGS adds rings and amulets. Why: engraving with a wand of wishing makes the wish
# (engrave.c zapnodir), the id-engine's engrave test does that for every picked-up wand, and 1 of the 4 unused wands of
# wishing in 720 real games lay on a dive landing square. PREP_DIVE_PICKUP (all five classes, off) measured 'almost never
# in view' on one game; DIVE_ITEM_LOG is the log-only count ('DIVE_ITEM_LOG ...' lines per candidate square, no action).
DIVE_WAND_PICKUP = False
DIVE_WAND_DIST = 10
DIVE_WAND_RINGS = False
DIVE_ITEM_LOG = False

#
# --- castle-inner lane: from inside the castle to the wand of wishing (castle_inner.py) ---
# CASTLE_INNER (off; RECOMMENDED ON, see below): the walk from the Crusher's lock-out square (07,08) -- or any square inside: castle-gate's
# sweep hand-off at (27,08), a no-tune entry, the east back door -- to the castle's wand of wishing: the throne room, the locked
# throne door (32,04)/(32,12) opened with a key, a digging wand, a pick-axe/mattock or a striking wand (never a kick:
# dokick.c wake_nearby() wakes everything within sqrt(XL*20), lock.c does it each turn of a blunt #force), the hallway, the
# tower (looked at from the hallway), the chest forced with a blade under the cursed scare monster scroll, the wand named by
# one zap for WISH_TELEPORT_ROUTE (the module then holds the chest square until the route is done or the level changes);
# castle 29: the secret door (38,08) dug open and the trap door (40,08). The form that ships is the DASH: no rest before the
# throne room (_GATE 0), an Elbereth at once when a wall-walker or a level 8+ respecter arrives next to us (_ELB), no hold.
# EVIDENCE (dev/replay.py: the same exact hand-off states, a bot started fresh there that remembers its last prayer; paired;
# pass = Valley reached; old leg = the Crusher's wand leg): held-out libraries pooled, 199 states: old leg 40 (20.1% [15-26],
# wand in hand 28 = 14.1%), CASTLE_INNER defaults 59 (29.6% [24-36], wand 48 = 24.1%), +30 -11, McNemar p 0.004 -- real-kit
# x4 salts 2-3 (castle-k-crush-x4, 93 hand-offs) 8 -> 17 (+13 -4), castle-gate's sweep v3 hand-offs (56) 19 -> 23 (+8 -4),
# fresh strong kits jf240-244 (Excalibur, AC -4; 50) 13 -> 19 (+9 -3); the 94 development states (x4 salts 0-1) 16 -> 19 (+9 -6),
# the 51 of salt 0 alone 10 -> 8 (-2); the hand-off is the same for both: HP >= 80%, the court drained west along row 08.
# Why a dash: awake monsters know where the hero is (monmove.c set_apparxy) and walk straight at her, wall-walkers through
# the walls at speed 9 (2-4 xorns per castle, all awake), so every turn spent resting (0.2-0.3 HP/turn at XL 7-10) or holding
# brings more of them: rest 0.85 + hold at (25,08) passed 7/51 on the real kits, 15/50 on fresh strong kits (21/46 on the
# dev library it was tuned on: not reproducible), 20/56 on the sweep states, and died at the hold 15 times of 35.
CASTLE_INNER = True
CASTLE_INNER_GATE = 0.0        # rest (Elbereth) in the antechamber and hall to this share of max HP before the throne room: 0 = none (was 0.85: the rests let the xorns converge, 7/51 vs 10/51)
# CASTLE_INNER_PIT (off): a pit dug in the one-wide hallway behind us (a few squares beyond the throne door) is a gate:
# a monster in a pit escapes 1 time in 40 per move (trap.c mintrap) and the queue behind it cannot pass; walkers all
# fall in (not flyers or wall-walkers). The followers that killed the walk-ins in the hallways (trolls, ogre kings,
# soldiers, harness R0/v1) arrive one at a time ~40 turns apart. REJECTED: 19/46 vs 21/46 without (8 of 26 hallway entrants
# died before the chest tower, 5 without), R321.
CASTLE_INNER_PIT = False
# CASTLE_INNER_GRIND (off): a pit at (24,08) plugs the one-wide hall (see castle_inner._hall_grind): the barracks stream
# and the court's remnants come at us one at a time, trapped one by one in the pit (1 turn in 40 to get out), and we
# rest to full HP on Elbereth three squares back between kills instead of being swarmed at the throne-room door. REJECTED:
# 17/46 vs 21/46 without (R321).
CASTLE_INNER_GRIND = False
CASTLE_INNER_GRIND_MIN = 15    # turns to wait at the stand square at least ...
CASTLE_INNER_GRIND_QUIET = 25  # ... and with nothing hostile in the hall/throne room in view for this long
CASTLE_INNER_GRIND_MAX = 700
# CASTLE_INNER_LOCK (off): a throne door unlocked with a key (46% of the real kits carry a key, lock pick or credit
# card) is closed and locked again behind us: monsters open closed doors but not locked ones (no keys); giants smash
# them, wall-walkers pass. No effect measured (real kits 7/51 with and without; it needs a key and 10 seconds to spare).
CASTLE_INNER_LOCK = False
# CASTLE_INNER_XORN (off): kill the wall-walkers (xorns, earth elementals) one at a time at full HP: a lone one next to us
# while healthy is fought (XORN_HP), and the antechamber -- quiet while we are west, the barracks stream is dormant --
# is where we wait for them to home in through the walls before going east. REJECTED: 5/51 vs 7/51 (a xorn costs ~55 HP to kill
# at XL 7-10, ~35 with Excalibur: Elbereth at its arrival, _ELB, costs ~5).
CASTLE_INNER_XORN = False
CASTLE_INNER_XORN_HP = 0.75
CASTLE_INNER_CLEAR_MIN = 30    # turns to wait in the antechamber at least
CASTLE_INNER_CLEAR_QUIET = 25  # ... with no wall-walker in view for this long
CASTLE_INNER_CLEAR_MAX = 150
CASTLE_INNER_SIDE = False      # pick the north or south hallway at the throne room entrance by what is near each door (no effect: 7/51 with and without)
# CASTLE_INNER_ELB (ON with CASTLE_INNER): a wall-walker or other heavy respecter (xorn, earth elemental, level 8+) arriving next
# to us gets an Elbereth at once, whatever our HP, and a few turns to flee (castle_inner._combat): it has just spent its move
# arriving, the engraving takes one action (28% garbled, one round of blows then), and a hero that keeps walking at speed 15 is
# not caught again by a speed 9 xorn. A fight with a xorn costs ~55 HP. Real-kit hand-offs: wall-walker deaths 23 -> 13 (never
# resting, with ELB, 51 states); it fired 5.6 times a game.
CASTLE_INNER_ELB = True
# CASTLE_INNER_AVOID (off): the walk is the cheapest route with a penalty around hostile monsters in view (1/2/3 per square at
# 3/2/1 squares from one, times _W) instead of the first shortest one: the BFS tie-break takes the NE diagonal and walks
# along row 5 into the heavy remnants of the court (trolls, ogres, giants: 117 of 141 at x 35..37, y 5..7), where R0's
# row-08 walk stays south of them (real-kit hand-offs jf82-s2, jf80-s14, jf87-s8: 3 deaths of G1 that the old leg survived).
# No effect measured: sweep states 23/56 with and without.
CASTLE_INNER_AVOID = False
# CASTLE_INNER_EXCAL (off): the module acts only for a hero with Excalibur in the pack; any other hero is left to the old wand leg.
# Not needed: the dash form beats rest + hold for Excalibur heroes too (fresh strong kits 19/50 vs 15/50, old leg 13/50).
CASTLE_INNER_EXCAL = False
# CASTLE_INNER_ADAPT (off): "dash unless strong": a hero without Excalibur walks by the dash form (no rest before the throne room,
# no hold, Elbereth at once for wall-walkers and level 8+ respecters), a hero with Excalibur by the configured rest/hold.
# Not needed (see _EXCAL).
CASTLE_INNER_ADAPT = False
CASTLE_INNER_AVOID_W = 2.0
# CASTLE_INNER_CROWD (off): 3+ hostile within 2 squares with an @ among them (a mob in the throne room: 23 of the old leg's 78
# deaths on 94 x4 hand-offs, soldiers + giant + troll + bat round one hero) -> back to the nearest hall/hallway square within
# 6 steps and fight from there, single file; held 20 turns while an @ is in view. No gain: 8/51 with and without (fired 32 times
# in 16 games).
CASTLE_INNER_CROWD = False
# CASTLE_INNER_HORN (off): a tooled horn (30% of the real kits: the instrument that played the passtune) is blown on 'Improvise?'
# when two hostiles are within 4 squares, a wall-walker within 5, or an @ within 3 below 85% HP: music.c awaken_monsters makes
# every monster in radius ~sqrt(XL*10) that fails resist() flee with no timer (soldiers, trolls, ogres, giants: MR 0, never;
# xorns resist 20 times in 100); a fleeing monster that can move away does not attack (opp_items.py has the source notes).
# No gain: 7/18 vs 7/18 on the horn-kit sweep hand-offs (old leg 9/18), ~10 blows a game.
CASTLE_INNER_HORN = False
CASTLE_INNER_HORN_GAP = 12     # turns between two blows
CASTLE_INNER_LOW = 0.5         # outside the hall: start resting (Elbereth) below this share of max HP ...
CASTLE_INNER_RESUME = 0.8      # ... and go on at this share
CASTLE_INNER_ORDER = 'east'    # the towers' order: 'east' = NE NW SE SW (the guards gather at the west ends), 'west' = NW NE SE SW
                               # (x4 dev states: east 19/94, west 14/94; 'south' SE SW NE NW 8/51 = east)
# CASTLE_INNER_HOLD (off): wait at (25,08) behind the closed throne-room door for the barracks stream (awake soldiers
# follow our square greedily: they run east along the barracks as we walk east and leave by a door a giant broke just
# as we arrive); they meet us one at a time (two with a polearm) at the door instead of six around us in the room.
# REJECTED: it gave 21/46 on the library it was tuned on and 15/50 on fresh seeds (old leg 13/50, dash 19/50); 15 of the 35
# deaths on the fresh library were at the hold (lieutenants, xorns, wand rays).
CASTLE_INNER_HOLD = False
CASTLE_INNER_HOLD_MIN = 20     # turns to wait at least
CASTLE_INNER_HOLD_MAX = 150    # ... and at most
#
# --- wishes lane (lane 5, readiness program 2026-10-01; wish_source.py): wishes from thrones and lamps ---
# All OFF in the commit that adds them. A wish from a throne or a lamp is a SINGLE wish (no wand route); see wish_source.py
# for the NetHack 3.6.6 mechanics (sit.c, mkroom.c, monmove.c disturb, hack.c check_special_room, sounds.c, apply.c dorub,
# potion.c djinni_from_bottle) and ledger F301/F302/F304.
# THRONE_SIT (off): a throne square is known on a Dungeons level (the throne glyph in the map or the #terrain view, found after
# 'You enter an opulent throne room!') -> walk to it, kill the sleeping court monsters in the way (a Valkyrie's Stealth keeps
# the rest asleep: monmove.c disturb, hack.c check_special_room), kill the ruler who sleeps on it, and #sit until it vanishes
# (1 wish in 13 thrones, also 1 genocide and 1 identify in 13; sit.c). Aborts below THRONE_ABORT_HP of max HP.
THRONE_SIT = False
THRONE_MIN_DEPTH = 5        # courts exist from depth 5 (mklev.c: u_depth > 4)
THRONE_MAX_DEPTH = 20       # above Medusa (the castle's own throne room is a different animal)
THRONE_MIN_XL = 6
THRONE_HP_FRAC = 0.8        # start the approach at this fraction of max HP (rest first: the court sleeps)
THRONE_MIN_HP = 45
THRONE_MID_REST_HP = 0.6    # started and below this fraction with nothing awake near: rest in the court (it sleeps)
THRONE_ABORT_HP = 0.45      # give the level up below this fraction
THRONE_SIT_HP = 36          # sit.c case 3: an electric shock does rnd(30)
THRONE_RULER_HP = 60        # the ruler (up to an Elvenking / ogre king: two attacks of 2d4+weapon) needs this much HP
THRONE_RULER_DIFF = 1      # the ruler on the throne is fought only up to difficulty XL + this (gnome king 6, dwarf king 8; Elvenking and ogre king 11 are not)
THRONE_DIFF = 3             # court monsters of difficulty above XL + this stay asleep (their squares are closed)
THRONE_MON_COST = 4         # path cost of killing a sleeper in the way
THRONE_AVOID = ()           # extra monster names never attacked
THRONE_TERRAIN_TRIES = 8    # #terrain looks for the throne (the first at once after entering a court)
THRONE_CROWD = 6            # ... and one whenever this many monsters are in view, 15+ turns apart (a court seen from its door)
THRONE_AWAKE_MAX = 4        # give the level up when this many monsters in view are awake (movers, or named in attack / dart / wield messages)
THRONE_QUIET_DOORS = True   # a locked door on the path is dug through with the pick-axe (a kick wakes the whole court: dokick.c wake_nearby), else the level is given up
THRONE_MAX_ACTIONS = 500
THRONE_TURNS = 900
THRONE_REST_TURNS = 300
THRONE_NOPATH = 12
THRONE_MAX_SITS = 60
THRONE_PANICS = 8
THRONE_DEBUG = False        # extra WISHSRC log lines (who the awake-monster tracker flagged)
THRONE_LOOP = 60            # actions per strategy body (the plan is re-made after each, see wish_source.throne_strategy)
THRONE_PICKUP_WT = 300      # objects on the throne square up to this weight are picked up (sit.c: #sit sits on an object first)
THRONE_ROT_WAIT = 420       # game turns to wait for a corpse on the throne to rot away (250 +- rnz(10), mkobj.c start_corpse_timeout)
# THRONE_HUNT (off, needs THRONE_SIT): a court sound (sounds.c: 1 in 200 per turn) or the entry message on a Dlvl
# HUNT_MIN_DEPTH..HUNT_MAX_DEPTH level -> explore that level (the PREP_MID exploration, budgeted) until a throne is seen.
THRONE_HUNT = False
HUNT_MIN_DEPTH = 5
HUNT_MAX_DEPTH = 12
HUNT_TURNS = 700            # turns of hunting at most (from the first call that wanted it)
HUNT_HP = 0.6
# LAMP_RUB (off): rub a carried magic-lamp candidate (an unidentified 'lamp' or a known magic lamp, never an unpaid one, never in
# a shop): apply.c dorub releases the djinni 1 time in 3; 'You see a puff of smoke' only from a magic lamp; a lamp that gave no
# smoke in LAMP_RUBS rubs is an oil lamp. LAMP_RUB_AT (for a lamp known to be magic): 'castle' = at the first quiet moment on a
# main-line level 25+ other than Medusa's (the wish is chosen with the final kit), 'dive' = at the first quiet moment once the dive
# has started, 'now' = at the first quiet moment, anywhere (a lamp that may be an oil lamp is tested at the first quiet moment
# whatever this says). A lamp KNOWN cursed (5% wish, 80% hostile djinni) is never rubbed.
# Evidence (R338): a blessed lamp rubbed on the castle landing of 448 real kits: djinni 337, wish 283, pass 22/448 (4.9%; 7.8% of the
# wishes); 62 landings die a median 11 turns after arrival before any rub. Real games (the 11 cand-k games that stood on a lamp for
# sale, supply's SUPPLY_BUY/KEEP/SELL on): 3 lamps bought, 2 rubbed (d25, d26), 1 wish; the third never found a quiet moment (trap-door
# chain d20 -> d27 with lieutenants adjacent). A random lamp is a wish 31% of the time (blessed 80, uncursed 20, cursed 5).
LAMP_RUB = True
LAMP_RUB_AT = 'castle'
LAMP_RUBS = 6               # a magic lamp shows djinni / smoke on 2 rubs in 3: 6 rubs without either (1 in 729) is an oil lamp
LAMP_TEST_UNKNOWN = True    # a lamp that may be an oil lamp is tested (rubbed) at the first quiet moment; on a puff of smoke it is kept
LAMP_MIN_MAXHP = 50         # no rubbing below this max HP (XL 1-5 in the grind): a hostile djinni (31% of random magic lamps) is a 7-HD fighter
# WISH_SINGLE (off): power.wish_text(purpose='single') -- the wish of a throne, a lamp or a water demon, with no wand route behind it --
# asks wish_source.single_wish(): the candidate with the best expected P(pass) for the pack, each candidate's harness value times how
# likely the pack makes it work (a ring of polymorph control needs a polymorph source, 2 cursed scrolls of teleportation a ring of
# teleport control, a levitation ring a castle on Dlvl 29), else WISH_SINGLE_DEFAULT ('polyctl' | 'lev' | 'tc' | 'ls').
# Evidence (ledger R323, R338; harness castle-k-real-x4: 448 salted real castle kits, base f414e9e): ONE identified wish in the pack at
# the landing -- none 2/448, polymorph control 19/448 (4.2%; kits with a polymorph source 16/56), 2 cursed teleport scrolls 11/448,
# levitation 9/448 (castle 29: 8/88), TC 6/448, magical breathing 3/448. A blessed lamp rubbed on the landing: 22/283 granted wishes pass
# (7.8%) with this policy, 5/283 (1.8%) with the old GDSM-first list (WISH_SINGLE off). No genocide class wish beats it for a kit
# without a route item (R350: removing every minotaur from 448 landings gave 0 passes, F353).
WISH_SINGLE = True
WISH_SINGLE_DEFAULT = 'polyctl'
WISH_SINGLE_EARLY = False   # dev (harness): single_wish chooses as an early wish would (priors, castle depth unknown) even on the castle
# --- wishes lane, phase 2 (lane 10, 2026-10-02; ledger I323/A335): the single wish by measured numbers. Flags OFF in the commit
# that adds them (flag-off replays cand-l5 008ef20 byte-identically). Evidence and numbers: the comment above wish_source.V2_*.
# WISH_SINGLE_V2 (off): wish_source.single_wish chooses with the cand-l5 table (single_wish_v2) instead of the phase-1 one: a TOOLED HORN
# (named through power.WISH_OBJECTS) unless a polymorph source / a TC ring is KNOWN (then polymorph control / 2 cursed scrolls), a
# levitation ring on a castle at Dlvl 29. Why the phase-1 policy asked for a TC ring in all 3 castle lamp wishes of cand-l5's gate
# (jf902 s2, jf903 s10, jf913 s1): tele_route.single_wish_value gives a bare TC ring 0.020 (T_P_NONE), above polymorph control
# (0.29 x P(source) = 0.006-0.020) and levitation (0.003). Evidence (ledger R398, R411, R414; item arms = castle-k-real-x4, 448 real kits,
# ONE wished item at the landing, 008ef20): tooled horn 21/448 = 4.7% (named; 18/448 as 'a horn'), polymorph control 19/448 (7/13 with a
# KNOWN source, 12/435 otherwise), magic flute 6/448, none 3/448; by composition on the same games phase-1 policy 28/448 = 6.2%, v2
# 31-33/448 = 6.9-7.4% (not significant, paired p 0.3-0.8); end to end with a BLESSED lamp rubbed at the landing: phase-1 22/448 = 4.9%
# (7.7% per granted wish, 287 wishes), v2 28/448 = 6.2% (9.8% per granted wish, 286 wishes), paired +6 passes, sign p 0.26.
WISH_SINGLE_V2 = True
# WISH_V2_GDSM (off): single_wish_v2 may also wish for a 'blessed greased +3 gray dragon scale mail' when the pack already holds a horn
# (the crusher route is there and armour class multiplies it) -- only with ARMOR_UP on as well (without it the bot never wears a
# carried piece). UNMEASURED end to end when this was written: V2_VAL_GDSM is the AC gradient of the identified-horn arm (AC <= -2 8.3%)
# and the metrics' causal test (instrument kits forced to AC -4: 12 -> 25 of 448), not an arm of its own; the arm (ledger I326, runs
# w10-armor1 igdsm vs ictl) decides. Stake is tiny either way (a horn kit's lamp wish: ~0.0005 passes per game), so it stays off until
# measured.
WISH_V2_GDSM = False
# WISH_V2_SHADOW (off, dev): log, once per game at the first step, what single_wish_v2 and the phase-1 single_wish would wish for the
# pack as it is ('WISHSRC [shadow] ...'), without wishing -- the per-kit decision of both policies on the same harness games.
WISH_V2_SHADOW = False
# AC_PROBE (off, dev): log 'WISHSRC acprobe +N AC a HP h/m' at +0/25/50/100/200 game turns of a run (armor II: the arrival AC after the wear pass).
AC_PROBE = False
# LAMP_RUB_FIRST (off): wish_source.lamp_strategy rubs a castle lamp at once -- on a castle-depth level (Dungeons, depth >= 25) only a
# hostile within LAMP_RUB_NEAR squares keeps it from rubbing (phase 1: any hostile in view). Why: harness R338 -- 62 of 448 blessed-lamp
# castle arrivals die before the first quiet moment (median 11 turns after landing) and 49 more mid-rub; landing census F360 -- a west
# minotaur is awake at turn 0 in 56% of castles (median distance 4, adjacent at median T+9), and the rub waits while it is in view. At the
# castle an unwished arrival passes ~0.7%, so a hostile djinni (31% of random lamps) costs almost nothing and a granted wish adds 4-7%.
# MEASURED (ledger R414, blessed lamp on castle-k-real-x4, 448 games, together with WISH_SINGLE_V2): rubbed 405 vs 392 lamps and 'died before
# any rub' 43 vs 56, but wishes granted 286 vs 287 and the median wish turn 2 in both -- the extra rubs are interrupted by the minotaur
# (mino_guard/emergency sit above the lamp in the preempt chain) -- so NO measurable gain: leave it off unless a later arm shows one.
LAMP_RUB_FIRST = False
LAMP_RUB_NEAR = 1
# HORN_LANDING (off): wish_source.horn_strategy blows a KNOWN tooled horn at a castle-likely landing (Dungeons, depth >= 25, bot x <= 9)
# before the west maze's minotaur arrives -- the first HORN_LANDING_TURNS turns of the visit, every HORN_LANDING_GAP turns, at most
# HORN_LANDING_MAX blows. Why: the bot first sees that minotaur at distance 1 in 76 of 176 horn-kit games (dark maze) and 49% of those
# die after the reactive blow; music.c awaken_monsters makes every MR-0 monster within dist2 < 10*XL flee untimed (a flee ends 1 in 25
# per move at full HP), but only a blow BEFORE its first round helps. MEASURED (ledger R424, identified tooled horn from turn 0 on
# castle-k-real-x4, 448 games, paired): crusher square 147 -> 174 (p 0.003), crush_over 87 -> 117 (p 0.001), throne 57 -> 78 (p 0.02), but
# tower 34 -> 37 and pass30 21 -> 21: the extra arrivals die in the walk-in (throne room -> tower). Harmless, no pass gain yet: turn it on
# together with a walk-in improvement.
HORN_LANDING = False
HORN_LANDING_TURNS = 50
HORN_LANDING_GAP = 15
HORN_LANDING_MAX = 4


# --- coordinator (main), 2026-10-01 evening: inventory model fix ---
# INV_FULL_LIST (off): item/inventory_items.InventoryItems.update() checks a carried container by APPLYING it, which plays game
# steps, in the middle of parsing the inventory (letter order). A strategy change (AgentChangeStrategy) or a panic raised inside
# that check left the item list cut at the container while _previous_inv_strs was already current, so every later update kept
# the cut list until the inventory text changed. cand-l4 gate jf910 s7: the Crusher took the castle's wand of wishing
# ('Z - a platinum wand', T14487), castle_inner preempted during the bag check of 'J - an empty bag named #0', and the bot saw
# 6 of its 27 items for the 610 turns it had left (no wand, so no wish; killed by a xorn). On: the exception is held, the rest
# of the list is parsed, then the exception is raised (same game steps, a complete list).
INV_FULL_LIST = True


# --- routes lane (phase 2, 2026-10-02): the lift / polymorph / teleport-control routes at the castle; all OFF in the commits that add them ---
# LIFT_EAST_DROP (off): castle_inner.owned_elsewhere() yields while the castle crossing is committed and the hero HOVERS over the
# east trap door (55,8) on a lift (castle_logic._door_step then comes down: 'over the trap door: coming down' -> _stop_levitating ->
# the ring comes off -> trap.c float_down() -> dotrap: the trap door opens, the Valley). Why: castle_inner sits above the crossing
# in the preempt chain and EAST_HALL is inside its shell, so a levitating hero that opened the back door with a key, a lock pick, a
# razing/striking wand (anything but a kick, which needs the lift off first) was taken over at (55,8): at castle 29 its PASSTUNE_C29
# trapdoor leg walked the LEVITATING hero west over the other four trap doors to (40,8) (a levitator never falls) through the east
# hall's xorns and earth elementals -- 4 of the 14 east arrivals of castle 29 in routes-lev-x4-cl5 (jf79-s7~s1 had 103/107 HP on the
# trap door and died 15 turns later); at castles 25-28 it logged 'no path from (55, 8) to (54, 3)' (the secret door (38,8) is not
# known) and held there 40-130 turns before 'M:stop': 16 of 26 died on that square, the 10 that reached 'M:stop' fell into the Valley.
# Evidence: ledger result (routes-lev-x4 arms) -- numbers filled in when the arm lands.
LIFT_EAST_DROP = True
# CASTLE_ZAP_RECOGNIZE (off): a wand of digging zapped DOWN at depth >= 25 on the main line that digs only a pit ('You dig a pit in
# the floor.') or answers 'The floor here is too hard to dig in.' (dig.c dighole, nohole: the castle) recognises the castle
# (castle.on_bottom), as the pick-axe path does. dive_logic's escape zap (WAND_RESERVE zone zap, mino_guard's zap) and its plain
# wand zap marked the level undiggable without it, and the pit-message test read only the last message page (a monster's attack
# replaces it): castle_key stayed None, so castle_logic's passage, the lift tests, CFP_RUSH and the xorn walk never ran. Evidence:
# routes-polyx14-cl5 (the 14 real polymorph-source kits x 4 salts + a worn ring of polymorph control + a wand of polymorph): 4 of the
# 10 games that zapped a digging wand down at the landing were never recognised -- they idled 2000-3000 turns on the west strip
# (jf79-s4~s1 spent 680 turns as a xorn, 6 controlled polymorphs, 'form: xorn' and no walk: xorn_strategy needs castle_key).
CASTLE_ZAP_RECOGNIZE = True
# XORN_STAIRS_NOTE (off): (1) VALLEY_XORN's '>' (dive_logic.valley_xorn) records the staircase both ways like agent.move('>') does --
# its raw agent.direction('>') did not, so on Gehennom level 2 the arrival square was an unknown floor to _wand_escape and
# _diggable_spot; (2) gehennom_escape does not zap down from a staircase or a square already refused, and any escape zap that
# 'bounces off the stairs' marks its square as a bad dig spot (WAND_STAIRS_FIX did that for the plain zap only). Evidence:
# routes-polyx14-cl5 jf88-s12~s1..s3 (a castle 25 xorn that walked the Valley's rock to the '>' in ~90 turns, then on the
# arrival '<' of Gehennom level 2: 'You start digging downward.  The stairs are too hard to dig in.', then the wand of digging
# twice: 'The beam bounces off the stairs and hits the ceiling.  You loosen a rock from the ceiling.  It falls on your head!',
# a minotaur adjacent each time, dead on depth 27). Any hero that takes the Valley's '>' this way (the xorn route) is affected.
XORN_STAIRS_NOTE = True
# POLY_RESUME (off; needs BREACH_RESUME): a castle passage given up for want of a way across ('nothing that crosses water') resumes
# when a wand of polymorph is named later (an engrave test, a deep-escape zap, the castle gamble's reads) and a worn ring may be
# polymorph control -- castle_cross._poly_now is then a way across (the xorn zap in rush_strategy). Evidence: routes-polyc14-cl5
# (the 14 real polymorph-source kits x 4 salts + a worn ring of polymorph control): jf86-s4~s2 named its iron wand 'polymorph' by
# an engrave test 27 turns after giving up and then idled 2,200 turns on the landing strip with the ring on; castle_logic's
# _maybe_resume counted only a lift, a plan item or a cold source as 'a way across'.
POLY_RESUME = True


# --- supply lane, phase 2 (lane 3, 2026-10-01 night; ledger I3xx): more route items at the Castle, and items the bot KNOWS it has ---
# All flags OFF in the commit that adds them (flag-off replays cand-l5 008ef20 byte-identically). Base 008ef20 has the phase-1
# supply flags (SUPPLY_BUY/KEEP/SELL/WAND500/TOWN) OFF and LAMP_RUB + LAMP_TEST_UNKNOWN ON.
# LAMP_RUB_FIX (off): wish_source._rub bookkeeping survives an interrupted rub. Found by the routes lane in castle-k-real-x4 (jf85-s12,
# cand-l5): rub 2 'a puff of smoke', rub 3 freed the djinni and the wish was made ('single wish: blessed ring of teleport control'),
# but T_ROUTE_TOP's tele_route preempts the moment the wished ring is in the pack, so AgentChangeStrategy left _rub's step before
# `st.djinni += 1; st.oil.add(g)`: the emptied (now OIL) lamp stayed a candidate, and with the letter in st.smoke the end test
# (`n >= LAMP_RUBS and g not in st.smoke`) never fired -- 'rub 4 .. rub 1969', 1,900 turns of 'Nothing happens' at the castle with the
# lamp in the hand instead of the sword, until the hero starved. P(smoke before the djinni) = 1/2 for a magic lamp (apply.c dorub:
# 1/3 djinni, 1/3 smoke, 1/3 nothing per rub), so half of all castle lamp wishes hit it. On: the exceptional exit of the RUB step counts
# the djinni from the wish counter / the message (and a puff of smoke), the lamp is taken out of the hand again by the next tick, and
# a lamp that has been rubbed LAMP_RUBS_MAX times is dropped from the candidates whatever it showed.
LAMP_RUB_FIX = True
LAMP_RUBS_MAX = 40          # (read with LAMP_RUB_FIX) rubs after which any lamp is judged spent: (2/3)^40 = 1e-7 for a magic lamp
# LAMP_CASTLE_TEST (off; read with LAMP_TEST_UNKNOWN False -- the mechanics-only fallback when TOOL_GLYPH_ID is not on): a lamp that
# may be an oil lamp is not test-rubbed early but kept and rubbed on the castle level like a known magic lamp. cand-l4's gate: 47
# games rubbed a lamp, 14 were magic, 11 of those were rubbed early (Dlvl 3-8) and lost to hostile 6 / peaceful 3 / vanished 2; the
# 3 castle rubs all wished. A rub of a magic lamp frees the djinni 1/3 and puffs smoke 1/3 (dorub), so a test rub loses the djinni
# half the time before it learns anything.
LAMP_CASTLE_TEST = False
# SUPPLY_FOOD_RESERVE (off; read with SUPPLY_BUY): BUY_FOOD leaves alone the price of a wanted lamp / instrument that was seen on the
# level, is not bought yet and is affordable now (not while hungry or with under one ration carried). Harness supply-twoshop (a lamp at
# 67 zm in Izchak's, junk sold in another shop to 128-153 zm): the gold became a food ration and two fortune cookies on the way back
# and the lamp was never bought, in 3 of 3 runs.
SUPPLY_FOOD_RESERVE = True
# SUPPLY_TOWN_FOOD_LAST (off; read with SUPPLY_TOWN): no food is bought while the Minetown sweep is under way (unless hungry or under one
# ration carried); after it BUY_FOOD walks back to the deli. Harness supply-minetown seed 0: a 120 zm hero spent 90 on a lembas wafer
# and a ration in the first shop and stood at 30 zm in front of a 50 zm magic lamp in the hardware store (the lamp was seen only
# after the deli: the reserve above cannot protect gold from a shop not seen yet).
SUPPLY_TOWN_FOOD_LAST = False
# SUPPLY_SCAN_TOWN_ONLY (off; read with SUPPLY_BUY): Supply.scan (stand on every shelf square of the shop we are in) acts only in the
# Gnomish Mines; the tour's check_items already walks the shelves of the Dlvl 1-4 shops. A2 on jf600: 8 of 15 games differ from the base,
# 5 of them at the first shelf walk of a shop (same shelves, other order, other RNG draws): a pure reshuffle of the early game.
SUPPLY_SCAN_TOWN_ONLY = False
# SUPPLY_ARMOR (off; read with SUPPLY_BUY; asked for by the AC lane, 2026-10-02): Supply.buy also buys armour for an EMPTY slot -- ANY
# body armour when nothing is worn on the body and no unworn suit is carried, gloves / boots / a helm / a shield into an empty slot
# only (never a second piece, never a replacement) -- at most SUPPLY_ARMOR_MAX zm a piece, after every lamp / instrument / scare
# monster, and never with the price of a wanted lamp / instrument we could pay right now. Only pieces whose type is certain and not
# magical (a Valkyrie knows the names of all non-magical armour, u_init.c knows_class(ARMOR_CLASS): a shelf shows leather armor, leather
# gloves, low boots, orcish helm; old / padded gloves, combat boots, a conical hat stay ambiguous and are never bought). A bought piece
# is worn with its beatitude unknown (inventory.get_best_armorset), about one shelf piece in eight is cursed. Census of the 150 cand-l5
# base games: body armour on a shelf in 60 games (leather armor 5-7 zm, studded leather 15-20, scale mail 45-60), gloves in 10 (leather
# gloves 8-11), boots 17, helm 12, shield 9; 14 of 63 castle arrivals wore no body armour and 62 of 63 no gloves.
SUPPLY_ARMOR = False
SUPPLY_ARMOR_MAX = 60
# PREEMPT_TRACE (dev tool, off; preempt_trace.py): log "PTRACE ..." for every step / atom block whose end-of-block preempt checks raised
# (which helper's tail was skipped: the bug class of F362), true or a dict {"fuzz": {"owner": [...], "p", "skip", "max", "seed"}} that
# also fires a harmless preemption at the exit of the named helpers. Logging only without "fuzz"; no game RNG is drawn either way.
PREEMPT_TRACE = False
# BUY_WALK_FIX (off; ledger B309's shape in item/inventory.py): buy_food / buy_instrument counted a walk to the shelf that a preempting
# strategy cut short as a failed walk (a try/finally around agent.go_to), and three failures leave the item alone for 2000 turns: in a
# town where peacefuls and fights interrupt, a 15 zm tooled horn (INSTRUMENT_KEEP is on in cand-l5) was out of reach for the rest of
# the visit. On: only a panic or a walk that ends short counts.
BUY_WALK_FIX = True
# PREEMPT_SAFE (off; F362 audit of the unowned multi-step modules): bookkeeping that follows a step / atom block is written in a
# finally so that the end-of-block preempt checks cannot skip it: Inventory.drop notes a dropped scroll that may be scare monster
# (note_scare, passed by the scare-drop sites) before anything can raise, wand_text_retest records its re-test, opp_items.play /
# use_camera record what the horn / camera turned out to be, known_items and id_engine keep their no-teleport and sell-test notes.
PREEMPT_SAFE = True
# ATTACK_GUARD (off; coordinator's F377 item): the global [yn] answer of agent.update is 'y', so 'Really attack Sipaliwini?' (uhitm.c
# attack_checks: the move or blow goes at a peaceful the hero can see) attacked the shopkeeper -- arrivals-base-jf659 s14: a fight
# with a small mimic in a general store killed a peaceful dwarf and the next blow hit the shopkeeper, who zapped a wand of striking
# until the hero was dead; shopkeeper / priest / watchman anger kills about 1 game in 100. On: that prompt is answered 'n' for a
# shopkeeper, temple priest, watchman, vault guard or quest leader (a proper name or an office), the monster tracker is refreshed, and
# the third refusal in one game turn is followed by a search turn (a refusal passes no game time). Other peacefuls are attacked as
# before (the Mines' gnomes: 48 prompts in the corpus; DWARF_HUNT wants a peaceful dwarf's pick-axe).
ATTACK_GUARD = True
ATTACK_GUARD_CAP = 3

# --- landing lane (lane 1 "landing", readiness program phase 2, 2026-10-01 night; dive_logic._landing_direct_update, ...) ---
# All OFF in the commit that adds them. Evidence (harness castle-k-instr-x4 = 112 real castle arrivals + an unidentified tonal
# instrument x 4 level salts, 448 games, paired per game; base = cand-l5 008ef20, run ck-instr-x4-cl5: crusher square 113, pass30 12):
# + LANDING_CRUSH_FIRST (existing flag) 163 / 15 -> + LANDING_DIRECT 184 / 19 -> + LANDING_ROUTE + LANDING_FOCUS 234 / 20 -> with the
# router's later fixes (run lnd-a4-final) 242 / 19: 54% of the landings reach the square (base 25%), the courtyard is reached in 205 of
# 400 maze landings after a median 18 turns (51 with CRUSH_FIRST alone), pass30 4.2% [2.7, 6.5] vs 2.7% [1.5, 4.6] (n.s.: the walk-in from the square is
# the next leak, not the landing). Why the games were lost (census, JF_CENSUS=1): 255 of the 448 landings have a MINOTAUR awake in the
# west maze at turn 0 (median distance 4, within 3 squares in 73, first within 3 squares at T+2, adjacent at T+9) and 88 a covetous
# lich (master/arch-lich teleports next to the hero a median 5 turns after the fall and summons nasties); the square is reached in 59%
# of the castles with neither and 8-30% in the others. The oracle route from a landing to the courtyard is a median 6 turns (dig 4
# turns per wall); the bot needed a median 31 (it stood still in 88% of those turns: recognition dig and pit 19%, rest 13%, scare-pile
# hold 11%, pit fights 11%).
# FINAL VALIDATION (one queued run lnd-final, 1982 games, per-game bot.cfg; tree b9e6839; dev/landing/final.py): the four flags
# CRUSH_FIRST + DIRECT + ROUTE + FOCUS on castle-k-instr-x4: square 246, crush_over 129, pass30 20/448 = 4.5% [2.9, 6.8], castlebench
# PASS 21; on the HELD-OUT level salts 5-8 (castle-k-instr-x4h, the same 112 kits, 448 pairs): square 124 -> 214 (+20.1 pt, t +8.5),
# crush_over 73 -> 120 (+10.5 pt, t +4.7), throne 51 -> 69, alive@300 +5.1 pt, but pass30 18 -> 18 (+11/-11). POOLED 896 pairs:
# square 237 -> 460 (t +14.4), crush_over 135 -> 249 (t +7.8), throne 90 -> 152 (t +5.1), pass30 30 -> 38 = 3.35% [2.4, 4.7] ->
# 4.24% [3.1, 5.8] (+0.9 pt, sign +29/-21 p 0.32: not significant). P(pass | on the square) is 30/237 = 12.7% for the cand-l5
# arrivals and 38/460 = 8.3% with the flags: the 223 extra arrivals convert at ~3.6% (weaker kits, castles with an awake minotaur or
# lich that follows them to the square). The flags are a funnel/survival gain that becomes passes with the square-phase fixes.
# Flag-off identity: 111 of 112 games byte-identical to cand-l5 (the 1 difference is a wall-clock shopkeeper name); real kits as
# carried (castle-k-real, 112): with the flags on 105 identical, the 7 that differ all carry a tonal instrument, 0 of 104 kit-less
# games change.
# LANDING_DIRECT (off; needs a crusher-armed kit, PASSTUNE_CRUSHER): at a castle-likely landing (Dungeons of Doom, depth >= 25,
# bot x <= 9, below Medusa if known) the castle is recognised on the first turn instead of by the dig that fails ('too hard to
# dig', median 6 turns later, in a pit). The level counts as undiggable from turn 0 (no recognition pit, no digging-wand zap
# by the minotaur guard, no scare-pile dig). Retracted when no castle sound is heard within LANDING_DIRECT_VERIFY turns.
LANDING_DIRECT = True
LANDING_DIRECT_VERIFY = 12
# LANDING_DIRECT_WINDOW: the game turns after the landing in which the recognition is still decided (1: only the first turns, the
# kit as it fell; 10: also when the instrument arrives a few turns later, e.g. a tooled horn wished from a lamp; asked by the
# wishes lane for WISH_SINGLE_V2 / LAMP_RUB_FIRST). Untested for that purpose; smoke: 14 kit-less real kits with the window at 12
# replay the base byte for byte.
LANDING_DIRECT_WINDOW = 1
# LANDING_DIRECT_ANY (off; with LANDING_DIRECT): the same recognition for every kit, not only the crusher-armed ones (the castle
# logic then works from turn 0 instead of from the failed recognition dig, a median 6 turns later, in a pit). With ROUTE_ALL on the
# 112 real kits (castle-k-real, no route item): courtyard reached in 31 of 99 maze landings instead of 22, median turn 29 instead of
# 50, but pass 0 -> 0 and sea-monster deaths 12 -> 20; routes' castle-k-polyc14 (56 games): pass30 19 -> 19. No gain: keep off.
LANDING_DIRECT_ANY = False
# LANDING_ROUTE (off; the crusher's walk out of the west maze): replaces CASTLE_WEST_DIG's straight L (rows first, digging every
# wall: 21.8 turns on the 400 true harness maps) by a replanned cheapest route over the maze (castle_logic._route_step): known
# squares 1 turn, walls 5 (apply + 3 dig turns + the step), unknown squares by the maze's structure (cells always floor, the
# corners between them always wall, the passages open 57% / 66%), diagonal moves and digs allowed (not between two solid squares
# when the pack weighs over 600), monsters and known traps avoided. 10.0 turns simulated (11.3 for a heavy hero, 8.7 with the
# whole map known).
LANDING_ROUTE = True
# LANDING_ROUTE_ALL (off; with LANDING_ROUTE): every Castle._approach caller (front door, polymorph, ...) leaves the west maze by the
# route, not only the crusher's (a kit with a digging tool; without one the route isn't used at all). Not used by the levitation
# route (castle_cross.cl_route_step has its own maze leg). Results: see LANDING_DIRECT_ANY. Keep off.
LANDING_ROUTE_ALL = False
# LANDING_ROUTE_ZAP (off; with LANDING_ROUTE): a KNOWN wand of digging with charges opens a wall of the maze in 1 turn per zap
# (zap.c zap_dig: in a maze level it digs one wall and stops) instead of the 4 turns of the pick-axe; at most LANDING_ROUTE_ZAPS
# charges (the castle floor can't be dug down; the rest of the charges stay for the dive through Gehennom). Harness
# landing-digwand (22 kits with a known wand of digging x 4 salts = 88 games, the four flags with / without): the zap ran in 41 games;
# square 45 -> 51 (+8/-2, t +2.0) but crush_over 29 -> 25, pass30 4 -> 5 (+3/-2): no pass gain measurable at n = 88. Keep off.
LANDING_ROUTE_ZAP = False
LANDING_ROUTE_ZAPS = 3
# LANDING_FOCUS (off; crusher-armed kit, castle known): while the walk to the crusher square is ahead the optional detours wait
# (dive_logic.landing_pending): the HP rest in the maze (a XL-7 hero heals 1 HP in 5 turns), and the scare-pile hold of
# CASTLE_SCARE (it kept the hero on a dropped, usually fake, pile for 150 turns after the last Elbereth-ignorer was seen and then
# rested to 90% HP: 16% of the first 40 turns of the 448 harness landings). With the flag the hold ends LANDING_FOCUS_HOLD turns
# after the last ignorer in view and never rests for HP.
LANDING_FOCUS = True
LANDING_FOCUS_HOLD = 12
# STRAT_TRACE (dev only, off): log 'STRAT <name>' whenever a different preempting strategy takes a step (agent.preempt), to see
# which layer spends the turns. Plays exactly as without it.
STRAT_TRACE = False

# --- arrivals lane (phase 2, 2026-10-02): more live castle arrivals; every flag below is OFF in the commit that adds it ---
# EAT_SWEEP (off): after a fight, walk to the fresh corpses of our own kills and eat them. Measured on the cand-l5 gate / jf650-659
# base: the hero's kills leave ~7,200 nutrition per game (monst.c cnutrit x corpse chance) and she eats <= 3,550 of it; with
# CORPSE_DEBUG on jf660, of the kills that left a visible corpse 51% were eaten, 33% were stepped over without a meal (a hostile
# in view keeps fight2 above the eater) and 16% never visited. The existing CLAIM_CORPSES only walks to corpses <= CLAIM_DIST (3)
# steps away that are <= CLAIM_MAX_AGE (15) turns old. The sweep takes any recorded corpse (a kill we saw, so its age is known)
# within EAT_SWEEP_DIST BFS steps whose age on arrival stays under CORPSE_MAX_AGE (eat.c rots at age/(10+rn2(20)) > 5: 59 turns are
# safe, 30 is the bot's own margin), worth at least EAT_SWEEP_MIN_NUT nutrition (EAT_SWEEP_MIN_NUT_HUNGRY when Hungry or worse), with
# no hostile within EAT_SWEEP_QUIET steps, in the tour and in a tool-less dive, never Satiated. Why it matters: 25% of the hunger
# cycles run out of food ~250 turns before a prayer is safe (median wait 250 turns, ~11 faints), 561 faint episodes per 270 games
# carry a 5.5% death risk within 200 turns against 0.9% baseline (F355; ~26 excess deaths per 270 games).
EAT_SWEEP = False
EAT_SWEEP_DIST = 12
EAT_SWEEP_AGE = 22
EAT_SWEEP_MIN_NUT = 40
EAT_SWEEP_MIN_NUT_HUNGRY = 10
EAT_SWEEP_QUIET = 8
# REST_STICKY (off): dive_logic.elbereth_rest ends the moment no hostile is within 2 squares. A scared monster flees for rnd(10)
# turns (rnd(100) one time in 7; monmove.c distfleeck) and comes back, so against a fast pack (fire ants, soldier ants, killer
# bees, jackals) the rest ended at 40-60% HP whenever the pack stepped off, the bot left its square to fight or explore, and the
# pack caught it in the open: the arrivals pack suite (XL8 Valkyrie, three fire ants) logs 'ELBERETH rest start' at HP 25/73,
# a rest that ends at 33/73 with the ants 3-4 squares away, two fights in the open and 36 -> 0 HP in 4 turns. With the flag a
# rest that has begun goes on while a monster that moves and respects Elbereth is in view within REST_STICKY_RADIUS squares
# (or was REST_STICKY_GRACE turns ago), for at most REST_STICKY_TURNS turns after the rest began (HP comes back 1 point per 5-6
# turns at XL 8, so the way up to ELBERETH_REST_UNTIL takes a long time; the passive 1/(40 + 3 Dex) wipe of the dust is read
# and re-engraved by the rest itself).
REST_STICKY = True
REST_STICKY_RADIUS = 8
REST_STICKY_GRACE = 12
REST_STICKY_TURNS = 300

# --- armour lane (phase 2; wear / keep logic; ledger F382, R423): AC at the castle arrival ---
# Castle arrivals (cand-k, 112): AC mean 0.7, median 0; the crusher route passes 6.8% at AC <= -2 against 2.0% above (F380,
# kit-clustered, z 4.0), and AC at Medusa moves the pass by 0.029 per point (F067). dev/digbench.py on 186 real dig starts:
# ARMOR_UP alone takes 0.3-0.4 AC; the next block is the mattock kits (32% of dig starts, AC +2.3 at the castle against -0.4 for
# pick-axe kits): the dive drops the starting +3 small shield (4 AC) because a dwarvish mattock is two-handed.
# MATTOCK_SHIELD (off): the shield is KEPT, not dropped, when the dive digs with a mattock (dive_logic.dig_with_tool, dig_toward;
# ItemPriority._split keeps it in the pack), and it goes back on where the mattock is not in use: on the castle level once the
# west maze is behind us or the visit is 60 turns old (the castle's own dig routes -- west dig, boulder smash, door digging --
# apply the tool at once and a worn shield refuses a mattock) and in the Valley. The pass wields the best ONE-handed weapon first, wears only a shield
# whose beatitude is known (the starting 'uncursed +3 small shield': an unknown one could be cursed and strand the mattock for
# good), and any refused dig ('You cannot dig a two-handed weapon while wearing a shield') takes the shield off again and keeps
# it off for MATTOCK_SHIELD_LOCK turns (wear_best_stuff too).
MATTOCK_SHIELD = True
MATTOCK_SHIELD_LOCK = 60
# ARMOR_VALUE (off): Inventory.get_best_armorset ranks the pieces of a slot by AC alone, so a KNOWN pair of speed boots (AC 1)
# never replaces iron shoes (AC 2), power gauntlets tie with leather gloves and lose to the worn piece, a shield of reflection
# (AC 2) loses to the +3 small shield (AC 4) -- the wishes lane spends its wishes on these pieces. With the flag a piece ranks by
# AC plus armor_value.BONUS (speed boots +8: R453 prices speed above a gray dragon scale mail; power gauntlets +3; reflection
# +4; magic resistance +4; oilskin +2 against eel wraps), and known levitation / fumbling / opposite-alignment pieces are never
# worn. It acts wherever wear_best_stuff / the item priority run (the tour's gather_items; the dive with ARMOR_UP).
ARMOR_VALUE = True

_raw = os.environ.get('JF_CFG')
if _raw:
    for _name, _value in json.loads(_raw).items():
        if _name in globals() and not _name.startswith('_'):
            globals()[_name] = _value

# JSON object keys are strings
GRIND_LEVELS = {int(_k): int(_v) for _k, _v in (GRIND_LEVELS or {}).items()}

if TOUR_FIXES is not None:
    EARLY_FIXES = LATE_FIXES = bool(TOUR_FIXES)
if LATE_FIXES:
    HAZARD_FIXES = True
