// POST /api/login { username, password } → 세션 쿠키 발급 + 로그인 이벤트 기록
const { ACCOUNTS, makeToken, sessionCookie } = require("../lib/auth");
const { logEvent } = require("../lib/kv");

module.exports = async (req, res) => {
  if (req.method !== "POST") return res.status(405).json({ ok: false });
  let body = req.body;
  if (typeof body === "string") {
    try {
      body = JSON.parse(body);
    } catch (e) {
      body = {};
    }
  }
  const username = (body && body.username || "").trim();
  const password = body && body.password || "";
  const acc = ACCOUNTS[username];
  // acc.password 가 비어있으면(=환경변수 미설정) 해당 계정은 로그인 불가.
  if (!acc || !acc.password || acc.password !== password) {
    return res.status(401).json({ ok: false, error: "아이디 또는 비밀번호가 올바르지 않습니다." });
  }
  res.setHeader("Set-Cookie", sessionCookie(makeToken(username)));
  try {
    await logEvent({ u: username, r: acc.role, type: "login", ts: Date.now() });
  } catch (e) {
    /* 로깅 실패는 로그인을 막지 않는다 */
  }
  return res.status(200).json({ ok: true, user: username, role: acc.role });
};
