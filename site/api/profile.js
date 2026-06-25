// POST /api/profile { newName?, newPassword? } → 본인 계정 이름(1회)·비밀번호(자유) 변경.
// 마스터는 이름 변경 불가(비번 변경은 허용). 변경분은 KV(cb:accounts)에 저장.
const { ACCOUNTS, authFromReq } = require("../lib/auth");
const { kvReady } = require("../lib/kv");
const { loadOverrides, saveOverrides, effective, validName } = require("../lib/accounts");

module.exports = async (req, res) => {
  if (req.method !== "POST") return res.status(405).json({ ok: false });
  const a = authFromReq(req);
  if (!a) return res.status(401).json({ ok: false, error: "로그인이 필요합니다." });
  if (!kvReady) return res.status(503).json({ ok: false, error: "저장소(KV) 미연동 — 변경 불가." });

  let body = req.body;
  if (typeof body === "string") {
    try { body = JSON.parse(body); } catch (e) { body = {}; }
  }
  const newName = body && typeof body.newName === "string" ? body.newName.trim() : "";
  const newPassword = body && typeof body.newPassword === "string" ? body.newPassword : "";

  const ov = await loadOverrides();
  const cur = effective(a.u, ov);
  const rec = Object.assign({}, ov[a.u]); // 기존 override 복사
  let changedName = false;

  // ── 비밀번호 변경(자유) ──
  if (newPassword) {
    if (newPassword.length < 1 || newPassword.length > 72) {
      return res.status(400).json({ ok: false, error: "비밀번호 길이가 올바르지 않습니다." });
    }
    rec.password = newPassword;
  }

  // ── 이름 변경(1회) ──
  if (newName && newName !== cur.loginId) {
    if (cur.role === "master") {
      return res.status(403).json({ ok: false, error: "마스터 계정은 이름을 바꿀 수 없습니다." });
    }
    if (cur.nameChanged) {
      return res.status(400).json({ ok: false, error: "이름은 한 번만 변경할 수 있습니다." });
    }
    if (!validName(newName)) {
      return res.status(400).json({ ok: false, error: "이름 형식 오류 (한글·영문·숫자·_ , 20자 이내)." });
    }
    // 중복 방지: 다른 슬롯의 원래 이름 + 현재 이름과 겹치면 안 됨
    const taken = new Set();
    for (const slot of Object.keys(ACCOUNTS)) {
      if (slot === a.u) continue;
      taken.add(slot);
      taken.add(effective(slot, ov).loginId);
    }
    if (taken.has(newName)) {
      return res.status(409).json({ ok: false, error: "이미 사용 중인 이름입니다." });
    }
    rec.loginId = newName;
    rec.nameChanged = true;
    changedName = true;
  }

  if (newPassword || changedName) {
    ov[a.u] = rec;
    await saveOverrides(ov);
  }

  const after = effective(a.u, ov);
  return res.status(200).json({
    ok: true,
    user: after.loginId,
    name: after.loginId,
    role: after.role,
    nameChanged: after.nameChanged,
    changedName,
    changedPassword: !!newPassword,
  });
};
