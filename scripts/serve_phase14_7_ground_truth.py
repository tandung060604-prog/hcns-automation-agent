#!/usr/bin/env python3
# ruff: noqa: E501
"""Serve a local-only, prediction-blinded Phase 14.7 Ground Truth UI."""

from __future__ import annotations

import argparse
import html
import json
import mimetypes
import threading
import urllib.parse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from hcns_agent.application.phase14_7_protocol import (
    apply_review_update,
    atomic_write_json,
    next_pending_case,
    public_review_case,
    review_progress,
    verify_hidden_snapshot,
)

HTML = r"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Phase 14.7 · Ground Truth kín</title>
<style>
:root{font-family:Inter,Segoe UI,Arial,sans-serif;color:#17332b;background:#edf3ef}
*{box-sizing:border-box}body{margin:0}.shell{max-width:1240px;margin:auto;padding:24px}
header{display:flex;justify-content:space-between;align-items:center;margin-bottom:18px}
h1{font-size:24px;margin:0}.badge{padding:8px 12px;border:1px solid #9eb7ac;border-radius:999px;background:#fff}
.notice{padding:12px 16px;border-left:4px solid #0d6b4f;background:#e3f2eb;margin-bottom:16px}
.grid{display:grid;grid-template-columns:minmax(420px,1fr) minmax(420px,1fr);gap:18px}
.card{background:#fff;border:1px solid #cad8d1;border-radius:14px;padding:18px;box-shadow:0 10px 32px #234c3b12}
.crop{min-height:180px;display:flex;align-items:center;justify-content:center;background:#f6f8f7;border-radius:10px;overflow:auto}
.crop img{max-width:100%;image-rendering:auto}.meta{font-size:13px;color:#53665e;margin:12px 0}
label{display:block;font-weight:650;margin-bottom:8px}textarea{width:100%;min-height:150px;padding:14px;font:20px/1.45 "Segoe UI",Arial,sans-serif;border:1px solid #9eb7ac;border-radius:10px}
.checks{margin:14px 0}.checks label{font-weight:400;margin:8px 0}
.actions{display:flex;gap:10px}.actions button{border:0;border-radius:9px;padding:12px 18px;font-weight:700;cursor:pointer}
#confirm{background:#0d6b4f;color:#fff;flex:1}#skip{background:#e9eeeb;color:#334b42}
button:disabled{opacity:.45;cursor:not-allowed}.page{width:100%;max-height:640px;object-fit:contain;background:#f6f8f7}
.error{color:#9b2727}.done{padding:48px;text-align:center}.muted{color:#60736b}
@media(max-width:900px){.grid{grid-template-columns:1fr}.shell{padding:14px}}
</style></head><body><div class="shell">
<header><div><h1>Ground Truth CCCD · Phase 14.7</h1><div class="muted">Phiên review độc lập, không hiển thị kết quả OCR</div></div><div id="progress" class="badge">Đang tải…</div></header>
<div class="notice">Prediction của PaddleOCR và hai VietOCR đã được khóa SHA‑256. Hãy nhập đúng những gì nhìn thấy trên ảnh; không suy đoán từ model.</div>
<main id="main" class="grid">
<section class="card"><div class="crop"><img id="crop" alt="Crop dòng cần xác nhận"></div><div id="meta" class="meta"></div>
<details><summary>Xem toàn bộ CCCD để lấy ngữ cảnh</summary><img id="page" class="page" alt="Trang nguồn"></details></section>
<section class="card"><label for="text">Ground Truth của dòng</label><textarea id="text" lang="vi" spellcheck="false" autocomplete="off" placeholder="Nhập nguyên văn từ ảnh crop…"></textarea>
<div class="checks"><label><input id="pixelCheck" type="checkbox"> Tôi đã đối chiếu trực tiếp với pixel ảnh</label>
<label><input id="accentCheck" type="checkbox"> Tôi đã kiểm tra chữ, số và toàn bộ dấu tiếng Việt</label></div>
<div id="error" class="error"></div><div class="actions"><button id="skip">Bỏ qua dòng không đọc được</button><button id="confirm" disabled>Xác nhận và chuyển tiếp</button></div></section>
</main></div>
<script>
let current=null;
const $=id=>document.getElementById(id);
function ready(){ $('confirm').disabled=!($('pixelCheck').checked&&$('accentCheck').checked&&$('text').value.trim()); }
['pixelCheck','accentCheck'].forEach(id=>$(id).addEventListener('change',ready));$('text').addEventListener('input',ready);
async function load(){
  $('error').textContent='';
  const status=await fetch('/api/status').then(r=>r.json());$('progress').textContent=`${status.reviewed}/${status.total} đã xác nhận · còn ${status.pending}`;
  const response=await fetch('/api/next');
  if(response.status===404){$('main').className='card done';$('main').innerHTML='<h2>Đã hoàn thành toàn bộ hàng đợi</h2><p>Ground Truth đã được lưu cục bộ. Không có prediction nào được hiển thị trong quá trình review.</p>';return}
  if(!response.ok)throw new Error(await response.text());
  current=await response.json();$('crop').src='/file/'+encodeURIComponent(current.cropPath);$('page').src='/file/'+encodeURIComponent(current.pageRenderPath);
  $('meta').textContent=`${current.documentId} · dòng ${current.lineIndex+1} · ${current.caseId}`;
  $('text').value='';$('pixelCheck').checked=false;$('accentCheck').checked=false;ready();$('text').focus();
}
async function save(status){
  $('confirm').disabled=true;$('skip').disabled=true;$('error').textContent='';
  try{
    const response=await fetch('/api/update',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({caseId:current.caseId,status,confirmedTranscription:$('text').value,reviewer:'local-reviewer'})});
    if(!response.ok)throw new Error((await response.json()).error||'Không thể lưu');
    $('skip').disabled=false;await load();
  }catch(error){$('error').textContent=error.message;$('skip').disabled=false;ready()}
}
$('confirm').onclick=()=>save('CONFIRMED');$('skip').onclick=()=>save('SKIPPED');load().catch(error=>$('error').textContent=error.message);
</script></body></html>"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    return parser.parse_args()


class ReviewStore:
    def __init__(self, dataset_root: Path) -> None:
        self.root = dataset_root.resolve()
        self.queue_path = (
            self.root
            / "ground_truth"
            / "private_phase14_7"
            / "review_queue_private.json"
        )
        self.status_path = (
            self.root
            / "predictions"
            / "PHASE14_7_HIDDEN_PREDICTIONS_STATUS.json"
        )
        self.private_path = (
            self.root
            / "predictions"
            / "phase14_7_hidden_predictions_private.json"
        )
        self.lock_path = (
            self.root / "locks" / "phase14_7_hidden_predictions.sha256"
        )
        self._lock = threading.Lock()
        self.verify()

    def read_json(self, path: Path) -> dict[str, Any]:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise TypeError("Expected a JSON object")
        return value

    def verify(self) -> None:
        queue = self.read_json(self.queue_path)
        status = self.read_json(self.status_path)
        verify_hidden_snapshot(
            queue=queue,
            status=status,
            private_artifact_path=self.private_path,
            lock_text=self.lock_path.read_text(encoding="ascii"),
        )

    def status(self) -> dict[str, int]:
        with self._lock:
            return review_progress(self.read_json(self.queue_path))

    def next_case(self) -> dict[str, Any] | None:
        with self._lock:
            queue = self.read_json(self.queue_path)
            case = next_pending_case(queue)
            return None if case is None else public_review_case(case)

    def update(self, payload: dict[str, Any]) -> dict[str, int]:
        with self._lock:
            queue = self.read_json(self.queue_path)
            apply_review_update(
                queue,
                case_id=str(payload.get("caseId", "")),
                status=str(payload.get("status", "")),
                transcription=str(payload.get("confirmedTranscription", "")),
                reviewer=str(payload.get("reviewer", "")),
                reviewed_at=datetime.now(timezone.utc).isoformat(),
            )
            progress = review_progress(queue)
            if progress["pending"] == 0:
                queue["groundTruthStatus"] = (
                    "USER_CONFIRMED_HELD_OUT_GROUND_TRUTH"
                )
                queue["confirmedAt"] = datetime.now(timezone.utc).isoformat()
            atomic_write_json(self.queue_path, queue)
            return progress

    def resolve_file(self, encoded_relative: str) -> Path:
        relative = urllib.parse.unquote(encoded_relative)
        candidate = (self.root / relative).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise PermissionError("Path escapes dataset root")
        allowed = (
            self.root / "ground_truth" / "private_phase14_7"
        ).resolve()
        if candidate != allowed and allowed not in candidate.parents:
            raise PermissionError("Only private Phase 14.7 review images are served")
        if not candidate.is_file():
            raise FileNotFoundError("Review image not found")
        return candidate


def handler_factory(store: ReviewStore) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "Phase14Review/1.0"

        def log_message(self, format: str, *args: Any) -> None:
            return

        def send_value(
            self,
            status: int,
            value: bytes | str | dict[str, Any],
            content_type: str = "application/json; charset=utf-8",
        ) -> None:
            if isinstance(value, dict):
                body = json.dumps(value, ensure_ascii=False).encode("utf-8")
            elif isinstance(value, str):
                body = value.encode("utf-8")
            else:
                body = value
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            try:
                if self.path in {"/", "/index.html"}:
                    self.send_value(200, HTML, "text/html; charset=utf-8")
                    return
                if self.path == "/api/status":
                    self.send_value(200, store.status())
                    return
                if self.path == "/api/next":
                    case = store.next_case()
                    if case is None:
                        self.send_value(404, {"done": True})
                    else:
                        self.send_value(200, case)
                    return
                if self.path.startswith("/file/"):
                    path = store.resolve_file(self.path[len("/file/") :])
                    self.send_value(
                        200,
                        path.read_bytes(),
                        mimetypes.guess_type(path.name)[0]
                        or "application/octet-stream",
                    )
                    return
                self.send_value(404, {"error": "not found"})
            except (FileNotFoundError, PermissionError, ValueError) as exc:
                self.send_value(400, {"error": html.escape(str(exc))})

        def do_POST(self) -> None:
            if self.path != "/api/update":
                self.send_value(404, {"error": "not found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 64 * 1024:
                    raise ValueError("Invalid request size")
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("Expected a JSON object")
                self.send_value(200, {"ok": True, **store.update(payload)})
            except (KeyError, TypeError, ValueError) as exc:
                self.send_value(400, {"error": str(exc)})

    return Handler


def main() -> int:
    args = parse_args()
    store = ReviewStore(args.dataset_root)
    server = ThreadingHTTPServer(
        (args.host, args.port),
        handler_factory(store),
    )
    print(
        f"Phase 14.7 Ground Truth ready at "
        f"http://{args.host}:{args.port}/ (local only)"
    )
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
