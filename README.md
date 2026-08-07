<!-- nethacker:result-page/v3 -->
<!-- nethacker:candidate sha256:2de238b2eef86058aa24f2a2c53f4e1d3b895e92d3a77e3ef2cf09e207a1c713 -->

# @vkurenkov is helping solve NetHack

This is my current program in a community effort to solve one of the hardest games ever made.

```text
 NETHACKERS // CHECKPOINT
 ------------------------------------------------------------------
 Hacker      @vkurenkov
 Program     adaptive-first-descent
 Objective   random
 Score       894 mean / 2 total episodes
 Evidence    SELF-REPORTED / private checkpoint, not registered
 Compute     gpt-5.6-sol / 7 calls / 13m 59s
 ------------------------------------------------------------------
                         @  Your move.
```

## Continue from here

Paste this as the entire message in Codex or Claude Code:

```text
I want to join the community of hackers solving NetHack at https://nethackers.dunnolab.ai, starting from https://github.com/vkurenkov/nethacker with objective random
```

## Latest result

| | |
| --- | --- |
| Objective | **Natural random** (`random`) |
| Local screen | mean **894**, median **894**, 2 total episodes |
| Checkpoint | generation -- / completed |
| Harness | Evolution |
| Compute | gpt-5.6-sol via codex, 3 candidates, 7 calls |
| Machine | macOS arm64 / 16 logical CPUs / 13m 59s |
| Verification | **NOT REGISTERED** |
| Program | [current source](solution/) + [Docker reproduction](Dockerfile) |
| Record | [result.json](result.json) |

This checkpoint is private and is not registered with the evolution hub. Private evolution works normally; hub sharing and verification begin only after the repository owner explicitly makes the repository public.

## Reproduce

```bash
docker build -t nethacker .
docker run --rm --network=none --read-only --tmpfs /tmp:rw,nosuid,nodev,size=1g nethacker
```

The current program is in [`solution/`](solution/). Every earlier checkpoint remains an ordinary
Git commit. Start a new lineage at [dunnolab/nethackers](https://github.com/dunnolab/nethackers).
