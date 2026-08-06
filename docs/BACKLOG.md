# Backlog

> Backlog có một task `IN_PROGRESS` tại mỗi workstream. Chi tiết trạng thái thực
> tế nằm ở [PROJECT_STATE.md](PROJECT_STATE.md); dữ liệu private không ghi ở đây.

| ID | Trạng thái | Mục tiêu | Phụ thuộc | Ưu tiên |
|---|---|---|---|---|
| LONGRUN-MAINT-001 | DONE | Chốt checkpoint, archive evidence cũ và kiểm tra nhất quán state/handoff | Current branch state | P1 |
| OCR-HO-V2-011 | REVIEW | Deterministic address ROI replay failed exact-improvement/DER gate; keep shadow-only and restore secondary recognizer runtime before next replay | OCR-HO-V2-009 | P0 |
| OCR-HO-V2-012 | REVIEW | Restored full secondary recognizers; v11.9.1 passes development gate but remains shadow-only pending explicit promotion decision | OCR-HO-V2-011 | P0 |
| OCR-HO-V2-013 | REVIEW | Promotion review and localhost canary for v11.9.1; no primary-runtime promotion until all 15 local shadow decisions are recorded | OCR-HO-V2-012 | P0 |
| OCR-EVIDENCE-LOCAL-001 | DONE (LOCAL HOLD) | Unified localhost evidence view for real prediction vs Ground Truth; keep Camunda closed until prediction artifacts and OCR gates are complete | OCR-HO-V2-013, DATA-10-R1 | P0 |
| DATA-13 | DONE (HOLD) | OCR scope allowlist and evaluate-once artifact for visual HR families; promotion remains disabled | DATA-12 | P0 |
| DATA-14 | DONE (DEV HOLD) | Recover CV/contract/certificate fields with shared layout-aware parsers; keep visual OCR manual-review and evaluate only on a new development split | DATA-13 | P0 |
| DATA-15 | DONE (DEV HOLD) | Seal independent Ground Truth for the user-provided Contract/CV/IELTS development split and run a separate aggregate comparison; promotion remains disabled | DATA-14 | P0 |
| OCR-HO-V2-007 | REVIEW | Tinh chinh ROI que quan/noi thuong tru va Unicode; replay development khong co exact improvement nen giu shadow | OCR-HO-V2-006 | P0 |
| OCR-HO-V2-008 | DONE | Token-alignment cho address đạt development gate; giữ shadow-only, chưa promote hoặc đổi held-out | OCR-HO-V2-007 | P0 |
| OCR-HO-V2-001 | REVIEW | Đã seal prediction ẩn trên 15 CCCD held-out; chờ xác nhận Ground Truth để evaluate-once | Manifest v2, policy 11.6 | P0 |
| OCR-HO-V2-002 | DONE | Review Ground Truth độc lập, loại ảnh mặt sau, khóa queue và evaluate đúng một lần trên 14 ảnh | OCR-HO-V2-001 | P0 |
| OCR-HO-V2-003 | DONE | Local inspector đối chiếu Ground Truth và output Phase 11.5/11.6 sau evaluate-once | OCR-HO-V2-002 | P1 |
| OCR-HO-V2-004 | REVIEW | OCR-HO v1.1 fixed-0° parser boundary fixes; development regression gate failed, so not promoted | OCR-HO-V2-003 | P0 |
| TF-P1-001 | DONE | Template-first cho đơn nghỉ phép và tăng ca DOCX | 14 mẫu synthetic local | P0 |
| TF-P1-002 | DONE | Commit/push Template-first, chạy API local và live smoke hai DOCX gốc | TF-P1-001 | P0 |
| TF-P1-003 | DONE | Tích hợp Template-first vào OCR Lab localhost và hiển thị kết quả trích xuất | TF-P1-002 | P0 |
| TF-P1-004 | DONE | Cập nhật README theo các mẫu HCNS chuẩn, giữ nguyên tài liệu năng lực cũ | TF-P1-003 | P0 |
| TF-P1-005 | DONE | Ẩn held-out khỏi localhost dành cho mentor, giữ private feature flag | TF-P1-003 | P0 |
| TF-P1-006 | DONE | Evidence chỉ hiển thị đơn nghỉ phép/tăng ca và CCCD, giữ panel metadata | TF-P1-005 | P0 |
| TF-P1-007 | DONE | Thiết kế lại product showcase bên phải hero | TF-P1-006 | P1 |
| TF-P1-008 | DONE | Redesign landing theo tham chiếu, dùng trạng thái sản phẩm thật | TF-P1-007 | P1 |
| TF-P2-001 | PLANNED | Pilot Human Review qua Camunda User Task | TF-P1-001 | P1 |
| TF-P2-002 | IN_PROGRESS | DOCX/PDF/ảnh/scan cho hai template; native pass, OCR text gate mở | TF-P1-001 và dữ liệu được phê duyệt | P0 |
| TF-P2-002B | DONE | Vietnamese OCR Candidate Evaluation & Field Recovery cho field động còn sai | TF-P2-002A checkpoint, TF-P2-003A governance | P0 |
| TF-P2-003A | DONE | Version Governance và UAT Harness cho hai biểu mẫu | TF-P2-002A checkpoint | P1 |
| TF-P2-003B | DONE | Execute UAT và quản trị phiên bản trên bốn định dạng | TF-P2-002B đạt 44/54 | P1 |
| TF-P2-004 | BLOCKED | Paddle OCR fidelity candidates không đạt gate; superseded by evidence selection | TF-P2-003B, parser boundary checkpoint | P0 |
| TF-P2-005 | DONE | Evidence-driven OCR Backend Selection và controlled EasyOCR promotion | TF-P2-004 candidate evidence | P0 |
| WEEKLY-REPORT-2026-W31 | DONE | Audit và báo cáo mentor đã khử định danh | Evidence local được cấp quyền | P1 |
| TF-P2-003 | BLOCKED | UAT và quản trị phiên bản hai biểu mẫu | TF-P2-002 đạt gate | P1 |
| M4-CAM-001 | DONE | Khóa closed-set Camunda cho đơn nghỉ phép/tăng ca; đồng bộ BPMN, allowlist và guard trước extraction | TF-P2-005 | P1 |
| M4-CAM-002 | DONE | Bind Template-first pipeline/private idempotent store vào External Task worker local | M4-CAM-001 | P1 |
| M4-CAM-003 | DONE | Projection đủ tám DMN input và routing shadow an toàn | M4-CAM-002 | P1 |
| M4-CAM-004 | DONE | Deploy BPMN/DMN và smoke hai loại tài liệu trên Camunda 7.13 local | M4-CAM-003, môi trường/quyền deploy | P1 |
| M4-CAM-005 | DONE | Hoàn thiện User Task, correction/re-upload loop, revalidation và reviewer audit | M4-CAM-004 | P1 |
| M4-CAM-006 | DONE | Dry-run 10/10 scenario; approve shadow pilot có điều kiện, giữ shadow routing và side effect giả lập | M4-CAM-005 | P1 |
| M5-CAM-001 | READY | Mở closed set đúng sáu loại, thêm bốn template review-first, gỡ Timesheet, giữ shadow-only và gate business/privacy/rollback | M4-CAM-006 | P0 |
| M5-CAM-002 | PLANNED | Hoàn tất Ground Truth/cohort được cấp quyền cho CV, IELTS, probation contract và CCCD mặt trước; evaluate-once aggregate-only | M5-CAM-001 | P0 |
| DATA-00 | DONE | Pin external source, isolate staging and reconcile dataset workstream | User-directed dataset commit | P0 |
| DATA-01 | DONE (PUBLIC TEST PROFILE) | Record explicit public/synthetic classification; keep unknown/private sources fail-closed | DATA-00 | P0 |
| DATA-02 | DONE | Build SHA-256/page-count inventory outside Git | DATA-01 | P0 |
| DATA-03 | DONE | Map CV/contract/certificate to generic IDP; add native TXT and versioned drift checks | DATA-02 | P0 |
| DATA-04 | DONE (HOLD) | Run EasyOCR aggregate-only pilot over 13 documents / 17 pages | DATA-03 | P0 |
| DATA-05 | DONE | Add synthetic inventory/mapping/parser regression coverage and checkpoint evidence | DATA-04 | P1 |
| DATA-06 | DONE | Add certificate schema and prediction-blind Ground Truth review artifact | DATA-05 | P0 |
| DATA-07 | DONE | Localhost review UI/API for source preview, prediction-blind editing and private Ground Truth persistence | DATA-06 approved | P0 |
| DATA-08 | DONE | Independent review and SEALED Ground Truth for active contract/CV/IELTS scope; defer CV text/PPTX and real-world contract images | DATA-07 | P0 |
| DATA-09 | DONE (HOLD) | Normalize typed HR fields and run post-seal aggregate pilot without opening predictions | DATA-06, DATA-08 | P0 |
| DATA-09-R1 | DONE (HOLD) | Rebuild typed projection and aggregate-only pilot for the sealed 2026-08-04 image expansion | DATA-08 sealed expansion | P0 |
| DATA-10 | APPROVED | Approve typed canonical projection for read-only downstream use; keep model/promotion gates disabled | DATA-09 | P0 |
| DATA-10-R1 | DONE (APPROVED, READ-ONLY) | Freeze the DATA-09-R1 typed projection for read-only downstream use; keep promotion disabled | DATA-09-R1 | P0 |
| DATA-11 | DONE (READ-ONLY) | Expose approved typed projection through loopback GET-only API and JSON/CSV export | DATA-10 | P0 |
| DATA-12 | DONE (HOLD) | Generate private predictions for active CV/IELTS/contract inputs and evaluate one aggregate-only prediction-vs-Ground-Truth report on localhost | DATA-10-R1 | P0 |

