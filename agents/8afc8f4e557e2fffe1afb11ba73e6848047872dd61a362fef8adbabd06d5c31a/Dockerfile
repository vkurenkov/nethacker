# syntax=docker/dockerfile:1.7
FROM ghcr.io/astral-sh/uv:0.11.2@sha256:c4f5de312ee66d46810635ffc5df34a1973ba753e7241ce3a08ef979ddd7bea5 AS uv
FROM python:3.12.7-slim-bookworm@sha256:60d9996b6a8a3689d36db740b49f4327be3be09a21122bd02fb8895abb38b50d

COPY --from=uv /uv /usr/local/bin/uv
ENV HOME=/tmp     LC_ALL=C.UTF-8     MPLBACKEND=Agg     MPLCONFIGDIR=/tmp/matplotlib     NUMBA_CACHE_DIR=/tmp/numba     PYTHONHASHSEED=0     PYTHONIOENCODING=utf-8     PYTHONPATH=/opt/runtime     TMPDIR=/tmp

COPY runtime/2f2e058433775caa/requirements.txt /tmp/requirements.txt
RUN uv pip install --system --no-cache --requirement /tmp/requirements.txt &&     rm /tmp/requirements.txt
COPY runtime/2f2e058433775caa/nethacker /opt/runtime/nethacker
COPY agents/8afc8f4e557e2fffe1afb11ba73e6848047872dd61a362fef8adbabd06d5c31a/heur /opt/autoascend/heur

LABEL org.opencontainers.image.title="NetHacker agent altar-logic-r7"       org.opencontainers.image.revision="sha256:8afc8f4e557e2fffe1afb11ba73e6848047872dd61a362fef8adbabd06d5c31a"       org.opencontainers.image.source="https://github.com/dunnolab/nethack-bot.git"       org.opencontainers.image.base.name="AutoAscend@fe3c9a21679d79c1a696987d90c4a6fe87f7c124"

USER 65532:65532
ENTRYPOINT ["python", "-m", "nethacker.runner", "--baseline", "/opt/autoascend"]
CMD ["--seed", "1168650410", "--max-steps", "5000"]
