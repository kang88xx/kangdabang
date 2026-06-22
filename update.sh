#!/bin/zsh
# 캉티룸 통계 자동 업데이트 — collect.py(수집) → build_dashboard.py(생성)
# 하루 1회 cron/launchd 로 돌리면 daily_summary 가 매일 한 줄씩 빠짐없이 쌓인다.
# 로그: data/update.log
cd "$(dirname "$0")" || exit 1
PY="./venv/bin/python"
LOG="data/update.log"
{
  echo "===== $(date '+%Y-%m-%d %H:%M:%S') 업데이트 시작 ====="
  "$PY" collect.py
  "$PY" build_dashboard.py
  echo "----- $(date '+%Y-%m-%d %H:%M:%S') 완료 -----"
} >> "$LOG" 2>&1