## DATA-00..DATA-05 acceptance criteria

- `DATA-00`: source commit is pinned; raw source is staged outside this Git
  repository; existing CCCD WIP remains untouched.
- `DATA-01`: governance fields are explicit; this synthetic repository source
  uses a user-directed `PUBLIC` + `APPROVED` test profile, while unknown/private
  sources still fail closed.
- `DATA-02`: every source has stable case ID, SHA-256, format and page count;
  inventory digest changes on any source drift.
- `DATA-03`: every category maps to a generic `DocumentType` or is rejected with
  a reason; Template-first v1 is never used as a fallback; TXT is native and
  PPTX remains `PARTIAL`.
- `DATA-04`: all staged documents run through the local pipeline; report is
  aggregate-only, OCR remains review-only, and no promotion occurs without
  approved Ground Truth.
- `DATA-05`: synthetic tests cover README exclusion, digest/page drift, mapping
  version drift, TXT routing and schema validation. Required checks are
  `pytest`, `ruff`, `mypy`, `compileall` and `check_repository.py`.
- `DATA-06`: certificate mapping has a versioned schema; the private review
  artifact covers every case/field with source digests, no model values, and
  remains `DRAFT` until an independent reviewer confirms it.
- `DATA-07`: localhost-only review routes expose source documents and the
  private draft for CV/contract/IELTS, hide predictions, persist edits outside
  Git, and allow `SEALED` only after every current field is explicitly
  confirmed. The contract subset is four cases × 14 fields; CV/IELTS review
  state is preserved across the contract-source replacement.
