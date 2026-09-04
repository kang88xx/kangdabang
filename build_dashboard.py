"""daily_summary.csv + 최신 channel_posts_*.csv (+ 선택 JSON 사이드카) 를 읽어
자체 완결형 HTML 대시보드를 생성합니다.

OkardCare Design System v1.0 (Forest/Signal 팔레트, Pretendard + Geist Mono, 사각 코너).

섹션 구성
    01 Overview      — 채널·그룹 핵심 지표 한눈에
    02 CHANNEL 성장   — 구독자 추이 / 순증·순감 / 수치 반영 기준 설명
    03 CHANNEL 조회   — 일일 조회수 / 도달률 / 참여율(ER)
    04 CHANNEL 포스트 — TOP 게시물 + 일별 포스트 성과 표 (포스트 링크 활성화)
    05 CHANNEL 공식   — stats.GetBroadcastStats (Premium/대형 채널 전용)
    06 GROUP 활동     — 멤버 / 메시지 / 활성 유저 / 활발한 멤버 (채널과 분리)


사용법:
    python build_dashboard.py                  # channels.py 의 모든 채널 (data/<key>/daily_summary.csv)
    python build_dashboard.py --only kang       # 특정 채널만

결과: data/<key>/dashboard.html (채널별)
"""
import base64
import csv
import glob
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))   # 포스트 시각을 한국시간으로 표시

ROOT = Path(__file__).parent
from channels import CHANNELS, data_dir, migrate_legacy_layout   # noqa: E402

# 사용법: python build_dashboard.py            → 모든 채널 (data/<key>/dashboard.html)
#         python build_dashboard.py --only kang → 특정 채널만


def load_summary(path):
    with path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k, v in r.items():
            if k != "date":
                r[k] = int(v) if (v not in (None, "")) else None
    return rows


