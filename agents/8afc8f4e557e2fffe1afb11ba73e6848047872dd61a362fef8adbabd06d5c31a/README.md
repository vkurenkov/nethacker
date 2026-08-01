# altar-logic-r7

Materialized symbolic AutoAscend candidate `sha256:8afc8f4e557e2fffe1afb11ba73e6848047872dd61a362fef8adbabd06d5c31a`.

This directory contains the actual evolved Python policy, not only a score claim. Neural
baselines, MuZero, notebooks, dataset tooling, visualization code, and legacy runners are
excluded. `manifest.json` records every included file digest.

## Reproduce

Run from the root of this personal `nethacker` repository:

```bash
docker build --file agents/8afc8f4e557e2fffe1afb11ba73e6848047872dd61a362fef8adbabd06d5c31a/Dockerfile --tag nethacker-agent:altar-logic-r7 .
docker run --rm --network=none --read-only --tmpfs /tmp:rw,nosuid,nodev,size=1g nethacker-agent:altar-logic-r7
```

The image defaults to the public smoke seed `1168650410` and 5,000 actions. Override the
runner arguments after the image name to select another seed or step limit.

## Provenance

- Baseline: [`dunnolab/nethack-bot@fe3c9a21679d79c1a696987d90c4a6fe87f7c124`](https://github.com/dunnolab/nethack-bot/tree/fe3c9a21679d79c1a696987d90c4a6fe87f7c124)
- Parent: `root AutoAscend baseline`
- Candidate schema: `nethacker.candidate/v1`
- Runtime: `runtime/2f2e058433775caa`
