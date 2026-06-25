// 계정 override 관리 — 일반 계정이 스스로 바꾼 이름/비밀번호를 KV에 저장한다.
//  - 슬롯(A/B/kang)은 코드(ACCOUNTS)에 고정: role + 초기 비번(env).
//  - 변경분만 KV(cb:accounts)에 { loginId, password, nameChanged } 로 저장.
//  - 로그인은 KV override 우선 → 없으면 초기값(슬롯명/env비번).
//  - 로그는 슬롯 기준으로 쌓고, 표시할 때 현재 loginId 로 매핑(이름 바꾸면 과거분도 반영).
const { ACCOUNTS } = require("./auth");
const { kvGet, kvSet, kvReady } = require("./kv");

const ACCT_KEY = "cb:accounts";

async function loadOverrides() {
  if (!kvReady) return {};
  try {
    const raw = await kvGet(ACCT_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch (e) {
    return {};
  }
}
async function saveOverrides(obj) {
  await kvSet(ACCT_KEY, JSON.stringify(obj));
}

// 슬롯의 현재 유효 상태(override 우선, 없으면 초기값)
function effective(slot, ov) {
  const base = ACCOUNTS[slot] || {};
  const o = (ov && ov[slot]) || {};
  return {
    slot,
    role: base.role,
    loginId: o.loginId || slot, // 초기 로그인 id = 슬롯명
    password: o.password != null ? o.password : base.password,
    nameChanged: !!o.nameChanged,
  };
}

// 타이핑한 id + pw 로 슬롯 찾기
async function resolveLogin(id, pw) {
  const ov = await loadOverrides();
  for (const slot of Object.keys(ACCOUNTS)) {
    const e = effective(slot, ov);
    if (e.loginId === id && e.password && e.password === pw) return e;
  }
  return null;
}

// 슬롯 -> 현재 표시 이름 매핑(로그 표시용)
async function nameMap() {
  const ov = await loadOverrides();
  const m = {};
  for (const slot of Object.keys(ACCOUNTS)) m[slot] = effective(slot, ov).loginId;
  return m;
}

// 이름 형식 검증(한글/영문/숫자/_ , 1~20자)
function validName(nm) {
  return typeof nm === "string" && /^[A-Za-z0-9가-힣_]{1,20}$/.test(nm);
}

module.exports = {
  loadOverrides,
  saveOverrides,
  effective,
  resolveLogin,
  nameMap,
  validName,
};
