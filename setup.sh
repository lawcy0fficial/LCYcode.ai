#!/usr/bin/env bash
# LCYcode.ai — fully automated setup. No manual steps, no login.
# Ollama is the core provider: this script verifies the daemon is
# actually up and the model actually responds before declaring success,
# not just that `ollama pull` exited zero.
set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

BOLD='\033[1m'; CYAN='\033[36m'; GREEN='\033[32m'; YELLOW='\033[33m'; RED='\033[31m'; RESET='\033[0m'

echo -e "${CYAN}${BOLD}"
echo "  _      _____ __     __            _      _ "
echo " | |    / ____|\ \   / /           | |    (_)"
echo " | |   | |      \ \_/ /___ ___   __| | ___  _ "
echo " | |   | |       \   // __/ _ \ / _\` |/ _ \| |"
echo " | |___| |____    | || (_| (_) | (_| |  __/| |"
echo " |______\_____|   |_| \___\___/ \__,_|\___||_|"
echo -e "${RESET}"
echo "offline-first agentic coding agent — automated setup"
echo "core: Ollama (local model) — cloud providers are optional fallbacks"
echo

# 1. Python venv
if [ ! -d ".venv" ]; then
  echo -e "${YELLOW}[1/7]${RESET} creating virtual environment..."
  python3 -m venv .venv
else
  echo -e "${YELLOW}[1/7]${RESET} virtual environment already exists, skipping"
fi
source .venv/bin/activate

# 2. Install the package (editable) + deps, from pyproject.toml
echo -e "${YELLOW}[2/7]${RESET} installing lcycode package + dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -e .

# 3. key.json bootstrap (demo keys, no login required)
FRESH_KEY_JSON=0
if [ ! -f "key.json" ]; then
  echo -e "${YELLOW}[3/7]${RESET} no key.json found — creating one from key.demo.json"
  cp key.demo.json key.json
  FRESH_KEY_JSON=1
  echo -e "        edit ${BOLD}key.json${RESET} later to drop in real OpenRouter / DeepSeek / Grok keys."
  echo -e "        cloud providers are optional — Ollama alone is enough to run this."
else
  echo -e "${YELLOW}[3/7]${RESET} key.json already exists, leaving it as-is"
fi

# 4. workspace dir
mkdir -p workspace
echo -e "${YELLOW}[4/7]${RESET} workspace/ ready"

# 5. Ollama daemon — install check, start-if-needed, model pull, live verification
echo -e "${YELLOW}[5/7]${RESET} configuring Ollama (the core provider)..."

OLLAMA_HOST=$(python3 - <<'PY'
import json
try:
    print(json.load(open("key.json")).get("ollama", {}).get("host", "http://127.0.0.1:11434"))
except Exception:
    print("http://127.0.0.1:11434")
PY
)
MODEL=$(python3 - <<'PY'
import json
try:
    print(json.load(open("key.json")).get("ollama", {}).get("model", "deepseek-coder:1.3b"))
except Exception:
    print("deepseek-coder:1.3b")
PY
)

if ! command -v ollama >/dev/null 2>&1; then
  echo -e "        ${RED}ollama is not installed.${RESET}"
  echo "        install it from https://ollama.com/download, then re-run ./setup.sh"
  echo "        (cloud providers in key.json will still work without it)"
else
  echo "        ollama binary found: $(command -v ollama)"

  # Is the daemon already answering?
  if curl -fsS "${OLLAMA_HOST}/api/tags" >/dev/null 2>&1; then
    echo "        ollama daemon already running at ${OLLAMA_HOST}"
  else
    echo "        ollama daemon not responding — starting it in the background..."
    nohup ollama serve > /tmp/lcycode-ollama.log 2>&1 &
    for i in $(seq 1 15); do
      sleep 1
      if curl -fsS "${OLLAMA_HOST}/api/tags" >/dev/null 2>&1; then
        echo "        daemon is up (took ${i}s)"
        break
      fi
      if [ "$i" -eq 15 ]; then
        echo -e "        ${RED}daemon did not come up after 15s — check /tmp/lcycode-ollama.log${RESET}"
      fi
    done
  fi

  # Auto-detect available RAM to recommend an appropriately-sized coding
  # model on a *fresh* key.json only (never override an existing choice).
  if [ "$FRESH_KEY_JSON" = "1" ]; then
    RAM_GB=$(python3 - <<'PY'
import os
try:
    pages = os.sysconf("SC_PHYS_PAGES")
    page_size = os.sysconf("SC_PAGE_SIZE")
    print(round(pages * page_size / (1024**3)))
except Exception:
    print(0)
PY
)
    if [ "$RAM_GB" -ge 16 ]; then
      RECOMMENDED="qwen2.5-coder:7b"
    elif [ "$RAM_GB" -ge 8 ]; then
      RECOMMENDED="deepseek-coder:6.7b"
    else
      RECOMMENDED="deepseek-coder:1.3b"
    fi
    if [ "$RECOMMENDED" != "$MODEL" ]; then
      echo "        detected ~${RAM_GB}GB RAM — recommending ${RECOMMENDED} over default ${MODEL}"
      python3 - "$RECOMMENDED" <<'PY'