- `DATA-08`: an independent reviewer confirms the 56 contract fields from the
  source DOCX/PDF files only, with predictions hidden; real-world image inputs
  remain deferred to a later workstream. CV active review is limited to DOCX,
  IMAGE and PDF_SCAN (10 fields/case); CV PLAIN_TEXT/PPTX remain inventory-only.
  IELTS keeps five identity/date fields with only `overall_score` as a score.
  The 101-field active queue is now SEALED after independent confirmation;
  predictions remain unopened. Typed normalization and aggregate pilot are
  deferred to DATA-09.

- `DATA-09`: derive typed canonical values from the sealed source-preserved
  fields, retain the original strings, run aggregate-only evaluation, and keep
  promotion disabled until a separate approval. The pilot completed on 10
  active documents / 101 fields: 97 normalized, 4 missing optional values and
  0 fields requiring re-review; the private artifacts remain outside Git.
- `DATA-10`: user-directed approval freezes the typed projection for read-only
  downstream consumption. The approval marker remains outside Git, predictions
  stay unopened, and `promotionAllowed=false` remains enforced.
- `DATA-11`: loopback API serves typed summary/document/export routes only via
  `GET`; each request revalidates projection, approval marker, aggregate report
  and SHA-256. JSON/CSV exports omit `sourceValue`, OCR text and predictions;
  write methods return `405`, and promotion remains disabled.

## OCR-HO-V2-001 acceptance criteria

- Manifest held-out gồm tối thiểu 15 tài liệu mới, không trùng SHA-256 với development.
- Prediction Phase 11.5 và Phase 11.6 được seal ngoài Git trước khi mở Ground Truth.
- Ground Truth được xác nhận từ ảnh gốc; prediction không hiển thị trong lúc review.
- Đánh giá đúng một lần, không chỉnh threshold trên tập held-out.
- Policy tiếp tục `SHADOW_REVIEW_ONLY` nếu candidate làm hỏng field primary hoặc không đạt gate.

## OCR-HO-V2-001 checkpoint (prediction sealed; evaluation pending)

- Dataset source: Roboflow test images selected deterministically by SHA-256 after
  excluding the 29 legacy Phase 11 samples and 8 prior private images. Fifteen
  file-level new documents were locked from 89 candidates.
- The source and authorization remain outside Git under the local private data
  root. The authorization records the user-directed local-only basis and the
  source dataset's CC BY 4.0 declaration; no network export was performed.
- Phase 11.5 and Phase 11.6 completed 15/15 documents with status
  `SHADOW_REVIEW_ONLY`; the sealed private prediction snapshot has
  `documentCount=15`, `groundTruthPresent=false`, and
  `predictionsHiddenDuringGroundTruthReview=true`.
- `validate_phase11_6_lock.py` returned `LOCK_VERIFIED` for phase `11.6.0`, six
  locked model artifacts, and 15 development documents. No promotion or
  threshold tuning was performed.
- Regression checks for this checkpoint: 10 held-out/lock tests passed, Ruff
  passed, repository hygiene passed, and `git diff --check` reported no content
  errors (only normal line-ending warnings).
- Ground Truth audit result: all 15 selected files have source YOLO label files,
  but those annotations contain only class IDs and polygons/boxes (field
  locations). They contain no text transcription for the eight OCR fields, so
  they are insufficient for an exact OCR evaluation.
- Decision: do not open or score the sealed predictions, and do not promote.
  The private manifest remains `PENDING_HUMAN_CONFIRMATION`; a human text
  transcription/verification pass is required before the one-time evaluation.

## TF-P1-001 acceptance criteria

- Hai template versioned được đăng ký và nhận diện bằng nội dung.
- Native DOCX parser được dùng; OCR không được gọi.
- Không tự điền field; thiếu/mâu thuẫn đi `MANUAL_REVIEW`.
- API và Camunda projection tương thích ngược, không chứa raw document.
- 14/14 mẫu đạt classification và required-field exact match 100%.
- Schema, unit test, static checks, tài liệu và handoff nhất quán.

## TF-P1-002 acceptance evidence

- Commit implementation `53b22fb` đã push và remote hash khớp local.
- API local bind `127.0.0.1:8765`; health và danh sách hai template phản hồi thành công.
- Hai DOCX gốc ngoài bộ regression được xử lý qua HTTP thật, đúng loại tài liệu,
  `AUTO_CONTINUE` và không có validation error.
- Chỉ báo cáo aggregate; session smoke-test đã xóa và không commit upload/PII.

## TF-P1-003 acceptance evidence

- `localhost:3000` chạy giao diện tổng; API root chuyển hướng về giao diện này.
- Template-first là chế độ mặc định, liệt kê hai template và giữ riêng luồng OCR/IDP cũ.
- Browser smoke hiển thị đúng loại đơn nghỉ phép, `SUCCESS`, `AUTO_CONTINUE`, field cards,
  quality metadata, JSON viewer và thao tác xóa local.
- Python 219 tests và web 8 tests pass; lint không có error hoặc warning mới.

## TF-P1-004 acceptance evidence

