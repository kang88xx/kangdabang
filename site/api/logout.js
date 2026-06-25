// POST /api/logout → 세션 쿠키 제거(계정 전환용)
const { clearCookie } = require("../lib/auth");

module.exports = async (req, res) => {
  res.setHeader("Set-Cookie", clearCookie());
  return res.status(200).json({ ok: true });
};