import json, sys
path = "key.json"
cfg = json.load(open(path))
cfg["ollama"]["model"] = sys.argv[1]
json.dump(cfg, open(path, "w"), indent=2)
PY
      MODEL="$RECOMMENDED"
    fi
  fi

  echo "        pulling ${MODEL} (skips if already present, can take a while first time)..."
  if ollama pull "$MODEL"; then
    echo "        pulled ${MODEL}"
  else
    echo -e "        ${RED}pull failed${RESET} — run 'ollama pull $MODEL' manually when ready"
  fi

  # Live verification: an actual chat call, not just a successful pull.
  echo "        verifying the model actually responds..."
  PROBE=$(curl -fsS "${OLLAMA_HOST}/api/chat" \
    -d "{\"model\": \"${MODEL}\", \"messages\": [{\"role\": \"user\", \"content\": \"reply with OK\"}], \"stream\": false}" \
    2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin).get('message',{}).get('content','')[:40])" 2>/dev/null || echo "")
  if [ -n "$PROBE" ]; then
    echo -e "        ${GREEN}verified${RESET} — model responded: \"${PROBE}\""
  else
    echo -e "        ${RED}could not verify a response${RESET} — check /tmp/lcycode-ollama.log and 'ollama list'"
  fi

  # Tool-calling capability check — EXECUTE stage relies on native tool
  # calls for reliability; a model that doesn't support them well just
  # falls back to a slower JSON-in-prose path, which is worth knowing.
  TOOL_SUPPORT=$(python3 -m lcycode.config.model_capabilities "$MODEL" 2>/dev/null || echo "unknown")
  case "$TOOL_SUPPORT" in
    good)
      echo -e "        tool-calling: ${GREEN}${MODEL} is known to handle native tool calls well${RESET}"
      ;;
    limited)
      echo -e "        tool-calling: ${YELLOW}${MODEL} has limited/inconsistent native tool-call support${RESET}"
      echo "        it will still work via the JSON-fallback path in EXECUTE, just less reliably."
      echo "        for more reliable autonomous building, consider: ollama pull qwen2.5-coder:7b"
      ;;
    *)
      echo "        tool-calling: unknown for ${MODEL} — not in the known-models list, your mileage may vary"
      ;;
  esac
fi

# 6. Sanity-check the whole stack imports and key.json validates
echo -e "${YELLOW}[6/7]${RESET} validating key.json and package imports..."
python3 -c "from lcycode.config.key_manager import KeyManager; KeyManager(); print('        key.json is valid')"

# 7. done
echo -e "${YELLOW}[7/7]${RESET} setup complete."
echo
echo -e "${GREEN}${BOLD}LCYcode.ai is ready.${RESET}"
echo "  GUI:   ./run.sh          (or: source .venv/bin/activate && python main.py)"
echo "  CLI:   ./run.sh cli      (or: source .venv/bin/activate && python main.py cli)"
echo "  Tests: source .venv/bin/activate && pytest"
echo
echo "  Verify: source .venv/bin/activate && python3 verify_live.py [--full]"
echo "  Runs real task(s) through the full agent loop against your actual"
echo "  ollama and reports per-stage timing + whether it used native tool"
echo "  calling — the test suite mocks providers, this doesn't. --full also"
echo "  exercises run_shell and a multi-step task."
echo
echo "  Fully offline: set ollama.offline_only = true in key.json to guarantee"
echo "  no cloud provider is ever called, regardless of routing.order."
echo
