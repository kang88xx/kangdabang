// POST /api/login { username, password } → 세션 쿠키 발급 + 로그인 이벤트 기록
// 계정 override(KV) 우선 → 없으면 초기값(슬롯명/env비번)으로 인증.
const { makeToken, sessionCookie } = require("../lib/auth");
const { logEvent } = require("../lib/kv");
const { resolveLogin } = require("../lib/accounts");

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

  const e = await resolveLogin(username, password);
  if (!e) {
    return res.status(401).json({ ok: false, error: "아이디 또는 비밀번호가 올바르지 않습니다." });
  }
  // 토큰은 슬롯(불변)을 담는다 → 이름을 바꿔도 세션/로그가 일관.
  res.setHeader("Set-Cookie", sessionCookie(makeToken(e.slot)));
  try {
    await logEvent({ u: e.slot, r: e.role, type: "login", ts: Date.now() });
  } catch (err) {
    /* 로깅 실패는 로그인을 막지 않는다 */
  }
  return res.status(200).json({ ok: true, user: e.loginId, role: e.role, name: e.loginId, nameChanged: e.nameChanged });
};
