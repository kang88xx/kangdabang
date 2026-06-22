#!/bin/zsh
# 더블클릭 → 로컬 서버 실행 → 브라우저에 대시보드(+ "🔄 지금 갱신" 버튼) 표시.
# 이 창을 닫거나 Ctrl+C 하면 서버 종료. 버튼은 이 서버로 열었을 때만 보인다.
cd "$(dirname "$0")" || exit 1
echo "대시보드 서버 시작 — 브라우저가 자동으로 열립니다. (종료: Ctrl+C 또는 이 창 닫기)"
exec ./venv/bin/python server.py
