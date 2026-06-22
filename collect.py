import asyncio
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from telethon import TelegramClient
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.messages import GetExportedChatInvitesRequest
from telethon.tl.functions.stats import (
    GetBroadcastStatsRequest, GetMessagePublicForwardsRequest,
)

from config import API_ID, API_HASH, CHANNEL, GROUP
from tg_graphs import load_graph, parse_graph, by_name

OUT_DIR = Path(__file__).parent / "data"
OUT_DIR.mkdir(exist_ok=True)

POST_WINDOW = 150          # 포스트 표/공유처 분석에 사용할 최근 게시물 수
FWD_TOP_N = 40             # 공유처를 조회할 상위(공유수) 포스트 수


async def collect_channel(client, username, since):
    """24시간 요약(summary) + 최근 POST_WINDOW개 포스트(posts)를 함께 수집."""
    entity = await client.get_entity(username)
    full = await client(GetFullChannelRequest(entity))
    subscribers = full.full_chat.participants_count

    posts, day_views, day_fwd, day_rep, day_new = [], 0, 0, 0, 0
    async for msg in client.iter_messages(entity, limit=POST_WINDOW):
        v = msg.views or 0
        f = msg.forwards or 0
        r = msg.replies.replies if msg.replies else 0
        posts.append({
            "date": msg.date.isoformat(), "id": msg.id,
            "views": v, "forwards": f, "replies": r,
            "text": (msg.text or "")[:80].replace("\n", " "),
        })
        if msg.date >= since:                 # 최근 24시간 요약용 집계
            day_new += 1
            day_views += v; day_fwd += f; day_rep += r

    summary = {
        "subscribers": subscribers, "new_posts": day_new,
        "views": day_views, "forwards": day_fwd, "replies": day_rep,
    }
    return entity, summary, posts


async def collect_post_forwards(client, entity, posts, top_n=FWD_TOP_N):
    """포스트별 '공개 재공유 채널 + 그 채널에서의 조회수'. (관리자/대형 채널 전용)"""
    targets = sorted([p for p in posts if p["forwards"] > 0],
                     key=lambda p: -p["forwards"])[:top_n]
    out = {}
    for p in targets:
        try:
            pf = await client(GetMessagePublicForwardsRequest(
                channel=entity, msg_id=p["id"], offset="", limit=30))
        except Exception:
            continue
        chats = {c.id: getattr(c, "title", "외부 채널") for c in getattr(pf, "chats", [])}
        channels = []
        for f in getattr(pf, "forwards", []) or []:
            m = getattr(f, "message", f)
            peer = getattr(m, "peer_id", None)
            cid = getattr(peer, "channel_id", None) or getattr(peer, "chat_id", None)
            channels.append({
                "title": chats.get(cid, "외부 채널"),
                "username": None,
                "views": getattr(m, "views", 0) or 0,
            })
        channels.sort(key=lambda c: -c["views"])
        if channels:
            out[str(p["id"])] = {
                "count": len(channels),
                "ext_views": sum(c["views"] for c in channels),
                "channels": channels,
            }
    return out


async def collect_group(client, username, since):
    entity = await client.get_entity(username)
    full = await client(GetFullChannelRequest(entity))
    members = full.full_chat.participants_count

    msg_count = 0
    speaker = Counter()
    async for msg in client.iter_messages(entity):
        if msg.date < since:
            break
        msg_count += 1
        if msg.sender_id:
            speaker[msg.sender_id] += 1

    top = []
    for sid, cnt in speaker.most_common(100):     # 활발한 멤버 — 페이지네이션용 전체
        name = f"user {sid}"
        username = None
        try:
            u = await client.get_entity(sid)
            username = getattr(u, "username", None)
            name = (getattr(u, "title", None)
                    or " ".join(x for x in [getattr(u, "first_name", None),
                                            getattr(u, "last_name", None)] if x)
                    or (("@" + username) if username else name))
        except Exception:
            pass
        top.append({"id": sid, "name": name, "username": username, "count": cnt})

    return {"members": members, "messages": msg_count,
            "active_users": len(speaker), "top_members": top}