def load_latest_posts(DATA_DIR):
    """게시물 리스트 반환 (조회수>0 만). posts_store.json(누적, 최대 2000건)이 있으면 그것을,
    없으면 가장 최근 channel_posts_*.csv 를 읽는다."""
    store = DATA_DIR / "posts_store.json"
    rows = []
    if store.exists():
        try:
            rows = list(json.loads(store.read_text(encoding="utf-8")).values())
        except Exception:
            rows = []
    if not rows:
        files = sorted(glob.glob(str(DATA_DIR / "channel_posts_*.csv")))
        if not files:
            return []
        with open(files[-1], encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    posts = []
    if True:
        for r in rows:
            views = int(r.get("views") or 0)
            if views <= 0:                       # 광고/서비스 메시지 제외
                continue
            try:
                _dt = datetime.fromisoformat(r["date"])
                # 그룹핑 날짜(_d)는 daily_summary와 동일하게 UTC 일 버킷,
                # 표시 시각(_t)은 한국시간(KST)으로.
                _d = _dt.astimezone(timezone.utc).strftime("%Y-%m-%d")
                _t = _dt.astimezone(KST).strftime("%H:%M")
            except Exception:
                _d, _t = r["date"][:10], r["date"][11:16]
            posts.append({
                "id": int(r["id"]),
                "iso": r["date"],                    # 쿼터(남은횟수) 기준시각 비교용 — HTML엔 미포함
                "date": _d,
                "time": _t,
                "views": views,
                "forwards": int(r.get("forwards") or 0),
                "replies": int(r.get("replies") or 0),
                "text": (r.get("text") or "").replace("**", "").strip()[:70] or "(미리보기 없음)",
            })
    posts.sort(key=lambda p: -p["id"])
    return posts


def load_json(DATA_DIR, name, default):
    p = DATA_DIR / name
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default


# ── 게시글 서비스 남은횟수(쿼터) ───────────────────────────────────────────
# 게시글 1건당 1회씩 차감되는 외부 서비스의 잔여 횟수를 우리 측에서 교차 확인한다.
# 기준시각(baseline) 이후 올라온 채널 게시글 수 = 사용량. 사용 내역은 data/quota.json에
# 게시글 id별로 누적 저장하므로, 매 갱신 재계산해도 이중 차감이 없고 옛 글이
# CSV 수집 창(POST_WINDOW)에서 밀려나도 사용량이 유지된다.
# 총 횟수·기준시각은 channels.py 의 quota 설정(mode:"count")에서 온다. 기준시각을 바꾸면
# 카운터가 자동 리셋된다. mode:"deadline" 이면 횟수 대신 마감일 D-day 를 표기한다.
def update_quota(posts, DATA_DIR, qcfg):
    if not qcfg:
        return {"available": False}
    if qcfg.get("mode") == "deadline":
        return {"available": True, "mode": "deadline",
                "deadline": qcfg["deadline"], "label": qcfg.get("label", "")}
    QUOTA_FILE = DATA_DIR / "quota.json"
    QUOTA_TOTAL = int(qcfg.get("total", 0))
    QUOTA_BASELINE = qcfg["baseline"]
    try:
        q = json.loads(QUOTA_FILE.read_text(encoding="utf-8"))
    except Exception:
        q = {}
    # 기준시각이 코드와 다르면(충전·잔여 보정으로 baseline을 갱신한 경우)
    # 기존 카운터를 버리고 새 기준으로 리셋한다 — 파일 값이 코드보다 우선이라 이 마이그레이션이 필요.
    if q.get("baseline") != QUOTA_BASELINE:
        q = {}
    q.setdefault("total", QUOTA_TOTAL)
    q.setdefault("baseline", QUOTA_BASELINE)
    counted = q.setdefault("counted", {})           # {post_id: "YYYY-MM-DD"}
    try:
        base_dt = datetime.fromisoformat(q["baseline"])
    except Exception:
        base_dt = datetime.fromisoformat(QUOTA_BASELINE)
    for p in posts:
        pid = str(p["id"])
        if pid in counted:
            continue
        try:
            dt = datetime.fromisoformat(p["iso"])
        except Exception:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if dt > base_dt:
            counted[pid] = p["date"]                # daily_summary와 동일한 UTC 일 버킷
    try:
        QUOTA_FILE.write_text(json.dumps(q, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception as e:
        print(f"quota.json 저장 실패(집계는 계속): {e}", file=sys.stderr)
    daily = {}
    for d in counted.values():
        daily[d] = daily.get(d, 0) + 1
    used = len(counted)
    return {
        "available": True,
        "mode": "count",
        "total": q["total"],
        "used": used,
        "remaining": max(0, q["total"] - used),
        "start": str(q["baseline"])[:10],
        "daily": [{"date": d, "count": daily[d]} for d in sorted(daily)],
    }


TEMPLATE = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__CHNAME__ · Kangtearoom Data</title>
<link rel="icon" type="image/png" href="__FAVICON__">
<link rel="apple-touch-icon" href="__FAVICON__">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Geist+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" as="style" crossorigin href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css" />
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  :root {
    --forest-950:#061B14; --forest-900:#0B3A2C; --forest-700:#134C39;
    --forest-500:#25876A; --forest-300:#8FBFAD; --forest-100:#DCEAE2;
    --signal:#14B87D; --positive:#1F8A5B; --negative:#C8404E;
    --info:#2E84AE; --chart-alt:#2E84AE;
    --ink-900:#14201B; --ink-700:#34433D; --ink-500:#5F6C65; --ink-300:#7E8C84;
    --paper:#F4F6F2; --white:#FFFFFF; --line:#E3E7DF; --line-soft:#EEF1EC;
  }
  * { box-sizing:border-box; }
  html,body { margin:0; padding:0; background:var(--paper);
    -webkit-font-smoothing:antialiased; -moz-osx-font-smoothing:grayscale; }
  body { font-family:'Pretendard',-apple-system,system-ui,sans-serif;
    color:var(--ink-900); font-feature-settings:'ss01','tnum'; }
  a { color:inherit; }
  .mono { font-family:'Geist Mono',monospace; font-variant-numeric:tabular-nums; }
  .eyebrow { font-family:'Geist Mono',monospace; font-size:11px; letter-spacing:.18em;
    text-transform:uppercase; color:var(--ink-500); }

  /* CHROME RAIL */
  .rail { position:sticky; top:0; z-index:20;
    background:#0C3F30; color:rgba(255,255,255,.62);
    font-family:'Geist Mono',monospace; font-size:11px; letter-spacing:.18em;
    text-transform:uppercase; border-bottom:1px solid rgba(255,255,255,.12); }
  .rail-in { max-width:1180px; margin:0 auto; padding:9px 64px; display:grid;
    grid-template-columns:1fr auto 1fr; align-items:center; }
  .rail .mid { color:#fff; letter-spacing:.05em; white-space:nowrap; }
  .rail .chlink { color:rgba(255,255,255,.82); text-transform:none; text-decoration:none;
    border-bottom:1px solid rgba(255,255,255,.28); padding-bottom:1px; transition:color .15s,border-color .15s; }
  .rail .chlink:hover { color:var(--signal); border-color:var(--signal); }
  .rail .end { text-align:right; display:flex; gap:12px; align-items:center; justify-content:flex-end; }
  .rail .lead { display:flex; align-items:center; gap:14px; min-width:0; }
  .chnav { display:inline-flex; border:1px solid rgba(255,255,255,.28); }
  .chnav a { font-family:'Geist Mono',monospace; font-size:11px; letter-spacing:.04em; text-transform:none;
    color:rgba(255,255,255,.72); text-decoration:none; padding:4px 11px; white-space:nowrap;
    transition:background .15s,color .15s; }
  .chnav a + a { border-left:1px solid rgba(255,255,255,.28); }
  .chnav a:hover { color:#fff; background:rgba(255,255,255,.08); }
  .chnav a.active { color:#0C3F30; background:#14B87D; font-weight:600; }
  .refresh-btn { font-family:'Geist Mono',monospace; font-size:10px; letter-spacing:.14em;
    text-transform:uppercase; color:#0C3F30; background:#14B87D; border:none;
    padding:5px 11px; cursor:pointer; border-radius:0; transition:opacity .15s, background .15s; }
  .refresh-btn:hover { background:#19d18f; }
  .refresh-btn:disabled { opacity:.5; cursor:progress; }
  .refresh-toast { position:fixed; bottom:22px; right:22px; z-index:50;
    background:#0C3F30; color:#fff; font-family:'Geist Mono',monospace; font-size:12px;
    letter-spacing:.04em; padding:12px 18px; border-left:3px solid #14B87D;
    box-shadow:0 8px 28px rgba(0,0,0,.28); max-width:340px; white-space:pre-line; }
  .refresh-toast.err { border-left-color:#E5484D; }

  /* ── 로그인 게이트 ───────────────────────────────────────── */
  /* 잠금 중엔 스크롤만 막고, 본문은 레이아웃을 유지(차트가 0px로 그려지는 문제 방지)한 채
     불투명 오버레이로 가린다. 로그인 성공 시 오버레이만 제거하면 차트가 정상 크기로 보인다. */
  body.auth-lock { overflow:hidden; }
  #authOverlay { position:fixed; inset:0; z-index:200; display:flex; align-items:center; justify-content:center;
    background:radial-gradient(120% 120% at 50% 0%, #0B3A2C 0%, #061B14 70%); padding:24px; }
  #authOverlay[hidden] { display:none; }
  .auth-card { width:100%; max-width:360px; background:var(--white); border:1px solid var(--line);
    padding:34px 30px 28px; box-shadow:0 24px 60px rgba(0,0,0,.4); }
  .auth-card .brand { font-family:'Geist Mono',monospace; font-size:11px; letter-spacing:.18em;
    text-transform:uppercase; color:var(--signal); margin-bottom:6px; }
  .auth-card h1 { margin:0 0 4px; font-size:22px; font-weight:600; letter-spacing:-.02em; }
  .auth-card .sub { font-size:12.5px; color:var(--ink-500); margin-bottom:22px; }
  .auth-card label { display:block; font-family:'Geist Mono',monospace; font-size:10.5px; letter-spacing:.12em;
    text-transform:uppercase; color:var(--ink-500); margin:0 0 6px; }
  .auth-card input { width:100%; padding:11px 12px; font-size:14px; font-family:inherit;
    border:1px solid var(--line); background:var(--paper); color:var(--ink-900); margin-bottom:16px; }
  .auth-card input:focus { outline:none; border-color:var(--forest-500); background:#fff; }
  .auth-card button { width:100%; padding:12px; font-family:'Geist Mono',monospace; font-size:12px;
    letter-spacing:.12em; text-transform:uppercase; color:#fff; background:var(--forest-900);
    border:none; cursor:pointer; transition:background .15s; }
  .auth-card button:hover { background:var(--forest-700); }
  .auth-card button:disabled { opacity:.55; cursor:progress; }
  .auth-err { color:var(--negative); font-size:12.5px; min-height:18px; margin-bottom:6px; }

  /* 상단 계정 칩 + 로그아웃 */
  #userChip { display:flex; gap:9px; align-items:center; }
  #userChip .who { color:#fff; text-transform:none; letter-spacing:.02em; }
  #userChip .who b { color:var(--signal); }
  .logout-btn { font-family:'Geist Mono',monospace; font-size:10px; letter-spacing:.12em;
    text-transform:uppercase; color:rgba(255,255,255,.82); background:transparent;
    border:1px solid rgba(255,255,255,.3); padding:4px 9px; cursor:pointer; transition:all .15s; }
  .logout-btn:hover { color:#fff; border-color:var(--signal); }

  /* ── 07b 접속 로그 (마스터 전용) ─────────────────────────── */
  .access-foot { font-family:'Geist Mono',monospace; font-size:11px; letter-spacing:.04em;
    color:var(--ink-500); margin-top:10px; }
  .ttag { display:inline-block; font-family:'Geist Mono',monospace; font-size:10px; letter-spacing:.08em;
    text-transform:uppercase; padding:2px 7px; color:#fff; }
  .ttag.login { background:var(--forest-500); }
  .ttag.ping { background:var(--info); }

  /* ── 09 내 계정 (일반 계정 전용) ─────────────────────────── */
  .prof-wrap { display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:16px; }
  .prof-card { background:var(--white); border:1px solid var(--line); padding:22px; }
  .prof-card input { width:100%; padding:11px 12px; font-size:14px; font-family:inherit;
    border:1px solid var(--line); background:var(--paper); color:var(--ink-900); margin-bottom:12px; }
  .prof-card input:focus { outline:none; border-color:var(--forest-500); background:#fff; }
  .prof-card input:disabled { color:var(--ink-300); background:var(--line-soft); cursor:not-allowed; }
  .prof-btn { font-family:'Geist Mono',monospace; font-size:11px; letter-spacing:.1em; text-transform:uppercase;
    color:#fff; background:var(--forest-900); border:none; padding:9px 16px; cursor:pointer; transition:background .15s; }
  .prof-btn:hover { background:var(--forest-700); }
  .prof-btn:disabled { opacity:.5; cursor:not-allowed; }
  .prof-msg { font-size:12.5px; margin-top:10px; min-height:16px; }
  .prof-msg.ok { color:var(--positive); }
  .prof-msg.err { color:var(--negative); }

  /* (헤더 cover 제거됨 — 상단 정보는 .rail 로 통합) */

  main { max-width:1180px; margin:0 auto; padding:22px 64px 0; }
  section { margin-bottom:34px; scroll-margin-top:58px; }
  #topMembers { scroll-margin-top:58px; }
  .basis-note { font-family:'Geist Mono',monospace; font-size:11.5px; line-height:1.5; letter-spacing:.01em;
    color:var(--ink-500); background:var(--white); border:1px solid var(--line); border-left:3px solid var(--signal);
    padding:8px 14px; margin-bottom:18px; }
  .basis-note b { color:var(--forest-700); font-weight:600; }
  .week-summary { font-size:14px; line-height:1.5; color:var(--ink-700);
    background:var(--white); border:1px solid var(--line); border-left:3px solid var(--forest-500);
    padding:9px 14px; margin-bottom:12px; font-size:13px; }
  .week-summary:empty { display:none; }
  .week-summary b { font-family:'Geist Mono',monospace; color:var(--forest-700); font-weight:600; }
  .sec-head { display:flex; align-items:baseline; gap:18px;
    border-top:1.5px solid var(--ink-900); padding-top:12px; margin-bottom:14px; }
  .sec-head .num { font-family:'Geist Mono',monospace; font-size:14px; font-weight:500; color:var(--signal); }
  .sec-head h2 { margin:4px 0 0; font-weight:500; font-size:21px; line-height:1.1; letter-spacing:-.02em; }
  .group-head .num { color:var(--info); }

  /* domain tag */
  .dtag { display:inline-block; font-family:'Geist Mono',monospace; font-size:10.5px;
    letter-spacing:.12em; text-transform:uppercase; padding:3px 8px; border:1px solid transparent;
    color:#fff; margin-left:auto; align-self:center; }
  .dtag.ch { background:var(--forest-500); border-color:var(--forest-500); }
  .dtag.gr { background:var(--info); border-color:var(--info); }
  .dtag.cobak { background:#1652f0; border-color:#1652f0; color:#fff; text-decoration:none; }

  /* KPI CARDS */
  .cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:12px; }
  .card { background:var(--white); border:1px solid var(--line); padding:14px 16px; }
  .card .label { font-size:12.5px; color:var(--ink-500); }
  .card .value { font-family:'Geist Mono',monospace; font-variant-numeric:tabular-nums;
    font-size:26px; font-weight:400; letter-spacing:-.02em; color:var(--ink-900); margin:6px 0 4px; }
  .card .delta { font-family:'Geist Mono',monospace; font-size:12px; font-weight:500; }
  .up { color:var(--positive); } .down { color:var(--negative); } .flat { color:var(--ink-300); }
  .cards-tight { gap:12px; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); }
  .cards-tight .card { padding:11px 13px; }
  .cards-tight .label { font-size:11.5px; line-height:1.3; }
  .cards-tight .value { font-size:19px; margin:5px 0 0; word-break:break-word; }
  .datesel { font-family:'Geist Mono',monospace; font-size:12px; text-transform:none; letter-spacing:0;
    color:var(--ink-900); background:var(--white); border:1px solid var(--line); padding:5px 10px; cursor:pointer; }
  .datesel:hover { border-color:var(--forest-300); }
  .quota-chip { margin-left:auto; font-family:'Geist Mono',monospace; font-size:12px; letter-spacing:.02em;
    text-transform:none; color:var(--forest-700); background:var(--white); border:1px solid var(--line);
    padding:5px 10px; cursor:pointer; transition:border-color .15s,color .15s; }
  .quota-chip b { color:var(--signal); font-weight:600; }
  .quota-chip:hover { border-color:var(--forest-300); color:var(--forest-500); }
  .quota-chip.static { cursor:default; }
  .quota-chip.static:hover { border-color:var(--line); color:var(--forest-700); }
  .quota-chip .due { color:var(--ink-500); }

  /* DETAIL BUTTON + MODAL */
  .card .detail-btn { margin-top:8px; font-family:'Geist Mono',monospace; font-size:10px;
    letter-spacing:.08em; text-transform:uppercase; color:var(--forest-500); background:none;
    border:1px solid var(--line); padding:3px 8px; cursor:pointer; transition:background .15s,color .15s,border-color .15s; }
  .card .detail-btn:hover { background:var(--forest-900); color:#fff; border-color:var(--forest-900); }
  .modal-back { position:fixed; inset:0; z-index:60; background:rgba(6,27,20,.55);
    display:none; align-items:center; justify-content:center; padding:24px; }
  .modal-back.show { display:flex; }
  .modal { background:var(--white); border:1px solid var(--line); max-width:540px; width:100%;
    max-height:82vh; display:flex; flex-direction:column; box-shadow:0 24px 64px rgba(0,0,0,.38); }
  .modal-head { display:flex; align-items:flex-start; justify-content:space-between; gap:16px;
    padding:18px 22px; border-bottom:1.5px solid var(--ink-900); }
  .modal-head h3 { margin:0; font-size:17px; font-weight:600; letter-spacing:-.01em; }
  .modal-head .sub { font-family:'Geist Mono',monospace; font-size:11px; color:var(--ink-500); margin-top:4px; }
  .modal-close { background:none; border:none; font-size:24px; line-height:1; cursor:pointer;
    color:var(--ink-500); padding:0 2px; }
  .modal-close:hover { color:var(--ink-900); }
  .modal-body { overflow-y:auto; overflow-x:auto; }
  .modal-body thead th { position:sticky; top:0; background:var(--white); z-index:1; }

  /* CHARTS */
  .grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
  /* 차트 2개(세로) + 목록(우측) · 표 2개 나란히 · 자동 열 */
  .grid.grid-side { grid-template-columns:1.15fr 1fr; align-items:start; }
  .grid.grid-auto { grid-template-columns:repeat(auto-fit,minmax(400px,1fr)); align-items:start; }
  .grid.grid-3 { grid-template-columns:1fr 1fr 1fr; }
  .stack { display:grid; gap:12px; }
  .panel-eyebrow { margin-bottom:8px; display:flex; align-items:center; gap:10px; flex-wrap:nowrap; white-space:nowrap; min-height:30px; }
  .panel-eyebrow .datesel { padding:4px 8px; }
  .sec-head .head-right { margin-left:auto; display:flex; align-items:center; gap:10px; }
  .sec-head .quota-chip { margin-left:0; }
  .chart-box { background:var(--white); border:1px solid var(--line); padding:14px 16px 10px; min-width:0; }
  .chart-box .eyebrow { margin-bottom:8px; }
  canvas { max-height:196px; max-width:100%; }

  /* CHART DETAIL POPUP — 차트 클릭 → 확대 팝업 */
  .chart-box.clickable { cursor:pointer; position:relative; transition:border-color .15s, box-shadow .15s; }
  .chart-box.clickable:hover, .chart-box.clickable:focus-visible { border-color:var(--forest-500);
    box-shadow:0 4px 18px rgba(11,58,44,.10); outline:none; }
  .chart-box.clickable::after { content:'상세보기 ↗'; position:absolute; top:12px; right:16px;
    font-family:'Geist Mono',monospace; font-size:10px; letter-spacing:.12em; text-transform:uppercase;
    color:var(--forest-500); opacity:0; transition:opacity .15s; pointer-events:none; }
  .chart-box.clickable:hover::after, .chart-box.clickable:focus-visible::after { opacity:1; }
  .modal.modal-wide { max-width:920px; max-height:90vh; }
  .cd-tools { display:flex; align-items:center; justify-content:space-between; gap:12px;
    padding:16px 22px 0; flex-wrap:wrap; }
  .range-tabs { display:flex; border:1px solid var(--line); }
  .range-tabs button { font-family:'Geist Mono',monospace; font-size:11px; letter-spacing:.08em;
    background:var(--white); border:none; border-right:1px solid var(--line);
    padding:8px 16px; cursor:pointer; color:var(--ink-500); transition:background .12s,color .12s; }
  .range-tabs button:last-child { border-right:none; }
  .range-tabs button:hover:not(.on) { color:var(--forest-700); }
  .range-tabs button.on { background:var(--forest-900); color:#fff; }
  .cd-points { font-family:'Geist Mono',monospace; font-size:11px; color:var(--ink-300); }
  .stat-strip { display:grid; grid-template-columns:repeat(4,1fr); gap:1px;
    background:var(--line-soft); border:1px solid var(--line-soft); margin:16px 22px 0; }
  .stat-strip .cell { background:var(--paper); padding:13px 15px; min-width:0; }
  .stat-strip .lb { font-family:'Geist Mono',monospace; font-size:10px; letter-spacing:.12em;
    text-transform:uppercase; color:var(--ink-500); margin-bottom:6px; white-space:nowrap;
    overflow:hidden; text-overflow:ellipsis; }
  .stat-strip .vl { font-family:'Geist Mono',monospace; font-variant-numeric:tabular-nums;
    font-size:16px; font-weight:600; color:var(--ink-900); }
  .cd-tools, .stat-strip, .cd-chart { flex-shrink:0; }
  .cd-chart { height:340px; padding:18px 22px 4px; }
  .cd-chart canvas { max-height:320px; }
  /* 팝업 전체(차트+표)가 한 덩어리로 스크롤 — 표만 따로 스크롤되지 않게 */
  #chartModal .modal { overflow-y:auto; }
  #chartModal .modal-body { flex:none; overflow:visible; min-height:120px;
    margin:8px 22px 20px; border-top:1px solid var(--line-soft); }
  #chartModal .modal-body thead th { top:0; }

  /* 차트 상세 팝업 — 표 크게 보기 (차트·요약 접고 일자별 표만 크게) */
  .tbl-toggle { font-family:'Geist Mono',monospace; font-size:11px; letter-spacing:.08em;
    background:var(--white); border:1px solid var(--line); padding:8px 14px; cursor:pointer;
    color:var(--forest-500); transition:background .12s,color .12s,border-color .12s; }
  .tbl-toggle:hover:not(.on) { border-color:var(--forest-300); color:var(--forest-700); }
  .tbl-toggle.on { background:var(--forest-900); color:#fff; border-color:var(--forest-900); }
  #chartModal.tbl .stat-strip, #chartModal.tbl .cd-chart { display:none; }
  #chartModal.tbl .modal-wide { height:90vh; }

  /* NOTE / 기준 설명 박스 */
  .note-box { background:var(--white); border:1px solid var(--line);
    border-left:3px solid var(--signal); padding:20px 22px; margin-bottom:24px; }
  .note-box h4 { margin:0 0 12px; font-size:14px; font-weight:600; letter-spacing:-.01em;
    display:flex; align-items:center; gap:8px; }
  .note-box h4 .ico { color:var(--signal); }
  .note-box dl { margin:0; display:grid; grid-template-columns:max-content 1fr; gap:8px 18px; }
  .note-box dt { font-family:'Geist Mono',monospace; font-size:12px; color:var(--forest-500);
    font-weight:500; white-space:nowrap; }
  .note-box dd { margin:0; font-size:13.5px; line-height:1.55; color:var(--ink-700); }
  .note-box dd code { font-family:'Geist Mono',monospace; font-size:12px; background:var(--forest-100);
    padding:1px 5px; color:var(--forest-700); }

  /* TABLE */
  .table-wrap { background:var(--white); border:1px solid var(--line); overflow-x:auto; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  thead th { font-family:'Geist Mono',monospace; font-size:10.5px; letter-spacing:.1em;
    text-transform:uppercase; color:var(--ink-500); text-align:right; padding:9px 12px;
    border-bottom:1.5px solid var(--ink-900); white-space:nowrap; }
  thead th.l { text-align:left; }
  tbody td { padding:8px 12px; border-bottom:1px solid var(--line-soft); text-align:right;
    font-family:'Geist Mono',monospace; font-variant-numeric:tabular-nums; color:var(--ink-700); }
  tbody td.l { text-align:left; font-family:'Pretendard',sans-serif; }
  tbody tr:hover { background:var(--paper); }
  tbody td a.post { color:var(--ink-900); text-decoration:none; font-weight:500;
    border-bottom:1px solid var(--forest-300); padding-bottom:1px; }
  tbody td a.post:hover { color:var(--forest-500); border-color:var(--signal); }
  tbody td a.ulink { color:inherit; text-decoration:none; border-bottom:1px solid var(--line); padding-bottom:1px; }
  tbody td a.ulink:hover { color:var(--forest-500); border-color:var(--forest-300); }
  .rank { display:inline-flex; align-items:center; justify-content:center; width:22px; height:22px;
    background:var(--forest-900); color:#fff; font-family:'Geist Mono',monospace; font-size:11px;
    font-weight:600; margin-right:10px; }
  .rank.t1 { background:var(--signal); } .rank.t2 { background:var(--forest-500); }

  /* PAGINATION */
  .pager { display:flex; flex-wrap:wrap; gap:5px; margin-top:10px; justify-content:center; }
  .pager button { font-family:'Geist Mono',monospace; font-size:11.5px; min-width:30px; padding:4px 8px;
    border:1px solid var(--line); background:var(--white); color:var(--ink-700); cursor:pointer;
    transition:background .12s,color .12s,border-color .12s; }
  .pager button:hover:not(:disabled) { border-color:var(--forest-300); color:var(--forest-700); }
  .pager button.active { background:var(--forest-900); color:#fff; border-color:var(--forest-900); }
  .pager button:disabled { opacity:.35; cursor:default; }
  .pager .gap { border:none; background:none; cursor:default; color:var(--ink-300); min-width:18px; padding:6px 2px; }
  .tabs { display:flex; flex-wrap:wrap; gap:6px; margin-bottom:10px; }
  .tab { font-family:'Geist Mono',monospace; font-size:12px; padding:5px 11px; border:1px solid var(--line);
    background:var(--white); color:var(--ink-500); cursor:pointer; transition:background .12s,color .12s,border-color .12s; }
  .tab:hover { border-color:var(--forest-300); }
  .tab.active { background:var(--forest-900); color:#fff; border-color:var(--forest-900); }
  .tab .sub { opacity:.6; margin-left:6px; font-size:11px; }
  .post-months { margin-bottom:6px; }
  .post-months .tab { padding:4px 10px; }
  .post-weeks { margin-bottom:12px; }
  .jl-months { margin-bottom:6px; }
  .jl-months .tab { padding:4px 10px; }
  /* 포스트 표 2개 나란히: 제목은 한 줄 말줄임(마우스 올리면 전체 제목) */
  .grid-posts table { table-layout:fixed; }
  .grid-posts th:not(.l) { width:54px; }
  .grid-posts th.num-wide { width:66px; }
  .grid-posts td { white-space:nowrap; }
  .grid-posts td.l { overflow:hidden; text-overflow:ellipsis; }
  .grid-posts td.l a.post { border-bottom:none; }
  .jl-tag { display:inline-block; font-family:'Geist Mono',monospace; font-size:11px; padding:2px 8px; font-weight:600; white-space:nowrap; }
  .jl-tag.join { color:var(--positive); border:1px solid #BFE0CF; }
  .jl-tag.left { color:var(--negative); border:1px solid #F0C9CD; }
  .jl-note { font-size:12px; color:var(--ink-300); margin-bottom:12px; line-height:1.5; }

  /* placeholder / empty state */
  .empty { background:var(--white); border:1px dashed var(--line); padding:18px 20px;
    text-align:center; color:var(--ink-500); font-size:14px; line-height:1.6; }
  .empty b { color:var(--ink-900); }
  .empty .tag { display:inline-block; font-family:'Geist Mono',monospace; font-size:11px;
    letter-spacing:.1em; text-transform:uppercase; color:var(--negative); margin-bottom:10px; }

  footer { border-top:1.5px solid var(--ink-900); margin-top:8px;
    padding:24px 64px 56px; display:flex; align-items:center; justify-content:space-between;
    flex-wrap:wrap; gap:16px; max-width:1180px; margin-left:auto; margin-right:auto; }
  footer .note { font-family:'Geist Mono',monospace; font-size:11px; letter-spacing:.14em;
    text-transform:uppercase; color:var(--ink-300); }
  @media (max-width:760px) { .grid, .grid.grid-side, .grid.grid-auto, .grid.grid-3 { grid-template-columns:1fr; }
    .note-box dl { grid-template-columns:1fr; gap:2px 0; }
    .note-box dt { margin-top:8px; }
    .rail-in, main, footer { padding-left:24px; padding-right:24px; }
    /* D2: 상단바 1행화 — "KANGTEAROOM DATA"·채널 링크 숨기고 [채널 토글 | 갱신·사용자] 2열, 높이 축소 */
    .rail .brand-txt, .rail .mid { display:none; }
    .rail-in { grid-template-columns:auto 1fr; align-items:center; gap:8px;
      padding-top:6px; padding-bottom:6px; }
    .rail .end { flex-wrap:wrap; gap:4px 10px; font-size:10px; letter-spacing:.04em; }
    .chnav a { padding:9px 12px; }
    .rail .end { justify-content:flex-end; }
    /* 1행 rail에 맞춰 섹션 앵커 보정 */
    section, #topMembers { scroll-margin-top:54px; }
    .cards-tight { grid-template-columns:repeat(2,minmax(0,1fr)); }
    .basis-note { line-height:1.6; }
    .eyebrow, .rail, .dtag { letter-spacing:.06em; }
    /* D1: 터치 타깃 ≥44px */
    .tab { padding:11px 16px; }
    .quota-chip { padding:11px 12px; }
    .pager button { min-width:44px; padding:11px 12px; }
    .detail-btn { width:100%; padding:12px 10px; text-align:center; }
    .modal-close { width:44px; height:44px; display:flex; align-items:center;
      justify-content:center; padding:0; }
    .tbl-toggle { padding:11px 16px; }
    #chartModal.tbl .modal { height:88vh; }
    /* D3: 모달 하단시트화 + 표 축소 */
    .modal-back { align-items:flex-end; padding:12px; }
    .modal { max-height:88vh; }
    .modal-body table { font-size:12px; }
    .modal-body th, .modal-body td { padding:9px 10px; }
    /* 차트 상세 팝업 모바일 */
    .cd-tools { padding:14px 14px 0; }
    .stat-strip { grid-template-columns:repeat(2,1fr); margin:14px 14px 0; }
    .cd-chart { height:250px; padding:14px 14px 0; }
    .cd-chart canvas { max-height:236px; }
    #chartModal .modal-body { margin:8px 14px 16px; } }
</style>
</head>
<body class="auth-lock">

  <div id="authOverlay">
    <form class="auth-card" id="authForm" autocomplete="off">
      <div class="brand">Kangtearoom · Internal</div>
      <h1>__CHNAME__ 통계</h1>
      <div class="sub">내부 전용 — 계정으로 로그인하세요.</div>
      <label for="authUser">아이디</label>
      <input id="authUser" name="username" type="text" autocomplete="username" autofocus>
      <label for="authPass">비밀번호</label>
      <input id="authPass" name="password" type="password" autocomplete="current-password">
      <div class="auth-err" id="authErr"></div>
      <button type="submit" id="authBtn">로그인</button>
    </form>
  </div>

  <div class="rail">
    <div class="rail-in">
      <span class="lead"><span class="brand-txt">KANGTEAROOM DATA</span><nav class="chnav" aria-label="채널 선택">__NAV__</nav></span>
      <span class="mid">__RAILMID__</span>
      <span class="end"><span id="lastUpdated">최종 업데이트 __GENERATED__ KST</span><button id="refreshBtn" class="refresh-btn" hidden>지금 갱신</button><span id="userChip" hidden><span class="who"></span><button type="button" id="logoutBtn" class="logout-btn">로그아웃</button></span></span>
    </div>
  </div>
  <div id="refreshToast" class="refresh-toast" role="status" aria-live="polite" hidden></div>

  <main>

    <div class="basis-note">데이터 기준 · <b>한국시간(KST) 오전 9시 ~ 다음날 09시 = 1일(24시간)</b> · 하루 48회 자동 갱신</div>

    <!-- 01 OVERVIEW -->
    <section>
      <div class="sec-head">
        <div><div class="eyebrow">Overview</div><h2>오늘의 핵심 지표</h2></div>
      </div>
      <div class="week-summary" id="weekSummary"></div>
      <div class="cards" id="cards"></div>
    </section>

    <!-- 02 CHANNEL 성장 -->
    <section id="sec-subs">
      <div class="sec-head">
        <div><div class="eyebrow">Channel · Growth</div><h2>채널 — 구독자 증감</h2></div>
        <span class="dtag ch">@__CHUSER__</span>
      </div>

      <div class="grid grid-side">
        <div class="stack">
          <div class="chart-box"><div class="eyebrow">구독자 추이</div><canvas id="subs"></canvas></div>
          <div class="chart-box"><div class="eyebrow">들어옴 · 나감 (일별)</div><canvas id="subsNet"></canvas></div>
        </div>
        <div>
          <div class="eyebrow panel-eyebrow">유입 · 이탈 인원 (누가)</div>
          <div id="joinLeave"></div>
        </div>
      </div>
    </section>

    <!-- 03 CHANNEL 조회 -->
    <section id="sec-reach">
      <div class="sec-head">
        <div><div class="eyebrow">Channel · Reach</div><h2>채널 — 조회수 · 도달 · 참여</h2></div>
        <span class="dtag ch">@__CHUSER__</span>
      </div>

      <div class="cards cards-tight" id="reachCards" style="margin-bottom:12px;"></div>
      <div class="grid">
        <div class="chart-box"><div class="eyebrow">일일 조회수</div><canvas id="views"></canvas></div>
        <div class="chart-box"><div class="eyebrow">공유 · 댓글 (인게이지먼트)</div><canvas id="engage"></canvas></div>
      </div>
    </section>

    <!-- 04 CHANNEL 포스트 -->
    <section>
      <div class="sec-head">
        <div><div class="eyebrow">Channel · Posts</div><h2>채널 — 포스트별 성과</h2></div>
        <span class="head-right"><button type="button" id="quotaChip" class="quota-chip" title="클릭하면 일자별 사용 내역" hidden>남은횟수: <b>—</b></button><span class="dtag ch">@__CHUSER__</span></span>
      </div>
      <div class="tabs post-months" id="postMonths"></div>
      <div class="tabs post-weeks" id="postWeeks"></div>
      <div class="grid grid-posts" style="align-items:start;">
        <div>
          <div class="eyebrow panel-eyebrow">TOP 게시물 · <span id="topWeekLabel">선택한 주</span> · 조회수 순</div>
          <div class="table-wrap">
            <table><thead><tr>
              <th class="l">#  게시물</th><th>날짜</th><th class="num-wide">조회수</th><th>공유</th><th>댓글</th>
            </tr></thead><tbody id="topPosts"></tbody></table>
          </div>
        </div>
        <div>
          <div class="eyebrow panel-eyebrow">
            <span>게시물 목록 · <span id="listWeekLabel">선택한 주</span></span>
            <select id="postDate" class="datesel"></select>
          </div>
          <div class="table-wrap">
            <table><thead><tr>
              <th class="l">게시물</th><th class="num-wide">시각</th><th class="num-wide">조회수</th><th>공유</th><th>댓글</th>
            </tr></thead><tbody id="allPosts"></tbody></table>
          </div>
          <div class="pager" id="allPostsPager"></div>
        </div>
      </div>
      <div class="jl-note" style="margin-top:8px;">제목은 한 줄로 줄여 표시됩니다 — 마우스를 올리면 전체 제목, 클릭하면 텔레그램에서 열립니다.</div>
    </section>

    <!-- 05 CHANNEL 공식 통계 -->
    <section>
      <div class="sec-head">
        <div><div class="eyebrow">Channel · Official</div><h2>채널 — 공식 통계</h2></div>
        <span class="dtag ch">@__CHUSER__</span>
      </div>
      <div id="officialStats"></div>
    </section>

    <!-- 06 GROUP -->
    <section id="sec-group">
      <div class="sec-head group-head">
        <div><div class="eyebrow">Group · Discussion</div><h2>그룹 — 토론 활동</h2></div>
        <span class="dtag gr">@__GRUSER__</span>
      </div>

      <div class="cards cards-tight" id="grCards" style="margin-bottom:12px;"></div>
      <div class="grid grid-3" style="margin-bottom:12px;">
        <div class="chart-box"><div class="eyebrow">그룹 멤버 추이</div><canvas id="grMembers"></canvas></div>
        <div class="chart-box"><div class="eyebrow">멤버 일별 순증 · 순감</div><canvas id="grNet"></canvas></div>
        <div class="chart-box"><div class="eyebrow">메시지 · 활성 유저</div><canvas id="grActivity"></canvas></div>
      </div>
      <div class="grid grid-auto">
        <div id="topMembers"></div>
        <div id="grJoinLeaveWrap" hidden>
          <div class="eyebrow panel-eyebrow">유입 · 이탈 인원 (누가)</div>
          <div id="joinLeaveGroup"></div>
          <div id="grJlNote" class="jl-note" style="margin-top:8px;"></div>
        </div>
      </div>
    </section>

    <!-- 07 코박 활동 -->
    <section id="sec-cobak">
      <div class="sec-head">
        <div><div class="eyebrow">Community · Cobak</div><h2>코박 활동 — 캉다방</h2></div>
        <a class="dtag cobak" id="cobakTag" href="https://cobak.co/" target="_blank" rel="noopener">cobak.co</a>
      </div>
      <div class="cards cards-tight" id="cobakCards" style="margin-bottom:12px;"></div>
      <div class="tabs post-months" id="cobakMonths"></div>
      <div class="eyebrow" style="margin-bottom:12px;">게시글 목록 — <span id="cobakMonthLabel">선택한 달</span> 최신순 · 5개씩 (제목 클릭 시 코박에서 열림)</div>
      <div class="table-wrap">
        <table><thead><tr>
          <th class="l">게시물</th><th>날짜</th><th>시각</th><th>조회수</th><th>추천</th><th>댓글</th>
        </tr></thead><tbody id="cobakPosts"></tbody></table>
      </div>
      <div class="pager" id="cobakPager"></div>
    </section>

    <!-- 08 접속 로그 (마스터 전용) -->
    <section id="sec-access" hidden>
      <div class="sec-head">
        <div><div class="eyebrow">Admin · Access</div><h2>접속 로그 — 사용 현황</h2></div>
        <button type="button" id="logRefresh" class="dtag" style="background:var(--ink-900);border:none;cursor:pointer;">새로고침</button>
      </div>
      <div class="cards cards-tight" id="accessCards" style="margin-bottom:12px;"></div>
      <div class="eyebrow" style="margin-bottom:12px;">일자별 접속 횟수 — 계정 탭을 누르면 해당 계정만 (로그인 = 접속, 사용 = 열어둔 동안 5분마다 1회)</div>
      <div class="tabs" id="accessTabs"></div>
      <div id="accessSummary" style="font-family:'Geist Mono',monospace;font-size:13px;letter-spacing:.01em;color:var(--ink-500);margin:2px 0 16px;min-height:18px;"></div>
      <div class="table-wrap">
        <table><thead><tr>
          <th class="l">날짜</th><th class="l">계정</th><th>로그인</th><th>사용</th><th>마지막 활동</th>
        </tr></thead><tbody id="accessLog"></tbody></table>
      </div>
      <div class="pager" id="accessPager"></div>
      <div class="access-foot" id="accessFoot"></div>
    </section>

    <!-- 09 내 계정 (일반 계정 전용) -->
    <section id="sec-profile" hidden>
      <div class="sec-head">
        <div><div class="eyebrow">My · Account</div><h2>내 계정 — 이름·비밀번호 변경</h2></div>
      </div>
      <div class="prof-wrap">
        <div class="prof-card">
          <div class="eyebrow" style="margin-bottom:10px;">계정 이름 <span id="profNameHint" style="color:var(--ink-300);text-transform:none;letter-spacing:0;">(1회만 변경 가능)</span></div>
          <input id="profName" type="text" maxlength="20" autocomplete="off">
          <button type="button" id="profNameBtn" class="prof-btn">이름 변경</button>
          <div id="profNameMsg" class="prof-msg"></div>
        </div>
        <div class="prof-card">
          <div class="eyebrow" style="margin-bottom:10px;">비밀번호 <span style="color:var(--ink-300);text-transform:none;letter-spacing:0;">(자유롭게 변경)</span></div>
          <input id="profPass" type="password" maxlength="72" autocomplete="new-password" placeholder="새 비밀번호">
          <button type="button" id="profPassBtn" class="prof-btn">비밀번호 변경</button>
          <div id="profPassMsg" class="prof-msg"></div>
        </div>
      </div>
    </section>

  </main>

  <div id="metricModal" class="modal-back" aria-hidden="true">
    <div class="modal" role="dialog" aria-modal="true" aria-labelledby="mmTitle">
      <div class="modal-head">
        <div><h3 id="mmTitle">지표</h3><div class="sub" id="mmSub"></div></div>
        <button class="modal-close" id="mmClose" aria-label="닫기">&times;</button>
      </div>
      <div class="modal-body">
        <table><thead id="mmHead"></thead>
        <tbody id="mmBody"></tbody></table>
      </div>
    </div>
  </div>

  <!-- 차트 상세 팝업 (차트 클릭 시) -->
  <div id="chartModal" class="modal-back" aria-hidden="true">
    <div class="modal modal-wide" role="dialog" aria-modal="true" aria-labelledby="cdTitle">
      <div class="modal-head">
        <div>
          <div class="eyebrow" id="cdEyebrow" style="margin-bottom:4px;"></div>
          <h3 id="cdTitle">차트 상세</h3>
          <div class="sub" id="cdSub"></div>
        </div>
        <button class="modal-close" id="cdClose" aria-label="닫기">&times;</button>
      </div>
      <div class="cd-tools">
        <div class="range-tabs" id="cdTabs">
          <button type="button" data-r="7">7일</button>
          <button type="button" data-r="30" class="on">30일</button>
          <button type="button" data-r="0">전체</button>
        </div>
        <div style="display:flex; align-items:center; gap:14px;">
          <span class="cd-points" id="cdPoints"></span>
          <button type="button" class="tbl-toggle" id="cdTableMax">표 크게 보기</button>
        </div>
      </div>
      <div class="stat-strip" id="cdStats"></div>
      <div class="cd-chart"><canvas id="cdCanvas"></canvas></div>
      <div class="modal-body">
        <table><thead id="cdHead"></thead>
        <tbody id="cdBody"></tbody></table>
      </div>
    </div>
  </div>

  <footer>
    <span class="note">본 자료는 내부 전용입니다 · 외부 유출 및 공유 금지</span>
  </footer>

<script>
const DATA     = __DATA__;
const POSTS    = __POSTS__;
const OFFICIAL = __OFFICIAL__;
const MEMBERS  = __MEMBERS__;

const COBAK    = __COBAK__;      // { available, nickname, totals:{posts,views,recommend,comments}, posts:[{id,title,url,views,recommend,comments,date}] }
const JOINLEAVE= __JOINLEAVE__;  // { available, events:[{date,kind,name,username,id}] }
const JOINLEAVE_GR = __JOINLEAVE_GR__;  // 그룹 유입·이탈
const QUOTA    = __QUOTA__;      // 게시글 서비스 { mode:"count", total, used, remaining, start, daily } | { mode:"deadline", deadline, label }
const CH_USER  = "__CHUSER__";
const HAS_GROUP = __HAS_GROUP__; // 연결 그룹 없으면 그룹 섹션·카드 숨김
const HAS_COBAK = __HAS_COBAK__; // 코박 섹션 표시 여부
if (!HAS_GROUP) { const g = document.getElementById('sec-group'); if (g) g.remove(); }
if (!HAS_COBAK) { const c = document.getElementById('sec-cobak'); if (c) c.remove(); }

const fmt  = n => Number(n).toLocaleString('ko-KR');
const pct  = n => (n*100).toFixed(1) + '%';
const esc  = s => { const d=document.createElement('div'); d.textContent=s; return d.innerHTML; };
const dates = DATA.map(r => r.date.slice(5));        // MM-DD
const last  = DATA[DATA.length-1], prev = DATA[DATA.length-2] || last;
const subsNow = last.ch_subscribers;

// ---------- 완료일(진행중 오늘 제외) 기준 최근 7일 헬퍼 ----------
// DATA의 마지막 행은 진행 중인 '오늘'이라 평균·요약에서 제외한다.
const DONE = DATA.length > 1 ? DATA.slice(0, -1) : DATA.slice();
const recent7 = DONE.slice(-7);
const avgOf = (rows, key) => {
  const xs = rows.map(r => r[key]).filter(v => v != null);
  return xs.length ? xs.reduce((a,b)=>a+b,0) / xs.length : null;
};

// E2: 스냅샷 지표(구독자·멤버) — 현재값 vs 최근7일평균 화살표 한 줄
function avg7(key, v){
  if (v == null) return '';
  const a = avgOf(recent7, key);
  if (a == null) return '';
  const d = v - a;
  const cls = d>0?'up':d<0?'down':'flat';
  const arrow = d>0?'▲':d<0?'▼':'—';
  return `<div class="delta ${cls}" style="font-size:11px;margin-top:3px;">`
    + `${arrow} ${fmt(Math.abs(Math.round(d)))} <span style="color:var(--ink-300);font-weight:400;">7일 평균 대비</span></div>`;
}

// ---------- E1: 주간 한 줄 요약 (Overview 최상단) ----------
(function(){
  const n = recent7.length;
  const el = document.getElementById('weekSummary');
  if (!el || !n){ if(el) el.remove(); return; }
  // 구독자 증감: 7일 구간 첫·끝 완료일 스냅샷 차이
  const subsVals = recent7.map(r=>r.ch_subscribers).filter(v=>v!=null);
  const subsDelta = subsVals.length>=2 ? subsVals[subsVals.length-1]-subsVals[0] : null;
  const viewsAvg = avgOf(recent7, 'ch_views');
  const msgAvg   = HAS_GROUP ? avgOf(recent7, 'gr_messages') : null;
  const head = n>=7 ? '최근 7일' : `집계 ${n}일`;
  const parts = [];
  if (subsDelta != null){
    const s = subsDelta>0?`+${fmt(subsDelta)}`:subsDelta<0?`-${fmt(Math.abs(subsDelta))}`:'±0';
    parts.push(`구독자 <b>${s}</b>`);
  }
  if (viewsAvg != null) parts.push(`조회수 일평균 <b>${fmt(Math.round(viewsAvg))}</b>`);
  if (msgAvg   != null) parts.push(`그룹 메시지 일평균 <b>${fmt(Math.round(msgAvg))}</b>`);
  if (!parts.length){ el.remove(); return; }
  el.innerHTML = `${head}(완료일 기준) · ` + parts.join(' · ');
})();

// ---------- 01 KPI 카드 ----------
const cards = [
  {label:'구독자', key:'ch_subscribers', flow:false, snap:true},
  {label:'채널 조회수 (일)', key:'ch_views', flow:true},
  {label:'그룹 멤버', key:'gr_members', flow:false, snap:true},
  {label:'그룹 메시지 (일)', key:'gr_messages', flow:true},
  {label:'그룹 활성 유저 (일)', key:'gr_active_users', flow:true},
];
document.getElementById('cards').innerHTML = cards.filter(c => HAS_GROUP || !c.key.startsWith('gr_')).map(c => {
  const v = last[c.key], pv = prev[c.key];
  const d = (v==null||pv==null) ? null : v - pv;
  // 유량형 지표(조회수·메시지·활성)는 오늘이 진행 중이라 전일대비가 가짜 급감으로 보임 → '집계중' 표기
  const cls = c.flow ? 'flat' : (d==null?'flat':d>0?'up':d<0?'down':'flat');
  const arrow = d==null?'—':d>0?'▲':d<0?'▼':'—';
  const deltaTxt = c.flow
    ? `<span style="color:var(--ink-300);font-weight:400;">오늘 집계중 (진행)</span>`
    : (d==null ? '—' : `${arrow} ${fmt(Math.abs(d))} <span style="color:var(--ink-300);font-weight:400;">전일대비</span>`);
  return `<div class="card">
    <div class="label">${c.label}</div>
    <div class="value">${v==null?'—':fmt(v)}</div>
    <div class="delta ${cls}">${deltaTxt}</div>
    ${c.snap ? avg7(c.key, v) : ''}
    <button class="detail-btn" data-key="${c.key}" data-label="${c.label}">일자별 기록</button>
  </div>`;
}).join('');

// ---------- 지표 상세 레이어 팝업 (일자별 기록) ----------
(function(){
  const modal = document.getElementById('metricModal');
  let lastFocus = null;
  function open(key, label){
    lastFocus = document.activeElement;
    const flow = (key === 'ch_subscribers') && DATA.some(r => r.ch_joined != null || r.ch_left != null);
    let html = '';
    for (let i = DATA.length - 1; i >= 0; i--){
      const cur = DATA[i], pr = DATA[i-1];
      const v = cur[key];
      const d = (i===0 || v==null || pr[key]==null) ? null : v - pr[key];
      const cls = d==null?'flat':d>0?'up':d<0?'down':'flat';
      const arrow = d==null?'':d>0?'▲':d<0?'▼':'—';
      const deltaCell = d==null ? '<span class="flat">—</span>'
        : `<span class="${cls}">${arrow} ${fmt(Math.abs(d))}</span>`;
      let extra = '';
      if (flow){
        const ji = cur.ch_joined, le = cur.ch_left;
        extra = `<td>${ji==null?'<span class="flat">—</span>':'<span class="up">+'+fmt(ji)+'</span>'}</td>`
              + `<td>${le==null?'<span class="flat">—</span>':'<span class="down">-'+fmt(le)+'</span>'}</td>`;
      }
      html += `<tr><td class="l">${cur.date}</td><td>${v==null?'<span class="flat">—</span>':fmt(v)}</td><td>${deltaCell}</td>${extra}</tr>`;
    }
    document.getElementById('mmHead').innerHTML =
      `<tr><th class="l">날짜</th><th>값</th><th>전일대비</th>${flow?'<th>들어옴</th><th>나감</th>':''}</tr>`;
    document.getElementById('mmTitle').textContent = label;
    document.getElementById('mmSub').textContent =
      `${DATA.length}일 기록 · ${DATA[0].date} ~ ${DATA[DATA.length-1].date}`;
    document.getElementById('mmBody').innerHTML = html;
    modal.classList.add('show'); modal.setAttribute('aria-hidden','false');
    document.getElementById('mmClose').focus();   // 열면 닫기 버튼에 포커스
  }
  function close(){
    modal.classList.remove('show'); modal.setAttribute('aria-hidden','true');
    if (lastFocus && lastFocus.focus) lastFocus.focus();   // 닫으면 호출 버튼으로 복귀
  }
  document.getElementById('mmClose').addEventListener('click', close);
  modal.addEventListener('click', e => { if (e.target === modal) close(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') close(); });
  document.addEventListener('click', e => {
    const btn = e.target.closest('.detail-btn');
    if (btn) open(btn.dataset.key, btn.dataset.label);
  });
})();

// ---------- 03 도달/참여 요약 카드 ----------
const dViews = last.ch_views, dFwd = last.ch_forwards, dRep = last.ch_replies;
const reach = subsNow ? dViews/subsNow : 0;
const er    = dViews ? (dFwd+dRep)/dViews : 0;
// A5: 도달률·ER은 진행 중인 '오늘' 값으로 계산되므로 완성치 오해 방지용 '(진행중)' 표식.
const wip = `<span style="color:var(--ink-300);font-weight:400;font-size:11px;"> (진행중)</span>`;
document.getElementById('reachCards').innerHTML = [
  {label:'도달률 (조회수÷구독자)', val:pct(reach), wip:true},
  {label:'참여율 ER ((공유+댓글)÷조회수)', val:pct(er), wip:true},
  {label:'오늘 공유', val:fmt(dFwd)},
  {label:'오늘 댓글', val:fmt(dRep)},
].map(c=>`<div class="card"><div class="label">${c.label}${c.wip?wip:''}</div><div class="value">${c.val}</div></div>`).join('');

// ---------- 차트 공통 ----------
Chart.defaults.color = '#7E8C84';
Chart.defaults.borderColor = '#EEF1EC';
Chart.defaults.font.family = "'Geist Mono', monospace";
Chart.defaults.font.size = 11;
const baseOpts = {
  responsive:true, maintainAspectRatio:false,
  plugins:{legend:{labels:{boxWidth:10,boxHeight:10,font:{size:11},color:'#5F6C65'}}},
  scales:{ y:{grid:{color:'#EEF1EC'},ticks:{color:'#7E8C84'},border:{color:'#E3E7DF'}},
           x:{grid:{display:false},ticks:{color:'#7E8C84'},border:{color:'#E3E7DF'}} }
};
const clone = o => JSON.parse(JSON.stringify(o));
// 차트마다 옵션을 복제해 공유 충돌 방지. 막대는 offset:true 로 양 끝 막대 잘림 방지.
const line = (id,ds)=> new Chart(document.getElementById(id),{type:'line',data:{labels:dates,datasets:ds},options:clone(baseOpts)});
const bar  = (id,ds)=>{ const o=clone(baseOpts); o.scales.x.offset=true; return new Chart(document.getElementById(id),{type:'bar',data:{labels:dates,datasets:ds},options:o}); };
const L = (label,key,color,fill=false)=>({label,data:DATA.map(r=>r[key]),borderColor:color,
  backgroundColor:fill?color+'22':color,tension:.25,pointRadius:2,pointBackgroundColor:color,borderWidth:2,fill});

// 02 구독자
line('subs', [L('구독자','ch_subscribers','#0B3A2C',true)]);
// 들어옴(+) · 나감(-) — 공식 통계 followers_graph 기반 (없으면 순증·순감으로 폴백)
const hasFlow = DATA.some(r => r.ch_joined != null || r.ch_left != null);
if (hasFlow) {
  const joinedArr = DATA.map(r => r.ch_joined);
  const leftArr   = DATA.map(r => r.ch_left == null ? null : -r.ch_left);
  const stackOpts = clone(baseOpts);
  stackOpts.scales.x.stacked = true; stackOpts.scales.y.stacked = true; stackOpts.scales.x.offset = true;
  new Chart(document.getElementById('subsNet'),{type:'bar',
    data:{labels:dates,datasets:[
      {label:'들어옴',data:joinedArr,backgroundColor:'#1F8A5B',borderRadius:0,stack:'flow'},
      {label:'나감',data:leftArr,backgroundColor:'#C8404E',borderRadius:0,stack:'flow'},
    ]},options:stackOpts});
} else {
  const net = DATA.map((r,i)=> (i===0||r.ch_subscribers==null||DATA[i-1].ch_subscribers==null)?null : r.ch_subscribers-DATA[i-1].ch_subscribers);
  new Chart(document.getElementById('subsNet'),{type:'bar',
    data:{labels:dates,datasets:[{label:'순증·순감',data:net,
      backgroundColor:net.map(v=>v==null?'#E3E7DF':v>=0?'#1F8A5B':'#C8404E'),borderRadius:0}]},
    options:(()=>{const o=clone(baseOpts);o.scales.x.offset=true;return o;})()});
}

// 03 조회/인게이지먼트
bar('views', [{label:'조회수',data:DATA.map(r=>r.ch_views),backgroundColor:'#25876A',borderRadius:0}]);
line('engage',[L('공유','ch_forwards','#2E84AE'),L('댓글','ch_replies','#1F8A5B')]);

// 06 그룹 — KPI 카드(전일대비) + 추이 + 순증·순감 (연결 그룹 있을 때만)
if (HAS_GROUP) {
const grCards = [
  {label:'그룹 멤버', key:'gr_members'},
  {label:'메시지 (일)', key:'gr_messages', flow:true},
  {label:'활성 유저 (일)', key:'gr_active_users', flow:true},
];
document.getElementById('grCards').innerHTML = grCards.map(c => {
  const v = last[c.key], pv = prev[c.key];
  const d = (v==null||pv==null) ? null : v - pv;
  const cls = c.flow ? 'flat' : (d==null?'flat':d>0?'up':d<0?'down':'flat');
  const arrow = d==null?'—':d>0?'▲':d<0?'▼':'—';
  const deltaTxt = c.flow
    ? `<span style="color:var(--ink-300);font-weight:400;">오늘 집계중 (진행)</span>`
    : (d==null ? '—' : `${arrow} ${fmt(Math.abs(d))} <span style="color:var(--ink-300);font-weight:400;">전일대비</span>`);
  return `<div class="card">
    <div class="label">${c.label}</div>
    <div class="value">${v==null?'—':fmt(v)}</div>
    <div class="delta ${cls}">${deltaTxt}</div>
    <button class="detail-btn" data-key="${c.key}" data-label="${c.label}">일자별 기록</button>
  </div>`;
}).join('');

line('grMembers',[L('멤버','gr_members','#2E84AE',true)]);
const grNet = DATA.map((r,i)=> (i===0||r.gr_members==null||DATA[i-1].gr_members==null)?null : r.gr_members-DATA[i-1].gr_members);
new Chart(document.getElementById('grNet'),{type:'bar',
  data:{labels:dates,datasets:[{label:'멤버 순증·순감',data:grNet,
    backgroundColor:grNet.map(v=>v==null?'#E3E7DF':v>=0?'#1F8A5B':'#C8404E'),borderRadius:0}]},
  options:(()=>{const o=clone(baseOpts);o.scales.x.offset=true;return o;})()});
line('grActivity',[L('메시지','gr_messages','#2E84AE'),L('활성 유저','gr_active_users','#0B3A2C')]);
}

// ---------- 차트 상세 팝업 (차트 클릭 → 확대 + 기간 전환 + 요약 + 일자별 표) ----------
(function(){
  const CH_TAG = '@__CHUSER__', GR_TAG = '@__GRUSER__';
  const INFO = {
    subs:      {eyebrow:'Channel · Growth', title:'구독자 추이', tag:CH_TAG, kind:'line', cumulative:true,
                series:[{label:'구독자', key:'ch_subscribers', color:'#0B3A2C', fill:true}]},
    subsNet:   hasFlow
      ? {eyebrow:'Channel · Growth', title:'들어옴 · 나감 (일별)', tag:CH_TAG, kind:'flow'}
      : {eyebrow:'Channel · Growth', title:'구독자 순증 · 순감 (일별)', tag:CH_TAG, kind:'net', netKey:'ch_subscribers'},
    views:     {eyebrow:'Channel · Reach', title:'일일 조회수', tag:CH_TAG, kind:'bar',
                series:[{label:'조회수', key:'ch_views', color:'#25876A'}]},
    engage:    {eyebrow:'Channel · Reach', title:'공유 · 댓글 (인게이지먼트)', tag:CH_TAG, kind:'line',
                series:[{label:'공유', key:'ch_forwards', color:'#2E84AE'},
                        {label:'댓글', key:'ch_replies', color:'#1F8A5B'}]},
    grMembers: {eyebrow:'Group · Discussion', title:'그룹 멤버 추이', tag:GR_TAG, kind:'line', cumulative:true,
                series:[{label:'멤버', key:'gr_members', color:'#2E84AE', fill:true}]},
    grNet:     {eyebrow:'Group · Discussion', title:'멤버 일별 순증 · 순감', tag:GR_TAG, kind:'net', netKey:'gr_members'},
    grActivity:{eyebrow:'Group · Discussion', title:'메시지 · 활성 유저', tag:GR_TAG, kind:'line',
                series:[{label:'메시지', key:'gr_messages', color:'#2E84AE'},
                        {label:'활성 유저', key:'gr_active_users', color:'#0B3A2C'}]},
  };
  const modal = document.getElementById('chartModal');
  if (!modal || typeof Chart === 'undefined') return;
  let curId = null, range = 30, inst = null, lastFocus = null;
  const $id  = x => document.getElementById(x);
  const nums = a => a.filter(v => v != null);
  const cell = (lb, vl, cls) => `<div class="cell"><div class="lb">${lb}</div><div class="vl ${cls||''}">${vl}</div></div>`;
  const sgn  = v => (v > 0 ? '+' : '') + fmt(v);
  const dash = '<span class="flat">—</span>';
  const netOf = key => DATA.map((r,i)=> (i===0||r[key]==null||DATA[i-1][key]==null)?null : r[key]-DATA[i-1][key]);
  const slice = arr => range === 0 ? arr : arr.slice(-range);

  function render(){
    const info = INFO[curId];
    const rows = slice(DATA), lbs = slice(dates), n = rows.length;
    $id('cdEyebrow').textContent = info.eyebrow;
    $id('cdTitle').textContent = info.title;
    $id('cdSub').textContent = `${info.tag} · ${range===0?'전체 기간':'최근 '+n+'일'} · ${rows[0].date} ~ ${rows[n-1].date}`;
    $id('cdPoints').textContent = `${n}일 기록 · 마지막 날은 집계 진행중`;
    modal.querySelectorAll('#cdTabs button').forEach(b => b.classList.toggle('on', +b.dataset.r === range));

    let datasets = [], type = 'line', stacked = false, stats = '', head = '', body = '';
    if (info.kind === 'flow'){
      const j = rows.map(r=>r.ch_joined), l = rows.map(r=>r.ch_left==null?null:-r.ch_left);
      type = 'bar'; stacked = true;
      datasets = [{label:'들어옴',data:j,backgroundColor:'#1F8A5B',borderRadius:0,stack:'flow'},
                  {label:'나감',data:l,backgroundColor:'#C8404E',borderRadius:0,stack:'flow'}];
      const tj = nums(j).reduce((a,b)=>a+b,0), tl = nums(rows.map(r=>r.ch_left)).reduce((a,b)=>a+b,0);
      const net = tj - tl;
      stats = cell('총 들어옴','+'+fmt(tj),'up') + cell('총 나감','-'+fmt(tl),'down')
        + cell('순증감', sgn(net), net>=0?'up':'down') + cell('일평균 순증', n?(net/n).toFixed(1):'—','');
      head = '<tr><th class="l">날짜</th><th>들어옴</th><th>나감</th><th>순증감</th></tr>';
      for (let i=n-1;i>=0;i--){
        const r=rows[i], jj=r.ch_joined, ll=r.ch_left;
        const nt = (jj==null||ll==null)?null:jj-ll;
        body += `<tr><td class="l">${r.date}</td>`
          + `<td>${jj==null?dash:'<span class="up">+'+fmt(jj)+'</span>'}</td>`
          + `<td>${ll==null?dash:'<span class="down">-'+fmt(ll)+'</span>'}</td>`
          + `<td>${nt==null?dash:`<span class="${nt>=0?'up':'down'}">${sgn(nt)}</span>`}</td></tr>`;
      }
    } else if (info.kind === 'net'){
      const net = slice(netOf(info.netKey));
      type = 'bar';
      datasets = [{label:'순증·순감',data:net,borderRadius:0,
        backgroundColor:net.map(v=>v==null?'#E3E7DF':v>=0?'#1F8A5B':'#C8404E')}];
      const xs = nums(net), sum = xs.reduce((a,b)=>a+b,0);
      stats = cell('순증감 합계', xs.length?sgn(sum):'—', sum>=0?'up':'down')
        + cell('일평균', xs.length?(sum/xs.length).toFixed(1):'—','')
        + cell('최대 증가', xs.length?sgn(Math.max(...xs)):'—','up')
        + cell('최대 감소', xs.length?sgn(Math.min(...xs)):'—','down');
      head = '<tr><th class="l">날짜</th><th>순증·순감</th></tr>';
      for (let i=n-1;i>=0;i--){
        const v = net[i];
        body += `<tr><td class="l">${rows[i].date}</td>`
          + `<td>${v==null?dash:`<span class="${v>=0?'up':'down'}">${sgn(v)}</span>`}</td></tr>`;
      }
    } else {
      type = info.kind === 'bar' ? 'bar' : 'line';
      datasets = info.series.map(s => type === 'bar'
        ? {label:s.label, data:rows.map(r=>r[s.key]), backgroundColor:s.color, borderRadius:0}
        : {label:s.label, data:rows.map(r=>r[s.key]), borderColor:s.color,
           backgroundColor:s.fill?s.color+'22':s.color, tension:.25, pointRadius:2,
           pointBackgroundColor:s.color, borderWidth:2, fill:!!s.fill});
      const xs = nums(rows.map(r=>r[info.series[0].key]));
      if (info.cumulative){
        const d = xs.length>=2 ? xs[xs.length-1]-xs[0] : null;
        stats = cell('현재', xs.length?fmt(xs[xs.length-1]):'—','')
          + cell('기간 증감', d==null?'—':sgn(d), d==null?'':d>=0?'up':'down')
          + cell('최고', xs.length?fmt(Math.max(...xs)):'—','')
          + cell('최저', xs.length?fmt(Math.min(...xs)):'—','');
      } else if (info.series.length === 1){
        const sum = xs.reduce((a,b)=>a+b,0);
        stats = cell('합계', xs.length?fmt(sum):'—','')
          + cell('일평균', xs.length?fmt(Math.round(sum/xs.length)):'—','')
          + cell('최고', xs.length?fmt(Math.max(...xs)):'—','')
          + cell('최저', xs.length?fmt(Math.min(...xs)):'—','');
      } else {
        stats = info.series.map(s => {
          const v = nums(rows.map(r=>r[s.key])), sum = v.reduce((a,b)=>a+b,0);
          return cell(s.label+' 합계', v.length?fmt(sum):'—','')
               + cell(s.label+' 일평균', v.length?fmt(Math.round(sum/v.length)):'—','');
        }).join('');
      }
      if (info.series.length === 1){
        head = `<tr><th class="l">날짜</th><th>${info.series[0].label}</th><th>전일대비</th></tr>`;
        const allV = DATA.map(r=>r[info.series[0].key]);
        const off = range === 0 ? 0 : Math.max(0, DATA.length - range);
        for (let i=n-1;i>=0;i--){
          const gi = off+i, v = allV[gi], pv = gi>0?allV[gi-1]:null;
          const d = (v==null||pv==null)?null:v-pv;
          const dc = d==null?dash:`<span class="${d>0?'up':d<0?'down':'flat'}">${d>0?'▲':d<0?'▼':'—'} ${fmt(Math.abs(d))}</span>`;
          body += `<tr><td class="l">${rows[i].date}</td><td>${v==null?dash:fmt(v)}</td><td>${dc}</td></tr>`;
        }
      } else {
        head = `<tr><th class="l">날짜</th>${info.series.map(s=>`<th>${s.label}</th>`).join('')}</tr>`;
        for (let i=n-1;i>=0;i--){
          body += `<tr><td class="l">${rows[i].date}</td>`
            + info.series.map(s=>{const v=rows[i][s.key];return `<td>${v==null?dash:fmt(v)}</td>`;}).join('')
            + '</tr>';
        }
      }
    }
    $id('cdStats').innerHTML = stats;
    $id('cdHead').innerHTML = head;
    $id('cdBody').innerHTML = body;

    if (inst) inst.destroy();
    const o = clone(baseOpts);
    if (type === 'bar') o.scales.x.offset = true;
    if (stacked){ o.scales.x.stacked = true; o.scales.y.stacked = true; }
    inst = new Chart($id('cdCanvas'), {type, data:{labels:lbs, datasets}, options:o});
  }

  function setTbl(on){
    modal.classList.toggle('tbl', on);
    const b = $id('cdTableMax');
    b.classList.toggle('on', on);
    b.textContent = on ? '차트 보기' : '표 크게 보기';
    if (!on && inst) requestAnimationFrame(() => inst.resize());
  }
  function open(id){
    lastFocus = document.activeElement;
    curId = id; range = 30;
    setTbl(false);
    render();
    modal.classList.add('show'); modal.setAttribute('aria-hidden','false');
    $id('cdClose').focus();
  }
  function close(){
    modal.classList.remove('show'); modal.setAttribute('aria-hidden','true');
    if (inst){ inst.destroy(); inst = null; }
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }
  Object.keys(INFO).forEach(id => {
    const cv = document.getElementById(id);
    if (!cv) return;
    const box = cv.closest('.chart-box');
    if (!box) return;
    box.classList.add('clickable');
    box.tabIndex = 0;
    box.setAttribute('role','button');
    box.setAttribute('aria-label', INFO[id].title + ' 상세보기');
    box.addEventListener('click', () => open(id));
    box.addEventListener('keydown', e => { if (e.key==='Enter'||e.key===' '){ e.preventDefault(); open(id); } });
  });
  $id('cdClose').addEventListener('click', close);
  $id('cdTableMax').addEventListener('click', () => setTbl(!modal.classList.contains('tbl')));
  modal.addEventListener('click', e => { if (e.target === modal) close(); });
  document.addEventListener('keydown', e => { if (e.key==='Escape' && modal.classList.contains('show')) close(); });
  $id('cdTabs').addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    range = +b.dataset.r; render();
  });
})();

// ---------- 04 포스트 표 — 월 → 주차 탭으로 주 단위 보기 ----------
// 주 = 월~일(데이터 일 버킷 기준). 주의 소속 월·주차는 그 주 '목요일'이 속한 달 기준(ISO 관례):
//   8/31(월)~9/6(일) 은 목요일 9/3 → "9월 1주차". 주차 = ceil(목요일 날짜 / 7).
// 초기 화면은 오늘이 속한 주. 게시물이 없는 주는 탭에 안 나오되 이번 주는 항상 표시.
const link = id => `https://t.me/${CH_USER}/${id}`;

if (POSTS.length) {
  const DAY = 86400000;
  const toTs = d => { const [y,m,dd] = d.split('-').map(Number); return Date.UTC(y, m-1, dd); };
  const isoOf = t => new Date(t).toISOString().slice(0,10);
  const md = t => { const x = new Date(t); return `${x.getUTCMonth()+1}/${x.getUTCDate()}`; };
  const mondayOf = d => { const t = toTs(d); return t - ((new Date(t).getUTCDay() + 6) % 7) * DAY; };

  const weeks = {};                                    // monTs → 주 객체
  const week = d => {
    const mon = mondayOf(d);
    if (!weeks[mon]) {
      const thu = new Date(mon + 3*DAY);
      weeks[mon] = { mon, sun: mon + 6*DAY, posts: [],
        month: isoOf(thu.getTime()).slice(0,7), idx: Math.ceil(thu.getUTCDate()/7) };
    }
    return weeks[mon];
  };
  for (const p of POSTS) week(p.date).posts.push(p);
  const todayIso = (typeof last !== 'undefined' && last && last.date) ? last.date : new Date().toISOString().slice(0,10);
  const curWeek = week(todayIso);                      // 이번 주는 게시물 0건이어도 존재

  const byMonth = {};
  for (const w of Object.values(weeks)) (byMonth[w.month] = byMonth[w.month] || []).push(w);
  const months = Object.keys(byMonth).sort();                              // 오래된 월 → 최근 월(맨 뒤)
  for (const m of months) byMonth[m].sort((a,b)=>a.mon-b.mon);             // 1주차 → 마지막 주
  const latestYear = months[months.length-1].slice(0,4);
  const mLabel = m => `${Number(m.slice(5))}월`;
  const mYear  = m => m.slice(0,4) !== latestYear ? `${m.slice(0,4)} · ` : '';

  const monthsEl = document.getElementById('postMonths');
  const weeksEl  = document.getElementById('postWeeks');
  const topBody  = document.getElementById('topPosts');
  const allBody  = document.getElementById('allPosts');
  const pager    = document.getElementById('allPostsPager');
  const sel      = document.getElementById('postDate');
  const wLabel = w => `${Number(w.month.slice(5))}월 ${w.idx}주차`;
  const wRange = w => `${md(w.mon)}~${md(w.sun)}`;

  const topRow = (p,i) => `
    <tr>
      <td class="l"><span class="rank ${i===0?'t1':i===1?'t2':''}">${i+1}</span>
        <a class="post" href="${link(p.id)}" target="_blank" rel="noopener" title="${esc(p.text)}">${esc(p.text)}</a></td>
      <td>${p.date.slice(5)}</td>
      <td>${fmt(p.views)}</td>
      <td>${fmt(p.forwards)}</td><td>${fmt(p.replies)}</td>
    </tr>`;
  const listRow = p => `
    <tr>
      <td class="l"><a class="post" href="${link(p.id)}" target="_blank" rel="noopener" title="${esc(p.text)}">${esc(p.text)}</a></td>
      <td style="white-space:nowrap;" title="${p.date}">${sel.value === '__week' ? p.date.slice(5) + ' ' : ''}${p.time}</td>
      <td>${fmt(p.views)}</td>
      <td>${fmt(p.forwards)}</td><td>${fmt(p.replies)}</td>
    </tr>`;
  const emptyRow = msg => `<tr><td class="l" colspan="5" style="text-align:center;color:var(--ink-300);padding:24px;">${msg}</td></tr>`;

  let curMonth = curWeek.month, cur = curWeek;

  function showWeek(w){
    cur = w;
    weeksEl.querySelectorAll('.tab').forEach(b => b.classList.toggle('active', Number(b.dataset.mon) === w.mon));
    document.getElementById('topWeekLabel').textContent = wLabel(w);
    document.getElementById('listWeekLabel').textContent = wLabel(w);
    const posts = w.posts.slice();
    topBody.innerHTML = posts.length
      ? posts.sort((a,b)=>b.views-a.views).slice(0,10).map(topRow).join('')
      : emptyRow(w === curWeek ? '이번 주에 올라온 게시물이 아직 없습니다.' : '이 주에는 게시물이 없습니다.');
    // 날짜 선택: 주 전체 + 게시물 있는 날짜(최신 먼저)
    const byDate = {};
    for (const p of w.posts) (byDate[p.date] = byDate[p.date] || []).push(p);
    const days = Object.keys(byDate).sort((a,b)=>b.localeCompare(a));
    sel.innerHTML = `<option value="__week">주 전체 · ${w.posts.length}건</option>`
      + days.map(d=>`<option value="${d}">${d.slice(5)} · ${byDate[d].length}건</option>`).join('');
    const showList = d => {
      const items = (d === '__week' ? w.posts : (byDate[d]||[])).slice()
        .sort((a,b)=> (b.date+b.time).localeCompare(a.date+a.time));
      if (!items.length){ allBody.innerHTML = emptyRow('게시물 없음'); pager.innerHTML=''; return; }
      paginate(allBody, pager, items, 10, listRow);
    };
    sel.onchange = () => showList(sel.value);
    const initial = byDate[todayIso] ? todayIso : (days[0] || '__week');
    sel.value = initial;
    showList(initial);
  }
  function showMonth(m){
    curMonth = m;
    monthsEl.querySelectorAll('.tab').forEach(b => b.classList.toggle('active', b.dataset.m === m));
    weeksEl.innerHTML = byMonth[m].map(w =>
      `<button type="button" class="tab" data-mon="${w.mon}">${wLabel(w)}<span class="sub">${wRange(w)} · ${w.posts.length}건</span></button>`).join('');
    weeksEl.querySelectorAll('.tab').forEach(b => b.addEventListener('click', () => showWeek(weeks[Number(b.dataset.mon)])));
  }
  monthsEl.innerHTML = months.map(m => {
    const n = byMonth[m].reduce((a,w)=>a+w.posts.length, 0);
    return `<button type="button" class="tab" data-m="${m}">${mLabel(m)}<span class="sub">${mYear(m)}${n}건</span></button>`;
  }).join('');
  monthsEl.querySelectorAll('.tab').forEach(b => b.addEventListener('click', () => {
    const arr = byMonth[b.dataset.m]; showMonth(b.dataset.m); showWeek(arr[arr.length-1]);
  }));
  showMonth(curMonth);
  showWeek(curWeek);
} else {
  const empty = `<tr><td class="l" colspan="5" style="text-align:center;color:var(--ink-300);padding:24px;">포스트 데이터 없음 — collect.py 실행 후 표시됩니다.</td></tr>`;
  document.getElementById('topPosts').innerHTML = empty;
  document.getElementById('allPosts').innerHTML = empty;
}

// ---------- 04b 게시글 서비스 남은횟수 (쿼터) ----------
// 게시글 1건당 1회 차감되는 외부 서비스의 잔여 횟수를 자체 집계로 교차 확인.
// 칩 클릭 → 일자별 사용 내역(몇일 · 몇건 · 그 시점 남은횟수) 레이어 팝업.
(function(){
  const chip = document.getElementById('quotaChip');
  if (!chip || !QUOTA || !QUOTA.available) return;
  chip.hidden = false;
  if (QUOTA.mode === 'deadline') {
    // 기간형(부스팅 등): 마감일까지 D-day + 마감일 병기. 클릭 팝업 없음.
    const [y,m,d] = QUOTA.deadline.split('-').map(Number);
    const kstNow = new Date(Date.now() + 9*3600*1000);              // KST 오늘 (달력일 기준)
    const today = Date.UTC(kstNow.getUTCFullYear(), kstNow.getUTCMonth(), kstNow.getUTCDate());
    const diff = Math.round((Date.UTC(y, m-1, d) - today) / 86400000);
    const dday = diff > 0 ? `D-${diff}` : diff === 0 ? 'D-DAY' : `종료 (+${-diff}일)`;
    chip.classList.add('static');
    chip.title = `${QUOTA.label || '기간'} 마감일 ${QUOTA.deadline}`;
    chip.innerHTML = `${esc(QUOTA.label || '기간')} <b>${dday}</b> <span class="due">· ${m}/${d} 마감</span>`;
    return;
  }
  chip.querySelector('b').textContent = fmt(QUOTA.remaining) + '회';
  chip.addEventListener('click', ()=>{
    document.getElementById('mmTitle').textContent = '게시글 서비스 — 남은횟수';
    document.getElementById('mmSub').textContent =
      `총 ${fmt(QUOTA.total)}회 · 사용 ${fmt(QUOTA.used)}건 · 남은 ${fmt(QUOTA.remaining)}회 · ${QUOTA.start} 기준 시작`;
    document.getElementById('mmHead').innerHTML =
      '<tr><th class="l">날짜</th><th>게시글</th><th>남은횟수</th></tr>';
    let cum = 0;
    const rows = QUOTA.daily.map(d => { cum += d.count; return {date:d.date, count:d.count, left:QUOTA.total - cum}; });
    rows.reverse();                                    // 최신일 먼저
    document.getElementById('mmBody').innerHTML = rows.length
      ? rows.map(r=>`<tr><td class="l">${r.date}</td><td>${fmt(r.count)}건</td><td>${fmt(r.left)}회</td></tr>`).join('')
        + `<tr><td class="l" style="font-weight:600;color:var(--ink-900);">합계</td>`
        + `<td style="font-weight:600;">${fmt(QUOTA.used)}건</td>`
        + `<td style="font-weight:600;color:var(--forest-700);">${fmt(QUOTA.remaining)}회 남음</td></tr>`
      : `<tr><td class="l" colspan="3" style="text-align:center;color:var(--ink-300);padding:24px;">아직 사용 내역이 없습니다 — ${QUOTA.start} 이후 게시글이 올라오면 자동 집계됩니다.</td></tr>`;
    const modal = document.getElementById('metricModal');
    modal.classList.add('show'); modal.setAttribute('aria-hidden','false');
    document.getElementById('mmClose').focus();        // 닫기는 기존 모달 핸들러(X·배경·ESC) 공용
  });
})();

// ---------- 05 공식 통계 ----------
(function(){
  const box = document.getElementById('officialStats');
  if (OFFICIAL && OFFICIAL.available) {
    const m = OFFICIAL.metrics || {};
    // E5: 값이 0(숫자) 또는 빈 문자열인 지표는 카드에서 숨김. "%" 등 문자열 값은 유지.
    const entries = Object.entries(m).filter(([,v]) =>
      !(v === 0 || v === null || v === '' || (typeof v === 'string' && v.trim() === '')));
    if (!entries.length) {
      box.innerHTML = `<div class="empty"><div class="tag">No official stats</div><b>공식 통계 지표 없음</b></div>`;
    } else {
      box.innerHTML = `<div class="cards cards-tight">` + entries.map(([k,v])=>
        `<div class="card"><div class="label">${esc(k)}</div><div class="value">${typeof v==='number'?fmt(v):esc(String(v))}</div></div>`
      ).join('') + `</div>`;
    }
  } else {
    const reason = (OFFICIAL && OFFICIAL.reason) ? esc(OFFICIAL.reason)
      : '아직 수집되지 않았거나, 채널 규모가 공식 통계 생성 조건(보통 구독자 50~500+)에 도달하지 않았습니다.';
    box.innerHTML = `<div class="empty"><div class="tag">No official stats</div>
      <b>공식 통계 미표시</b><br>${reason}<br>
      <span style="font-size:12.5px;">구독자 ${fmt(subsNow)}명 · 조건 충족 시 collect.py가 자동 수집합니다.</span></div>`;
  }
})();

// ---------- 공용 페이지네이션 ----------
function paginate(bodyEl, pagerEl, items, pageSize, rowFn){
  const pageCount = Math.max(1, Math.ceil(items.length / pageSize));
  function nums(cur){
    const set = new Set([1,pageCount,cur,cur-1,cur+1,cur-2,cur+2]);
    const arr = [...set].filter(n=>n>=1&&n<=pageCount).sort((a,b)=>a-b);
    const out=[]; let prev=0;
    for(const n of arr){ if(n-prev>1) out.push('…'); out.push(n); prev=n; }
    return out;
  }
  function render(pg){
    pg = Math.min(Math.max(1,pg), pageCount);
    const s = (pg-1)*pageSize;
    bodyEl.innerHTML = items.slice(s, s+pageSize).map((it,i)=>rowFn(it, s+i)).join('');
    if(pageCount<=1){ pagerEl.innerHTML=''; return; }
    let b = `<button ${pg===1?'disabled':''} data-pg="${pg-1}">‹</button>`;
    for(const n of nums(pg))
      b += n==='…' ? `<span class="gap">…</span>`
                   : `<button class="${n===pg?'active':''}" data-pg="${n}">${n}</button>`;
    b += `<button ${pg===pageCount?'disabled':''} data-pg="${pg+1}">›</button>`;
    pagerEl.innerHTML = b;
  }
  pagerEl.onclick = e => { const x=e.target.closest('button[data-pg]'); if(x&&!x.disabled) render(parseInt(x.dataset.pg,10)); };
  render(1);
}

// ---------- 02b 유입 · 이탈 인원 (누가) ----------
function kstShort(iso){
  if(!iso) return '—';
  const d = new Date(new Date(iso).getTime() + 9*3600*1000);  // KST 표시
  const p = n => String(n).padStart(2,'0');
  return `${p(d.getUTCMonth()+1)}-${p(d.getUTCDate())} ${p(d.getUTCHours())}:${p(d.getUTCMinutes())}`;
}
// opts.months / opts.base 가 있으면(채널) 월 탭을 두고, 월 클릭 시 <base><YYYY-MM>.json 을 불러온다.
// 페이지에는 최근 1000건만 내장 → 최신 월은 내장분으로 즉시 그린 뒤 파일이 오면 전체로 교체.
function renderJoinLeave(box, src, opts){
  if(!box) return;
  const base = (src && src.available) ? (src.events || []) : null;
  if (base && base.length){
    const months = (opts && Array.isArray(opts.months)) ? opts.months.slice().sort() : [];
    const latestYear = months.length ? months[months.length-1].slice(0,4) : '';
    const mLabel = m => `${Number(m.slice(5))}월` + (m.slice(0,4)!==latestYear ? `<span class="sub">${m.slice(0,4)}</span>` : '');
    box.innerHTML = `
      ${months.length ? `<div class="tabs jl-months">${months.map(m=>`<button type="button" class="tab" data-m="${m}">${mLabel(m)}</button>`).join('')}</div>` : ''}
      <div class="tabs jl-kinds">
        <button class="tab active" data-f="all">전체 <span class="n"></span></button>
        <button class="tab" data-f="join">유입 <span class="n"></span></button>
        <button class="tab" data-f="left">이탈 <span class="n"></span></button>
      </div>
      <div class="jl-note" id="jlNote" hidden></div>
      <div class="table-wrap"><table><thead><tr><th class="l">구분</th><th class="l">멤버</th><th>시각</th></tr></thead><tbody></tbody></table></div>
      <div class="pager"></div>`;
    const tabs = box.querySelector('.jl-kinds');
    const mtabs = box.querySelector('.jl-months');
    const note = box.querySelector('#jlNote');
    const body = box.querySelector('tbody'), pager = box.querySelector('.pager');
    let jl = base, filter = 'all', curM = months.length ? months[months.length-1] : null;
    const cache = {};
    function setNote(t){ note.hidden = !t; note.textContent = t || ''; }
    const rowFn = e => {
      const tag = e.kind==='join' ? `<span class="jl-tag join">유입</span>` : `<span class="jl-tag left">이탈</span>`;
      const uname = e.username ? ` <span style="color:var(--ink-300);">@${esc(e.username)}</span>` : '';
      const label = `${esc(e.name||('user '+e.id))}${uname}`;
      const cell = e.username ? `<a class="ulink" href="https://t.me/${encodeURIComponent(e.username)}" target="_blank" rel="noopener">${label}</a>` : label;
      return `<tr><td class="l">${tag}</td><td class="l">${cell}</td><td>${kstShort(e.date)}</td></tr>`;
    };
    function draw(){
      const jn = jl.filter(e=>e.kind==='join').length, lv = jl.length - jn;
      const ns = tabs.querySelectorAll('.n'); ns[0].textContent = fmt(jl.length); ns[1].textContent = fmt(jn); ns[2].textContent = fmt(lv);
      const items = filter==='all' ? jl : jl.filter(e=>e.kind===filter);
      if (!items.length){ body.innerHTML = `<tr><td class="l" colspan="3" style="text-align:center;color:var(--ink-300);padding:24px;">기록 없음</td></tr>`; pager.innerHTML=''; return; }
      paginate(body, pager, items, 10, rowFn);
    }
    tabs.addEventListener('click', ev=>{
      const t = ev.target.closest('.tab'); if(!t) return;
      tabs.querySelectorAll('.tab').forEach(x=>x.classList.toggle('active', x===t));
      filter = t.dataset.f; draw();
    });
    async function loadMonth(m){
      curM = m;
      mtabs.querySelectorAll('.tab').forEach(x=>x.classList.toggle('active', x.dataset.m===m));
      const isLatest = m === months[months.length-1];
      if (cache[m]) { jl = cache[m]; setNote(''); draw(); return; }
      jl = isLatest ? base : []; setNote(isLatest ? '' : '불러오는 중…'); draw();
      try {
        const r = await fetch(`${opts.base}${m}.json`, {cache:'no-cache'});
        if (!r.ok) throw new Error(r.status);
        const data = await r.json();
        cache[m] = Array.isArray(data) ? data : [];
      } catch (e) {
        if (curM !== m) return;
        setNote(isLatest ? `월별 파일을 불러오지 못해 최근 ${fmt(base.length)}건만 표시합니다.` : '이 달의 기록 파일을 불러오지 못했습니다.');
        return;
      }
      if (curM !== m) return;
      jl = cache[m]; setNote(''); draw();
    }
    if (mtabs){
      mtabs.addEventListener('click', ev=>{ const t = ev.target.closest('.tab'); if(t) loadMonth(t.dataset.m); });
      loadMonth(curM);
    } else {
      draw();
    }
  } else {
    const reason = (src && src.reason) ? esc(src.reason)
      : 'collect.py가 admin log(관리자 권한)에서 유입·이탈 이벤트를 수집하면 표시됩니다. (그룹은 공개링크 가입이 로그에 안 남을 수 있음)';
    box.innerHTML = `<div class="empty"><div class="tag">No join/leave log</div>
      <b>유입·이탈 인원 데이터 없음</b><br>${reason}</div>`;
  }
}
renderJoinLeave(document.getElementById('joinLeave'), JOINLEAVE, {months: JOINLEAVE.months || [], base: "__JLBASE__"});
// 그룹 유입·이탈은 admin log에 안 남으므로 멤버 명단 스냅샷 diff로 추정.
// 수집 성공(available)이면 항상 노출하되, 방식의 한계를 캡션으로 안내한다.
(function(){
  const wrap = document.getElementById('grJoinLeaveWrap');
  const note = document.getElementById('grJlNote');
  const src = JOINLEAVE_GR;
  if (!(src && src.available)) return;              // 수집 실패 시에만 숨김
  wrap.hidden = false;
  const events = Array.isArray(src.events) ? src.events : [];
  if (note){
    note.innerHTML = '텔레그램 그룹은 가입/탈퇴가 관리자 로그에 남지 않아, '
      + '<b>멤버 명단을 매 갱신마다 비교</b>해 추정합니다. '
      + '시각은 <b>감지된 시점</b>(정확한 가입·탈퇴 순간이 아님)이며, '
      + '갱신 사이에 들어왔다 바로 나간 멤버는 누락될 수 있습니다.'
      + (!events.length
          ? '<br><b>' + (src.baseline ? '기준선을 저장했습니다 — ' : '')
            + '다음 갱신부터 유입·이탈이 표시됩니다.</b>'
          : '');
  }
  const box = document.getElementById('joinLeaveGroup');
  if (events.length) renderJoinLeave(box, src);    // 표는 이벤트가 있을 때만
  else if (box) box.innerHTML = '';                // 빈값이면 캡션만 노출
})();

// ---------- 06 활발한 멤버 (10명씩 페이지네이션) ----------
(function(){
  const box = document.getElementById('topMembers');
  if (!box) return;
  if (MEMBERS && MEMBERS.length) {
    box.innerHTML = `<div class="eyebrow panel-eyebrow">활발한 멤버 — 발화 수 순 (전체 ${MEMBERS.length}명)</div>
      <div class="table-wrap"><table><thead><tr><th class="l">#  멤버</th><th>발화 수</th></tr></thead><tbody id="tmBody"></tbody></table></div>
      <div class="pager" id="tmPager"></div>`;
    paginate(document.getElementById('tmBody'), document.getElementById('tmPager'), MEMBERS, 10,
      (m,i)=>{
        const uname = m.username ? ` <span style="color:var(--ink-300);">@${esc(m.username)}</span>` : '';
        const rank = `<span class="rank ${i===0?'t1':i===1?'t2':''}">${i+1}</span>`;
        const label = `${esc(m.name||('user '+m.id))}${uname}`;
        const who = m.username ? `<a class="ulink" href="https://t.me/${encodeURIComponent(m.username)}" target="_blank" rel="noopener">${label}</a>` : label;
        return `<tr><td class="l">${rank}${who}</td><td>${fmt(m.count)}</td></tr>`;
      });
  } else {
    box.innerHTML = `<div class="empty"><div class="tag">No member data</div>
      <b>활발한 멤버 데이터 없음</b><br>collect.py가 그룹 발화 집계를 저장하면 표시됩니다.</div>`;
  }
})();

// ---------- 07 코박 활동 (캉다방) ----------
(function(){
  const cardsBox = document.getElementById('cobakCards');
  const body     = document.getElementById('cobakPosts');
  if (!HAS_COBAK || !cardsBox) return;
  if (!COBAK || !COBAK.available) {
    cardsBox.innerHTML = `<div class="empty" style="grid-column:1/-1;"><div class="tag">No cobak data</div>
      <b>코박 활동 데이터 없음</b><br>cobak.py 실행 후 표시됩니다.</div>`;
    return;
  }
  const t = COBAK.totals || {};
  const tag = document.getElementById('cobakTag');
  if (tag && COBAK.source_url) tag.href = COBAK.source_url;

  cardsBox.innerHTML = [
    {label:'총 게시글', val:t.posts},
    {label:'총 뷰',     val:t.views},
    {label:'총 추천',   val:t.recommend},
    {label:'총 댓글',   val:t.comments},
  ].map(c=>`<div class="card"><div class="label">${c.label}</div><div class="value">${fmt(c.val||0)}</div></div>`).join('');

  const posts = (COBAK.posts || []).filter(p => p.date);
  const monthsEl = document.getElementById('cobakMonths');
  const pager    = document.getElementById('cobakPager');
  const label    = document.getElementById('cobakMonthLabel');
  if (!posts.length) {
    body.innerHTML = `<tr><td class="l" colspan="6" style="text-align:center;color:var(--ink-300);padding:24px;">게시글 없음</td></tr>`;
    return;
  }
  // 월 탭(오래된 달 → 최근 달) · 기본 = 최근 달 · 5개씩 페이지
  const byMonth = {};
  for (const p of posts) (byMonth[p.date.slice(0,7)] = byMonth[p.date.slice(0,7)] || []).push(p);
  const months = Object.keys(byMonth).sort();
  const latestYear = months[months.length-1].slice(0,4);
  const row = p => `
      <tr>
        <td class="l"><a class="post" href="${p.url}" target="_blank" rel="noopener">${esc(p.title)}</a></td>
        <td>${(p.date||'').slice(5)}</td>
        <td>${p.time||''}</td>
        <td>${fmt(p.views)}</td>
        <td>${fmt(p.recommend)}</td>
        <td>${fmt(p.comments)}</td>
      </tr>`;
  function show(m){
    monthsEl.querySelectorAll('.tab').forEach(b => b.classList.toggle('active', b.dataset.m === m));
    label.textContent = `${m.slice(0,4)}년 ${Number(m.slice(5))}월`;
    const items = byMonth[m].slice().sort((a,b)=> ((b.date+(b.time||'')).localeCompare(a.date+(a.time||''))));
    paginate(body, pager, items, 5, row);
  }
  monthsEl.innerHTML = months.map(m =>
    `<button type="button" class="tab" data-m="${m}">${Number(m.slice(5))}월<span class="sub">${m.slice(0,4)!==latestYear ? m.slice(0,4)+' · ' : ''}${byMonth[m].length}건</span></button>`).join('');
  monthsEl.querySelectorAll('.tab').forEach(b => b.addEventListener('click', () => show(b.dataset.m)));
  show(months[months.length-1]);
})();

// ---------- 인증 게이트 + 접속 로그(마스터) ----------
(function(){
  const body      = document.body;
  const overlay   = document.getElementById('authOverlay');
  const form      = document.getElementById('authForm');
  const userInput = document.getElementById('authUser');
  const passInput = document.getElementById('authPass');
  const errBox    = document.getElementById('authErr');
  const btn       = document.getElementById('authBtn');
  const chip      = document.getElementById('userChip');
  const logoutBtn = document.getElementById('logoutBtn');
  const accessSec = document.getElementById('sec-access');
  const profileSec = document.getElementById('sec-profile');
  let pingTimer = null, logTimer = null;

  const kstDate = ts => new Date(ts).toLocaleDateString('ko-KR',{timeZone:'Asia/Seoul',month:'2-digit',day:'2-digit'});
  const kstTime = ts => new Date(ts).toLocaleTimeString('ko-KR',{timeZone:'Asia/Seoul',hour:'2-digit',minute:'2-digit',hour12:false});

  function ping(){ fetch('/api/ping',{method:'POST'}).catch(()=>{}); }

  function setChip(name, role){
    chip.querySelector('.who').innerHTML = `<b>${esc(name)}</b>${role==='master'?' · 마스터':''}`;
  }

  function unlock(name, role, nameChanged){
    body.classList.remove('auth-lock');
    overlay.setAttribute('hidden','');
    setChip(name, role);
    chip.removeAttribute('hidden');
    window.dispatchEvent(new Event('resize'));      // 차트 크기 재계산
    ping();
    pingTimer = setInterval(ping, 5*60*1000);        // 사용 중 5분마다 핑
    if (role === 'master'){
      profileSec.setAttribute('hidden','');
      accessSec.removeAttribute('hidden');
      loadLogs();
      logTimer = setInterval(loadLogs, 60*1000);     // 로그 1분마다 자동 갱신
    } else {
      accessSec.setAttribute('hidden','');
      profileSec.removeAttribute('hidden');
      initProfile(name, role, !!nameChanged);
    }
  }

  // ----- 내 계정(일반 계정): 이름 1회 변경 + 비밀번호 자유 변경 -----
  function initProfile(name, role, nameChanged){
    const nameIn = document.getElementById('profName');
    const nameBtn = document.getElementById('profNameBtn');
    const nameHint = document.getElementById('profNameHint');
    const nameMsg = document.getElementById('profNameMsg');
    const passIn = document.getElementById('profPass');
    const passBtn = document.getElementById('profPassBtn');
    const passMsg = document.getElementById('profPassMsg');
    nameIn.value = name;
    if (nameChanged){
      nameIn.disabled = true; nameBtn.disabled = true;
      nameHint.textContent = '(이미 변경됨 — 더 이상 못 바꿈)';
    }
    nameBtn.onclick = async ()=>{
      const nm = (nameIn.value||'').trim();
      nameMsg.className='prof-msg'; nameMsg.textContent='';
      if (!nm || nm===name){ nameMsg.className='prof-msg err'; nameMsg.textContent='새 이름을 입력하세요.'; return; }
      if (!confirm(`계정 이름을 "${nm}" 으로 변경할까요?\n이름은 한 번만 바꿀 수 있고, 다음 로그인부터 새 이름을 사용합니다.`)) return;
      nameBtn.disabled=true;
      try{
        const r = await fetch('/api/profile',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({newName:nm})});
        const d = await r.json().catch(()=>({}));
        if (r.ok && d.ok && d.changedName){
          nameMsg.className='prof-msg ok'; nameMsg.textContent='이름이 변경됐어요. 다음 로그인부터 새 이름을 사용하세요.';
          nameIn.value=d.name; nameIn.disabled=true; nameBtn.disabled=true; nameHint.textContent='(이미 변경됨 — 더 이상 못 바꿈)';
          setChip(d.name, role);
        } else { nameMsg.className='prof-msg err'; nameMsg.textContent=d.error||'변경에 실패했습니다.'; nameBtn.disabled=false; }
      }catch(e){ nameMsg.className='prof-msg err'; nameMsg.textContent='서버 오류 — 잠시 후 다시 시도하세요.'; nameBtn.disabled=false; }
    };
    passBtn.onclick = async ()=>{
      const pw = passIn.value||'';
      passMsg.className='prof-msg'; passMsg.textContent='';
      if (!pw){ passMsg.className='prof-msg err'; passMsg.textContent='새 비밀번호를 입력하세요.'; return; }
      passBtn.disabled=true;
      try{
        const r = await fetch('/api/profile',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({newPassword:pw})});
        const d = await r.json().catch(()=>({}));
        if (r.ok && d.ok && d.changedPassword){ passMsg.className='prof-msg ok'; passMsg.textContent='비밀번호가 변경됐어요. 다음 로그인부터 적용됩니다.'; passIn.value=''; }
        else { passMsg.className='prof-msg err'; passMsg.textContent=d.error||'변경에 실패했습니다.'; }
      }catch(e){ passMsg.className='prof-msg err'; passMsg.textContent='서버 오류 — 잠시 후 다시 시도하세요.'; }
      finally{ passBtn.disabled=false; }
    };
  }

  // 세션 복원 — 이미 로그인돼 있으면 바로 통과
  fetch('/api/me').then(r=> r.ok ? r.json() : null).then(d=>{
    if (d && d.ok) unlock(d.name||d.user, d.role, d.nameChanged);
    else userInput.focus();
  }).catch(()=> userInput.focus());

  form.addEventListener('submit', async (e)=>{
    e.preventDefault();
    errBox.textContent=''; btn.disabled=true; btn.textContent='확인 중…';
    try{
      const res = await fetch('/api/login',{
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ username:userInput.value, password:passInput.value })
      });
      const d = await res.json().catch(()=>({}));
      if (res.ok && d.ok){ unlock(d.name||d.user, d.role, d.nameChanged); }
      else { errBox.textContent = d.error || '로그인에 실패했습니다.'; passInput.value=''; passInput.focus(); }
    }catch(err){ errBox.textContent='서버 오류 — 잠시 후 다시 시도하세요.'; }
    finally{ btn.disabled=false; btn.textContent='로그인'; }
  });

  logoutBtn.addEventListener('click', async ()=>{
    if (pingTimer) clearInterval(pingTimer);
    if (logTimer) clearInterval(logTimer);
    try{ await fetch('/api/logout',{method:'POST'}); }catch(e){}
    location.reload();
  });

  let logFilter = '__all';   // 선택된 계정 탭(자동 갱신해도 유지)
  async function loadLogs(){
    const tabsBox = document.getElementById('accessTabs');
    const summary = document.getElementById('accessSummary');
    const tbody   = document.getElementById('accessLog');
    const pager   = document.getElementById('accessPager');
    const foot    = document.getElementById('accessFoot');
    let d;
    try{
      const r = await fetch('/api/logs');
      d = await r.json();
      if (!r.ok || !d.ok){ foot.textContent='로그를 불러올 수 없습니다.'; return; }
    }catch(e){ foot.textContent='로그 요청 실패.'; return; }

    if (d.kvReady === false){
      tabsBox.innerHTML=''; summary.innerHTML='';
      tbody.innerHTML = `<tr><td class="l" colspan="5" style="text-align:center;color:var(--ink-300);padding:24px;">로그 저장소(KV) 미연동 — 연결 후 표시됩니다.</td></tr>`;
      pager.innerHTML=''; foot.textContent=''; return;
    }

    const users = d.users || [];      // 모든 계정(0건 포함), 접속 횟수 순
    const evs   = d.events || [];
    const daily = d.daily || [];      // 계정×날짜(KST) 집계, 최신일 먼저
    const total = d.total || evs.length;
    if (!users.some(u=>u.user===logFilter)) logFilter = '__all';   // 사라진 계정 선택 방어

    // 계정 카드: 최근 접속 시각 한 줄 + 총 로그인 수
    const cards = document.getElementById('accessCards');
    if (cards) cards.innerHTML = users.map(u => `
      <div class="card">
        <div class="label">${esc(u.user)}${u.role==='master'?' · 마스터':''}</div>
        <div class="value" style="font-size:18px;">${u.last ? `${kstDate(u.last)} ${kstTime(u.last)}` : '—'}</div>
        <div class="delta flat"><span style="color:var(--ink-300);font-weight:400;">${u.last ? '최근 접속' : '접속 기록 없음'} · 로그인 ${fmt(u.logins)}회</span></div>
      </div>`).join('');

    // 탭: 전체 + 계정별 (계정 추가 시 자동 생성)
    tabsBox.innerHTML = [`<button class="tab" data-u="__all">전체 ${fmt(total)}</button>`]
      .concat(users.map(u=>`<button class="tab" data-u="${esc(u.user)}">${esc(u.user)}${u.role==='master'?' · 마스터':''} ${fmt(u.total)}</button>`))
      .join('');

    const rowFn = r => `
      <tr>
        <td class="l">${r.date}</td>
        <td class="l">${esc(r.user)}</td>
        <td>${fmt(r.logins)}회</td>
        <td>${fmt(r.pings)}회</td>
        <td>${r.last ? kstTime(r.last) : '—'}</td>
      </tr>`;

    function apply(user){
      logFilter = user;
      tabsBox.querySelectorAll('.tab').forEach(x=>x.classList.toggle('active', x.dataset.u===user));
      if (user==='__all'){
        summary.innerHTML = `<b style="color:var(--forest-700);">전체</b> · 총 ${fmt(total)}건 · 계정 ${fmt(users.length)}개`;
      } else {
        const u = users.find(x=>x.user===user);
        summary.innerHTML = (u && u.total)
          ? `<b style="color:var(--forest-700);">${esc(u.user)}</b>${u.role==='master'?' · 마스터':''} · 총 ${fmt(u.total)} · 로그인 ${fmt(u.logins)} · 사용 ${fmt(u.pings)} · 최근 ${kstDate(u.last)} ${kstTime(u.last)}`
          : `<b style="color:var(--forest-700);">${esc(user)}</b> · 접속 기록 없음`;
      }
      const items = user==='__all' ? daily : daily.filter(r=>r.user===user);
      if (items.length) paginate(tbody, pager, items, 10, rowFn);
      else { tbody.innerHTML = `<tr><td class="l" colspan="5" style="text-align:center;color:var(--ink-300);padding:24px;">기록 없음</td></tr>`; pager.innerHTML=''; }
    }
    tabsBox.onclick = ev => { const t = ev.target.closest('.tab'); if(!t) return; apply(t.dataset.u); };
    apply(logFilter);
    foot.textContent = `총 이벤트 ${fmt(total)}건 · 일자별 ${fmt(daily.length)}행 · 60초마다 자동 갱신`;
  }
  document.getElementById('logRefresh').addEventListener('click', loadLogs);
})();


</script>

<script>
/* 로컬 갱신 버튼 — server.py(로컬 서버)로 열었을 때만 동작.
   Vercel 등 정적 호스팅에서는 버튼을 숨겨 죽은 버튼이 보이지 않게 함. */
(function(){
  var isLocal = ["localhost","127.0.0.1","::1"].indexOf(location.hostname) !== -1;
  var btn = document.getElementById("refreshBtn");
  var toast = document.getElementById("refreshToast");
  if (!isLocal || !btn) return;            // 로컬 서버로 연 경우에만 노출
  btn.hidden = false;

  function showToast(msg, isErr){
    toast.textContent = msg;
    toast.classList.toggle("err", !!isErr);
    toast.hidden = false;
  }
  function hideToast(delay){ setTimeout(function(){ toast.hidden = true; }, delay); }

  btn.addEventListener("click", function(){
    btn.disabled = true;
    var label = btn.textContent;
    btn.textContent = "수집 중…";
    showToast("텔레그램에서 최신 데이터를 수집하고 있습니다…\n(채널·그룹 규모에 따라 30초~2분 소요)", false);
    fetch("/refresh", { method: "POST" })
      .then(function(r){ return r.json().then(function(j){ return { ok: r.ok, body: j }; }); })
      .then(function(res){
        if (res.ok && res.body.ok) {
          showToast("갱신 완료 — 새 데이터로 다시 불러옵니다.", false);
          hideToast(1200);
          setTimeout(function(){ location.reload(); }, 900);
        } else {
          showToast("갱신 실패:\n" + (res.body.error || "알 수 없는 오류"), true);
          btn.disabled = false; btn.textContent = label;
          hideToast(8000);
        }
      })
      .catch(function(e){
        showToast("서버에 연결할 수 없습니다.\nserver.py 가 실행 중인지 확인하세요.\n" + e, true);
        btn.disabled = false; btn.textContent = label;
        hideToast(8000);
      });
  });
})();
</script>
</body>
</html>"""


PLACEHOLDER = """<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>__CHNAME__ · Kangtearoom Data</title><link rel="icon" type="image/png" href="__FAVICON__">
<style>
  body { margin:0; font-family:-apple-system,'Pretendard','Noto Sans KR',sans-serif; background:#F3F5F1; color:#0B3A2C; }
  .rail { background:#0C3F30; color:rgba(255,255,255,.62); font-family:'Geist Mono',monospace; font-size:11px; letter-spacing:.18em; text-transform:uppercase; }
  .rail-in { max-width:1180px; margin:0 auto; padding:9px 24px; display:flex; align-items:center; gap:14px; }
  .chnav { display:inline-flex; border:1px solid rgba(255,255,255,.28); }
  .chnav a { font-size:11px; letter-spacing:.04em; text-transform:none; color:rgba(255,255,255,.72); text-decoration:none; padding:4px 11px; }
  .chnav a + a { border-left:1px solid rgba(255,255,255,.28); }
  .chnav a.active { color:#0C3F30; background:#14B87D; font-weight:600; }
  main { max-width:640px; margin:80px auto; padding:0 24px; text-align:center; }
  .tag { font-family:'Geist Mono',monospace; font-size:11px; letter-spacing:.18em; text-transform:uppercase; color:#5B6B62; }
  h1 { font-size:22px; margin:12px 0 10px; }
  p { color:#5B6B62; line-height:1.7; font-size:14px; }
</style></head>
<body>
  <div class="rail"><div class="rail-in"><span>KANGTEAROOM DATA</span><nav class="chnav">__NAV__</nav></div></div>
  <main>
    <div class="tag">Preparing</div>
    <h1>__CHNAME__ — 데이터 준비 중</h1>
    <p>__REASON__</p>
  </main>
</body></html>"""


def nav_html(active_key):
    """헤더 채널 토글 버튼. 사이트 경로 기준 절대 링크(/, /mirae/)."""
    parts = []
    for c in CHANNELS:
        href = "/" + (c["path"].strip("/") + "/" if c["path"] else "")
        cls = ' class="active" aria-current="page"' if c["key"] == active_key else ""
        parts.append(f'<a href="{href}"{cls}>{c["name"]}</a>')
    return "".join(parts)


def build_channel(ch, favicon):
    key = ch["key"]
    d = data_dir(key)
    out = d / "dashboard.html"
    ch_user = (ch.get("channel") or "").lstrip("@")
    gr_user = (ch.get("group") or "").lstrip("@")
    nav = nav_html(key)

    src = d / "daily_summary.csv"
    rows = load_summary(src) if src.exists() else []
    if not rows:
        reason = ("channels.py 에 채널 @username 을 입력하면 다음 갱신부터 수집이 시작됩니다."
                  if not ch.get("channel") else
                  "아직 수집된 데이터가 없습니다. 다음 자동 갱신(30분 주기) 후 표시됩니다.")
        out.write_text(PLACEHOLDER.replace("__CHNAME__", ch["name"]).replace("__NAV__", nav)
                       .replace("__FAVICON__", favicon).replace("__REASON__", reason), encoding="utf-8")
        print(f"[{ch['name']}] 데이터 없음 → 준비 중 페이지 생성 ({out})")
        return "placeholder"

    posts = load_latest_posts(d)
    quota = update_quota(posts, d, ch.get("quota"))
    posts_out = [{k: v for k, v in p.items() if k != "iso"} for p in posts]
    official = load_json(d, "broadcast_stats.json", {"available": False})
    members = load_json(d, "group_top_members.json", []) if gr_user else []
    joinleave = load_json(d, "join_leave.json", {"available": False})
    joinleave["months"] = sorted(p.stem[len("join_leave_"):] for p in d.glob("join_leave_20*.json"))
    jl_base = "/" + (ch["path"].strip("/") + "/" if ch["path"] else "") + "jl/"
    joinleave_gr = load_json(d, "join_leave_group.json", {"available": False}) if gr_user else {"available": False}
    cobak = load_json(d, "cobak_stats.json", {"available": False}) if ch.get("cobak") else {"available": False}

    rail_mid = (f'<a class="chlink" href="https://t.me/{ch_user}" target="_blank" rel="noopener">@{ch_user}</a>'
                if ch_user else "")
    if gr_user:
        rail_mid += f' · <a class="chlink" href="https://t.me/{gr_user}" target="_blank" rel="noopener">@{gr_user}</a>'

    html = (TEMPLATE
            .replace("__FAVICON__", favicon)
            .replace("__GENERATED__", datetime.now(KST).strftime("%Y-%m-%d %H:%M"))
            .replace("__CHNAME__", ch["name"])
            .replace("__NAV__", nav)
            .replace("__RAILMID__", rail_mid)
            .replace("__JLBASE__", jl_base)
            .replace("__CHUSER__", ch_user)
            .replace("__GRUSER__", gr_user)
            .replace("__HAS_GROUP__", "true" if gr_user else "false")
            .replace("__HAS_COBAK__", "true" if ch.get("cobak") else "false")
            .replace("__DATA__", json.dumps(rows, ensure_ascii=False))
            .replace("__POSTS__", json.dumps(posts_out, ensure_ascii=False))
            .replace("__QUOTA__", json.dumps(quota, ensure_ascii=False))
            .replace("__OFFICIAL__", json.dumps(official, ensure_ascii=False))
            .replace("__MEMBERS__", json.dumps(members, ensure_ascii=False))
            .replace("__JOINLEAVE__", json.dumps(joinleave, ensure_ascii=False))
            .replace("__JOINLEAVE_GR__", json.dumps(joinleave_gr, ensure_ascii=False))
            .replace("__COBAK__", json.dumps(cobak, ensure_ascii=False)))

    out.write_text(html, encoding="utf-8")
    print(f"[{ch['name']}] 대시보드 생성 → {out}")
    print(f"  요약 {len(rows)}일 · 포스트 {len(posts)}건 · "
          f"공식통계 {'O' if official.get('available') else 'X'} · "
          f"멤버 {len(members)} · 쿼터 {quota.get('mode', '-')}")
    return "ok"


def main():
    migrate_legacy_layout()
    only = None
    if len(sys.argv) > 2 and sys.argv[1] == "--only":
        only = sys.argv[2]
    logo = ROOT / "assets" / "kang_logo.png"
    favicon = ("data:image/png;base64," + base64.b64encode(logo.read_bytes()).decode()) if logo.exists() else ""

    results = {}
    for ch in CHANNELS:
        if only and ch["key"] != only:
            continue
        results[ch["key"]] = build_channel(ch, favicon)

    # 주 채널(첫 번째)에 실제 데이터가 없으면 빌드 실패 — update.sh 게이트가 배포를 막는다.
    primary = CHANNELS[0]["key"]
    if results.get(primary, "ok") != "ok":
        print(f"주 채널({primary}) 데이터가 없습니다 — 빌드 실패", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
