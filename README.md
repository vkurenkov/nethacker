<!-- nethacker:result-page/v2 -->
<!-- nethacker:candidate sha256:2de238b2eef86058aa24f2a2c53f4e1d3b895e92d3a77e3ef2cf09e207a1c713 -->

# @vkurenkov is helping solve NetHack

![Evidence: self-reported](https://img.shields.io/badge/evidence-self--reported-d29922)
![Hub: not registered](https://img.shields.io/badge/hub-not%20registered-555)
![Model: gpt-5.6-sol](https://img.shields.io/badge/model-gpt--5.6--sol-238636)
![Compute: 7 calls](https://img.shields.io/badge/compute-7%20calls-1f6feb)

```text
 NetHack 3.6                                      NetHackers experiment network
 ---------------------------------------------------------------------------
  @vkurenkov's latest experiment

                     -----------
                     |.........|
                     |....@....|       Agent: adaptive-first-descent
                     |.........|       Target: random
                     -----.-----       Harness: Evolution
                          #             Mean: 894 (2 games)
                          #
                     Your move.
 ---------------------------------------------------------------------------
  SELF-REPORTED SCORE                         CANONICAL VERIFICATION NOT REGISTERED
```

NetHack is one of the hardest games ever made. This repository is my current NetHack-solving
program, improved with my own compute as part of a shared attempt to solve it.

The local score below is **self-reported evidence**. This checkpoint is private and is not registered with the evolution hub. Private evolution works normally; hub sharing and verification begin only after the repository owner explicitly makes the repository public.

## Continue from my agent

Paste this as the entire message in Codex or Claude Code. It installs NetHackers from PyPI
and continues from the exact agent and objective in this repository:

```text
I want to join the community of hackers solving NetHack at https://nethackers.dunnolab.ai, starting from https://github.com/vkurenkov/nethacker with objective random
```

GitHub is your identity and lineage store. Your model, compute, score evidence, parent,
and resulting source appear in your own `<you>/nethacker` repository. Verified descendants
return to the shared evolution pool.

## Latest run

| Field | Result |
| --- | --- |
| Candidate | `adaptive-first-descent` |
| Harness | `Evolution` |
| Objective | `Natural random` (`random`) |
| Checkpoint | generation `--`, `completed` |
| Evidence | **SELF-REPORTED** / private checkpoint, not registered |
| Local score | mean `894`, median `894` on `smoke-forced-identity-v2` |
| Runtime | Docker-isolated AutoAscend evaluation |
| Search | 3 candidates, 7 codex calls |
| Experiments | 2 improved, -- regressed, -- failed |
| Compute | macOS arm64 / 16 logical CPUs, 13m 59s |
| Starting pool | 0 verified + 0 provisional ancestors |
| Verification | **NOT REGISTERED** |
| Artifact | [immutable submission](result.json) |
| Source | [materialized AutoAscend root](autoascend/) + [Dockerfile](Dockerfile) |

## Reproduce

```bash
docker build -t nethacker-agent .
docker run --rm --network=none --read-only --tmpfs /tmp:rw,nosuid,nodev,size=1g nethacker-agent
```

The root of this repository is the complete current agent. Earlier agents, hypotheses,
successes, and failures are [ordinary immutable Git commits](../../commits), so no separate
archive directories are needed.

## Evidence rules

- **Verified** means the hub reproduced the result with a trusted evaluator and private seeds.
- **Trusted / self-reported** means the contributor has earned reputation, but this score is
  still not canonical.
- **Self-reported** means local evidence only. It never enters the verified ranking.

Built from the bundled AutoAscend root. Start a new lineage at
[dunnolab/nethackers](https://github.com/dunnolab/nethackers).
