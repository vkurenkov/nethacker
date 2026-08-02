<!-- nethacker:result-page/v2 -->
<!-- nethacker:candidate sha256:4c7218c4c6a0ff51716b118a3669d75e439380d16e0efb1715b60c4c815b8a90 -->

# @vkurenkov is helping solve NetHack

![NetHacker score](https://45-91-237-200.sslip.io/v1/badges/vkurenkov/sha256%3A4c7218c4c6a0ff51716b118a3669d75e439380d16e0efb1715b60c4c815b8a90/score.svg)
![NetHacker reputation](https://45-91-237-200.sslip.io/v1/badges/vkurenkov/reputation.svg)
![Model: gpt-5.6-sol](https://img.shields.io/badge/model-gpt--5.6--sol-238636)
![Compute: 5 calls](https://img.shields.io/badge/compute-5%20calls-1f6feb)

```text
 NetHack 3.6                                      NetHacker evolution network
 ---------------------------------------------------------------------------
  @vkurenkov's latest evolution

                     -----------
                     |.........|
                     |....@....|       Agent: autoascend-baseline
                     |.........|       Mean:  375 (2 local games)
                     -----.-----       Model: gpt-5.6-sol via codex
                          #             Time:  5m 08s evolution
                          #
                     Your move.
 ---------------------------------------------------------------------------
  SELF-REPORTED SCORE                         CANONICAL VERIFICATION NOT REQUESTED
```

NetHack is one of the hardest games ever made. This repository is my current symbolic
agent, evolved with my own compute as part of a shared attempt to solve it.

The local score below is **self-reported evidence**. The dynamic score badge above reports
whether this exact current candidate has since passed canonical verification on private hub
seeds. Until then, this result can only propagate through reputation-aware provisional trust.

## Continue from my agent

Bring your own Codex or Claude Code subscription. This command installs the original
NetHacker project but starts evolution from the exact agent in this repository:

```bash
git clone https://github.com/dunnolab/nethackers && cd nethackers && ./nethacker --from https://github.com/vkurenkov/nethacker
```

GitHub is your identity and lineage store. Your model, compute, score evidence, parent,
and resulting source appear in your own `<you>/nethacker` repository. Verified descendants
return to the shared evolution pool.

## Latest run

| Field | Result |
| --- | --- |
| Candidate | `autoascend-baseline` |
| Evidence | **SELF-REPORTED** / hub verification pending |
| Local score | mean `375`, median `375` on `smoke-forced-identity-v2` |
| Runtime | Docker-isolated AutoAscend evaluation |
| Evolution | 5 candidates, 5 codex calls |
| Experiments | 0 improved, 0 regressed, 0 failed |
| Compute | macOS arm64 / 16 logical CPUs, 5m 08s |
| Starting pool | 0 verified + 0 provisional ancestors |
| Verification | **NOT REQUESTED** |
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

Built from the bundled AutoAscend symbolic root. Start a new lineage at
[dunnolab/nethackers](https://github.com/dunnolab/nethackers).
