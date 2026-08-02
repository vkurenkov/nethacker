# syntax=docker/dockerfile:1.7@sha256:a57df69d0ea827fb7266491f2813635de6f17269be881f696fbfdf2d83dda33e
FROM ghcr.io/astral-sh/uv:0.11.2@sha256:c4f5de312ee66d46810635ffc5df34a1973ba753e7241ce3a08ef979ddd7bea5 AS uv
FROM python:3.12.7-slim-bookworm@sha256:60d9996b6a8a3689d36db740b49f4327be3be09a21122bd02fb8895abb38b50d AS build

COPY --from=uv /uv /usr/local/bin/uv
COPY requirements.txt /tmp/requirements.txt
RUN uv venv /opt/venv && \
    uv pip install --python /opt/venv/bin/python --no-cache --requirement /tmp/requirements.txt

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
COPY run.py /opt/nethacker/run.py
COPY autoascend /opt/autoascend

LABEL org.opencontainers.image.title="NetHacker agent autoascend-baseline" \
      org.opencontainers.image.revision="sha256:4c7218c4c6a0ff51716b118a3669d75e439380d16e0efb1715b60c4c815b8a90" \
      org.opencontainers.image.source="autoascend" \
      org.opencontainers.image.base.name="AutoAscend@fe3c9a21679d79c1a696987d90c4a6fe87f7c124"

USER 65532:65532
ENTRYPOINT ["/opt/venv/bin/python", "/opt/nethacker/run.py", "--baseline", "/opt/autoascend"]
CMD ["--seed", "1168650410", "--max-steps", "5000"]
