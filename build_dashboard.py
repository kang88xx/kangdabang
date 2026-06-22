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
    python build_dashboard.py                  # data/daily_summary.csv 사용
    python build_dashboard.py data/sample_summary.csv

결과: data/dashboard.html
"""
import csv
import glob
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))   # 포스트 시각을 한국시간으로 표시

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else DATA_DIR / "daily_summary.csv"
OUT = DATA_DIR / "dashboard.html"

# 채널/그룹 username (포스트 링크 생성용). config.py 없으면 기본값 사용.
try:
    from config import CHANNEL, GROUP
    CH_USER = CHANNEL.lstrip("@")
    GR_USER = GROUP.lstrip("@")
except Exception:
    CH_USER, GR_USER = "kang_tearoom", "kangtearoom_chat"


def load_summary(path):
    with path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k, v in r.items():
            if k != "date":
                r[k] = int(v) if (v not in (None, "")) else None
    return rows


def load_latest_posts():
    """가장 최근 channel_posts_*.csv 를 읽어 포스트 리스트 반환 (조회수>0 만)."""
    files = sorted(glob.glob(str(DATA_DIR / "channel_posts_*.csv")))
    if not files:
        return []
    posts = []
    with open(files[-1], encoding="utf-8") as f:
        for r in csv.DictReader(f):
            views = int(r.get("views") or 0)
            if views <= 0:                       # 광고/서비스 메시지 제외
                continue
            try:
                _dt = datetime.fromisoformat(r["date"]).astimezone(KST)
                _d, _t = _dt.strftime("%Y-%m-%d"), _dt.strftime("%H:%M")
            except Exception:
                _d, _t = r["date"][:10], r["date"][11:16]
            posts.append({
                "id": int(r["id"]),
                "date": _d,
                "time": _t,
                "views": views,
                "forwards": int(r.get("forwards") or 0),
                "replies": int(r.get("replies") or 0),
                "text": (r.get("text") or "").replace("**", "").strip()[:70] or "(미리보기 없음)",
            })
    return posts


def load_json(name, default):
    p = DATA_DIR / name
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default


TEMPLATE = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>캉 티룸 · 텔레그램 통계</title>
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
    --info:#2E84AE; --chart-alt:#6E63D6;
    --ink-900:#14201B; --ink-700:#34433D; --ink-500:#5F6C65; --ink-300:#9BA7A0;
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

  /* (헤더 cover 제거됨 — 상단 정보는 .rail 로 통합) */

  main { max-width:1180px; margin:0 auto; padding:40px 64px 0; }
  section { margin-bottom:64px; scroll-margin-top:58px; }
  #topMembers { scroll-margin-top:58px; }
  .basis-note { font-family:'Geist Mono',monospace; font-size:11.5px; line-height:1.5; letter-spacing:.01em;
    color:var(--ink-500); background:var(--white); border:1px solid var(--line); border-left:3px solid var(--signal);
    padding:11px 16px; margin-bottom:40px; }
  .basis-note b { color:var(--forest-700); font-weight:600; }
  .sec-head { display:flex; align-items:baseline; gap:18px;
    border-top:1.5px solid var(--ink-900); padding-top:16px; margin-bottom:28px; }
  .sec-head .num { font-family:'Geist Mono',monospace; font-size:14px; font-weight:500; color:var(--signal); }
  .sec-head h2 { margin:6px 0 0; font-weight:500; font-size:26px; line-height:1.1; letter-spacing:-.022em; }
  .group-head .num { color:var(--info); }

  /* domain tag */
  .dtag { display:inline-block; font-family:'Geist Mono',monospace; font-size:10.5px;
    letter-spacing:.12em; text-transform:uppercase; padding:3px 8px; border:1px solid var(--line);
    color:var(--ink-500); margin-left:auto; align-self:center; }
  .dtag.ch { color:var(--forest-500); border-color:var(--forest-300); }
  .dtag.gr { color:var(--info); border-color:#BcdAE8; }

  /* KPI CARDS */
  .cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:16px; }
  .card { background:var(--white); border:1px solid var(--line); padding:22px; }
  .card .label { font-size:13px; color:var(--ink-500); }
  .card .value { font-family:'Geist Mono',monospace; font-variant-numeric:tabular-nums;
    font-size:32px; font-weight:400; letter-spacing:-.02em; color:var(--ink-900); margin:10px 0 6px; }
  .card .delta { font-family:'Geist Mono',monospace; font-size:12.5px; font-weight:500; }
  .up { color:var(--positive); } .down { color:var(--negative); } .flat { color:var(--ink-300); }
  .cards-tight { gap:12px; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); }
  .cards-tight .card { padding:15px 14px; }
  .cards-tight .label { font-size:11.5px; line-height:1.3; }
  .cards-tight .value { font-size:21px; margin:8px 0 0; word-break:break-word; }
  .datesel { font-family:'Geist Mono',monospace; font-size:12px; text-transform:none; letter-spacing:0;
    color:var(--ink-900); background:var(--white); border:1px solid var(--line); padding:5px 10px; cursor:pointer; }
  .datesel:hover { border-color:var(--forest-300); }
  .scroll-link { cursor:pointer; border-bottom:1px dotted var(--ink-300); padding-bottom:1px; transition:color .15s,border-color .15s; }
  .scroll-link:hover { color:var(--forest-500); border-color:var(--forest-500); }

  /* DETAIL BUTTON + MODAL */
  .card .detail-btn { margin-top:12px; font-family:'Geist Mono',monospace; font-size:10.5px;
    letter-spacing:.08em; text-transform:uppercase; color:var(--forest-500); background:none;
    border:1px solid var(--line); padding:5px 10px; cursor:pointer; transition:background .15s,color .15s,border-color .15s; }
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
  .modal-body { overflow-y:auto; }
  .modal-body thead th { position:sticky; top:0; background:var(--white); z-index:1; }

  /* CHARTS */
  .grid { display:grid; grid-template-columns:1fr 1fr; gap:16px; }
  .chart-box { background:var(--white); border:1px solid var(--line); padding:24px; min-width:0; }
  .chart-box .eyebrow { margin-bottom:16px; }
  canvas { max-height:236px; max-width:100%; }

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
  table { width:100%; border-collapse:collapse; font-size:13.5px; }
  thead th { font-family:'Geist Mono',monospace; font-size:11px; letter-spacing:.1em;
    text-transform:uppercase; color:var(--ink-500); text-align:right; padding:14px 16px;
    border-bottom:1.5px solid var(--ink-900); white-space:nowrap; }
  thead th.l { text-align:left; }
  tbody td { padding:13px 16px; border-bottom:1px solid var(--line-soft); text-align:right;
    font-family:'Geist Mono',monospace; font-variant-numeric:tabular-nums; color:var(--ink-700); }
  tbody td.l { text-align:left; font-family:'Pretendard',sans-serif; }
  tbody tr:hover { background:var(--paper); }
  tbody td a.post { color:var(--ink-900); text-decoration:none; font-weight:500;
    border-bottom:1px solid var(--forest-300); padding-bottom:1px; }
  tbody td a.post:hover { color:var(--forest-500); border-color:var(--signal); }
  .rank { display:inline-flex; align-items:center; justify-content:center; width:22px; height:22px;
    background:var(--forest-900); color:#fff; font-family:'Geist Mono',monospace; font-size:11px;
    font-weight:600; margin-right:10px; }
  .rank.t1 { background:var(--signal); } .rank.t2 { background:var(--forest-500); }
  .badge { font-family:'Geist Mono',monospace; font-size:11px; padding:2px 7px;
    border:1px solid var(--line); color:var(--ink-500); }

  /* PAGINATION */
  .pager { display:flex; flex-wrap:wrap; gap:6px; margin-top:16px; justify-content:center; }
  .pager button { font-family:'Geist Mono',monospace; font-size:12px; min-width:34px; padding:6px 10px;
    border:1px solid var(--line); background:var(--white); color:var(--ink-700); cursor:pointer;
    transition:background .12s,color .12s,border-color .12s; }
  .pager button:hover:not(:disabled) { border-color:var(--forest-300); color:var(--forest-700); }
  .pager button.active { background:var(--forest-900); color:#fff; border-color:var(--forest-900); }
  .pager button:disabled { opacity:.35; cursor:default; }
  .pager .gap { border:none; background:none; cursor:default; color:var(--ink-300); min-width:18px; padding:6px 2px; }
  .tabs { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:14px; }
  .tab { font-family:'Geist Mono',monospace; font-size:12px; padding:7px 14px; border:1px solid var(--line);
    background:var(--white); color:var(--ink-500); cursor:pointer; transition:background .12s,color .12s,border-color .12s; }
  .tab:hover { border-color:var(--forest-300); }
  .tab.active { background:var(--forest-900); color:#fff; border-color:var(--forest-900); }
  .jl-tag { display:inline-block; font-family:'Geist Mono',monospace; font-size:11px; padding:2px 8px; font-weight:600; }
  .jl-tag.join { color:var(--positive); border:1px solid #BFE0CF; }
  .jl-tag.left { color:var(--negative); border:1px solid #F0C9CD; }

  /* 공유처 (public forwards) — 표 안 펼침 */
  details.fwd { font-family:'Geist Mono',monospace; }
  details.fwd > summary { cursor:pointer; list-style:none; color:var(--chart-alt);
    font-size:12px; font-weight:500; white-space:nowrap; }
  details.fwd > summary::-webkit-details-marker { display:none; }
  details.fwd > summary::after { content:' ▾'; color:var(--ink-300); }
  details.fwd[open] > summary::after { content:' ▴'; }
  .fwdlist { margin-top:8px; display:flex; flex-direction:column; gap:4px;
    text-align:left; max-width:280px; margin-left:auto; }
  .fwdlist .row { display:flex; justify-content:space-between; gap:12px; font-size:11.5px;
    padding:3px 8px; background:var(--paper); border:1px solid var(--line-soft); }
  .fwdlist .row span:first-child { color:var(--ink-700); overflow:hidden;
    text-overflow:ellipsis; white-space:nowrap; }
  .fwdlist .row span:last-child { color:var(--chart-alt); font-variant-numeric:tabular-nums; }
  .fwd-none { color:var(--ink-300); }

  /* placeholder / empty state */
  .empty { background:var(--white); border:1px dashed var(--line); padding:28px 24px;
    text-align:center; color:var(--ink-500); font-size:14px; line-height:1.6; }
  .empty b { color:var(--ink-900); }
  .empty .tag { display:inline-block; font-family:'Geist Mono',monospace; font-size:11px;
    letter-spacing:.1em; text-transform:uppercase; color:var(--negative); margin-bottom:10px; }

  footer { border-top:1.5px solid var(--ink-900); margin-top:8px;
    padding:24px 64px 56px; display:flex; align-items:center; justify-content:space-between;
    flex-wrap:wrap; gap:16px; max-width:1180px; margin-left:auto; margin-right:auto; }
  footer .note { font-family:'Geist Mono',monospace; font-size:11px; letter-spacing:.14em;
    text-transform:uppercase; color:var(--ink-300); }
  @media (max-width:760px) { .grid { grid-template-columns:1fr; }
    .note-box dl { grid-template-columns:1fr; gap:2px 0; }
    .note-box dt { margin-top:8px; }
    .rail-in, main, footer { padding-left:24px; padding-right:24px; }
    /* 상단바: 모바일에서 세로 스택 → 오버플로 방지 */
    .rail-in { grid-template-columns:1fr; justify-items:center; gap:3px; padding-top:7px; padding-bottom:7px; }
    .rail .mid { white-space:normal; text-align:center; letter-spacing:.02em; }
    .rail .end { justify-content:center; }
    .cards-tight { grid-template-columns:repeat(2,minmax(0,1fr)); }
    .basis-note { line-height:1.6; }
    .eyebrow, .rail, .dtag, .badge { letter-spacing:.06em; } }
</style>
</head>
<body>

  <div class="rail">
    <div class="rail-in">
      <span>KANGTEAROOM DATA</span>
      <span class="mid"><a class="chlink" href="https://t.me/__CHUSER__" target="_blank" rel="noopener">@__CHUSER__</a> · <a class="chlink" href="https://t.me/__GRUSER__" target="_blank" rel="noopener">@__GRUSER__</a></span>
      <span class="end"><span id="lastUpdated">__END__</span><button id="refreshBtn" class="refresh-btn" hidden>🔄 지금 갱신</button></span>
    </div>
  </div>
  <div id="refreshToast" class="refresh-toast" role="status" aria-live="polite" hidden></div>

  <main>

    <div class="basis-note">데이터 기준 · <b>한국시간(KST) 오전 9시 ~ 다음날 오전 9시 = 1일(24시간)</b> · 매일 09:00에 새 날 집계 시작(텔레그램 공식 통계 UTC 일 버킷 기준) · 6시간마다 자동 갱신(09·15·21·03시) · 오늘 값은 9시부터 현재까지 누적(진행 중)</div>

    <!-- 01 OVERVIEW -->
    <section>
      <div class="sec-head">
        <div><div class="eyebrow">Overview</div><h2>오늘의 핵심 지표</h2></div>
      </div>
      <div class="cards" id="cards"></div>
    </section>

    <!-- 02 CHANNEL 성장 -->
    <section id="sec-subs">
      <div class="sec-head">
        <div><div class="eyebrow">Channel · Growth</div><h2>채널 — 구독자 증감</h2></div>
        <span class="dtag ch">@__CHUSER__</span>
      </div>

      <div class="grid">
        <div class="chart-box"><div class="eyebrow">구독자 추이</div><canvas id="subs"></canvas></div>
        <div class="chart-box"><div class="eyebrow">들어옴 · 나감 (일별)</div><canvas id="subsNet"></canvas></div>
      </div>
    </section>

    <!-- 02b 유입 · 이탈 인원 -->
    <section>
      <div class="sec-head">
        <div><div class="eyebrow">Channel · Members</div><h2>채널 — 유입 · 이탈 인원</h2></div>
        <span class="dtag ch">@__CHUSER__</span>
      </div>
      <div id="joinLeave"></div>
    </section>

    <!-- 03 CHANNEL 조회 -->
    <section id="sec-reach">
      <div class="sec-head">
        <div><div class="eyebrow">Channel · Reach</div><h2>채널 — 조회수 · 도달 · 참여</h2></div>
        <span class="dtag ch">@__CHUSER__</span>
      </div>

      <div class="cards" id="reachCards" style="margin-bottom:16px;"></div>
      <div class="grid">
        <div class="chart-box"><div class="eyebrow">일일 조회수</div><canvas id="views"></canvas></div>
        <div class="chart-box"><div class="eyebrow">공유 · 댓글 (인게이지먼트)</div><canvas id="engage"></canvas></div>
      </div>
    </section>

    <!-- 04 CHANNEL 포스트 -->
    <section>
      <div class="sec-head">
        <div><div class="eyebrow">Channel · Posts</div><h2>채널 — 포스트별 성과</h2></div>
        <span class="dtag ch">@__CHUSER__</span>
      </div>
      <div class="eyebrow" style="margin-bottom:12px;">TOP 게시물 — 조회수 순 (제목 클릭 시 텔레그램에서 열림 · 공유처 펼치면 재공유 채널·외부 조회수)</div>
      <div class="table-wrap" style="margin-bottom:28px;">
        <table><thead><tr>
          <th class="l">#  게시물</th><th>날짜</th><th>조회수</th><th>도달률</th><th>공유</th><th>공유처 · 외부조회</th><th>댓글</th><th>ER</th>
        </tr></thead><tbody id="topPosts"></tbody></table>
      </div>
      <div class="eyebrow" style="margin-bottom:12px;display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
        <span>일별 게시물 — 날짜별 보기</span>
        <select id="postDate" class="datesel"></select>
      </div>
      <div class="table-wrap">
        <table><thead><tr>
          <th class="l">게시물</th><th>시각</th><th>조회수</th><th>도달률</th><th>공유</th><th>공유처 · 외부조회</th><th>댓글</th><th>ER</th>
        </tr></thead><tbody id="allPosts"></tbody></table>
      </div>
      <div class="pager" id="allPostsPager"></div>
    </section>

    <!-- 05 CHANNEL 공식 통계 -->
    <section>
      <div class="sec-head">
        <div><div class="eyebrow">Channel · Official</div><h2>채널 — 공식 통계</h2></div>
        <span class="dtag ch">@__CHUSER__</span>
      </div>
      <div class="note-box">
        <h4><span class="ico">◆</span> 텔레그램 공식 통계 — <code>stats.GetBroadcastStats</code></h4>
        <dl>
          <dt>제공 데이터</dt>
          <dd>구독자 성장 그래프, <b>조회 출처</b>(채널/검색/공유/링크), 알림 끈 비율(mute), 시간대별 조회, 게시물별 노출 등 — 텔레그램이 직접 집계한 값입니다.</dd>
          <dt>이용 조건</dt>
          <dd>채널 규모가 <b>일정 이상(보통 구독자 50~500+)</b>이어야 API가 데이터를 반환합니다. 그 미만이면 “통계 미생성” 상태입니다.</dd>
          <dt>권한</dt>
          <dd>채널 <b>관리자</b> 계정으로만 호출 가능합니다.</dd>
        </dl>
      </div>
      <div id="officialStats"></div>
    </section>

    <!-- 06 GROUP -->
    <section id="sec-group">
      <div class="sec-head group-head">
        <div><div class="eyebrow">Group · Discussion</div><h2>그룹 — 토론 활동</h2></div>
        <span class="dtag gr">@__GRUSER__</span>
      </div>

      <div class="cards" id="grCards" style="margin-bottom:16px;"></div>
      <div class="grid" style="margin-bottom:16px;">
        <div class="chart-box"><div class="eyebrow">그룹 멤버 추이</div><canvas id="grMembers"></canvas></div>
        <div class="chart-box"><div class="eyebrow">멤버 일별 순증 · 순감</div><canvas id="grNet"></canvas></div>
        <div class="chart-box"><div class="eyebrow">메시지 · 활성 유저</div><canvas id="grActivity"></canvas></div>
      </div>
      <div id="topMembers"></div>
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

  <footer>
    <span class="note">본 자료는 내부 전용입니다 · 외부 유출 및 공유 금지</span>
  </footer>

<script>
const DATA     = __DATA__;
const POSTS    = __POSTS__;
const OFFICIAL = __OFFICIAL__;
const MEMBERS  = __MEMBERS__;

const FWDS     = __FWDS__;     // { msg_id: {count, ext_views, channels:[{title,views}]} }
const JOINLEAVE= __JOINLEAVE__;  // { available, events:[{date,kind,name,username,id}] }
const CH_USER  = "__CHUSER__";

const fmt  = n => Number(n).toLocaleString('ko-KR');
const pct  = n => (n*100).toFixed(1) + '%';
const esc  = s => { const d=document.createElement('div'); d.textContent=s; return d.innerHTML; };
const dates = DATA.map(r => r.date.slice(5));        // MM-DD
const last  = DATA[DATA.length-1], prev = DATA[DATA.length-2] || last;
const subsNow = last.ch_subscribers;

// ---------- 01 KPI 카드 ----------
const cards = [
  {label:'구독자', key:'ch_subscribers', dom:'채널', scroll:'sec-subs'},
  {label:'채널 조회수 (일)', key:'ch_views', dom:'채널', scroll:'sec-reach'},
  {label:'그룹 멤버', key:'gr_members', dom:'그룹', scroll:'sec-group'},
  {label:'그룹 메시지 (일)', key:'gr_messages', dom:'그룹', scroll:'sec-group'},
  {label:'그룹 활성 유저', key:'gr_active_users', dom:'그룹', scroll:'topMembers'},
];
document.getElementById('cards').innerHTML = cards.map(c => {
  const v = last[c.key], pv = prev[c.key];
  const d = (v==null||pv==null) ? null : v - pv;
  const cls = d==null?'flat':d>0?'up':d<0?'down':'flat', arrow = d==null?'—':d>0?'▲':d<0?'▼':'—';
  const deltaTxt = d==null ? '—' : `${arrow} ${fmt(Math.abs(d))} <span style="color:var(--ink-300);font-weight:400;">전일대비</span>`;
  return `<div class="card">
    <div class="label">${c.scroll ? `<a class="scroll-link" data-scroll="${c.scroll}" title="해당 섹션으로 이동">${c.label}</a>` : c.label} <span class="badge">${c.dom}</span></div>
    <div class="value">${v==null?'—':fmt(v)}</div>
    <div class="delta ${cls}">${deltaTxt}</div>
    <button class="detail-btn" data-key="${c.key}" data-label="${c.label}">📊 일자별 기록</button>
  </div>`;
}).join('');

// '그룹 활성 유저' 카드 라벨 클릭 → 활발한 멤버 표로 스크롤
document.addEventListener('click', e => {
  const s = e.target.closest('.scroll-link');
  if (s){ const t = document.getElementById(s.dataset.scroll); if (t) t.scrollIntoView({behavior:'smooth', block:'start'}); }
});

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
document.getElementById('reachCards').innerHTML = [
  {label:'도달률 (조회수÷구독자)', val:pct(reach)},
  {label:'참여율 ER ((공유+댓글)÷조회수)', val:pct(er)},
  {label:'오늘 공유', val:fmt(dFwd)},
  {label:'오늘 댓글', val:fmt(dRep)},
].map(c=>`<div class="card"><div class="label">${c.label}</div><div class="value">${c.val}</div></div>`).join('');

// ---------- 차트 공통 ----------
Chart.defaults.color = '#9BA7A0';
Chart.defaults.borderColor = '#EEF1EC';
Chart.defaults.font.family = "'Geist Mono', monospace";
Chart.defaults.font.size = 11;
const baseOpts = {
  responsive:true, maintainAspectRatio:false,
  plugins:{legend:{labels:{boxWidth:10,boxHeight:10,font:{size:11},color:'#5F6C65'}}},
  scales:{ y:{grid:{color:'#EEF1EC'},ticks:{color:'#9BA7A0'},border:{color:'#E3E7DF'}},
           x:{grid:{display:false},ticks:{color:'#9BA7A0'},border:{color:'#E3E7DF'}} }
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
line('engage',[L('공유','ch_forwards','#6E63D6'),L('댓글','ch_replies','#1F8A5B')]);

// 06 그룹 — KPI 카드(전일대비) + 추이 + 순증·순감
const grCards = [
  {label:'그룹 멤버', key:'gr_members'},
  {label:'메시지 (일)', key:'gr_messages'},
  {label:'활성 유저 (일)', key:'gr_active_users'},
];
document.getElementById('grCards').innerHTML = grCards.map(c => {
  const v = last[c.key], pv = prev[c.key];
  const d = (v==null||pv==null) ? null : v - pv;
  const cls = d==null?'flat':d>0?'up':d<0?'down':'flat', arrow = d==null?'—':d>0?'▲':d<0?'▼':'—';
  const deltaTxt = d==null ? '—' : `${arrow} ${fmt(Math.abs(d))} <span style="color:var(--ink-300);font-weight:400;">전일대비</span>`;
  return `<div class="card">
    <div class="label">${c.label}</div>
    <div class="value">${v==null?'—':fmt(v)}</div>
    <div class="delta ${cls}">${deltaTxt}</div>
    <button class="detail-btn" data-key="${c.key}" data-label="${c.label}">📊 일자별 기록</button>
  </div>`;
}).join('');

line('grMembers',[L('멤버','gr_members','#2E84AE',true)]);
const grNet = DATA.map((r,i)=> (i===0||r.gr_members==null||DATA[i-1].gr_members==null)?null : r.gr_members-DATA[i-1].gr_members);
new Chart(document.getElementById('grNet'),{type:'bar',
  data:{labels:dates,datasets:[{label:'멤버 순증·순감',data:grNet,
    backgroundColor:grNet.map(v=>v==null?'#E3E7DF':v>=0?'#1F8A5B':'#C8404E'),borderRadius:0}]},
  options:(()=>{const o=clone(baseOpts);o.scales.x.offset=true;return o;})()});
line('grActivity',[L('메시지','gr_messages','#2E84AE'),L('활성 유저','gr_active_users','#0B3A2C')]);

// ---------- 04 포스트 표 (하이퍼링크) ----------
const link = id => `https://t.me/${CH_USER}/${id}`;
const erOf = p => p.views ? ((p.forwards+p.replies)/p.views) : 0;
const reachOf = p => subsNow ? p.views/subsNow : 0;

// 공유처 셀: 공개 재공유 채널 + 그 채널에서의 조회수 (없으면 '—')
const fwdCell = p => {
  const f = FWDS[String(p.id)];
  if (!f || !f.channels || !f.channels.length)
    return `<td><span class="fwd-none">—</span></td>`;
  const rows = f.channels.map(c =>
    `<div class="row"><span>${esc(c.title)}</span><span>${fmt(c.views)}</span></div>`).join('');
  return `<td><details class="fwd"><summary>${f.count}곳 · ${fmt(f.ext_views)}</summary>
    <div class="fwdlist">${rows}</div></details></td>`;
};

if (POSTS.length) {
  // TOP 게시물 — 조회수 순 (게시 날짜 포함)
  const top = [...POSTS].sort((a,b)=>b.views-a.views).slice(0,10);
  document.getElementById('topPosts').innerHTML = top.map((p,i)=>`
    <tr>
      <td class="l"><span class="rank ${i===0?'t1':i===1?'t2':''}">${i+1}</span>
        <a class="post" href="${link(p.id)}" target="_blank" rel="noopener">${esc(p.text)}</a></td>
      <td>${p.date.slice(5)}</td>
      <td>${fmt(p.views)}</td><td>${pct(reachOf(p))}</td>
      <td>${fmt(p.forwards)}</td>${fwdCell(p)}<td>${fmt(p.replies)}</td><td>${pct(erOf(p))}</td>
    </tr>`).join('');

  // 일별 게시물 — 날짜 선택 → 해당일 게시물만 (시간 역순)
  const rowHtml = p => `
    <tr>
      <td class="l"><a class="post" href="${link(p.id)}" target="_blank" rel="noopener">${esc(p.text)}</a></td>
      <td>${p.time}</td>
      <td>${fmt(p.views)}</td><td>${pct(reachOf(p))}</td>
      <td>${fmt(p.forwards)}</td>${fwdCell(p)}<td>${fmt(p.replies)}</td><td>${pct(erOf(p))}</td>
    </tr>`;
  const allBody = document.getElementById('allPosts');
  const pager   = document.getElementById('allPostsPager');
  const sel     = document.getElementById('postDate');
  const byDate = {};
  for (const p of POSTS) (byDate[p.date] = byDate[p.date] || []).push(p);
  const days = Object.keys(byDate).sort((a,b)=>b.localeCompare(a));   // 최신일 먼저
  sel.innerHTML = days.map(d=>`<option value="${d}">${d.slice(5)} · ${byDate[d].length}건</option>`).join('');
  function show(d){
    const items = (byDate[d]||[]).slice().sort((a,b)=>(b.time||'').localeCompare(a.time||''));
    paginate(allBody, pager, items, 10, rowHtml);
  }
  sel.addEventListener('change', ()=> show(sel.value));
  show(days[0]);
} else {
  const empty = `<tr><td class="l" colspan="8" style="text-align:center;color:var(--ink-300);padding:24px;">포스트 데이터 없음 — collect.py 실행 후 표시됩니다.</td></tr>`;
  document.getElementById('topPosts').innerHTML = empty;
  document.getElementById('allPosts').innerHTML = empty;
}

// ---------- 05 공식 통계 ----------
(function(){
  const box = document.getElementById('officialStats');
  if (OFFICIAL && OFFICIAL.available) {
    const m = OFFICIAL.metrics || {};
    const entries = Object.entries(m);
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
// 이름의 문자(스크립트)로 출신을 '추정'한다. 텔레그램 API는 국적/전화번호를 주지 않으므로 어디까지나 추정값.
function originGuess(s){
  if(!s) return '—';
  const tests = [
    [/[\u0590-\u05FF]/, '히브리어 (이스라엘 추정)'],
    [/[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF]/, '아랍어'],
    [/[\u0400-\u04FF]/, '키릴 (러시아·동유럽 추정)'],
    [/[\uAC00-\uD7A3\u1100-\u11FF]/, '한국어'],
    [/[\u3040-\u30FF]/, '일본어'],
    [/[\u4E00-\u9FFF]/, '중국어'],
    [/[\u0E00-\u0E7F]/, '태국어'],
    [/[\u0900-\u097F]/, '데바나가리 (인도 추정)'],
    [/[A-Za-z]/, '라틴 문자'],
  ];
  for(const [re,label] of tests){ if(re.test(s)) return label; }
  return '기타 / 이모지';
}
(function(){
  const box = document.getElementById('joinLeave');
  const jl = (JOINLEAVE && JOINLEAVE.available) ? (JOINLEAVE.events || []) : null;
  if (jl && jl.length){
    const jn = jl.filter(e=>e.kind==='join').length;
    const lv = jl.filter(e=>e.kind==='left').length;
    box.innerHTML = `
      <div class="tabs" id="jlTabs">
        <button class="tab active" data-f="all">전체 ${jl.length}</button>
        <button class="tab" data-f="join">유입 ${jn}</button>
        <button class="tab" data-f="left">이탈 ${lv}</button>
      </div>
      <div class="table-wrap"><table><thead><tr><th class="l">구분</th><th class="l">멤버</th><th class="l">추정 출신</th><th>시각</th></tr></thead><tbody id="jlBody"></tbody></table></div>
      <div class="pager" id="jlPager"></div>`;
    const body = document.getElementById('jlBody'), pager = document.getElementById('jlPager');
    const rowFn = e => {
      const tag = e.kind==='join' ? `<span class="jl-tag join">유입</span>` : `<span class="jl-tag left">이탈</span>`;
      const uname = e.username ? ` <span style="color:var(--ink-300);">@${esc(e.username)}</span>` : '';
      const dt = e.date ? (e.date.slice(5,10)+' '+e.date.slice(11,16)) : '—';
      const origin = `<span style="color:var(--ink-500);font-size:12px;">${esc(originGuess(e.name))}</span>`;
      return `<tr><td class="l">${tag}</td><td class="l">${esc(e.name||('user '+e.id))}${uname}</td><td class="l">${origin}</td><td>${dt}</td></tr>`;
    };
    function apply(f){ paginate(body, pager, f==='all'?jl:jl.filter(e=>e.kind===f), 10, rowFn); }
    document.getElementById('jlTabs').addEventListener('click', ev=>{
      const t = ev.target.closest('.tab'); if(!t) return;
      document.querySelectorAll('#jlTabs .tab').forEach(x=>x.classList.toggle('active', x===t));
      apply(t.dataset.f);
    });
    apply('all');
  } else {
    const reason = (JOINLEAVE && JOINLEAVE.reason) ? esc(JOINLEAVE.reason)
      : 'collect.py가 admin log(채널 관리자 권한)에서 유입·이탈 이벤트를 수집하면 표시됩니다.';
    box.innerHTML = `<div class="empty"><div class="tag">No join/leave log</div>
      <b>유입·이탈 인원 데이터 없음</b><br>${reason}</div>`;
  }
})();

// ---------- 06 활발한 멤버 (10명씩 페이지네이션) ----------
(function(){
  const box = document.getElementById('topMembers');
  if (MEMBERS && MEMBERS.length) {
    box.innerHTML = `<div class="eyebrow" style="margin-bottom:12px;">활발한 멤버 — 발화 수 순 (전체 ${MEMBERS.length}명)</div>
      <div class="table-wrap"><table><thead><tr><th class="l">#  멤버</th><th>발화 수</th></tr></thead><tbody id="tmBody"></tbody></table></div>
      <div class="pager" id="tmPager"></div>`;
    paginate(document.getElementById('tmBody'), document.getElementById('tmPager'), MEMBERS, 10,
      (m,i)=>{
        const uname = m.username ? ` <span style="color:var(--ink-300);">@${esc(m.username)}</span>` : '';
        return `<tr><td class="l"><span class="rank ${i===0?'t1':i===1?'t2':''}">${i+1}</span>${esc(m.name||('user '+m.id))}${uname}</td><td>${fmt(m.count)}</td></tr>`;
      });
  } else {
    box.innerHTML = `<div class="empty"><div class="tag">No member data</div>
      <b>활발한 멤버 데이터 없음</b><br>collect.py가 그룹 발화 집계를 저장하면 표시됩니다.</div>`;
  }
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


def main():
    rows = load_summary(SRC)
    if not rows:
        print("데이터가 없습니다:", SRC)
        return

    posts = load_latest_posts()
    official = load_json("broadcast_stats.json", {"available": False})
    members = load_json("group_top_members.json", [])

    fwds = load_json("post_forwards.json", {})
    joinleave = load_json("join_leave.json", {"available": False})



    html = (TEMPLATE
            .replace("__END__", rows[-1]["date"])
            .replace("__CHUSER__", CH_USER)
            .replace("__GRUSER__", GR_USER)
            .replace("__DATA__", json.dumps(rows, ensure_ascii=False))
            .replace("__POSTS__", json.dumps(posts, ensure_ascii=False))
            .replace("__OFFICIAL__", json.dumps(official, ensure_ascii=False))
            .replace("__MEMBERS__", json.dumps(members, ensure_ascii=False))
            .replace("__FWDS__", json.dumps(fwds, ensure_ascii=False))
            .replace("__JOINLEAVE__", json.dumps(joinleave, ensure_ascii=False)))

    OUT.write_text(html, encoding="utf-8")
    print(f"대시보드 생성 완료 → {OUT}")
    print(f"  요약 {len(rows)}일 · 포스트 {len(posts)}건 · "
          f"공식통계 {'O' if official.get('available') else 'X'} · "
          f"멤버 {len(members)}")
    print(f"열기: open {OUT}")


if __name__ == "__main__":
    main()
