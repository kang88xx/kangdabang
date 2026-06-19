"""daily_summary.csv 를 읽어 자체 완결형 HTML 대시보드를 생성합니다.
OkardCare Design System v1.0 적용 (Forest/Signal 팔레트, Pretendard + Geist Mono, 사각 코너).

사용법:
    python build_dashboard.py                  # data/daily_summary.csv 사용
    python build_dashboard.py data/sample.csv  # 다른 CSV 지정

결과: data/dashboard.html  (더블클릭으로 바로 열림, 인터넷만 있으면 됨)
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "daily_summary.csv"
OUT = ROOT / "data" / "dashboard.html"


def load_rows(path):
    with path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k, v in r.items():
            if k != "date":
                r[k] = int(v)
    return rows


HTML = """<!DOCTYPE html>
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
  :root {{
    --forest-950:#061B14; --forest-900:#0B3A2C; --forest-700:#134C39;
    --forest-500:#25876A; --forest-300:#8FBFAD; --forest-100:#DCEAE2;
    --signal:#14B87D; --positive:#1F8A5B; --negative:#C8404E;
    --info:#2E84AE; --chart-alt:#6E63D6;
    --ink-900:#14201B; --ink-700:#34433D; --ink-500:#5F6C65; --ink-300:#9BA7A0;
    --paper:#F4F6F2; --white:#FFFFFF; --line:#E3E7DF; --line-soft:#EEF1EC;
  }}
  * {{ box-sizing:border-box; }}
  html,body {{ margin:0; padding:0; background:var(--paper);
    -webkit-font-smoothing:antialiased; -moz-osx-font-smoothing:grayscale; }}
  body {{ font-family:'Pretendard',-apple-system,system-ui,sans-serif;
    color:var(--ink-900); font-feature-settings:'ss01','tnum'; }}
  .mono {{ font-family:'Geist Mono',monospace; font-variant-numeric:tabular-nums; }}
  .eyebrow {{ font-family:'Geist Mono',monospace; font-size:11px; letter-spacing:.18em;
    text-transform:uppercase; color:var(--ink-500); }}

  /* CHROME RAIL */
  .rail {{ position:sticky; top:0; z-index:20; display:grid;
    grid-template-columns:1fr auto 1fr; align-items:center;
    background:#0C3F30; color:rgba(255,255,255,.62);
    font-family:'Geist Mono',monospace; font-size:11px; letter-spacing:.18em;
    text-transform:uppercase; padding:9px 28px; border-bottom:1px solid rgba(255,255,255,.12); }}
  .rail .mid {{ color:#fff; letter-spacing:.22em; }}
  .rail .end {{ text-align:right; }}

  /* COVER */
  header.cover {{ background:linear-gradient(158deg,#0E4636 0%,#0A2C22 58%,#061B14 100%);
    color:#fff; padding:64px 64px 56px; }}
  .cover-in {{ max-width:1180px; margin:0 auto; }}
  .logo {{ display:flex; align-items:center; gap:11px; margin-bottom:48px; }}
  .logo span {{ font-size:18px; font-weight:600; letter-spacing:-.02em; }}
  .logo .accent {{ color:var(--signal); }}
  .cover h1 {{ margin:0; font-weight:300; font-size:clamp(34px,5vw,60px);
    line-height:1.0; letter-spacing:-.035em; }}
  .cover h1 b {{ font-weight:500; border-bottom:3px solid var(--signal); padding-bottom:2px; }}
  .cover p {{ margin:24px 0 0; max-width:56ch; font-size:16px; line-height:1.6;
    color:rgba(255,255,255,.74); font-weight:300; }}
  .pills {{ display:flex; flex-wrap:wrap; gap:9px; margin-top:32px; }}
  .pills span {{ border:1px solid rgba(255,255,255,.26); border-radius:999px;
    padding:6px 15px; font-size:13px; font-weight:500; }}

  main {{ max-width:1180px; margin:0 auto; padding:72px 64px 0; }}
  section {{ margin-bottom:72px; }}
  .sec-head {{ display:flex; align-items:baseline; gap:18px;
    border-top:1.5px solid var(--ink-900); padding-top:16px; margin-bottom:32px; }}
  .sec-head .num {{ font-family:'Geist Mono',monospace; font-size:14px; font-weight:500; color:var(--signal); }}
  .sec-head h2 {{ margin:6px 0 0; font-weight:500; font-size:26px; line-height:1.1; letter-spacing:-.022em; }}

  /* KPI CARDS */
  .cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(186px,1fr)); gap:16px; }}
  .card {{ background:var(--white); border:1px solid var(--line); padding:22px; }}
  .card .label {{ font-size:13px; color:var(--ink-500); }}
  .card .value {{ font-family:'Geist Mono',monospace; font-variant-numeric:tabular-nums;
    font-size:34px; font-weight:400; letter-spacing:-.02em; color:var(--ink-900); margin:10px 0 6px; }}
  .card .delta {{ font-family:'Geist Mono',monospace; font-size:12.5px; font-weight:500; }}
  .up {{ color:var(--positive); }}
  .down {{ color:var(--negative); }}
  .flat {{ color:var(--ink-300); }}

  /* CHARTS */
  .grid {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
  .chart-box {{ background:var(--white); border:1px solid var(--line); padding:24px; }}
  .chart-box .eyebrow {{ margin-bottom:16px; }}
  canvas {{ max-height:236px; }}

  footer {{ border-top:1.5px solid var(--ink-900); margin-top:8px;
    padding:24px 0 56px; display:flex; align-items:center; justify-content:space-between;
    flex-wrap:wrap; gap:16px; max-width:1180px; margin-left:auto; margin-right:auto; }}
  footer .left {{ display:flex; align-items:center; gap:10px; }}
  footer .left span {{ font-size:15px; font-weight:600; letter-spacing:-.02em; }}
  footer .note {{ font-family:'Geist Mono',monospace; font-size:11px; letter-spacing:.14em;
    text-transform:uppercase; color:var(--ink-300); }}
  @media (max-width:760px) {{ .grid {{ grid-template-columns:1fr; }}
    header.cover, main {{ padding-left:28px; padding-right:28px; }} }}
</style>
</head>
<body>

  <div class="rail">
    <span>캉 티룸 — 텔레그램 통계</span>
    <span class="mid">v1.0</span>
    <span class="end">{end}</span>
  </div>

  <header class="cover">
    <div class="cover-in">
      <div class="logo">
        <svg width="26" height="26" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <polygon points="12,2 21,7 21,17 12,22 3,17 3,7" stroke="#fff" stroke-width="1.6" stroke-linejoin="miter"></polygon>
          <circle cx="12" cy="12" r="2.4" fill="#14B87D"></circle>
        </svg>
        <span>캉 <span class="accent">티룸</span></span>
      </div>
      <div class="eyebrow" style="color:rgba(255,255,255,.55);margin-bottom:22px;">Telegram analytics · @kang_tearoom · @kangtearoom_chat</div>
      <h1>최근 24시간을 <b>한 장으로.</b></h1>
      <p>채널과 그룹의 성장·도달·참여를 매일 기록합니다. 사각 코너, 헤어라인, 테뷸러 숫자 — 읽기 위한 대시보드.</p>
      <div class="pills">
        <span>구독자</span><span>조회수</span><span>멤버</span><span>참여</span>
      </div>
    </div>
  </header>

  <main>
    <section>
      <div class="sec-head">
        <span class="num">01</span>
        <div>
          <div class="eyebrow">Overview</div>
          <h2>오늘의 핵심 지표</h2>
        </div>
      </div>
      <div class="cards" id="cards"></div>
    </section>

    <section>
      <div class="sec-head">
        <span class="num">02</span>
        <div>
          <div class="eyebrow">Trends</div>
          <h2>{days}일 추이</h2>
        </div>
      </div>
      <div class="grid">
        <div class="chart-box"><div class="eyebrow">구독자 / 그룹 멤버</div><canvas id="audience"></canvas></div>
        <div class="chart-box"><div class="eyebrow">채널 일일 조회수</div><canvas id="views"></canvas></div>
        <div class="chart-box"><div class="eyebrow">그룹 메시지 / 활성 유저</div><canvas id="group"></canvas></div>
        <div class="chart-box"><div class="eyebrow">채널 인게이지먼트 — 공유 · 댓글</div><canvas id="engage"></canvas></div>
      </div>
    </section>
  </main>

  <footer>
    <div class="left">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none"><polygon points="12,2 21,7 21,17 12,22 3,17 3,7" stroke="#0B3A2C" stroke-width="1.8" stroke-linejoin="miter"></polygon><circle cx="12" cy="12" r="2.6" fill="#14B87D"></circle></svg>
      <span>캉 <span style="color:#14B87D;">티룸</span></span>
    </div>
    <span class="note">{footer}</span>
  </footer>

<script>
const DATA = {data_json};
const fmt = n => n.toLocaleString('ko-KR');
const dates = DATA.map(r => r.date.slice(5));  // MM-DD

// ----- KPI 카드 -----
const cards = [
  {{label:'구독자', key:'ch_subscribers'}},
  {{label:'채널 조회수 (일)', key:'ch_views'}},
  {{label:'그룹 멤버', key:'gr_members'}},
  {{label:'그룹 메시지 (일)', key:'gr_messages'}},
  {{label:'활성 유저 (일)', key:'gr_active_users'}},
];
const last = DATA[DATA.length-1], prev = DATA[DATA.length-2] || last;
document.getElementById('cards').innerHTML = cards.map(c => {{
  const v = last[c.key], d = v - prev[c.key];
  const cls = d>0?'up':d<0?'down':'flat';
  const arrow = d>0?'▲':d<0?'▼':'—';
  return `<div class="card">
    <div class="label">${{c.label}}</div>
    <div class="value">${{fmt(v)}}</div>
    <div class="delta ${{cls}}">${{arrow}} ${{fmt(Math.abs(d))}} <span style="color:var(--ink-300);font-weight:400;">전일대비</span></div>
  </div>`;
}}).join('');

// ----- 차트 (OkardCare 라이트 테마) -----
Chart.defaults.color = '#9BA7A0';
Chart.defaults.borderColor = '#EEF1EC';
Chart.defaults.font.family = "'Geist Mono', monospace";
Chart.defaults.font.size = 11;
const baseOpts = {{
  responsive:true, maintainAspectRatio:false,
  plugins:{{legend:{{labels:{{boxWidth:10,boxHeight:10,font:{{size:11}},color:'#5F6C65'}}}}}},
  scales:{{
    y:{{grid:{{color:'#EEF1EC'}}, ticks:{{color:'#9BA7A0'}}, border:{{color:'#E3E7DF'}}}},
    x:{{grid:{{display:false}}, ticks:{{color:'#9BA7A0'}}, border:{{color:'#E3E7DF'}}}}
  }}
}};
const line = (id, datasets) => new Chart(document.getElementById(id), {{
  type:'line', data:{{labels:dates, datasets}}, options:baseOpts
}});
const bar = (id, datasets) => new Chart(document.getElementById(id), {{
  type:'bar', data:{{labels:dates, datasets}}, options:baseOpts
}});
const ds = (label, key, color, fill=false) => ({{
  label, data:DATA.map(r=>r[key]), borderColor:color,
  backgroundColor:fill?color+'22':color, tension:.25, pointRadius:2,
  pointBackgroundColor:color, borderWidth:2, fill
}});

line('audience', [ds('구독자','ch_subscribers','#0B3A2C',true), ds('그룹 멤버','gr_members','#14B87D')]);
bar('views', [{{label:'조회수', data:DATA.map(r=>r.ch_views), backgroundColor:'#25876A', borderRadius:0}}]);
line('group', [ds('메시지','gr_messages','#2E84AE'), ds('활성 유저','gr_active_users','#0B3A2C')]);
line('engage', [ds('공유','ch_forwards','#6E63D6'), ds('댓글','ch_replies','#1F8A5B')]);
</script>
</body>
</html>"""


def main():
    rows = load_rows(SRC)
    if not rows:
        print("데이터가 없습니다:", SRC)
        return

    sample_note = ""
    if SRC.name != "daily_summary.csv":
        sample_note = " · 샘플(가상) 데이터 미리보기"

    html = HTML.format(
        end=rows[-1]["date"],
        days=len(rows),
        data_json=json.dumps(rows, ensure_ascii=False),
        footer=f"{rows[0]['date']} – {rows[-1]['date']} · {len(rows)} records{sample_note}",
    )
    OUT.write_text(html, encoding="utf-8")
    print(f"대시보드 생성 완료 → {OUT}")
    print(f"열기: open {OUT}")


if __name__ == "__main__":
    main()
