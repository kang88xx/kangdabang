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
import base64
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
                _dt = datetime.fromisoformat(r["date"])
                # 그룹핑 날짜(_d)는 daily_summary와 동일하게 UTC 일 버킷,
                # 표시 시각(_t)은 한국시간(KST)으로.
                _d = _dt.astimezone(timezone.utc).strftime("%Y-%m-%d")
                _t = _dt.astimezone(KST).strftime("%H:%M")
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
<title>Kangtearoom Data Analysis</title>
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

  main { max-width:1180px; margin:0 auto; padding:40px 64px 0; }
  section { margin-bottom:64px; scroll-margin-top:58px; }
  #topMembers { scroll-margin-top:58px; }
  .basis-note { font-family:'Geist Mono',monospace; font-size:11.5px; line-height:1.5; letter-spacing:.01em;
    color:var(--ink-500); background:var(--white); border:1px solid var(--line); border-left:3px solid var(--signal);
    padding:11px 16px; margin-bottom:40px; }
  .basis-note b { color:var(--forest-700); font-weight:600; }
  .week-summary { font-size:14px; line-height:1.5; color:var(--ink-700);
    background:var(--white); border:1px solid var(--line); border-left:3px solid var(--forest-500);
    padding:13px 18px; margin-bottom:20px; }
  .week-summary:empty { display:none; }
  .week-summary b { font-family:'Geist Mono',monospace; color:var(--forest-700); font-weight:600; }
  .sec-head { display:flex; align-items:baseline; gap:18px;
    border-top:1.5px solid var(--ink-900); padding-top:16px; margin-bottom:28px; }
  .sec-head .num { font-family:'Geist Mono',monospace; font-size:14px; font-weight:500; color:var(--signal); }
  .sec-head h2 { margin:6px 0 0; font-weight:500; font-size:26px; line-height:1.1; letter-spacing:-.022em; }
  .group-head .num { color:var(--info); }

  /* domain tag */
  .dtag { display:inline-block; font-family:'Geist Mono',monospace; font-size:10.5px;
    letter-spacing:.12em; text-transform:uppercase; padding:3px 8px; border:1px solid transparent;
    color:#fff; margin-left:auto; align-self:center; }
  .dtag.ch { background:var(--forest-500); border-color:var(--forest-500); }
  .dtag.gr { background:var(--info); border-color:var(--info); }
  .dtag.cobak { background:#1652f0; border-color:#1652f0; color:#fff; text-decoration:none; }

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
  .modal-body { overflow-y:auto; overflow-x:auto; }
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
  tbody td a.ulink { color:inherit; text-decoration:none; border-bottom:1px solid var(--line); padding-bottom:1px; }
  tbody td a.ulink:hover { color:var(--forest-500); border-color:var(--forest-300); }
  .rank { display:inline-flex; align-items:center; justify-content:center; width:22px; height:22px;
    background:var(--forest-900); color:#fff; font-family:'Geist Mono',monospace; font-size:11px;
    font-weight:600; margin-right:10px; }
  .rank.t1 { background:var(--signal); } .rank.t2 { background:var(--forest-500); }

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
  .jl-note { font-size:12px; color:var(--ink-300); margin-bottom:12px; line-height:1.5; }

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
    /* D2: 상단바 1행화 — "KANGTEAROOM DATA" 숨기고 2열 정리, 높이 축소 */
    .rail-in > span:first-child { display:none; }
    .rail-in { grid-template-columns:1fr auto; align-items:center; gap:8px;
      padding-top:6px; padding-bottom:6px; }
    .rail .mid { white-space:normal; letter-spacing:.02em; text-align:left; }
    .rail .end { justify-content:flex-end; }
    /* 1행 rail에 맞춰 섹션 앵커 보정 */
    section, #topMembers { scroll-margin-top:54px; }
    .cards-tight { grid-template-columns:repeat(2,minmax(0,1fr)); }
    .basis-note { line-height:1.6; }
    .eyebrow, .rail, .dtag { letter-spacing:.06em; }
    /* D1: 터치 타깃 ≥44px */
    .tab { padding:11px 16px; }
    .pager button { min-width:44px; padding:11px 12px; }
    .detail-btn { width:100%; padding:12px 10px; text-align:center; }
    .modal-close { width:44px; height:44px; display:flex; align-items:center;
      justify-content:center; padding:0; }
    /* D3: 모달 하단시트화 + 표 축소 */
    .modal-back { align-items:flex-end; padding:12px; }
    .modal { max-height:88vh; }
    .modal-body table { font-size:12px; }
    .modal-body th, .modal-body td { padding:9px 10px; } }
</style>
</head>
<body class="auth-lock">

  <div id="authOverlay">
    <form class="auth-card" id="authForm" autocomplete="off">
      <div class="brand">Kangtearoom · Internal</div>
      <h1>캉다방 통계</h1>
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
      <span>KANGTEAROOM DATA</span>
      <span class="mid"><a class="chlink" href="https://t.me/__CHUSER__" target="_blank" rel="noopener">@__CHUSER__</a> · <a class="chlink" href="https://t.me/__GRUSER__" target="_blank" rel="noopener">@__GRUSER__</a></span>
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

      <div class="grid">
        <div class="chart-box"><div class="eyebrow">구독자 추이</div><canvas id="subs"></canvas></div>
        <div class="chart-box"><div class="eyebrow">들어옴 · 나감 (일별)</div><canvas id="subsNet"></canvas></div>
      </div>
      <div class="eyebrow" style="margin:28px 0 12px;">유입 · 이탈 인원 (누가)</div>
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
      <div class="eyebrow" style="margin-bottom:12px;">TOP 게시물 — 조회수 순 (제목 클릭 시 텔레그램에서 열림)</div>
      <div class="table-wrap" style="margin-bottom:28px;">
        <table><thead><tr>
          <th class="l">#  게시물</th><th>날짜</th><th>조회수</th><th>공유</th><th>댓글</th>
        </tr></thead><tbody id="topPosts"></tbody></table>
      </div>
      <div class="eyebrow" style="margin-bottom:12px;display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
        <span>일별 게시물 — 날짜별 보기</span>
        <select id="postDate" class="datesel"></select>
      </div>
      <div class="table-wrap">
        <table><thead><tr>
          <th class="l">게시물</th><th>시각</th><th>조회수</th><th>공유</th><th>댓글</th>
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
      <div id="grJoinLeaveWrap" hidden>
        <div class="eyebrow" style="margin:28px 0 12px;">유입 · 이탈 인원 (누가)</div>
        <div id="grJlNote" class="jl-note"></div>
        <div id="joinLeaveGroup"></div>
      </div>
    </section>

    <!-- 07 코박 활동 -->
    <section id="sec-cobak">
      <div class="sec-head">
        <div><div class="eyebrow">Community · Cobak</div><h2>코박 활동 — 캉다방</h2></div>
        <a class="dtag cobak" id="cobakTag" href="https://cobak.co/" target="_blank" rel="noopener">cobak.co</a>
      </div>
      <div class="cards" id="cobakCards" style="margin-bottom:24px;"></div>
      <div class="eyebrow" style="margin-bottom:12px;">게시글 목록 — 최신순 (제목 클릭 시 코박에서 열림)</div>
      <div class="table-wrap">
        <table><thead><tr>
          <th class="l">게시물</th><th>날짜</th><th>시각</th><th>조회수</th><th>추천</th><th>댓글</th>
        </tr></thead><tbody id="cobakPosts"></tbody></table>
      </div>
    </section>

    <!-- 08 접속 로그 (마스터 전용) -->
    <section id="sec-access" hidden>
      <div class="sec-head">
        <div><div class="eyebrow">Admin · Access</div><h2>접속 로그 — 사용 현황</h2></div>
        <button type="button" id="logRefresh" class="dtag" style="background:var(--ink-900);border:none;cursor:pointer;">새로고침</button>
      </div>
      <div class="eyebrow" style="margin-bottom:12px;">계정 선택 — 탭을 누르면 해당 계정만 표시 (계정은 자동 생성)</div>
      <div class="tabs" id="accessTabs"></div>
      <div id="accessSummary" style="font-family:'Geist Mono',monospace;font-size:13px;letter-spacing:.01em;color:var(--ink-500);margin:2px 0 16px;min-height:18px;"></div>
      <div class="table-wrap">
        <table><thead><tr>
          <th class="l">계정</th><th>유형</th><th>날짜</th><th>시각</th>
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
const CH_USER  = "__CHUSER__";

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
  const msgAvg   = avgOf(recent7, 'gr_messages');
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
document.getElementById('cards').innerHTML = cards.map(c => {
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

// 06 그룹 — KPI 카드(전일대비) + 추이 + 순증·순감
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

// ---------- 04 포스트 표 (하이퍼링크) ----------
const link = id => `https://t.me/${CH_USER}/${id}`;

if (POSTS.length) {
  // TOP 게시물 — 조회수 순 (게시 날짜 포함)
  const top = [...POSTS].sort((a,b)=>b.views-a.views).slice(0,10);
  document.getElementById('topPosts').innerHTML = top.map((p,i)=>`
    <tr>
      <td class="l"><span class="rank ${i===0?'t1':i===1?'t2':''}">${i+1}</span>
        <a class="post" href="${link(p.id)}" target="_blank" rel="noopener">${esc(p.text)}</a></td>
      <td>${p.date.slice(5)}</td>
      <td>${fmt(p.views)}</td>
      <td>${fmt(p.forwards)}</td><td>${fmt(p.replies)}</td>
    </tr>`).join('');

  // 일별 게시물 — 날짜 선택 → 해당일 게시물만 (시간 역순)
  const rowHtml = p => `
    <tr>
      <td class="l"><a class="post" href="${link(p.id)}" target="_blank" rel="noopener">${esc(p.text)}</a></td>
      <td>${p.time}</td>
      <td>${fmt(p.views)}</td>
      <td>${fmt(p.forwards)}</td><td>${fmt(p.replies)}</td>
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
  const empty = `<tr><td class="l" colspan="5" style="text-align:center;color:var(--ink-300);padding:24px;">포스트 데이터 없음 — collect.py 실행 후 표시됩니다.</td></tr>`;
  document.getElementById('topPosts').innerHTML = empty;
  document.getElementById('allPosts').innerHTML = empty;
}

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
function renderJoinLeave(box, src){
  if(!box) return;
  const jl = (src && src.available) ? (src.events || []) : null;
  if (jl && jl.length){
    const jn = jl.filter(e=>e.kind==='join').length;
    const lv = jl.filter(e=>e.kind==='left').length;
    box.innerHTML = `
      <div class="tabs">
        <button class="tab active" data-f="all">전체 ${jl.length}</button>
        <button class="tab" data-f="join">유입 ${jn}</button>
        <button class="tab" data-f="left">이탈 ${lv}</button>
      </div>
      <div class="table-wrap"><table><thead><tr><th class="l">구분</th><th class="l">멤버</th><th>시각</th></tr></thead><tbody></tbody></table></div>
      <div class="pager"></div>`;
    const tabs = box.querySelector('.tabs');
    const body = box.querySelector('tbody'), pager = box.querySelector('.pager');
    const rowFn = e => {
      const tag = e.kind==='join' ? `<span class="jl-tag join">유입</span>` : `<span class="jl-tag left">이탈</span>`;
      const uname = e.username ? ` <span style="color:var(--ink-300);">@${esc(e.username)}</span>` : '';
      const label = `${esc(e.name||('user '+e.id))}${uname}`;
      const cell = e.username ? `<a class="ulink" href="https://t.me/${encodeURIComponent(e.username)}" target="_blank" rel="noopener">${label}</a>` : label;
      return `<tr><td class="l">${tag}</td><td class="l">${cell}</td><td>${kstShort(e.date)}</td></tr>`;
    };
    function apply(f){ paginate(body, pager, f==='all'?jl:jl.filter(e=>e.kind===f), 10, rowFn); }
    tabs.addEventListener('click', ev=>{
      const t = ev.target.closest('.tab'); if(!t) return;
      tabs.querySelectorAll('.tab').forEach(x=>x.classList.toggle('active', x===t));
      apply(t.dataset.f);
    });
    apply('all');
  } else {
    const reason = (src && src.reason) ? esc(src.reason)
      : 'collect.py가 admin log(관리자 권한)에서 유입·이탈 이벤트를 수집하면 표시됩니다. (그룹은 공개링크 가입이 로그에 안 남을 수 있음)';
    box.innerHTML = `<div class="empty"><div class="tag">No join/leave log</div>
      <b>유입·이탈 인원 데이터 없음</b><br>${reason}</div>`;
  }
}
renderJoinLeave(document.getElementById('joinLeave'), JOINLEAVE);
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
  if (MEMBERS && MEMBERS.length) {
    box.innerHTML = `<div class="eyebrow" style="margin-bottom:12px;">활발한 멤버 — 발화 수 순 (전체 ${MEMBERS.length}명)</div>
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

  const posts = COBAK.posts || [];
  if (posts.length) {
    body.innerHTML = posts.map(p=>`
      <tr>
        <td class="l"><a class="post" href="${p.url}" target="_blank" rel="noopener">${esc(p.title)}</a></td>
        <td>${(p.date||'').slice(5)}</td>
        <td>${p.time||''}</td>
        <td>${fmt(p.views)}</td>
        <td>${fmt(p.recommend)}</td>
        <td>${fmt(p.comments)}</td>
      </tr>`).join('');
  } else {
    body.innerHTML = `<tr><td class="l" colspan="6" style="text-align:center;color:var(--ink-300);padding:24px;">게시글 없음</td></tr>`;
  }
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
      tbody.innerHTML = `<tr><td class="l" colspan="4" style="text-align:center;color:var(--ink-300);padding:24px;">로그 저장소(KV) 미연동 — 연결 후 표시됩니다.</td></tr>`;
      pager.innerHTML=''; foot.textContent=''; return;
    }

    const users = d.users || [];      // 모든 계정(0건 포함), 접속 횟수 순
    const evs   = d.events || [];
    const total = d.total || evs.length;
    if (!users.some(u=>u.user===logFilter)) logFilter = '__all';   // 사라진 계정 선택 방어

    // 탭: 전체 + 계정별 (계정 추가 시 자동 생성)
    tabsBox.innerHTML = [`<button class="tab" data-u="__all">전체 ${fmt(total)}</button>`]
      .concat(users.map(u=>`<button class="tab" data-u="${esc(u.user)}">${esc(u.user)}${u.role==='master'?' · 마스터':''} ${fmt(u.total)}</button>`))
      .join('');

    const rowFn = ev => `
      <tr>
        <td class="l">${esc(ev.u)}</td>
        <td><span class="ttag ${ev.type==='login'?'login':'ping'}">${ev.type==='login'?'로그인':'사용'}</span></td>
        <td>${kstDate(ev.ts)}</td>
        <td>${kstTime(ev.ts)}</td>
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
      const items = user==='__all' ? evs : evs.filter(e=>e.u===user);
      if (items.length) paginate(tbody, pager, items, 12, rowFn);
      else { tbody.innerHTML = `<tr><td class="l" colspan="4" style="text-align:center;color:var(--ink-300);padding:24px;">기록 없음</td></tr>`; pager.innerHTML=''; }
    }
    tabsBox.onclick = ev => { const t = ev.target.closest('.tab'); if(!t) return; apply(t.dataset.u); };
    apply(logFilter);
    foot.textContent = `총 ${fmt(total)}건 · 표시 ${evs.length}건 · 60초마다 자동 갱신`;
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


def main():
    rows = load_summary(SRC)
    if not rows:
        print("데이터가 없습니다:", SRC, file=sys.stderr)
        sys.exit(1)   # 빈 빌드 차단 — update.sh 게이트가 비정상 종료를 감지

    posts = load_latest_posts()
    official = load_json("broadcast_stats.json", {"available": False})
    members = load_json("group_top_members.json", [])

    joinleave = load_json("join_leave.json", {"available": False})
    joinleave_gr = load_json("join_leave_group.json", {"available": False})
    cobak = load_json("cobak_stats.json", {"available": False})



    logo = ROOT / "assets" / "kang_logo.png"
    favicon = ("data:image/png;base64," + base64.b64encode(logo.read_bytes()).decode()) if logo.exists() else ""

    html = (TEMPLATE
            .replace("__FAVICON__", favicon)
            .replace("__GENERATED__", datetime.now(KST).strftime("%Y-%m-%d %H:%M"))
            .replace("__CHUSER__", CH_USER)
            .replace("__GRUSER__", GR_USER)
            .replace("__DATA__", json.dumps(rows, ensure_ascii=False))
            .replace("__POSTS__", json.dumps(posts, ensure_ascii=False))
            .replace("__OFFICIAL__", json.dumps(official, ensure_ascii=False))
            .replace("__MEMBERS__", json.dumps(members, ensure_ascii=False))
            .replace("__JOINLEAVE__", json.dumps(joinleave, ensure_ascii=False))
            .replace("__JOINLEAVE_GR__", json.dumps(joinleave_gr, ensure_ascii=False))
            .replace("__COBAK__", json.dumps(cobak, ensure_ascii=False)))

    OUT.write_text(html, encoding="utf-8")
    print(f"대시보드 생성 완료 → {OUT}")
    print(f"  요약 {len(rows)}일 · 포스트 {len(posts)}건 · "
          f"공식통계 {'O' if official.get('available') else 'X'} · "
          f"멤버 {len(members)}")
    print(f"열기: open {OUT}")


if __name__ == "__main__":
    main()