- README đặt hai mẫu HCNS chuẩn và cách thử DOCX mới trên dashboard ở phần đầu.
- README phân biệt 14 hồ sơ regression thuộc 2 loại biểu mẫu, dẫn tới báo cáo metric.
- Universal Intake, OCR/CCCD, generic IDP và Camunda cũ vẫn được giữ và gắn phạm vi rõ ràng.
- `git diff --check`, repository hygiene và 4 API tests pass.
## TF-P1-005 acceptance evidence

- Mentor view mặc định không render nav, metrics, tab hoặc tài liệu held-out.
- Frontend không gọi held-out summary/evidence khi feature flag tắt.
- `VITE_SHOW_HELDOUT=true` giữ nguyên chế độ quan sát riêng và build thành công.
- Browser smoke trên localhost không tìm thấy nhãn/nav/tab held-out; 9 web tests pass.

## TF-P1-006 acceptance evidence

- Endpoint chỉ đọc liệt kê và trả kết quả Template-first, lọc đúng nghỉ phép/tăng ca.
- Evidence mặc định chỉ còn tab Template-first và CCCD; upload HCNS generic không bị xóa.
- Panel metadata/Schema/JSON bên phải được giữ cho cả Template-first và CCCD.
- Browser smoke: một Template-first session, 30 CCCD; held-out và tab generic không hiển thị.

## TF-P1-007 acceptance evidence

- Hero dùng product showcase cho hai biểu mẫu chuẩn thay vì ảnh/visualization PII.
- Showcase mô tả chính xác DOCX → Template → JSON, validation và quality routing.
- Browser smoke xác nhận cả hai biểu mẫu và toàn bộ quality footer hiển thị rõ.

## TF-P1-008 acceptance evidence

- Landing hero giới thiệu HCNS Automation Agent, Template-first, Camunda và Human-in-the-Loop.
- Showcase dùng số template/session/CCCD thật, không thêm taskbar hoặc số liệu giả.
- Web build/tests pass; lint không có error.

## TF-P2-002 acceptance checkpoint

- API/UI nhận `.docx`, `.pdf`, `.png`, `.jpg`, `.jpeg`; panel metadata bên phải được giữ.
- UX mặc định chỉ có một vùng upload; ảnh/PDF hiển thị cạnh field/JSON. Luồng
  OCR/IDP cũ được giữ sau cờ `VITE_SHOW_LEGACY_UPLOAD`.
- File nguồn Template-first được lưu theo session và chỉ phục vụ lại qua endpoint
  loopback `/api/documents/source`.
- DOCX: 10/10 classification, 90/90 required-field exact match, 0 schema error.
- Native PDF: 10/10 classification, 90/90 required-field exact match, 0 schema error.
- Ảnh camera và PDF scan: 6/6 xử lý, 6/6 classification, 0 schema error,
  6/6 `MANUAL_REVIEW`, 0 false `AUTO_CONTINUE`.
- OCR required-field exact match hiện 31/54 (57.41%), chưa đạt gate đã duyệt là 80%.
- Không dùng Ground Truth/native counterpart để bù giá trị OCR; report chỉ chứa aggregate.
- Manifest nguồn khai báo 30 file nhưng thực có 26; 10 tham chiếu `files.image` bị stale.
- Live HTTP smoke ảnh camera trả đúng `LEAVE_REQUEST`, dùng PaddleOCR và bắt buộc
  `MANUAL_REVIEW`; session smoke đã xóa.
- API preview 6 tests và web 9 tests/build pass; full-suite checkpoint trước đó:
  Python 225 tests, Ruff, mypy, hygiene và diff check pass.

## TF-P2-002A implementation checkpoint

- Đã triển khai phục hồi field theo ROI cố định cho hai layout, parser dùng
  nhãn + vị trí hình học, và provenance chỉ chứa field/confidence/box/reason.
- Bộ sáu ảnh khóa đạt 41/54 (75.93%) và PDF scan đạt 36/54 (66.67%) ở lần chạy
  mới nhất; cả hai đều classification 6/6, schema 0, review 6/6, false auto 0.
- Gate 44/54 (81.48%) chưa đạt; lỗi còn lại là tên tiếng Việt động, `reason`
  và `workContent`. Không được mở TF-P2-003 hoặc dùng Ground Truth để bù giá trị.

## TF-P2-003A scope checkpoint

- Version manifest đóng băng `leave-request-v1` và `overtime-request-v1`, ghép
  `templateVersion`, `schemaRef`, `parserVersion` và required fields.
- UAT harness xác thực matrix DOCX/native PDF/ảnh/PDF scan, gate quality và
  aggregate-only reporting trước khi evaluator được chạy.
- TF-P2-003B (execute UAT) đã hoàn tất và pass toàn bộ gate sau khi candidate OCR vượt 44/54.

## TF-P2-002B completion checkpoint

- Trạng thái `DONE`; chỉ một task Template-first được phép triển khai tại một thời điểm.
- Phạm vi field: 4 tên động, 6 `reason`, 3 `workContent`; PDF scan thêm `department`
  và `jobTitle`.
- Không dùng Ground Truth/native twin để điền kết quả và không hardcode tên/nội dung.
- EasyOCR candidate được chọn cho controlled local evaluation: ảnh 48/54 (88.89%),
  PDF scan 45/54 (83.33%); cả hai 6/6 classification, schema errors 0, 6/6
  `MANUAL_REVIEW`, false `AUTO_CONTINUE` 0.
- Native DOCX/PDF vẫn 90/90 required-field exact match. Candidate không dùng
  Ground Truth/native twin để điền giá trị và report aggregate không chứa raw values.
