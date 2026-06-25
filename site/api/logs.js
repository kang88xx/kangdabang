// GET /api/logs → (마스터 전용) 전체 접속 로그를 계정별로 집계해 반환.
// 로그는 슬롯(A/B/kang) 기준으로 쌓이지만, 표시는 현재 이름으로 매핑(이름 바꾸면 반영).
const { authFromReq, ACCOUNTS } = require("../lib/auth");
const { readEvents, kvReady } = require("../lib/kv");
const { nameMap } = require("../lib/accounts");

module.exports = async (req, res) => {
  const a = authFromReq(req);
  if (!a) return res.status(401).json({ ok: false, error: "로그인이 필요합니다." });
  if (a.r !== "master") return res.status(403).json({ ok: false, error: "마스터 전용입니다." });

  if (!kvReady) {
    // KV 미연동 상태 — 사이트는 작동하되 로그 저장소가 아직 연결되지 않음.
    return res.status(200).json({ ok: true, kvReady: false, users: [], events: [] });
  }

  let events = [];
  try {
    events = await readEvents();
  } catch (e) {
    return res.status(200).json({ ok: true, kvReady: true, error: String(e), users: [], events: [] });
  }

  // 슬롯 -> 현재 표시 이름 매핑(이름 변경 반영). 실패해도 슬롯명으로 폴백.
  let map = {};
  try { map = await nameMap(); } catch (e) { map = {}; }
  const dn = (slot) => map[slot] || slot;

  // 계정별 집계: 총 횟수 / 로그인 수 / 사용(핑) 수 / 최초·최근 접속.
  // 슬롯 기준으로 집계하되 user 필드는 현재 이름. 모든 등록 계정을 0건으로 깔아둔다
  // — 접속 기록 없는 계정도 탭/목록에 노출, 계정 추가 시 자동 항목 생성.
  const byUser = {};
  for (const slot of Object.keys(ACCOUNTS)) {
    byUser[slot] = { user: dn(slot), slot, role: ACCOUNTS[slot].role, total: 0, logins: 0, pings: 0, first: null, last: null };
  }
  for (const ev of events) {
    if (!ev || !ev.u) continue;
    const slot = ev.u; // 로그는 슬롯 기준
    let u = byUser[slot];
    if (!u) u = byUser[slot] = { user: dn(slot), slot, role: ev.r, total: 0, logins: 0, pings: 0, first: null, last: null };
    u.total++;
    if (ev.type === "login") u.logins++;
    else u.pings++;
    if (u.first === null || ev.ts < u.first) u.first = ev.ts;
    if (u.last === null || ev.ts > u.last) u.last = ev.ts;
  }
  const users = Object.values(byUser).sort((x, y) => y.total - x.total);

  // 상세 타임라인(최신순, 최대 800건) — u 를 현재 이름으로 치환.
  const timeline = events
    .slice()
    .sort((x, y) => y.ts - x.ts)
    .slice(0, 800)
    .map((ev) => ({ u: dn(ev.u), r: ev.r, type: ev.type, ts: ev.ts }));

  return res.status(200).json({ ok: true, kvReady: true, total: events.length, users, events: timeline });
};
