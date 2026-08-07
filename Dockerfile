# syntax=docker/dockerfile:1.7@sha256:a57df69d0ea827fb7266491f2813635de6f17269be881f696fbfdf2d83dda33e
FROM ghcr.io/astral-sh/uv:0.11.2@sha256:c4f5de312ee66d46810635ffc5df34a1973ba753e7241ce3a08ef979ddd7bea5 AS uv
FROM python:3.12.7-slim-bookworm@sha256:60d9996b6a8a3689d36db740b49f4327be3be09a21122bd02fb8895abb38b50d AS build

COPY --from=uv /uv /usr/local/bin/uv
COPY requirements.txt /tmp/requirements.txt
RUN uv venv /opt/venv && \
    uv pip install --python /opt/venv/bin/python --no-cache --requirement /tmp/requirements.txt
RUN uv pip install --python /opt/venv/bin/python --no-cache "nethackers==0.7.0"

FROM python:3.12.7-slim-bookworm@sha256:60d9996b6a8a3689d36db740b49f4327be3be09a21122bd02fb8895abb38b50d

ENV HOME=/tmp \
    LC_ALL=C.UTF-8 \
    MPLBACKEND=Agg \
    MPLCONFIGDIR=/tmp/matplotlib \
    NUMBA_CACHE_DIR=/tmp/numba \
    PYTHONHASHSEED=0 \
    PYTHONIOENCODING=utf-8 \
    TMPDIR=/tmp

COPY --from=build /opt/venv /opt/venv
COPY solution /opt/solution

LABEL org.opencontainers.image.title="NetHackers agent adaptive-first-descent" \
      org.opencontainers.image.revision="sha256:2de238b2eef86058aa24f2a2c53f4e1d3b895e92d3a77e3ef2cf09e207a1c713" \
      org.opencontainers.image.source="autoascend" \
      org.opencontainers.image.base.name="AutoAscend@fe3c9a21679d79c1a696987d90c4a6fe87f7c124"

USER 65532:65532
ENTRYPOINT ["/opt/venv/bin/python", "-m", "nethackers.eval.runner", "--baseline", "/opt/solution"]
CMD ["--seed", "1168650410", "--max-steps", "5000"]
