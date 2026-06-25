// POST /api/ping → 사용 중 주기적 핑 1건 기록(활성 사용량 측정용). 로그인 세션 필요.
const { authFromReq } = require("../lib/auth");
const { logEvent } = require("../lib/kv");

module.exports = async (req, res) => {
  const a = authFromReq(req);
  if (!a) return res.status(401).json({ ok: false });
  try {
    await logEvent({ u: a.u, r: a.r, type: "ping", ts: Date.now() });
  } catch (e) {
    /* best-effort */
  }
  return res.status(200).json({ ok: true });
};
