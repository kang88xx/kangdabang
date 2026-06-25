"""코박(cobak.co) '캉다방' 활동 수집기.

cobak.co 커뮤니티에 '캉다방' 닉네임으로 올라오는 게시글을 주기적으로 가져와
data/cobak_stats.json 에 총게시글·총뷰·총추천·총댓글 + 게시글 목록(하이퍼링크)으로 저장한다.

데이터 출처(공개 JSON API, 인증 불필요):
    https://cobak.co/api/v1/users/user-575132/posts?limit=100
        - total_count : 총 게시글 수
        - list[*].shown_count    : 조회수(뷰)
        - list[*].recommend_count: 추천수
        - list[*].comment_count  : 댓글수
        - list[*].category.id    : 게시판 id (글 URL 생성에 사용)

설계 메모
  - 외부 의존성 없음(urllib 표준 라이브러리만 사용).
  - 실패해도 절대 update.sh 배포를 막지 않는다(항상 exit 0):
    가져오기 실패 시 기존 cobak_stats.json 이 있으면 그대로 두고,
    없으면 available:false 로 비워 둔다.
"""
import json
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))

ROOT = Path(__file__).parent
OUT = ROOT / "data" / "cobak_stats.json"

# 수집 대상 — '캉다방'(닉네임) cobak 유저. 최초 글 URL에서 확인한 user id.
NICKNAME = "캉다방"
USER_ID = 575132
SOURCE_URL = "https://cobak.co/ko/community/3/post/2044104"
API_URL = f"https://cobak.co/api/v1/users/user-{USER_ID}/posts?limit=100"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36")


def fetch(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def build():
    data = fetch(API_URL)
    items = data.get("list") or []

    posts = []
    tv = tr = tc = 0
    for p in items:
        views = int(p.get("shown_count") or 0)
        rec = int(p.get("recommend_count") or 0)
        cmt = int(p.get("comment_count") or 0)
        board = (p.get("category") or {}).get("id") or 3
        ts = p.get("timestamp")
        try:
            _dt = datetime.fromtimestamp(int(ts), KST)
            date = _dt.strftime("%Y-%m-%d")
            time = _dt.strftime("%H:%M")
        except Exception:
            date = (p.get("updated_time") or "")[:10]
            time = (p.get("updated_time") or "")[11:16]
        tv += views
        tr += rec
        tc += cmt
        posts.append({
            "id": p.get("id"),
            "title": (p.get("title") or "(제목 없음)").strip(),
            "url": f"https://cobak.co/ko/community/{board}/post/{p.get('id')}",
            "views": views,
            "recommend": rec,
            "comments": cmt,
            "date": date,
            "time": time,
        })

    posts.sort(key=lambda x: (x["date"], x["time"]), reverse=True)   # 최신 글 먼저
    return {
        "available": True,
        "nickname": NICKNAME,
        "user_id": USER_ID,
        "source_url": SOURCE_URL,
        "totals": {
            "posts": int(data.get("total_count") or len(posts)),
            "views": tv,
            "recommend": tr,
            "comments": tc,
        },
        "posts": posts,
        "generated": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
    }


def main():
    try:
        result = build()
    except Exception as e:
        # 실패 게이트: 배포를 막지 않는다. 기존 데이터가 있으면 보존.
        print(f"[cobak] 수집 실패 — 기존 데이터 유지: {e}", file=sys.stderr)
        if not OUT.exists():
            OUT.write_text(json.dumps({"available": False}, ensure_ascii=False),
                           encoding="utf-8")
        return 0

    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    t = result["totals"]
    print(f"[cobak] OK — 글 {t['posts']} · 뷰 {t['views']} · "
          f"추천 {t['recommend']} · 댓글 {t['comments']} → {OUT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
