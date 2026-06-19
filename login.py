from telethon import TelegramClient
from config import API_ID, API_HASH

with TelegramClient("my_session", API_ID, API_HASH) as client:
    me = client.loop.run_until_complete(client.get_me())
    print(f"로그인 성공: {me.first_name} (@{me.username})")
    print("my_session.session 파일이 생성됐어요. 다음부턴 재로그인 불필요.")
