FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY lcycode ./lcycode
COPY frontend ./frontend
COPY main.py key.demo.json ./

RUN pip install --no-cache-dir -e .

# key.json is expected to be mounted in (see docker-compose.yml) so real
# keys never get baked into the image. Falls back to the demo template
# on first boot if nothing is mounted.
VOLUME ["/app/workspace"]

EXPOSE 8420

# Uses /api/health (added once the connectivity work landed) rather than
# just checking the port is open — reports "unhealthy" if key.json is
# invalid or Ollama isn't reachable, not just if the process crashed.
# python3 -c avoids pulling in curl just for this one check.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python3 -c "import json,urllib.request,sys; \
    d=json.load(urllib.request.urlopen('http://localhost:8420/api/health', timeout=3)); \
    sys.exit(0 if d.get('status') == 'ok' else 1)" || exit 1

CMD ["python", "main.py"]
