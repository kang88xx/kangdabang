#!/bin/zsh
# 더블클릭하면 즉시: 수집(collect) → 대시보드 생성(build) → 크롬으로 열기
cd "$(dirname "$0")" || exit 1
echo "캉티룸 통계 갱신 중… (30초~2분 소요)"
./update.sh
echo "완료. 크롬으로 엽니다."
open -a "Google Chrome" data/dashboard.html
