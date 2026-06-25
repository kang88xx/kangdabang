// GET /api/me → 현재 세션 확인(로그인 상태/역할/현재 이름/이름변경 가능여부).
const { authFromReq } = require("../lib/auth");
const { loadOverrides, effective } = require("../lib/accounts");

module.exports = async (req, res) => {
  const a = authFromReq(req);
  if (!a) return res.status(401).json({ ok: false });
  let e;
  try {
    e = effective(a.u, await loadOverrides());
  } catch (err) {
    e = { loginId: a.u, role: a.r, nameChanged: false };
  }
  return res.status(200).json({ ok: true, user: e.loginId, role: e.role, name: e.loginId, nameChanged: e.nameChanged });
};
