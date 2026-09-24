#!/usr/bin/env bash
set -euo pipefail
MODEL="${1:-modelo_validacao.yml}"
python3 simulator.py run "$MODEL"
