// Upstash Redis(=Vercel KV) REST API 래퍼 — 의존성 없음(Node 18+ 전역 fetch 사용).
// Vercel KV 연동 시 자동 주입되는 환경변수 KV_REST_API_URL / KV_REST_API_TOKEN 사용.
// 환경변수가 없으면 kvReady=false 로 동작하며, 로깅은 조용히 건너뛴다(사이트는 정상 작동).
const URL = process.env.KV_REST_API_URL;
const TOKEN = process.env.KV_REST_API_TOKEN;
const kvReady = !!(URL && TOKEN);
const LOG_KEY = "cb:accesslog";
const MAX_LOG = 9999; // 최근 1만 건 보관(누적, LTRIM)

async function cmd(args) {
  if (!kvReady) return null;
  const res = await fetch(URL, {
    method: "POST",
    headers: { Authorization: `Bearer ${TOKEN}`, "Content-Type": "application/json" },
    body: JSON.stringify(args),
  });
  if (!res.ok) throw new Error("kv " + res.status);
  const j = await res.json();
  return j.result;
}

// 접속/사용 이벤트 1건 누적 기록. ev = { u, r, type:'login'|'ping', ts }
async function logEvent(ev) {
  await cmd(["LPUSH", LOG_KEY, JSON.stringify(ev)]);
  await cmd(["LTRIM", LOG_KEY, "0", String(MAX_LOG)]);
}

// 전체 이벤트 읽기(최신순으로 저장돼 있음).
async function readEvents() {
  const arr = await cmd(["LRANGE", LOG_KEY, "0", "-1"]);
  return (arr || [])
    .map((s) => {
      try {
        return JSON.parse(s);
      } catch (e) {
        return null;
      }
    })
    .filter(Boolean);
}

module.exports = { kvReady, logEvent, readEvents };
