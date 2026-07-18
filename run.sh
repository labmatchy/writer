#!/usr/bin/env bash
# One-command runner: checks the environment, installs only what's missing,
# then generates lab-test descriptions with the project defaults.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

DEFAULT_INPUT="input/testnames.txt"
DEFAULT_OUTPUT="output/lab_test_descriptions.csv"
DEFAULT_MODEL="gemma4:latest"
OLLAMA_HOST="${OLLAMA_HOST:-http://localhost:11434}"
VENV_DIR="${ROOT_DIR}/.venv"

INPUT_PATH="$DEFAULT_INPUT"
OUTPUT_PATH="$DEFAULT_OUTPUT"
MODEL_NAME="$DEFAULT_MODEL"

usage() {
  cat <<EOF
Usage: ./run.sh [--input PATH] [--output PATH] [--model NAME]

Defaults:
  --input   ${DEFAULT_INPUT}
  --output  ${DEFAULT_OUTPUT}
  --model   ${DEFAULT_MODEL}
EOF
}

log() {
  printf '==> %s\n' "$*"
}

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --input)
      [[ $# -ge 2 ]] || fail "--input requires a path"
      INPUT_PATH="$2"
      shift 2
      ;;
    --output)
      [[ $# -ge 2 ]] || fail "--output requires a path"
      OUTPUT_PATH="$2"
      shift 2
      ;;
    --model)
      [[ $# -ge 2 ]] || fail "--model requires a name"
      MODEL_NAME="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "Unknown argument: $1 (try --help)"
      ;;
  esac
done

# Resolve relative paths against the repo root.
[[ "$INPUT_PATH" = /* ]] || INPUT_PATH="${ROOT_DIR}/${INPUT_PATH}"
[[ "$OUTPUT_PATH" = /* ]] || OUTPUT_PATH="${ROOT_DIR}/${OUTPUT_PATH}"

log "Checking Python"
if ! command -v python3 >/dev/null 2>&1; then
  fail "python3 was not found. Install Python 3.9+ and try again."
fi

PYTHON_VERSION="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)' \
  || fail "Python 3.9+ is required (found ${PYTHON_VERSION})."
log "Python ${PYTHON_VERSION} found"

log "Checking virtual environment"
if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  log "Creating virtual environment at .venv"
  python3 -m venv "$VENV_DIR"
else
  log "Virtual environment already exists"
fi

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"
PYTHON="${VENV_DIR}/bin/python"
PIP="${VENV_DIR}/bin/pip"

log "Checking Python dependencies"
if ! "$PYTHON" - <<'PY'
import importlib.util
import sys

required = ("pandas", "openpyxl", "openai", "tqdm", "blood_testing")
missing = [name for name in required if importlib.util.find_spec(name) is None]
if missing:
    print(",".join(missing))
    sys.exit(1)
PY
then
  log "Installing missing package dependencies"
  "$PIP" install --upgrade pip
  "$PIP" install -e .
else
  log "Dependencies already installed"
fi

log "Checking input file"
[[ -f "$INPUT_PATH" ]] || fail "Input file not found: ${INPUT_PATH}"
log "Input: ${INPUT_PATH}"

log "Checking Ollama CLI"
if ! command -v ollama >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    log "Ollama not found; installing with Homebrew"
    brew install ollama
  else
    fail "ollama was not found. Install it from https://ollama.com/download and try again."
  fi
else
  log "Ollama CLI found"
fi

ollama_ready() {
  curl -fsS "${OLLAMA_HOST}/api/tags" >/dev/null 2>&1
}

log "Checking Ollama server at ${OLLAMA_HOST}"
STARTED_OLLAMA=0
if ollama_ready; then
  log "Ollama server is already running"
else
  log "Starting Ollama server"
  ollama serve >/tmp/blood-testing-ollama.log 2>&1 &
  STARTED_OLLAMA=1
  for _ in $(seq 1 30); do
    if ollama_ready; then
      break
    fi
    sleep 1
  done
  ollama_ready || fail "Ollama server did not become ready. See /tmp/blood-testing-ollama.log"
  log "Ollama server is ready"
fi

log "Checking model ${MODEL_NAME}"
if ollama list 2>/dev/null | awk 'NR > 1 { print $1 }' | grep -Fxq "$MODEL_NAME"; then
  log "Model ${MODEL_NAME} already available"
else
  log "Pulling model ${MODEL_NAME}"
  ollama pull "$MODEL_NAME"
fi

mkdir -p "$(dirname "$OUTPUT_PATH")"

log "Generating descriptions"
"$PYTHON" -m blood_testing \
  --input "$INPUT_PATH" \
  --output "$OUTPUT_PATH" \
  --model "$MODEL_NAME"

log "Done"
if [[ "$STARTED_OLLAMA" -eq 1 ]]; then
  log "Note: Ollama was started by this script and is still running in the background."
fi
