// GET /api/logs → (마스터 전용) 전체 접속 로그를 계정별로 집계해 반환.
const { authFromReq } = require("../lib/auth");
const { readEvents, kvReady } = require("../lib/kv");

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

  // 계정별 집계: 총 횟수 / 로그인 수 / 사용(핑) 수 / 최초·최근 접속
  const byUser = {};
  for (const ev of events) {
    if (!ev || !ev.u) continue;
    let u = byUser[ev.u];
    if (!u) u = byUser[ev.u] = { user: ev.u, role: ev.r, total: 0, logins: 0, pings: 0, first: ev.ts, last: ev.ts };
    u.total++;
    if (ev.type === "login") u.logins++;
    else u.pings++;
    if (ev.ts < u.first) u.first = ev.ts;
    if (ev.ts > u.last) u.last = ev.ts;
  }
  const users = Object.values(byUser).sort((x, y) => y.total - x.total);

  // 상세 타임라인(최신순, 최대 800건)
  const timeline = events.slice().sort((x, y) => y.ts - x.ts).slice(0, 800);

  return res.status(200).json({ ok: true, kvReady: true, total: events.length, users, events: timeline });
};
