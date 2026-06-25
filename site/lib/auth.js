// 캉다방 대시보드 — 내부용 인증 (서버사이드).
// 계정/비밀번호는 함수(서버)에서만 검증하므로 클라이언트 HTML 소스에 노출되지 않는다.
// 비밀번호는 Vercel 환경변수(PW_KANG / PW_A / PW_B)로만 주입한다 — git에 평문을 남기지 않는다.
// 환경변수가 없으면 해당 계정은 로그인 불가(login.js에서 빈 비번 거부).
const crypto = require("crypto");

const ACCOUNTS = {
  kang: { password: process.env.PW_KANG, role: "master" },
  A: { password: process.env.PW_A, role: "user" },
  B: { password: process.env.PW_B, role: "user" },
};

// 토큰 서명용 비밀키. 보안을 위해 Vercel 환경변수 AUTH_SECRET 설정 권장.
const SECRET = process.env.AUTH_SECRET || "kangdabang-internal-secret-please-set-env";
const COOKIE_NAME = "cb_auth";
const MAX_AGE = 60 * 60 * 24 * 30; // 30일

function b64u(s) {
  return Buffer.from(s).toString("base64url");
}
function sign(payload) {
  return crypto.createHmac("sha256", SECRET).update(payload).digest("base64url");
}

function makeToken(user) {
  const payload = b64u(JSON.stringify({ u: user, r: ACCOUNTS[user].role, iat: Date.now() }));
  return payload + "." + sign(payload);
}

function verifyToken(token) {
  if (!token || token.indexOf(".") < 0) return null;
  const [payload, sig] = token.split(".");
  if (sign(payload) !== sig) return null; // 위조 차단
  try {
    const data = JSON.parse(Buffer.from(payload, "base64url").toString("utf8"));
    if (!ACCOUNTS[data.u]) return null;
    return data; // { u, r, iat }
  } catch (e) {
    return null;
  }
}

function parseCookies(req) {
  const h = req.headers.cookie || "";
  const out = {};
  h.split(";").forEach((c) => {
    const s = c.trim();
    const i = s.indexOf("=");
    if (i > 0) out[s.slice(0, i)] = decodeURIComponent(s.slice(i + 1));
  });
  return out;
}

function authFromReq(req) {
  return verifyToken(parseCookies(req)[COOKIE_NAME]);
}

function sessionCookie(token) {
  return `${COOKIE_NAME}=${token}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${MAX_AGE}`;
}
function clearCookie() {
  return `${COOKIE_NAME}=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0`;
}

module.exports = {
  ACCOUNTS,
  makeToken,
  verifyToken,
  authFromReq,
  sessionCookie,
  clearCookie,
};