- PaddleOCR là default ở checkpoint lịch sử này; TF-P2-005 đã đổi policy sau full UAT
  và ghi nhận rollback rõ ràng qua `HCNS_TEMPLATE_OCR_BACKEND=paddle`.

## TF-P2-003B completion checkpoint

- Trạng thái `DONE`; version manifest FROZEN_V1 khóa template/schema/parser pairing
  cho `leave-request-v1` và `overtime-request-v1`.
- UAT full matrix chạy đủ `docx`, `pdf`, `image`, `scan_pdf`, mỗi format 10/10
  available/processed; classification 10/10 và schema errors 0.
- Required-field exact match: DOCX 90/90, native PDF 90/90, image 82/90 (91.11%),
  scan PDF 77/90 (85.56%). OCR 20/20 items `MANUAL_REVIEW`, false `AUTO_CONTINUE` 0.
- Fail-closed mismatch test pass; report aggregate-only (`containsRawFieldValues: false`)
  và dataset integrity 30 actual files/30 references/0 stale references.
- Chưa có external deployment side effect; phạm vi kế hoạch hiện tại là local-only.

## TF-P2-004 checkpoint (2026-08-02)

- Parser boundary repair đã commit tại `655f51c`; targeted tests 19/19 pass.
- Paddle `PP-OCRv5_mobile_rec` candidate chỉ đạt 21/54 trên cả ảnh và PDF scan,
  nên không được promote. Classification 6/6, schema 0, OCR `MANUAL_REVIEW`
  6/6 và false `AUTO_CONTINUE` 0.
- Candidate `PP-OCRv5_server_rec` đạt 17/54 trên ảnh khóa và cũng bị loại.
- EasyOCR opt-in rerun đạt 50/54 ảnh và 48/54 PDF scan; cả hai pass quality
  gates. Candidate Paddle không đạt nên checkpoint này được supersede bởi TF-P2-005.

## TF-P2-005 checkpoint (2026-08-02)

- Trạng thái `DONE`; EasyOCR `vi-greedy` được promote làm backend mặc định cho
  ảnh/PDF scan của Template-first. Paddle rollback qua `HCNS_TEMPLATE_OCR_BACKEND=paddle`.
- Full UAT default: DOCX 90/90, native PDF 90/90, image 86/90, scan PDF 82/90;
  classification 10/10 cả bốn format, schema 0, OCR manual review 20/20,
  false auto 0 và report aggregate-only.
- CPU p95: 23.5s/image, 22.6s/scan PDF; model cache 93.99 MiB. Rollback Paddle
  smoke pass; VietOCR không được cài hoặc dùng trong route này.
- Deployment/production-readiness không thuộc kế hoạch hiện tại; không mở lại OCR
  candidate nếu chưa có evidence mới.

## OCR-HO-V2-002 checkpoint (local Ground Truth review gate)

- Đã thêm contract/backend local-only cho 15 CCCD held-out v2: summary, source
  preview, review/save, lock và evaluate-once. Endpoint không đọc prediction trong
  lúc người dùng xác nhận Ground Truth.
- Đã thêm UI `LOCAL GROUND TRUTH REVIEW · CCCD`, gated bởi
  `VITE_SHOW_GROUND_TRUTH_REVIEW=true`. Mỗi ảnh có 8 field, checkbox
  `Không có trên ảnh`, và hai assertion bắt buộc kiểm tra chữ/dấu với ảnh gốc.
- Prediction snapshot vẫn sealed ngoài Git; summary thực tế đang ở
  `PENDING_HUMAN_CONFIRMATION`, 4/14 tài liệu trong metric đã review, evaluate
  chưa chạy.
- Scope amendment: `CCCD-HO-005` được xác nhận là ảnh mặt sau
  (`OUT_OF_SCOPE_BACK`), không đánh dấu 8 field là không có và không đưa vào
  metric. Source audit vẫn giữ 15 ảnh; metric denominator còn 14 ảnh.
- Ground Truth và ảnh nguồn tiếp tục nằm ngoài repository tại private root; không
  ghi PII vào commit/report. Chỉ sau khi người dùng lưu đủ 14 tài liệu hợp lệ,
  giữ ảnh loại ở trạng thái `EXCLUDED`, và bấm khóa mới cho phép evaluate đúng
  một lần.
- Validation: `tests/test_cccd_heldout_review.py` 5 passed; web build và rendered
  HTML 9 passed; template API regression 25 passed; compileall và Ruff cho module
  mới/script/test đều pass.
- Evaluate-once đã chạy đúng một lần sau khi khóa Ground Truth: 14 tài liệu hợp lệ,
  112 field. Phase 11.5/11.6 đều đạt strict exact match 50.00%, ASCII exact
  match 50.89%, CER 80.71%, DER 16.14%; promotion gate giữ
  `SHADOW_REVIEW_ONLY` vì không đạt accepted precision/field presence và còn một
  sensitive false acceptance. Không có exact regression và không promote model.

## OCR-HO-V2-003 checkpoint (post-evaluation local inspector)

- Đã thêm endpoint read-only `/cccd-heldout/review/evaluation?id=...`; endpoint
  chỉ đọc Ground Truth và sealed prediction sau khi queue đã `CONFIRMED` và
  evaluate-once đã tạo report. Trong lúc review hoặc trước evaluation, prediction
  tiếp tục bị chặn.
