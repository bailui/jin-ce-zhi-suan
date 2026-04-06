#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export CONFIG_PRIVATE_PATH="${PROJECT_ROOT}/config.private.json"
export CUSTOM_STRATEGIES_PRIVATE_PATH="${PROJECT_ROOT}/data/strategies/custom_strategies.private.json"
export CUSTOM_STRATEGIES_WRITE_PRIVATE=1
export HTTP_PROXY=""
export HTTPS_PROXY=""
export ALL_PROXY=""
export http_proxy=""
export https_proxy=""
export all_proxy=""
export NO_PROXY="*"
export no_proxy="*"

if [ ! -d "${PROJECT_ROOT}/.venv" ]; then
  python3 -m venv "${PROJECT_ROOT}/.venv"
fi

source "${PROJECT_ROOT}/.venv/bin/activate"

python -m pip install -q -r "${PROJECT_ROOT}/requirements.txt" fastapi uvicorn tushare akshare websockets wsproto

if [ ! -f "${CONFIG_PRIVATE_PATH}" ]; then
  cat > "${CONFIG_PRIVATE_PATH}" <<'EOF'
{
  "data_provider": {
    "tushare_token": "",
    "default_api_key": "",
    "default_api_url": "",
    "llm_api_key": "",
    "strategy_llm_api_key": ""
  }
}
EOF
fi

python server.py --host 127.0.0.1 --port 8000
