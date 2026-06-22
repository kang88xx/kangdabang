"""로컬 대시보드 서버 — '지금 갱신' 버튼을 받쳐주는 미니 백엔드.

브라우저(정적 HTML)는 텔레그램 수집(collect.py)을 직접 실행할 수 없으므로,
이 작은 로컬 서버가 버튼 클릭(POST /refresh)을 받아 수집→빌드를 대신 실행한다.

  GET  /          → data/dashboard.html (가장 최근 빌드된 대시보드)
  POST /refresh   → collect.py 실행 후 build_dashboard.py 실행, 결과를 JSON으로 반환

표준 라이브러리만 사용한다(추가 설치 불필요). 수집/빌드는 이 서버를 띄운
것과 동일한 파이썬(sys.executable, 보통 venv)으로 서브프로세스 실행한다.

사용법:
    source venv/bin/activate        # telethon 등이 깔린 환경
    python server.py                # 기본 http://127.0.0.1:8765
    PORT=9000 python server.py      # 포트 변경

이 서버는 로컬 전용이며 127.0.0.1 에만 바인딩한다(외부 노출 없음).
"""
import json
import os
import subprocess
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
DASHBOARD = DATA_DIR / "dashboard.html"
PY = sys.executable                      # server.py 를 띄운 동일 파이썬(venv 권장)
PORT = int(os.environ.get("PORT", "8765"))
REFRESH_TIMEOUT = 600                     # 수집+빌드 합산 최대 대기(초)

_refresh_lock = Lock()                    # 동시에 두 번 누르는 것 방지


def _run(args, timeout):
    """서브프로세스를 ROOT 에서 실행하고 (성공여부, 합쳐진 로그)를 반환."""
    proc = subprocess.run(
        [PY, *args], cwd=ROOT, timeout=timeout,
        stdin=subprocess.DEVNULL,         # 로그인 프롬프트로 인한 무한대기 방지
        capture_output=True, text=True,
    )
    log = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0, log.strip()


def do_refresh():
    """collect.py → build_dashboard.py 순차 실행. (ok, message) 반환."""
    if not _refresh_lock.acquire(blocking=False):
        return False, "이미 갱신이 진행 중입니다. 잠시 후 다시 시도하세요."
    try:
        ok, log = _run(["collect.py"], REFRESH_TIMEOUT)
        if not ok:
            return False, "collect.py 실행 실패\n\n" + log[-1500:]
        ok, log = _run(["build_dashboard.py"], 120)
        if not ok:
            return False, "build_dashboard.py 실행 실패\n\n" + log[-1500:]
        return True, "갱신 완료"
    except subprocess.TimeoutExpired:
        return False, "시간 초과 — 수집이 너무 오래 걸립니다."
    except Exception as e:                 # 세션 만료 등 예기치 못한 오류
        return False, f"{type(e).__name__}: {e}"
    finally:
        _refresh_lock.release()


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            if not DASHBOARD.exists():
                self._send(404, "대시보드가 아직 생성되지 않았습니다. "
                                "먼저 python build_dashboard.py 를 실행하세요.")
                return
            self._send(200, DASHBOARD.read_bytes())
        else:
            self._send(404, "Not found")

    def do_POST(self):
        if self.path.split("?", 1)[0] != "/refresh":
            self._send(404, json.dumps({"ok": False, "error": "Not found"}),
                       "application/json")
            return
        ok, msg = do_refresh()
        self._send(200 if ok else 500,
                   json.dumps({"ok": ok, "error": None if ok else msg},
                              ensure_ascii=False),
                   "application/json; charset=utf-8")

    def log_message(self, fmt, *args):    # 간결한 콘솔 로그
        sys.stderr.write("  %s — %s\n" % (self.address_string(), fmt % args))


def main():
    url = f"http://127.0.0.1:{PORT}/"
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"대시보드 서버 실행 중 → {url}")
    print(f"  파이썬: {PY}")
    print("  Ctrl+C 로 종료\n")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n종료합니다.")
        srv.shutdown()


if __name__ == "__main__":
    main()