- Localhost hiển thị output theo từng ảnh và 8 field: Ground Truth, Phase 11.5,
  Phase 11.6, strict/ASCII match, status/error class, confidence và ROI bbox.
  `CCCD-HO-005` không có output vì vẫn ngoài metric.
- Dữ liệu chi tiết chỉ được phục vụ loopback từ private root; không ghi raw OCR,
  Ground Truth hoặc prediction vào Git/report công khai.
- Validation: targeted review tests 5 passed, full Python suite 248 passed / 16
  subtests, web build + rendered HTML 10 passed, module Ruff/compileall passed,
  repository hygiene passed.

## OCR-HO-V2-004 checkpoint (development regression, 2026-08-03)

- OCR-HO v1.1 keeps the orientation policy at `fixed_0_degree`; 90°/180°/270°
  variants are not selected or evaluated. Output carries schema/recognizer
  version `1.1.0`, `DEVELOPMENT_ONLY`, and always requires `MANUAL_REVIEW`.
- Parser changes add bounded bilingual-label cleanup, typo aliases for origin,
  residence, and expiry labels, geometry-aware multiline address selection, and
  remove the unsafe whole-page expiry-date fallback. No Ground Truth or sibling
  document is used to fill a value.
- Development comparison uses the archived, user-reviewed 15-document dataset
  (120 fields; all selected rotations were 0°). Baseline Phase 11.5: strict
  exact 60.00%, ASCII exact 61.67%, CER 43.60%, DER 12.65%, field presence
  95.83%. OCR-HO v1.1: strict exact 36.67%, ASCII exact 40.00%, CER 50.75%,
  DER 17.00%, field presence 70.00%.
- Gate decision is `DEVELOPMENT_FAIL`: schema errors 0 and manual-review policy
  passed, but exact regression (33 fields), presence, CER/DER, and no-regression
  gates failed. `productionPromotionAllowed=false`; the official 14-document
  held-out evaluate-once report remains immutable and was not rerun.
- Localhost smoke output is available as OCR-HO v1.1 with `fixed 0°`; this is a
  shadow development build, not a production promotion.

## OCR-HO-V2-005 checkpoint (guarded candidate recovery, 2026-08-03)

- Candidate policy `ocr-ho-v2-005-guarded-vietnamese-candidate-recovery` v1.2.0
  ranks only sealed Phase 11.5 OCR evidence. It removes bilingual-label and
  neighboring-line contamination, then applies a recovery only when the
  baseline is field-locally unsafe and at least two recognizer families agree.
- Orientation remains `fixed_0_degree`; every candidate field is forced to
  `MANUAL_REVIEW`, schema errors are 0, and no Ground Truth/native twin is
  passed to the selector. The official 14-document evaluate-once artifact was
  not read or mutated.
- Development replay: 15 archived reviewed images / 120 fields. Baseline
  strict/ASCII exact 60.00%/61.67%, CER 43.60%, DER 12.65%, presence 95.83%.
  Guarded candidate strict/ASCII exact remains 60.00%/61.67%, CER improves to
  43.06%, DER remains 12.65%, presence remains 95.83%; exact improvements and
  regressions are both 0.
- Gate is `DEVELOPMENT_PASS` with `productionPromotionAllowed=false`: the
  result is a non-regressing shadow checkpoint, not a production promotion.
  Only 1 guarded recovery was applied; 12 of 13 baseline-risk fields remain
  review-only because candidate evidence is insufficient or unsafe.
- Validation: targeted OCR-HO-V2-005 tests 5 passed; evaluator completed on
  the 15-document archive; report is aggregate-only and stored outside Git.
- Next task should add fresh field-level ROI/recognizer evidence for the
  unresolved names, sex/nationality, and origin/residence fields before any
  runtime promotion or held-out reevaluation.

## OCR-HO-V2-008 checkpoint (token-alignment candidate, 2026-08-03)

- Candidate `OCR-HO-V2 v11.8.1` group token sequence sau label/Unicode cleanup,
  yêu cầu hỗ trợ từ ít nhất hai recognizer family và khôi phục separator cấu trúc
  cho `placeOfOrigin`; `placeOfResidence` vẫn dùng guarded v11.7 selector.
- Development replay 15 ảnh / 120 field, fixed 0°: strict exact 60.00% ->
  60.83%, ASCII exact 61.67% -> 63.33%, CER 43.60% -> 42.47%, DER
  12.65% -> 12.25%, presence 95.83% và region selection 81.67%.
- Exact improvement/regression là 1/0, schema errors 0, manual review 120/120.
  Gate `DEVELOPMENT_PASS`, nhưng `productionPromotionAllowed=false` theo yêu
  cầu; không promote, không đổi localhost primary và không chạy held-out.
- Aggregate report private-only: `CCCD_OCR_HO_V2_008_DEVELOPMENT_COMPARISON`.

## OCR-HO-V2-007 checkpoint (address ROI + Unicode replay, 2026-08-03)

- Candidate `OCR-HO-V2 v11.7.1` chi thay the co dieu kien hai field
  `placeOfOrigin` va `placeOfResidence`; cac field con lai duoc giu tu Phase
  11.5. ROI bat dau tu cung dong label, dung truoc label ke tiep, lam sach label
  song ngu/ngay het han va chi sua mojibake Unicode co the dao nguoc.
- Replay development tren 15 anh / 120 field, co dinh 0° va `MANUAL_REVIEW`
  100%: strict/ASCII exact giu 60.00%/61.67%; CER giam 43.60% -> 43.27%;
  DER giam 12.65% -> 12.25%; presence giu 95.83%; region selection tang
  73.33% -> 81.67%.
