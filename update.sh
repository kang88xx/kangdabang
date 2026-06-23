#!/bin/zsh
# 캉티룸 통계 자동 업데이트 — collect.py(수집) → build_dashboard.py(생성) → site 복사 → Vercel 배포
# launchd(com.kangtearoom.update)가 6시간마다(KST 09·15·21·03시) 실행한다.
# 로그: data/update.log
#
# 배포 인증: vercel CLI 전역 로그인(auth.json)을 그대로 사용 → 별도 토큰 불필요.
# PATH 설정: launchd는 최소 PATH로 돌기 때문에 homebrew bin(node·vercel)을 직접 잡아준다.
export PATH="/opt/homebrew/bin:$PATH"
cd "$(dirname "$0")" || exit 1
PY="./venv/bin/python"
LOG="data/update.log"
{
  echo "===== $(date '+%Y-%m-%d %H:%M:%S') 업데이트 시작 ====="
  "$PY" collect.py
  "$PY" build_dashboard.py
  # 배포본(site/index.html)을 최신 빌드로 교체 → 헤더의 '최종 업데이트' 시각이 이 시점으로 갱신됨
  cp data/dashboard.html site/index.html
  echo "----- $(date '+%Y-%m-%d %H:%M:%S') 빌드 완료, Vercel 배포 시작 -----"
  ( cd site && vercel deploy --prod --yes )
  echo "----- $(date '+%Y-%m-%d %H:%M:%S') 완료 -----"
} >> "$LOG" 2>&1
