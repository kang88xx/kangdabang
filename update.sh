#!/bin/zsh
# 캉티룸 통계 자동 업데이트 — collect.py(수집) → build_dashboard.py(생성) → site 복사 → Vercel 배포
# launchd(com.kangtearoom.update)가 6시간마다(KST 09·15·21·03시) 실행한다.
# 로그: data/update.log
#
# 실패 게이트: 수집/빌드가 실패하거나 오늘 데이터가 비면 배포를 건너뛰고 맥 알림을 띄운다.
#   → 옛 데이터로 '가짜 신선' 배포되는 것을 막는다. (화면 있는 맥에서만 알림이 보임)
# 배포 인증: vercel CLI 전역 로그인(auth.json) 사용 → 별도 토큰 불필요.
# PATH: launchd 최소 PATH 대응으로 homebrew bin(node·vercel) 선반영.
export PATH="/opt/homebrew/bin:$PATH"
cd "$(dirname "$0")" || exit 1
PY="./venv/bin/python"
LOG="data/update.log"
LAUNCHD_LOG="data/launchd.log"

# 맥 알림(화면 있을 때 표시) — 헤드리스 맥미니에선 조용히 무시됨
notify() { osascript -e "display notification \"$1\" with title \"캉다방 통계 — 업데이트 실패\"" 2>/dev/null; }

# B2) PID 락 — 중복 실행 차단(회차 겹침·맥미니+이맥 동시구동 시 같은 텔레그램 세션 동시접속 방지)
LOCK="data/update.lock"
if [ -e "$LOCK" ] && kill -0 "$(cat "$LOCK" 2>/dev/null)" 2>/dev/null; then
  echo "이미 실행 중 — 이번 회차 건너뜀"; exit 0
fi
echo $$ > "$LOCK"; trap 'rm -f "$LOCK"' EXIT

# B5) 로그 무한 증가 방지 — 최근 200KB만 보존(append 전에 잘라냄)
[ -f "$LOG" ] && tail -c 200000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
[ -f "$LAUNCHD_LOG" ] && tail -c 200000 "$LAUNCHD_LOG" > "$LAUNCHD_LOG.tmp" && mv "$LAUNCHD_LOG.tmp" "$LAUNCHD_LOG"

{
  echo "===== $(date '+%Y-%m-%d %H:%M:%S') 업데이트 시작 ====="

  # 1) 수집 — 실패 시 배포 중단
  if ! "$PY" collect.py; then
    echo "!!! collect.py 실패 — 빌드/배포 중단"; notify "데이터 수집 실패 — 대시보드 미갱신"; exit 1
  fi

  # 2) 빈 데이터 가드 — 오늘 포스트 CSV가 실제로 생겼는지(비어있지 않은지)
  TODAY_CSV="data/channel_posts_$(date -u +%Y-%m-%d).csv"
  if [ ! -s "$TODAY_CSV" ]; then
    echo "!!! 오늘 데이터 없음($TODAY_CSV) — 배포 중단"; notify "수집 데이터 없음 — 대시보드 미갱신"; exit 1
  fi

  # 3) 빌드 — 실패 시 배포 중단
  if ! "$PY" build_dashboard.py; then
    echo "!!! build_dashboard.py 실패 — 배포 중단"; notify "대시보드 생성 실패"; exit 1
  fi

  # 4) 배포본 교체 + Vercel 배포(1회 재시도)
  cp data/dashboard.html site/index.html
  echo "----- $(date '+%Y-%m-%d %H:%M:%S') 빌드 완료, Vercel 배포 시작 -----"
  if ! ( cd site && vercel deploy --prod --yes ); then
    echo "배포 1차 실패 — 30초 후 재시도"; sleep 30
    ( cd site && vercel deploy --prod --yes ) || { echo "!!! 배포 재시도 실패"; notify "Vercel 배포 실패"; exit 1; }
  fi
  echo "----- $(date '+%Y-%m-%d %H:%M:%S') 완료 -----"
} >> "$LOG" 2>&1