- Exact improvement/regression la 0/0, schema errors 0. Gate la
  `DEVELOPMENT_FAIL` vi policy yeu cau toi thieu mot exact improvement. Khong
  promote candidate, khong doi localhost primary, khong doc hoac sua held-out
  evaluate-once. Bao cao aggregate private-only.

## OCR-HO-V2-011 checkpoint (deterministic address ROI, 2026-08-04)

- Implemented `phase11_9_cccd_v2.py` as a shadow-only candidate. It derives
  `placeOfOrigin`/`placeOfResidence` crops from residence/expiry label geometry
  and never reads Ground Truth for candidate selection.
- The replay runner now supports explicit `--paddle-only`; this run used only
  `paddle_ppocrv5` because optional EasyOCR/VietOCR packages were unavailable.
- Development replay covered 15 reviewed images / 120 fields at fixed 0
  degrees. Strict exact stayed 60.00%, ASCII exact moved 61.67% -> 62.50%,
  CER improved 43.60% -> 41.44%, but DER regressed 12.65% -> 15.81% and no
  exact improvement was observed (0 improvements / 0 regressions).
- Schema errors were 0 and all 120 fields stayed `MANUAL_REVIEW`. Gate is
  `DEVELOPMENT_FAIL`; `productionPromotionAllowed=false`. Do not promote,
  change localhost primary, or reopen the held-out evaluate-once artifact.
- Aggregate report is private-only:
  `CCCD_OCR_HO_V2_011_DEVELOPMENT_COMPARISON.{json,md}`.

## OCR-HO-V2-012 checkpoint (full recognizer replay, 2026-08-04)

- Reused the locked private secondary runtime with EasyOCR 1.7.2, VietOCR
  0.3.13 and CPU Torch; all four EasyOCR/VietOCR model hashes passed the
  policy lock. The old venv launcher was bypassed with the current Python
  runtime and an isolated secondary `PYTHONPATH`; Paddle primary remained in
  `D:\venv_paddle`.
- Fixed an existing Camunda adapter eager-import cycle with lazy runtime
  exports; this preserves the public adapter names and lets the OCR runner
  import safely.
- Full replay covered 15 reviewed images / 120 fields at fixed 0 degrees:
  strict exact 60.00% -> 60.83%, ASCII exact 61.67% -> 62.50%, CER 43.60%
  -> 42.09%, DER 12.65% -> 11.46%, presence 95.83%, region selection
  73.33% -> 83.33%, exact improvements/regressions 1/0.
- Schema errors were 0 and all 120 fields stayed `MANUAL_REVIEW`.
  `DEVELOPMENT_PASS` is recorded, but `productionPromotionAllowed=false`;
  no localhost primary or held-out evaluate-once artifact was changed.
- Aggregate report remains private-only:
  `CCCD_OCR_HO_V2_011_DEVELOPMENT_COMPARISON.{json,md}`.

## OCR-HO-V2-013 checkpoint (promotion review and local canary, 2026-08-04)

- The shadow API now selects the newest private v11.9.1 development artifact
  when `CCCD_OCR_HO_V2_011_DEVELOPMENT_COMPARISON.json` is present, while
  retaining the v11.8 fallback for older synthetic/test roots.
- Localhost canary is exposed through the existing shadow routes with schema
  `ocr-ho-v2-013-promotion-review/1.0.0`, candidate `11.9.1`, policy
  `phase11.9-v2-deterministic-address-roi`, 15 development images, and
  `groundTruthLoaded=false`. The browser label is versioned dynamically.
- The development gate remains `DEVELOPMENT_PASS`, but
  `productionPromotionAllowed=false`; review counts are `PENDING=15` and no
  review decision was written automatically. The primary runtime and official
  held-out evaluate-once artifact are unchanged.
- Local smoke: `GET /health`, `GET /ocr-ho-v2/shadow/summary`, and one detail
  preview all returned successfully on loopback API port 8765; the web shell
  returned HTTP 200 on `http://localhost:3000/`.

## OCR-HO-V2-009 checkpoint (local shadow UAT, 2026-08-03)

- Added a private-only inspector for candidate `OCR-HO-V2 v11.8.1` over the
  existing 15-document development archive. The UI shows the source image,
  Phase 11.5 baseline, Phase 11.8.1 candidate, changed/protected field tags,
  ROI bbox, confidence and recognizer profiles.
- The inspector reads `phase11_5/identity_card.json` and
  `phase11_8_v2/field_consensus.json` only; it does not load Ground Truth and
  does not alter the Template-first or CCCD primary runtime.
- Local reviews are persisted outside Git in
  `output/phase11/OCR_HO_V2_009_SHADOW_UAT_REVIEWS.json`. Each document
  requires source comparison, changed-field inspection and confirmation that
  the result remains `MANUAL_REVIEW` before a decision is saved.
- API endpoints: `GET /ocr-ho-v2/shadow/summary`,
  `GET /ocr-ho-v2/shadow/document?id=...&mode=detail|preview|source`, and
  `POST /ocr-ho-v2/shadow/review?id=...`.
- Status remains `REVIEW`: development gate is still
  `DEVELOPMENT_PASS`, but `productionPromotionAllowed=false`; no held-out
  evaluate-once was rerun and no promotion was performed.
- Validation: Python shadow UAT/API tests 3 passed; rendered web tests 11
  passed; web ESLint 0 errors (23 pre-existing warnings); Ruff passed for new
  module/tests and `E501` passed for the API changes. Web build was not run
  because the sandbox denies writes to `node_modules/.vite-temp`.

