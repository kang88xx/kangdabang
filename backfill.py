"""과거 N일치 일일 요약을 텔레그램 '공식 통계' 그래프에서 역수집한다.

daily_summary.csv 는 collect.py 가 '매일 1회' 누적해야만 채워진다(스냅샷 방식).
하지만 채널/그룹의 공식 통계가 활성화돼 있으면(=관리자 계정), 텔레그램이 이미
일자별 그래프를 보관 중이므로 과거치를 한 번에 끌어올 수 있다.

가져오는 지표(공식 그래프에서 추출 가능한 것만):
  채널  ch_subscribers ← growth_graph(누적 구독자)
        ch_joined      ← followers_graph(일별 들어온 인원)
        ch_left        ← followers_graph(일별 나간 인원)
        ch_views       ← interactions_graph(일별 조회수)
        ch_forwards    ← interactions_graph(일별 공유수)
  그룹  gr_members     ← growth_graph(누적 멤버)
        gr_messages    ← messages_graph(일별 메시지)

공식 그래프에 '일자별 값'이 없는 항목(ch_new_posts, ch_replies, gr_active_users)은
비워 둔다 → 대시보드에서 '—'(공백)으로 표시되어 0과 구분된다.
기존 daily_summary.csv 의 '실측' 행(collect.py 수집분)은 그대로 우선한다.

실행:  python backfill.py [일수=30]
"""
import asyncio
import csv
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from telethon import TelegramClient
from telethon.tl.functions.stats import (
    GetBroadcastStatsRequest, GetMegagroupStatsRequest,
)

from config import API_ID, API_HASH, CHANNEL, GROUP
from tg_graphs import load_graph, parse_graph, by_name, first_series

OUT_DIR = Path(__file__).parent / "data"
SUMMARY = OUT_DIR / "daily_summary.csv"
HEADER = ["date", "ch_subscribers", "ch_joined", "ch_left", "ch_new_posts",
          "ch_views", "ch_forwards", "ch_replies",
          "gr_members", "gr_messages", "gr_active_users"]
DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 30


def read_existing():
    rows = {}
    if SUMMARY.exists():
        with SUMMARY.open(encoding="utf-8") as f:
            for r in csv.DictReader(f):
                rows[r["date"]] = r
    return rows


def num(x):
    return "" if x is None else str(int(round(float(x))))


async def main():
    async with TelegramClient("my_session", API_ID, API_HASH) as client:
        print(f"=== 과거 {DAYS}일 역수집 (공식 통계 그래프) ===\n")

        ch = await client.get_entity(CHANNEL)
        gr = await client.get_entity(GROUP)

        # ── 채널 공식 통계 ──────────────────────────────
        subs, joined, left, views, shares = {}, {}, {}, {}, {}
        try:
            bs = await client(GetBroadcastStatsRequest(channel=ch))
            growth = parse_graph(await load_graph(client, getattr(bs, "growth_graph", None)))
            foll = parse_graph(await load_graph(client, getattr(bs, "followers_graph", None)))
            inter = parse_graph(await load_graph(client, getattr(bs, "interactions_graph", None)))
            subs = first_series(growth)                       # 누적 구독자
            joined = by_name(foll, "join", "들어")             # 일별 들어온 인원
            left = by_name(foll, "left", "leav", "나가", "나감")  # 일별 나간 인원
            views = by_name(inter, "view", "조회")
            shares = by_name(inter, "share", "forward", "공유")
            print(f"[채널] 구독자 {len(subs)}일 · 들어옴 {len(joined)}일 · "
                  f"나감 {len(left)}일 · 조회 {len(views)}일 · 공유 {len(shares)}일")
        except Exception as e:
            print(f"[채널] 공식 통계 실패 — {type(e).__name__}: {e}")

        # ── 그룹 공식 통계 ──────────────────────────────
        gmembers, gmsgs = {}, {}
        try:
            ms = await client(GetMegagroupStatsRequest(channel=gr))
            ggrowth = parse_graph(await load_graph(client, getattr(ms, "growth_graph", None)))
            gmsg = parse_graph(await load_graph(client, getattr(ms, "messages_graph", None)))
            gmembers = first_series(ggrowth)                  # 누적 멤버
            gmsgs = first_series(gmsg)                        # 일별 메시지
            print(f"[그룹] 멤버 {len(gmembers)}일 · 메시지 {len(gmsgs)}일")
        except Exception as e:
            print(f"[그룹] 공식 통계 실패 — {type(e).__name__}: {e}")

        if not any([subs, joined, left, views, shares, gmembers, gmsgs]):
            print("\n가져온 그래프가 없습니다. (채널/그룹 규모·관리자 권한 확인)")
            return

        # ── 병합 ───────────────────────────────────────
        cutoff = (datetime.now(timezone.utc) - timedelta(days=DAYS)).strftime("%Y-%m-%d")
        bf_dates = {d for d in (set(subs) | set(joined) | set(left) | set(views)
                                | set(shares) | set(gmembers) | set(gmsgs)) if d >= cutoff}

        existing = read_existing()
        merged = {}

        # 1) 역수집값으로 기본 행 구성
        for d in bf_dates:
            merged[d] = {
                "date": d,
                "ch_subscribers": num(subs.get(d)),
                "ch_joined": num(joined.get(d)),
                "ch_left": num(left.get(d)),
                "ch_new_posts": "",
                "ch_views": num(views.get(d)),
                "ch_forwards": num(shares.get(d)),
                "ch_replies": "",
                "gr_members": num(gmembers.get(d)),
                "gr_messages": num(gmsgs.get(d)),
                "gr_active_users": "",
            }

        # 2) 기존 실측 행이 항상 우선 (있는 값만 덮어씀)
        for d, row in existing.items():
            merged.setdefault(d, {"date": d, **{k: "" for k in HEADER[1:]}})
            for k in HEADER[1:]:
                v = (row.get(k) or "").strip()
                if v != "":
                    merged[d][k] = v

        out = [merged[d] for d in sorted(merged)]
        with SUMMARY.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=HEADER)
            w.writeheader()
            w.writerows(out)

        print(f"\n요약 → {SUMMARY} ({len(out)}일)")
        print("이제 'python build_dashboard.py' 로 대시보드를 다시 만드세요.")


if __name__ == "__main__":
    asyncio.run(main())
