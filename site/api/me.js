// GET /api/me → 현재 세션 확인(로그인 상태/역할). 페이지 로드 시 재로그인 없이 복원용.
const { authFromReq } = require("../lib/auth");

module.exports = async (req, res) => {
  const a = authFromReq(req);
  if (!a) return res.status(401).json({ ok: false });
  return res.status(200).json({ ok: true, user: a.u, role: a.r });
};