## OCR-HO-V2-006 checkpoint (targeted ROI/recognizer replay)

- Candidate `OCR-HO-V2 v11.6.1` chạy ROI/recognizer mới cho năm field mục tiêu:
  `fullName`, `sex`, `nationality`, `placeOfOrigin`, `placeOfResidence`; ba field
  còn lại được bảo vệ bằng Phase 11.5. Chính sách vẫn cố định 0 độ và
  `MANUAL_REVIEW` 100%.
- Replay development trên 15 ảnh / 120 field: strict/ASCII exact giữ
  60.00%/61.67%; CER giảm 43.60% -> 42.52%; presence giữ 95.83%; DER tăng
  12.65% -> 13.83%. Không có exact improvement hoặc exact regression; schema
  error 0.
- Gate `DEVELOPMENT_FAIL` vì DER tăng và chưa có exact improvement. Không
  promote runtime, không đọc/sửa held-out evaluate-once, không đưa raw PII vào
  Git. Báo cáo aggregate chỉ nằm ở private output.

## LOCAL-SCOPE-001 - Mentor-safe localhost (DONE)

- Scope: hide unrelated/held-out/private review data from the default localhost
  view without deleting files or changing immutable evaluation artifacts.
- Done: overview fetches only active template sessions unless a private review
  flag is enabled; dashboard tabs and review summaries follow the same flags.
- Docs updated: root README, OCR Lab README, WORKFLOWS, PROJECT_STATE and
  HANDOFF. Camunda is unchanged.

### DATA-15-PREDICTION-INSPECTOR - Review predictions before scoring (DONE/DEV HOLD)

- Localhost exposes the new 12-document prediction-only split with field-level
  provenance; it intentionally shows no EM because user-authoritative Ground
  Truth has not been supplied.
- The earlier 41.96% aggregate is provisional self-annotation only. Do not use
  it for promotion; obtain/correct Ground Truth, then run a fresh dev aggregate.

### DATA-15-GT-REVIEW - Official annotation queue (READY/DRAFT)

- Fresh private draft: `C:\tmp\bo10-official-ground-truth-draft-20260805.json`;
  12 documents / 112 fields, all pending and prediction-blind.
- Review in localhost `DATA-08 · 4 contract case review`; save each case,
confirm every field, then SEALED. Benchmark remains intentionally unrun.

### DATA-15-GT-SEALED - GroundTruth ready for development scoring (READY)

- Official GroundTruth is sealed: 12/12 documents and 112/112 fields confirmed;
  predictions remain unopened.
- Next: run the separate development aggregate comparison only. Keep the old
  evaluate-once artifact immutable.

### DATA-15-DEV-AGGREGATE - Official comparison completed (HOLD)

- Development-only comparison used the SEALED 112-field GroundTruth and the
  DATA-13 prediction artifact without changing the old evaluate-once output.
- Strict exact is `30/112` (`26.79%`); accepted long-text policy is `43/112`
  (`38.39%`). Classification is `11/12`, schema errors `0`; accepted family
  rates are Contract `16/42`, CV `27/50`, IELTS `0/20`.
- DATA-13 localhost now loads the private report and shows field-level
  GroundTruth/prediction/evidence. Next: fix parser/OCR errors revealed by the
  comparison, then rerun development-only; do not promote or reopen GT.

### DATA-16-PARSER-V2 - Contract/CV parser/layout fixes (DONE / HOLD)

- Replaced fixed-line assumptions for native Contract/CV extraction with
  section-aware and narrative/layout-aware parsing. Native Contract accepted
  rate is `40/42`; CV accepted rate is `42/50` on the fresh 12-document split.
- Fresh private artifacts:
  `C:\tmp\bo10-dev-predictions-data13-parser-v2-20260806.json`,
  `C:\tmp\bo10-dev-aggregate-comparison-parser-v2-20260806.json`, and marker.
  Strict overall `69/112`; accepted text `82/112`; classification `11/12`;
  schema errors `0`; decision `HOLD`.
- Localhost is wired to this report. IELTS/certificate (`0/20`) and scanned CV
  remain the next bottleneck; OCR is still forced to manual review.
- Preserve the sealed GroundTruth and old evaluate-once artifacts. The next
  comparison must create a new private prediction/report/marker set.

### DATA-17-OCR-HYBRID - Certificate/IELTS and scanned-CV OCR (DONE / DEV HOLD)

- Added local EasyOCR `vi+en` for scanned CV and local PaddleOCR layout parsing
  for IELTS; no document is sent to cloud. Native documents keep native parsing.
- Fresh development-only comparison: strict `90/112` (`80.36%`), accepted
  text `104/112` (`92.86%`); Contract `40/42`, CV `30/50` strict / `44/50`
  accepted, IELTS `20/20`. Classification `12/12`, schema errors `0`.
- All 5 image/scan documents remain `MANUAL_REVIEW`; false auto-continue `0`,
  `UNSUPPORTED_NO_OCR` `0`. DATA-13 localhost shows field-level
  GroundTruth/prediction/evidence and mismatch reason.
- Artifacts: `C:\tmp\bo10-dev-predictions-data13-ocr-v7-20260806.json`,
  `C:\tmp\bo10-dev-aggregate-comparison-ocr-v7-20260806.json` and marker.
  `evaluateOnceArtifactTouched=false`; promotion is disabled. Remaining work
  is CV narrative OCR coverage and the Contract representative-name subset.