async def collect_broadcast_stats(client, entity):
    """텔레그램 공식 통계. 규모/권한 미충족 시 available=False."""
    try:
        s = await client(GetBroadcastStatsRequest(channel=entity))
    except Exception as e:
        return {"available": False, "reason": f"호출 불가 — {type(e).__name__}: {e}"}

    def cur(obj, attr):
        o = getattr(s, attr, None)
        return int(getattr(o, "current", 0) or 0) if o is not None else None

    en = getattr(s, "enabled_notifications", None)
    part = int(getattr(en, "part", 0) or 0)
    total = int(getattr(en, "total", 0) or 0)
    metrics = {}
    metrics["구독자 (공식)"] = cur(s, "followers")
    metrics["게시물당 평균 조회"] = cur(s, "views_per_post")
    metrics["게시물당 평균 공유"] = cur(s, "shares_per_post")
    rpp = cur(s, "reactions_per_post")
    if rpp is not None:
        metrics["게시물당 평균 반응"] = rpp
    if total:
        metrics["알림 켠 인원"] = f"{part:,} / {total:,}"
        metrics["음소거 비율"] = f"{(total - part) / total * 100:.1f}%"
    metrics = {k: v for k, v in metrics.items() if v is not None}
    return {"available": True, "metrics": metrics, "period_days": 0}

async def collect_followers_today(client, entity):
    """오늘(그래프 최신일) 들어온/나간 인원. 공식 통계 followers_graph 기반.
    호출 불가/미생성 시 (None, None)."""
    try:
        bs = await client(GetBroadcastStatsRequest(channel=entity))
        foll = parse_graph(await load_graph(client, getattr(bs, "followers_graph", None)))
    except Exception:
        return None, None
    joined = by_name(foll, "join", "들어")
    left = by_name(foll, "left", "leav", "나가", "나감")
    # 오늘 그래프 포인트가 아직 없으면 None (과거 값을 오늘로 오표기하지 않음 → '진행 중' 표시)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return joined.get(today), left.get(today)


def _disp_name(u):
    if u is None:
        return None
    return (getattr(u, "title", None)
            or " ".join(x for x in [getattr(u, "first_name", None),
                                    getattr(u, "last_name", None)] if x)
            or (("@" + u.username) if getattr(u, "username", None) else f"user {getattr(u, 'id', '?')}"))


async def collect_join_leave(client, entity, limit=500):
    """admin log에서 '누가' 가입/탈퇴했는지 수집. 관리자 권한 필요.
    채널은 가입/탈퇴 이벤트가 풍부; 그룹은 공개링크 가입이 로그에 안 남을 수 있음.
    호출 불가 시 available=False."""
    events = []
    try:
        async for e in client.iter_admin_log(entity, join=True, leave=True,
                                             invite=True, limit=limit):
            cls = type(e.action).__name__
            kind = "join" if "Join" in cls else ("left" if "Leave" in cls else None)
            if not kind:
                continue
            u = e.user
            events.append({
                "date": e.date.isoformat(),
                "kind": kind,
                "name": _disp_name(u),
                "username": getattr(u, "username", None),
                "id": getattr(u, "id", None),
            })
    except Exception as ex:
        return {"available": False, "reason": f"{type(ex).__name__}: {ex}"}
    return {"available": True, "events": events}

async def collect_invite_sources(client, entity):
    try:
        me = await client.get_me()
        res = await client(GetExportedChatInvitesRequest(
            peer=entity, admin_id=me.id, limit=50))
    except Exception:
        return []
    out = []
    for inv in getattr(res, "invites", []):
        out.append({
            "link": getattr(inv, "link", ""),
            "title": getattr(inv, "title", None) or getattr(inv, "link", ""),
            "count": getattr(inv, "usage", None) or 0,
        })
    out.sort(key=lambda x: x["count"], reverse=True)
    return out


def write_json(name, obj):
    (OUT_DIR / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2),
                               encoding="utf-8")


