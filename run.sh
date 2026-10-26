#!/usr/bin/env bash
# Запуск веб-интерфейса Streamlit
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

echo "🚀 Запуск Game Playtest Video Recap Web UI..."
streamlit run app.py
