import asyncio
from telethon import TelegramClient
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.stats import (
    GetBroadcastStatsRequest, GetMessagePublicForwardsRequest,
)
from telethon.tl.types import InputPeerEmpty
from config import API_ID, API_HASH, CHANNEL


async def main():
    async with TelegramClient("my_session", API_ID, API_HASH) as client:
        me = await client.get_me()
        print("로그인:", me.first_name, "(@%s)" % me.username if me.username else "")

        ent = await client.get_entity(CHANNEL)
        full = await client(GetFullChannelRequest(ent))
        subs = full.full_chat.participants_count
        print("채널:", CHANNEL, "구독자:", subs)

        # 공식 통계 가용?
        try:
            stats = await client(GetBroadcastStatsRequest(channel=ent))
            print("공식통계: OK")
            print("  followers.current      =", getattr(stats.followers, "current", "?"))
            print("  views_per_post.current =", getattr(stats.views_per_post, "current", "?"))
            print("  shares_per_post.current=", getattr(stats.shares_per_post, "current", "?"))
            en = stats.enabled_notifications
            print("  enabled_notif part/total =", getattr(en, "part", "?"), "/", getattr(en, "total", "?"))
            print("  attr list:", [a for a in dir(stats) if not a.startswith("_")][:30])
        except Exception as e:
            print("공식통계 실패:", type(e).__name__, e)

        # 첫 forwards>0 포스트에 대해 public forwards 테스트
        target = None
        async for msg in client.iter_messages(ent, limit=60):
            if (msg.forwards or 0) > 0:
                target = msg
                break
        if target:
            print(f"\npublic forwards 테스트 (msg {target.id}, fwd={target.forwards}):")
            try:
                pf = await client(GetMessagePublicForwardsRequest(
                    channel=ent, msg_id=target.id, offset_rate=0,
                    offset_peer=InputPeerEmpty(), offset_id=0, limit=20))
                print("  반환 타입:", type(pf).__name__)
                print("  attrs:", [a for a in dir(pf) if not a.startswith("_")][:20])
                msgs = getattr(pf, "messages", None) or getattr(pf, "forwards", None) or []
                print("  count:", len(msgs))
                for m in msgs[:5]:
                    print("   -", type(m).__name__, "| views:", getattr(getattr(m,'message',m),'views', '?'))
            except Exception as e:
                print("  public forwards 실패:", type(e).__name__, e)
        else:
            print("forwards>0 포스트 없음")


asyncio.run(main())