async def main():
    # 1일 기준 = 한국시간(KST) 오전 9시 ~ 다음날 9시 = UTC 00:00 ~ 24:00.
    # 텔레그램 공식 통계 그래프가 UTC 일 버킷(=KST 9시)이므로 동일 기준으로 맞춘다.
    now_utc = datetime.now(timezone.utc)
    since = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)  # 오늘 버킷 시작(=KST 오늘 9시)
    today = now_utc.strftime("%Y-%m-%d")                                # 그래프와 동일한 UTC 날짜 라벨

    async with TelegramClient("my_session", API_ID, API_HASH) as client:
        print(f"=== 통계 수집 ({today}) ===\n")

        ent, ch, posts = await collect_channel(client, CHANNEL, since)
        print(f"[채널 {CHANNEL}] 구독자 {ch['subscribers']:,} · "
              f"24h 포스트 {ch['new_posts']} · 조회 {ch['views']:,} · "
              f"수집 포스트 {len(posts)}건")

        gr = await collect_group(client, GROUP, since)
        print(f"[그룹 {GROUP}] 멤버 {gr['members']:,} · "
              f"메시지 {gr['messages']:,} · 활성 {gr['active_users']:,}")

        official = await collect_broadcast_stats(client, ent)
        write_json("broadcast_stats.json", official)
        print(f"공식 통계 : {'수집됨' if official.get('available') else '미생성'}")

        ch_joined, ch_left = await collect_followers_today(client, ent)
        if ch_joined is not None or ch_left is not None:
            print(f"오늘 유입 : 들어옴 {ch_joined or 0} · 나감 {ch_left or 0}")

        joinleave = await collect_join_leave(client, ent)
        write_json("join_leave.json", joinleave)
        if joinleave.get("available"):
            ev = joinleave["events"]
            jn = sum(1 for e in ev if e["kind"] == "join")
            lv = sum(1 for e in ev if e["kind"] == "left")
            print(f"유입/이탈 : 유입 {jn} · 이탈 {lv} (admin log {len(ev)}건)")
        else:
            print(f"유입/이탈 : 미수집 — {joinleave.get('reason', '')}")

        gr_ent = await client.get_entity(GROUP)
        joinleave_gr = await collect_join_leave(client, gr_ent)
        write_json("join_leave_group.json", joinleave_gr)
        if joinleave_gr.get("available"):
            evg = joinleave_gr["events"]
            jng = sum(1 for e in evg if e["kind"] == "join")
            lvg = sum(1 for e in evg if e["kind"] == "left")
            print(f"그룹 유입/이탈 : 유입 {jng} · 이탈 {lvg} (admin log {len(evg)}건)")
        else:
            print(f"그룹 유입/이탈 : 미수집 — {joinleave_gr.get('reason', '')}")

        fwds = await collect_post_forwards(client, ent, posts)
        write_json("post_forwards.json", fwds)
        print(f"공유처    : {len(fwds)}개 포스트")

        invites = await collect_invite_sources(client, ent)
        write_json("invite_sources.json", invites)
        write_json("group_top_members.json", gr["top_members"])
        print(f"유입 링크 : {len(invites)}개 · 활발 멤버 {len(gr['top_members'])}명\n")

        # 포스트 CSV (대시보드 표/공유처 매칭용)
        posts_csv = OUT_DIR / f"channel_posts_{today}.csv"
        with posts_csv.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["date", "id", "views", "forwards", "replies", "text"])
            w.writeheader()
            w.writerows(posts)
        print(f"포스트 → {posts_csv}")

        # 일일 요약 (같은 날짜는 1행만 — 멱등 · 역수집 컬럼 보존)
        summary_csv = OUT_DIR / "daily_summary.csv"
        header = ["date", "ch_subscribers", "ch_joined", "ch_left", "ch_new_posts",
                  "ch_views", "ch_forwards", "ch_replies",
                  "gr_members", "gr_messages", "gr_active_users"]
        existing = {}
        if summary_csv.exists():
            with summary_csv.open(encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    existing[r["date"]] = r
        existing[today] = {
            "date": today,
            "ch_subscribers": ch["subscribers"],
            "ch_joined": "" if ch_joined is None else ch_joined,
            "ch_left": "" if ch_left is None else ch_left,
            "ch_new_posts": ch["new_posts"],
            "ch_views": ch["views"],
            "ch_forwards": ch["forwards"],
            "ch_replies": ch["replies"],
            "gr_members": gr["members"],
            "gr_messages": gr["messages"],
            "gr_active_users": gr["active_users"],
        }
        rows = [{k: existing[d].get(k, "") for k in header} for d in sorted(existing)]
        with summary_csv.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=header)
            w.writeheader()
            w.writerows(rows)
        print(f"요약 → {summary_csv} ({len(rows)}일)")


if __name__ == "__main__":
    asyncio.run(main())
