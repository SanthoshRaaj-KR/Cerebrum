# The interview backend: FastAPI + pipecat.
#
# python:3.13-slim rather than alpine — pipecat pulls in onnxruntime,
# numpy, scipy and av, which all ship manylinux wheels but no musl ones.
# On alpine pip falls back to building them from source, which turns a
# two-minute image into a twenty-minute one.
FROM python:3.13-slim

# libgomp1: onnxruntime (Silero VAD, Smart Turn) links against OpenMP.
# The rest of pipecat's audio stack ships prebuilt wheels and needs nothing.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first, as their own layer: requirements.txt changes far less
# often than the source, so rebuilds after a code edit skip the whole
# ~700MB install.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/

ENV PYTHONPATH=/app/backend \
    PYTHONUNBUFFERED=1 \
    INTERVIEW_AGENT_HOST=0.0.0.0 \
    INTERVIEW_AGENT_PORT=7332

EXPOSE 7332

# config.yaml is bind-mounted by compose rather than copied, so editing a
# mode or the question count doesn't need a rebuild.

HEALTHCHECK --interval=10s --timeout=5s --start-period=40s --retries=5 \
    CMD curl -fsS http://localhost:7332/api/health || exit 1

CMD ["python", "-m", "interview_agent.bridge"]
