# syfthub/endpoint-runner — base image for SyftHub endpoint containers.
#
# Security model: this image embeds the in-container loader (server.py)
# AND bwrap. server.py runs as the entrypoint and never imports the
# user's runner.py — every request spawns a fresh bwrap-isolated child
# which loads runner.py inside the sandbox. .env, policy/, setup.yaml
# are never present in the container's filesystem; the host loader
# materializes a synth dir containing only code + declared resources
# and bind-mounts it at /app/synth.
#
# This Dockerfile is also the contract for custom endpoint Dockerfiles:
# any image that wants to be used as an endpoint runner MUST have bwrap
# installed AND the syft_runtime files at /usr/local/lib/syft_runtime/,
# AND must pass the build-time bwrap verification probe. The host SDK
# checks the syfthub.sandbox.bwrap=verified label before launching.

FROM python:3.11-slim AS base

# bubblewrap is the in-container sandbox; ca-certificates lets HTTPS
# proxies work from the handler.
RUN apt-get update && apt-get install -y --no-install-recommends \
        bubblewrap \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Non-root user — uid/gid match the container spec (BuildEndpointSpec
# sets User: "1000:1000"). User name MUST be "runner" — existing
# user-authored Dockerfiles `FROM syfthub/endpoint-runner` reference it
# (chown runner:runner …, USER runner, /home/runner/...).
RUN groupadd -g 1000 runner && \
    useradd -u 1000 -g 1000 -m -d /home/runner -s /bin/sh runner

# The trusted in-container runtime: server.py is the entrypoint,
# syft_entry.py is the per-bwrap-child loader, _syft_audit.py is the
# audit hook (imported explicitly by syft_entry.py — see comment near
# ENV below), session_loop.py is the in-bwrap AgentSession.
#
# These files are owned by root and chmod a-w so even a compromised
# runner user cannot tamper with them.
COPY server.py syft_entry.py _syft_audit.py session_loop.py _protocol.py \
     /usr/local/lib/syft_runtime/
RUN chown root:root /usr/local/lib/syft_runtime/*.py && \
    chmod a-w /usr/local/lib/syft_runtime/*.py && \
    chmod a+r /usr/local/lib/syft_runtime/*.py

# Mount points that the host binds into at runtime.
#   /app/synth   <- bind RO, code + declared resources only
#   /app/ws      <- bind RW, workspace pool
#   /app/.cache  <- volume RW, pip cache
#   /app/.store  <- volume RW, policy SQLite
RUN mkdir -p /app/synth /app/ws /app/.cache /app/.store && \
    chown -R runner:runner /app/ws /app/.cache /app/.store && \
    chmod 555 /app/synth

# NOTE: We do NOT run bwrap during the build. Docker BuildKit applies a
# restrictive seccomp profile to build containers that blocks
# unshare(CLONE_NEWUSER) — the very syscall bwrap needs. This is a build
# sandbox limitation, not a host kernel one; bwrap works fine at
# `docker run` time where we control the security flags.
# Verification happens at runtime via VerifyImage (see ../build.go) which
# spawns a one-shot container with the same hardening as a real endpoint
# container and probes bwrap there.

# Intentionally NOT setting PYTHONPATH globally. The audit hook lives at
# /usr/local/lib/syft_runtime/_syft_audit.py — Python's `site` module
# would auto-import it if its directory ended up on sys.path (which
# happens whenever PYTHONPATH points there OR a script is launched from
# that dir). Both would cause server.py and any RUN-step Python process
# in user-side images to be subject to the handler's audit policy, which
# is wrong.
#
# server.py spawns the bwrap child with
#   --setenv PYTHONPATH=/usr/local/lib/syft_runtime
# so the hook is only on the handler subprocess.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

USER runner
WORKDIR /app/synth

EXPOSE 8080

LABEL syfthub.sandbox.bwrap="verified" \
      syfthub.sandbox.version="2" \
      org.opencontainers.image.title="syfthub-endpoint-runner" \
      org.opencontainers.image.description="SyftHub container runner with bwrap-isolated handler subprocess"

ENTRYPOINT ["python3", "/usr/local/lib/syft_runtime/server.py"]
