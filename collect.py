import asyncio
import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

from telethon import TelegramClient
from telethon.tl.functions.channels import GetFullChannelRequest

from config import API_ID, API_HASH, CHANNEL, GROUP

OUT_DIR = Path(__file__).parent / "data"
OUT_DIR.mkdir(exist_ok=True)


async def collect_channel(client, username, since):
    entity = await client.get_entity(username)
    full = await client(GetFullChannelRequest(entity))
    subscribers = full.full_chat.participants_count

    posts = []
    async for msg in client.iter_messages(entity):
        if msg.date < since:
            break
        posts.append({
            "date": msg.date.isoformat(),
            "id": msg.id,
            "views": msg.views or 0,
            "forwards": msg.forwards or 0,
            "replies": msg.replies.replies if msg.replies else 0,
            "text": (msg.text or "")[:80].replace("\n", " "),
        })

    return {
        "subscribers": subscribers,
        "posts": posts,
        "total_views": sum(p["views"] for p in posts),
        "total_forwards": sum(p["forwards"] for p in posts),
        "total_replies": sum(p["replies"] for p in posts),
    }


async def collect_group(client, username, since):
    entity = await client.get_entity(username)
    full = await client(GetFullChannelRequest(entity))
    members = full.full_chat.participants_count

    msg_count = 0
    active_users = set()
    async for msg in client.iter_messages(entity):
        if msg.date < since:
            break
        msg_count += 1
        if msg.sender_id:
            active_users.add(msg.sender_id)

    return {
        "members": members,
        "messages": msg_count,
        "active_users": len(active_users),
    }


async def main():
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    today = datetime.now().strftime("%Y-%m-%d")

    async with TelegramClient("my_session", API_ID, API_HASH) as client:
        print(f"=== 최근 24시간 통계 ({today}) ===\n")

        ch = await collect_channel(client, CHANNEL, since)
        print(f"[채널 {CHANNEL}]")
        print(f"  구독자        : {ch['subscribers']:,}")
        print(f"  신규 포스트   : {len(ch['posts'])}")
        print(f"  총 조회수     : {ch['total_views']:,}")
        print(f"  총 공유수     : {ch['total_forwards']:,}")
        print(f"  총 댓글수     : {ch['total_replies']:,}\n")

        gr = await collect_group(client, GROUP, since)
        print(f"[그룹 {GROUP}]")
        print(f"  멤버          : {gr['members']:,}")
        print(f"  메시지 수     : {gr['messages']:,}")
        print(f"  활성 유저     : {gr['active_users']:,}\n")

        posts_csv = OUT_DIR / f"channel_posts_{today}.csv"
        if ch["posts"]:
            with posts_csv.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=ch["posts"][0].keys())
                w.writeheader()
                w.writerows(ch["posts"])
            print(f"포스트 상세 → {posts_csv}")

        summary_csv = OUT_DIR / "daily_summary.csv"
        new_file = not summary_csv.exists()
        with summary_csv.open("a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new_file:
                w.writerow([
                    "date", "ch_subscribers", "ch_new_posts", "ch_views",
                    "ch_forwards", "ch_replies",
                    "gr_members", "gr_messages", "gr_active_users",
                ])
            w.writerow([
                today, ch["subscribers"], len(ch["posts"]),
                ch["total_views"], ch["total_forwards"], ch["total_replies"],
                gr["members"], gr["messages"], gr["active_users"],
            ])
        print(f"일일 요약 → {summary_csv}")


if __name__ == "__main__":
    asyncio.run(main())
