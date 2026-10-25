#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export OLLAMA_MODELS="$project_root/data/ollama-models"
export OLLAMA_HOST="127.0.0.1:11435"
export OLLAMA_NO_CLOUD=1

exec ollama serve
