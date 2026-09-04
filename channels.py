"""수집·대시보드 대상 채널 목록 (여러 채널 지원).

각 항목:
  key      : 데이터 폴더 이름(data/<key>/) — 영문, 바꾸지 말 것(누적 데이터 위치)
  name     : 화면 표시 이름(헤더 토글 버튼 라벨)
  channel  : 텔레그램 채널 @username. None 이면 수집 건너뜀(대시보드는 '준비 중' 표시)
  group    : 연결된 토론 그룹 @username. None 이면 그룹 섹션 자체를 숨김
  path     : 사이트 경로. "" = 루트(/), "mirae" = /mirae/
  cobak    : 코박 활동 섹션 표시 여부(cobak.py 수집 대상은 캉다방 고정)
  quota    : 게시글 서비스 표시 방식
             {"mode": "count", "total": 50, "baseline": "<ISO 시각>"}  → 남은횟수 카운트
             {"mode": "deadline", "deadline": "YYYY-MM-DD", "label": "부스팅"} → D-day 표기
             None → 칩 숨김

API_ID/API_HASH 는 그대로 config.py(비공개)에 둔다. 이 파일은 git 에 포함되어
맥미니가 자동으로 받으므로, 채널 추가/변경은 여기만 고쳐 push 하면 된다.
"""
from pathlib import Path
import shutil

ROOT = Path(__file__).parent
DATA_ROOT = ROOT / "data"

CHANNELS = [
    {
        "key": "kang",
        "name": "캉다방",
        "channel": "@kang_tearoom",
        "group": "@kangtearoom_chat",
        "path": "",
        "cobak": True,
        # 2026-09-30 까지 부스팅 기간 — 횟수 대신 D-day 로 표기
        "quota": {"mode": "deadline", "deadline": "2026-09-30", "label": "부스팅"},
    },
    {
        "key": "mirae",
        "name": "미래전략식",
        "channel": None,          # TODO: @username 입력 시 수집 시작
        "group": None,            # 그룹 세션 보류
        "path": "mirae",
        "cobak": False,
        # 2026-09-04 기준 잔여 50회 — 이 시각 이후 게시글 1건당 1회 차감
        "quota": {"mode": "count", "total": 50, "baseline": "2026-09-04T11:40:00+09:00"},
    },
]

PRIMARY = CHANNELS[0]


def by_key(key):
    for c in CHANNELS:
        if c["key"] == key:
            return c
    raise KeyError(f"채널 key 없음: {key}")


def data_dir(key):
    d = DATA_ROOT / key
    d.mkdir(parents=True, exist_ok=True)
    return d


# 채널별 폴더로 옮길 옛(단일 채널) 데이터 파일들. 로그·락·샘플은 data/ 에 그대로 둔다.
_LEGACY_FILES = [
    "daily_summary.csv", "broadcast_stats.json", "post_forwards.json",
    "join_leave.json", "join_leave_group.json", "group_members_snapshot.json",
    "group_top_members.json", "quota.json", "cobak_stats.json", "dashboard.html",
]


def migrate_legacy_layout():
    """data/ 바로 아래 있던 단일 채널 파일을 data/<PRIMARY key>/ 로 1회 이동.
    이미 옮겨졌거나 옛 파일이 없으면 아무것도 하지 않는다."""
    legacy = DATA_ROOT / "daily_summary.csv"
    if not legacy.exists():
        return []
    dest = data_dir(PRIMARY["key"])
    moved = []
    for name in _LEGACY_FILES:
        src = DATA_ROOT / name
        if src.exists() and not (dest / name).exists():
            shutil.move(str(src), str(dest / name))
            moved.append(name)
    for src in sorted(DATA_ROOT.glob("channel_posts_*.csv")):
        if not (dest / src.name).exists():
            shutil.move(str(src), str(dest / src.name))
            moved.append(src.name)
    if moved:
        print(f"[migrate] 옛 데이터 {len(moved)}개 → data/{PRIMARY['key']}/ 이동")
    return moved
