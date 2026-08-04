#!/usr/bin/env python3
"""Serve the local-only, prediction-blinded Phase 16 Ground Truth UI."""

# Embedded HTML/CSS/JS is intentionally kept in one local-only server artifact.
# ruff: noqa: E501

from __future__ import annotations

import argparse
import ipaddress
import json
import mimetypes
import threading
import urllib.parse
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from hcns_agent.application.phase16_heldout import (
    CONFIRMED,
    PENDING,
    SKIPPED,
    validate_review_queue,
)

HTML = """<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Phase 16 · Ground Truth kín</title>
<style>
:root{font-family:Inter,Segoe UI,sans-serif;color:#17211d;background:#edf2ee}
*{box-sizing:border-box}body{margin:0}header{padding:18px 28px;background:#123f32;color:#fff}
header b{font-size:19px}.sub{opacity:.78;font-size:13px;margin-top:4px}
main{max-width:1500px;margin:auto;padding:20px}.toolbar,.panel{background:#fff;border:1px solid #cbd8d1;border-radius:14px}
.toolbar{display:flex;gap:12px;align-items:center;padding:12px 16px;margin-bottom:16px}
.toolbar button,.save{border:0;border-radius:9px;padding:11px 16px;font-weight:700;cursor:pointer}
.toolbar button{background:#e4ece7;color:#123f32}.badge{margin-left:auto;font-weight:700;color:#17644d}
.grid{display:grid;grid-template-columns:minmax(420px,1.1fr) minmax(420px,.9fr);gap:16px}
.panel{padding:16px}.meta{display:flex;justify-content:space-between;gap:12px;margin-bottom:12px}
.meta strong{font-size:18px}.muted{color:#65736d;font-size:13px}
#preview{width:100%;height:72vh;border:1px solid #d9e1dc;border-radius:10px;background:#f7f9f7}
.native{height:72vh;display:grid;place-items:center;text-align:center;padding:40px;border:1px dashed #afbeb6;border-radius:10px}
.native a{display:inline-block;margin-top:12px;color:#126044;font-weight:700}
.field{display:grid;grid-template-columns:160px 1fr auto;gap:10px;align-items:center;margin:9px 0}
.field label{font-size:13px;font-weight:700}.field input[type=text]{width:100%;padding:10px;border:1px solid #bdcbc4;border-radius:8px}
.table-editor{margin-top:16px;padding-top:14px;border-top:1px solid #d9e1dc}.table-editor textarea{width:100%;min-height:230px;padding:10px;border:1px solid #bdcbc4;border-radius:8px;font:12px Consolas,monospace;white-space:pre}
.table-help{font-size:12px;color:#65736d;line-height:1.5;margin:7px 0}
.skip{font-size:12px;white-space:nowrap}.save{width:100%;margin-top:14px;background:#17644d;color:#fff;font-size:16px}
.guide{margin:12px 0;padding:12px;border-left:4px solid #b77a16;background:#fff7e8;color:#66440d;font-size:13px;line-height:1.5}
.results{margin-top:16px}.metric-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:12px}.metric{padding:12px;border:1px solid #d9e1dc;border-radius:9px}.metric b{display:block;font-size:20px;margin-top:5px}.decision{color:#9b2f2f}
#message{min-height:24px;padding-top:9px;color:#9b2f2f}.done{color:#17644d!important}
@media(max-width:900px){.grid{grid-template-columns:1fr}#preview,.native{height:55vh}.field{grid-template-columns:1fr}.badge{margin-left:0}.metric-grid{grid-template-columns:repeat(2,1fr)}}
</style>
</head>
<body>
<header><b>HR Document Intelligence · Phase 16</b><div class="sub">Ground Truth kín · prediction không được tải vào trang này</div></header>
<main>
  <div class="toolbar"><button id="prev">← Trước</button><button id="next">Sau →</button><span id="position"></span><span class="badge" id="progress"></span></div>
  <div class="grid">
    <section class="panel"><div class="meta"><div><strong id="docId"></strong><div class="muted" id="family"></div></div><div class="muted" id="sourceName"></div></div><div id="viewer"></div></section>
    <section class="panel"><h2>Ground Truth theo trường</h2><div class="muted">Chỉ nhập giá trị nhìn thấy trực tiếp; không suy luận từ ngữ cảnh. Chọn “Không có” nếu tài liệu không chứa trường đó.</div><div class="guide" id="guide"></div><div id="fields"></div><button class="save" id="save">Xác nhận tài liệu và chuyển tiếp</button><div id="message"></div></section>
  </div>
  <section class="panel results" id="resultsPanel" hidden><h2>Kết quả held-out Phase 16</h2><div class="muted">Báo cáo aggregate sau khi Ground Truth 18/18 được khóa; không hiển thị raw prediction hoặc PII.</div><div class="metric-grid" id="resultMetrics"></div></section>
</main>
<script>
const labels={fullName:'Họ và tên',headline:'Tiêu đề nghề nghiệp',email:'Email',phoneNumber:'Số điện thoại',address:'Địa chỉ',documentTitle:'Tên tài liệu',requestNumber:'Số đơn',employeeName:'Tên nhân viên',employeeId:'Mã nhân viên',department:'Phòng ban',jobTitle:'Chức danh/vị trí công việc',reason:'Lý do',startDate:'Ngày bắt đầu',endDate:'Ngày kết thúc',documentNumber:'Số văn bản',action:'Loại/Nội dung văn bản',salary:'Mức lương',effectiveDate:'Ngày hiệu lực',credentialName:'Tên bằng/chứng chỉ',major:'Chuyên ngành',institution:'Đơn vị cấp',issueDate:'Ngày cấp',graduationYear:'Năm tốt nghiệp',classification:'Xếp loại',tableTitle:'Tên bảng',period:'Kỳ dữ liệu',rowCount:'Số dòng',columnCount:'Số cột',organization:'Tổ chức/Công ty'};
const familyGuides={CONTRACT_DECISION:'Với hợp đồng, “Loại/Nội dung văn bản” là tiêu đề hoặc loại hợp đồng nhìn thấy trực tiếp. Chỉ nhập chức danh khi tài liệu nêu rõ vị trí/chức vụ làm việc; trình độ học vấn hoặc chuyên môn không phải chức danh. Ngày ở phần đầu văn bản không tự động là ngày bắt đầu hay ngày hiệu lực.'};
let state={documents:[]},index=0,current=null;
const $=id=>document.getElementById(id);
async function json(url,options){const r=await fetch(url,options);const v=await r.json();if(!r.ok)throw new Error(v.error||'Lỗi máy chủ');return v}
async function loadState(){state=await json('/api/state');const pending=state.documents.findIndex(d=>d.status!=='CONFIRMED');index=pending<0?0:pending;await load();await loadResults()}
async function loadResults(){try{const result=await json('/api/results'),overall=result.overall||{},items=[['Quyết định',result.decision?.controlledPilot||'—','decision'],['Phân loại',percent(overall.classificationAccuracy),''],['Field Exact Match',percent(overall.fieldExactMatchRate),''],['Field Completeness',percent(overall.fieldCompleteness),''],['Table Cell Exact',percent(overall.tableExactCellRate),''],['Table Completeness',percent(overall.tableCompleteness),''],['CER',percent(overall.cer),''],['Sensitive false acceptance',String(result.sensitiveFieldFalseAcceptanceCount??'—'),'decision']];$('resultMetrics').innerHTML=items.map(([label,value,cls])=>`<div class="metric"><span class="muted">${label}</span><b class="${cls}">${value}</b></div>`).join('');$('resultsPanel').hidden=false}catch(e){$('resultsPanel').hidden=true}}
function percent(value){return typeof value==='number'?`${(value*100).toFixed(2)}%`:'—'}
async function load(){if(!state.documents.length)return;current=await json('/api/document?id='+encodeURIComponent(state.documents[index].documentId));$('docId').textContent=current.documentId;$('family').textContent=current.reviewProfile||current.documentFamily;$('sourceName').textContent=current.sourceName;$('position').textContent=`${index+1}/${state.documents.length}`;$('progress').textContent=`${state.confirmed}/${state.total} đã xác nhận`;$('guide').textContent=familyGuides[current.reviewProfile]||familyGuides[current.documentFamily]||'Chỉ nhập dữ liệu có bằng chứng trực tiếp trong tài liệu; trường không xuất hiện phải chọn “Không có”.';
 const ext=current.sourceExtension.toLowerCase(),url='/source?id='+encodeURIComponent(current.documentId),viewer=$('viewer');viewer.innerHTML='';
 if(['.jpg','.jpeg','.png','.pdf'].includes(ext)){const el=document.createElement(ext==='.pdf'?'iframe':'img');el.id='preview';el.src=url;el.alt='Tài liệu nguồn';viewer.appendChild(el)}
 else{viewer.innerHTML=`<div class="native"><div><b>Định dạng ${ext.slice(1).toUpperCase()}</b><p>Mở file gốc bằng ứng dụng local để đối chiếu.</p><a href="${url}">Mở / tải tài liệu nguồn</a></div></div>`}
 const fields=$('fields');fields.innerHTML='';Object.entries(current.fields).forEach(([name,field])=>{const row=document.createElement('div');row.className='field';row.innerHTML=`<label>${labels[name]||name}</label><input type="text" data-name="${name}"><label class="skip"><input type="checkbox" data-skip="${name}"> Không có</label>`;const input=row.querySelector('input[type=text]'),skip=row.querySelector('input[type=checkbox]');input.value=field.value||'';skip.checked=field.status==='SKIPPED';input.disabled=skip.checked;skip.onchange=()=>{input.disabled=skip.checked;if(skip.checked)input.value=''};fields.appendChild(row)});

 $('message').textContent='';$('message').className=''}
async function save(){try{const fields={},skipped=[];document.querySelectorAll('[data-name]').forEach(el=>fields[el.dataset.name]=el.value);document.querySelectorAll('[data-skip]:checked').forEach(el=>skipped.push(el.dataset.skip));const payload={documentId:current.documentId,fields,skipped};await json('/api/update',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});$('message').textContent='Đã lưu cục bộ';$('message').className='done';await loadState()}catch(e){$('message').textContent=e.message}}
$('prev').onclick=()=>{index=(index-1+state.documents.length)%state.documents.length;load()};$('next').onclick=()=>{index=(index+1)%state.documents.length;load()};$('save').onclick=save;loadState().catch(e=>$('message').textContent=e.message);
</script>
</body></html>"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


class ReviewStore:
    def __init__(self, dataset_root: Path) -> None:
        self.root = dataset_root.resolve()
        self.queue_path = self.root / "ground_truth" / "review_queue_private.json"
        self.status_path = (
            self.root / "predictions" / "HIDDEN_PREDICTIONS_STATUS.json"
        )
        self.report_path = self.root / "reports" / "PHASE16_HELDOUT_RESULTS.json"
        self._lock = threading.Lock()
        self.verify()

    @staticmethod
    def read_json(path: Path) -> dict[str, Any]:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(value, dict):
            raise TypeError("Expected a JSON object")
        return value

    def verify(self) -> None:
        queue = self.read_json(self.queue_path)
        validate_review_queue(queue)
        status = self.read_json(self.status_path)
        if status.get("status") != "BLINDED_PREDICTIONS_READY":
            raise ValueError("Hidden predictions are not sealed")
        if status.get("predictionsHiddenDuringReview") is not True:
            raise ValueError("Predictions are not marked hidden")
        if status.get("datasetDigest") != queue.get("datasetDigest"):
            raise ValueError("Ground Truth queue and predictions do not match")

    def state(self) -> dict[str, Any]:
        with self._lock:
            queue = self.read_json(self.queue_path)
            documents = [
                {
                    "documentId": document["documentId"],
                    "documentFamily": document["documentFamily"],
                    "status": document["status"],
                }
                for document in queue["documents"]
            ]
            confirmed = sum(
                document["status"] == CONFIRMED for document in queue["documents"]
            )
            return {
                "total": len(documents),
                "confirmed": confirmed,
                "pending": len(documents) - confirmed,
                "documents": documents,
            }

    def results(self) -> dict[str, Any]:
        with self._lock:
            report = self.read_json(self.report_path)
            if report.get("containsRealPII") is not False:
                raise ValueError("Phase 16 report is not aggregate-only")
            allowed = {
                "schemaVersion",
                "evaluatedAt",
                "documentCount",
                "overall",
                "byFamily",
                "sensitiveFieldFalseAcceptanceCount",
                "decision",
                "evaluationRunCount",
                "thresholdRetuned",
                "predictionsWereHidden",
            }
            return {key: report[key] for key in allowed if key in report}

    def document(self, document_id: str) -> dict[str, Any]:
        with self._lock:
            queue = self.read_json(self.queue_path)
            document = next(
                (
                    item
                    for item in queue["documents"]
                    if item["documentId"] == document_id
                ),
                None,
            )
            if document is None:
                raise KeyError("Unknown document")
            source = self.resolve_source(document)
            return {
                "documentId": document["documentId"],
                "documentFamily": document["documentFamily"],
                "documentType": document.get("documentType"),
                "reviewProfile": document.get("reviewProfile"),
                "status": document["status"],
                "sourceName": source.name,
                "sourceExtension": source.suffix,
                "fields": document["fields"],
                "tables": document.get("tables"),
                "predictionsVisibleDuringReview": False,
            }

    def update(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            queue = self.read_json(self.queue_path)
            document_id = str(payload.get("documentId") or "")
            document = next(
                (
                    item
                    for item in queue["documents"]
                    if item["documentId"] == document_id
                ),
                None,
            )
            if document is None:
                raise KeyError("Unknown document")
            values = payload.get("fields")
            if not isinstance(values, dict) or set(values) != set(document["fields"]):
                raise ValueError("Ground Truth field set is incomplete")
            skipped_value = payload.get("skipped") or []
            if not isinstance(skipped_value, list):
                raise ValueError("Skipped fields must be a list")
            skipped = {str(name) for name in skipped_value}
            if not skipped <= set(document["fields"]):
                raise ValueError("Unknown skipped field")
            for name in document["fields"]:
                value = str(values[name] or "").strip()
                if name in skipped:
                    document["fields"][name] = {"status": SKIPPED, "value": ""}
                elif value:
                    document["fields"][name] = {
                        "status": CONFIRMED,
                        "value": value,
                    }
                else:
                    raise ValueError(
                        f"Field {name} requires a value or 'Không có'"
                    )
            document["status"] = CONFIRMED
            document["reviewedAt"] = utc_now()
            if all(item["status"] == CONFIRMED for item in queue["documents"]):
                queue["groundTruthStatus"] = (
                    "USER_REVIEWED_HELD_OUT_GROUND_TRUTH"
                )
                queue["reviewedAt"] = utc_now()
            else:
                queue["groundTruthStatus"] = PENDING
            validate_review_queue(queue)
            atomic_write_json(self.queue_path, queue)
            return self.state_unlocked(queue)

    @staticmethod
    def state_unlocked(queue: dict[str, Any]) -> dict[str, int]:
        confirmed = sum(
            document["status"] == CONFIRMED for document in queue["documents"]
        )
        return {
            "total": len(queue["documents"]),
            "confirmed": confirmed,
            "pending": len(queue["documents"]) - confirmed,
        }

    def source_for_id(self, document_id: str) -> Path:
        with self._lock:
            queue = self.read_json(self.queue_path)
            document = next(
                (
                    item
                    for item in queue["documents"]
                    if item["documentId"] == document_id
                ),
                None,
            )
            if document is None:
                raise KeyError("Unknown document")
            return self.resolve_source(document)

    def resolve_source(self, document: dict[str, Any]) -> Path:
        candidate = (self.root / str(document["sourcePath"])).resolve()
        source_root = (self.root / "source").resolve()
        if candidate != source_root and source_root not in candidate.parents:
            raise PermissionError("Source path escapes the held-out source root")
        if not candidate.is_file():
            raise FileNotFoundError("Source document is missing")
        return candidate


def handler_factory(store: ReviewStore) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "Phase16Review/1.0"

        def log_message(self, format: str, *args: Any) -> None:
            return

        def local_client(self) -> bool:
            try:
                return ipaddress.ip_address(self.client_address[0]).is_loopback
            except ValueError:
                return False

        def send_value(
            self,
            status: int,
            value: bytes | str | dict[str, Any],
            content_type: str = "application/json; charset=utf-8",
            disposition: str | None = None,
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
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'")
            if disposition:
                self.send_header("Content-Disposition", disposition)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if not self.local_client():
                self.send_value(403, {"error": "local access only"})
                return
            try:
                parsed = urllib.parse.urlparse(self.path)
                query = urllib.parse.parse_qs(parsed.query)
                if parsed.path in {"/", "/index.html"}:
                    self.send_value(200, HTML, "text/html; charset=utf-8")
                elif parsed.path == "/api/state":
                    self.send_value(200, store.state())
                elif parsed.path == "/api/results":
                    self.send_value(200, store.results())
                elif parsed.path == "/api/document":
                    self.send_value(200, store.document(query.get("id", [""])[0]))
                elif parsed.path == "/source":
                    path = store.source_for_id(query.get("id", [""])[0])
                    inline = path.suffix.casefold() in {
                        ".jpg",
                        ".jpeg",
                        ".png",
                        ".pdf",
                    }
                    disposition = (
                        f'inline; filename="{path.name}"'
                        if inline
                        else f'attachment; filename="{path.name}"'
                    )
                    self.send_value(
                        200,
                        path.read_bytes(),
                        mimetypes.guess_type(path.name)[0]
                        or "application/octet-stream",
                        disposition,
                    )
                else:
                    self.send_value(404, {"error": "not found"})
            except (FileNotFoundError, KeyError, PermissionError, ValueError) as exc:
                self.send_value(400, {"error": str(exc)})

        def do_POST(self) -> None:
            if not self.local_client():
                self.send_value(403, {"error": "local access only"})
                return
            if self.path != "/api/update":
                self.send_value(404, {"error": "not found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 128 * 1024:
                    raise ValueError("Invalid request size")
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("Expected a JSON object")
                self.send_value(200, {"ok": True, **store.update(payload)})
            except (KeyError, TypeError, ValueError) as exc:
                self.send_value(400, {"error": str(exc)})

    return Handler


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8777)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.host not in {"127.0.0.1", "::1", "localhost"}:
        raise ValueError("Phase 16 Ground Truth server must remain local-only")
    store = ReviewStore(args.dataset_root)
    server = ThreadingHTTPServer((args.host, args.port), handler_factory(store))
    print(
        f"Phase 16 Ground Truth ready at "
        f"http://{args.host}:{args.port}/ (predictions hidden)"
    )
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
