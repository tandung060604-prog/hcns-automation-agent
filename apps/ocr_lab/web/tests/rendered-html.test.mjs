import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  pendingReviewCases,
  resumePendingReview,
} from "../app/review-queue.mjs";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request("http://localhost/", {
      headers: { accept: "text/html" },
    }),
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );
}

test("server-renders the VinHRIS landing page", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>VinHRIS \| AI document operations cho HR<\/title>/i);
  assert.match(html, /VinHRIS/);
  assert.match(html, /AI DOCUMENT OPERATIONS FOR HR/);
  assert.match(html, /Human review ready/);
  assert.match(html, /Business JSON/);
  assert.match(html, /template-first-local-workflow\.png/);
  assert.match(html, /Mở workspace/);
  assert.match(html, /vinhris-hero-source\.mp4/);
  assert.match(html, /Bật âm thanh/);
  assert.match(html, /Kiến tạo một cuộc sống tốt đẹp hơn cho mọi người/);
  assert.match(html, /WORKSPACE PROOF \/ TEMPLATE-FIRST/);
  assert.match(html, /Xem một hồ sơ đi qua VinHRIS/);
  assert.match(html, /SAMPLE DOCUMENT · KHÔNG PHẢI PII THẬT/);
  assert.match(html, /vinhris-journey-progress/);
  assert.doesNotMatch(html, /Your site is taking shape|Building your site/);
});

test("keeps Phase 11.4 CCCD controls in the local workspace flow", async () => {
  const [dashboard, css, page, workspacePage, layout] = await Promise.all([
    readFile(new URL("../app/Dashboard.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/globals.css", import.meta.url), "utf8"),
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/workspace/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/layout.tsx", import.meta.url), "utf8"),
  ]);

  assert.match(dashboard, /phase11_3/);
  assert.match(dashboard, /phase11_4/);
  assert.match(dashboard, /"11\.3"/);
  assert.match(dashboard, /"11\.4"/);
  assert.match(dashboard, /\/user\/phase11-3-evidence/);
  assert.match(dashboard, /\/user\/phase11-4-evidence/);
  assert.match(dashboard, /\/user\/identity-card/);
  assert.match(dashboard, /Ground Truth theo trường CCCD/);
  assert.match(dashboard, /phase9Before/);
  assert.match(dashboard, /phase11After/);
  assert.match(dashboard, /needs_review/);
  assert.match(css, /\.identity-fields/);
  assert.match(css, /\.identity-ground-truth-grid/);
  assert.match(css, /\.field-evaluation/);
  assert.match(page, /VinHRISLanding/);
  assert.match(workspacePage, /<Dashboard/);
  assert.match(layout, /VinHRIS \| AI document operations/);
});

test("shows Phase 11.5 Unicode, ASCII and crop evidence controls", async () => {
  const source = await readFile(
    new URL("../app/Dashboard.tsx", import.meta.url),
    "utf8",
  );
  assert.match(source, /phase11_5/);
  assert.match(source, /asciiValue/);
  assert.match(source, /phase11-5-crop/);
  assert.match(source, /phase11-5-evidence/);
  assert.match(source, /errorSignals/);
  assert.match(source, /evidenceErrorClass/);
  assert.match(source, /Prediction tiếng Việt/);
  assert.match(source, /Prediction không dấu/);
});

test("exposes the Phase 15 multi-format IDP and field review flow", async () => {
  const [dashboard, css] = await Promise.all([
    readFile(new URL("../app/Dashboard.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/globals.css", import.meta.url), "utf8"),
  ]);

  assert.match(dashboard, /\.docx,\.pdf/);
  assert.match(dashboard, /DOCX, PDF native parser/);
  assert.match(dashboard, /phase12\?:/);
  assert.match(dashboard, /phase15\?:/);
  assert.match(dashboard, /PHASE 15 \/ UNIFIED INTAKE/);
  assert.match(dashboard, /Kết quả trên 18 tài liệu thật/);
  assert.match(dashboard, /Phương pháp nào đang thực sự chạy/);
  assert.match(dashboard, /primaryProfile=vietocr_vgg_seq2seq/);
  assert.match(dashboard, /Không auto-switch fallback/);
  assert.match(dashboard, /Biểu mẫu HCNS chuẩn và CCCD/);
  assert.match(dashboard, /CCCD đã Ground Truth/);
  assert.match(dashboard, /\/user\/source/);
  assert.match(dashboard, /\/heldout\/evidence/);
  assert.match(dashboard, /EvidenceInspector/);
  assert.doesNotMatch(dashboard, /upload HCNS local/);
  assert.match(dashboard, /đơn nghỉ phép &amp; tăng ca/);
  assert.match(dashboard, /Live v5 mới nhất · parser 2\.0/);
  assert.match(dashboard, /CCCD Phase \$\{phase11Label/);
  assert.match(dashboard, /NGUỒN PREDICTION/);
  assert.match(dashboard, /LIVE PP-OCRV5 REPLAY · AUDIT ONLY/);
  assert.match(dashboard, /Business JSON/);
  assert.doesNotMatch(dashboard, /Phase 7 \/ 114 synthetic samples/);
  assert.match(dashboard, /userResult\.phase15 \? "phase15" : "phase12"/);
  assert.match(dashboard, /\/user\/phase15-review/);
  assert.match(dashboard, /\/user\/phase15-reviewed-result/);
  assert.match(dashboard, /\/user\/phase15-reviewed-business/);
  assert.match(dashboard, /Xác nhận các trường Phase 15/);
  assert.match(dashboard, /Tải Business JSON/);
  assert.match(css, /\.phase12-strip/);
  assert.match(css, /\.phase15-review/);
  assert.match(css, /\.evidence-inspector/);
  assert.match(css, /\.evidence-field-row/);
  assert.match(css, /\.evidence-json/);
});

test("hides held-out evidence by default behind a private local flag", async () => {
  const [dashboard, envExample] = await Promise.all([
    readFile(new URL("../app/Dashboard.tsx", import.meta.url), "utf8"),
    readFile(new URL("../.env.example", import.meta.url), "utf8"),
  ]);

  assert.match(
    dashboard,
    /const SHOW_HELDOUT = import\.meta\.env\.VITE_SHOW_HELDOUT === "true"/,
  );
  assert.match(
    dashboard,
    /SHOW_HELDOUT \? "heldout" : "templates"/,
  );
  assert.match(
    dashboard,
    /if \(SHOW_HELDOUT\) \{\s+fetch\(`\$\{API_BASE\}\/heldout\/summary`\)/,
  );
  assert.match(
    dashboard,
    /SHOW_HELDOUT \? <a href="#metrics">Held-out thật<\/a> : null/,
  );
  assert.match(dashboard, /SHOW_HELDOUT && evidenceMode === "heldout"/);
  assert.match(envExample, /^VITE_SHOW_HELDOUT=false$/m);
  assert.match(
    dashboard,
    /const SHOW_GROUND_TRUTH_REVIEW =\s+import\.meta\.env\.VITE_SHOW_GROUND_TRUTH_REVIEW === "true"/,
  );
  assert.match(envExample, /^VITE_SHOW_GROUND_TRUTH_REVIEW=false$/m);
  assert.match(dashboard, /\/cccd-heldout\/review\/summary/);
  assert.match(dashboard, /\/cccd-heldout\/review\/save\?id=/);
  assert.match(dashboard, /\/cccd-heldout\/review\/disposition\?id=/);
  assert.match(dashboard, /\/cccd-heldout\/review\/lock/);
  assert.match(dashboard, /\/cccd-heldout\/review\/evaluate/);
  assert.match(dashboard, /\/cccd-heldout\/review\/evaluation\?id=/);
  assert.match(dashboard, /data-testid="ground-truth-source-preview"/);
  assert.match(dashboard, /data-testid="ground-truth-evaluation-inspector"/);
  assert.match(dashboard, /OUTPUT THẬT SAU EVALUATE-ONCE/);
  assert.match(dashboard, /OUT_OF_SCOPE_BACK/);
  assert.match(dashboard, /Prediction vẫn bị ẩn/);
});

test("exposes the OCR-HO-V2-009 local shadow UAT inspector behind a private flag", async () => {
  const [dashboard, css, envExample, api] = await Promise.all([
    readFile(new URL("../app/Dashboard.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/globals.css", import.meta.url), "utf8"),
    readFile(new URL("../.env.example", import.meta.url), "utf8"),
    readFile(new URL("../../api/serve_dashboard_api.py", import.meta.url), "utf8"),
  ]);
  assert.match(dashboard, /VITE_SHOW_OCR_HO_SHADOW_UAT === "true"/);
  assert.match(envExample, /^VITE_SHOW_OCR_HO_SHADOW_UAT=false$/m);
  assert.match(dashboard, /\/ocr-ho-v2\/shadow\/summary/);
  assert.match(dashboard, /\/ocr-ho-v2\/shadow\/document\?id=/);
  assert.match(dashboard, /\/ocr-ho-v2\/shadow\/review\?id=/);
  assert.match(dashboard, /data-testid="ocr-ho-shadow-source-preview"/);
  assert.match(dashboard, /data-testid="ocr-ho-shadow-inspector"/);
  assert.match(dashboard, /groundTruthLoaded: false/);
  assert.match(dashboard, /SHADOW_REVIEW_ONLY/);
  assert.match(css, /\.shadow-uat-inspector/);
  assert.match(css, /\.shadow-uat-row\.changed/);
  assert.match(api, /--ocr-ho-shadow-root/);
  assert.match(api, /\/ocr-ho-v2\/shadow\/summary/);
});

test("exposes the DATA-08 independent contract review panel behind a private flag", async () => {
  const [dashboard, component, envExample, css] = await Promise.all([
    readFile(new URL("../app/Dashboard.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/ExternalDatasetReview.tsx", import.meta.url), "utf8"),
    readFile(new URL("../.env.example", import.meta.url), "utf8"),
    readFile(new URL("../app/globals.css", import.meta.url), "utf8"),
  ]);
  assert.match(dashboard, /VITE_SHOW_EXTERNAL_DATASET_REVIEW === "true"/);
  assert.match(envExample, /^VITE_SHOW_EXTERNAL_DATASET_REVIEW=false$/m);
  assert.match(dashboard, /<ExternalDatasetReview \/>/);
  assert.match(component, /\/external-dataset\/review\/summary/);
  assert.match(component, /\/external-dataset\/review\/save\?id=/);
  assert.match(component, /\/external-dataset\/review\/lock/);
  assert.match(component, /predictionsHiddenDuringReview/);
  assert.match(component, /EXTERNAL DATASET · INDEPENDENT REVIEW/);
  assert.match(component, /function categoryScopeLabel\(/);
  assert.match(component, /categoryScopeLabel\(summary, "contract"\)/);
  assert.match(component, /categoryScopeLabel\(summary, "cv"\)/);
  assert.match(component, /categoryScopeLabel\(summary, "ielts"\)/);
  assert.match(component, /Family name \+ First name/);
  assert.match(component, /không tự đảo hoặc tách thành field khác/);
  assert.match(component, /item\.reviewable/);
  assert.match(component, /PDF_TEXT/);
  assert.match(component, /Không có \/ không đọc được/);
  assert.match(component, /save-current-external-review/);
  assert.match(component, /Lưu review hiện tại/);
  assert.match(component, /DRAFT_STORAGE_PREFIX/);
  assert.match(component, /Bạn còn dữ liệu chưa lưu/);
  assert.match(css, /external-review-primary-save:disabled/);
});

test("exposes one Template-first upload with source preview and structured results", async () => {
  const [dashboard, css, envExample] = await Promise.all([
    readFile(new URL("../app/Dashboard.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/globals.css", import.meta.url), "utf8"),
    readFile(new URL("../.env.example", import.meta.url), "utf8"),
  ]);

  assert.match(dashboard, /\/api\/templates/);
  assert.match(dashboard, /\/api\/documents\/process/);
  assert.match(dashboard, /\/api\/documents\/sessions/);
  assert.match(dashboard, /\/api\/documents\/result\?id=/);
  assert.match(dashboard, /\/api\/documents\/source\?id=/);
  assert.match(dashboard, /useState<"template" \| "legacy">\("template"\)/);
  assert.match(dashboard, /SHOW_LEGACY_UPLOAD/);
  assert.match(dashboard, /Tải tài liệu HCNS/);
  assert.match(dashboard, /Trích xuất tài liệu/);
  assert.match(dashboard, /TXT, DOCX, PDF, XLSX, PPTX, PNG, JPG\/JPEG/);
  assert.match(dashboard, /Thông tin trích xuất từ biểu mẫu chuẩn/);
  assert.match(dashboard, /Xem JSON đầy đủ/);
  assert.match(dashboard, /Không có trong tài liệu/);
  assert.match(dashboard, /TemplateResultPanel/);
  assert.match(dashboard, /TemplateDocumentPreview/);
  assert.match(dashboard, /TemplateEvidenceInspector/);
  assert.match(dashboard, /activeTemplateEvidencePreviewUrl/);
  assert.match(dashboard, /\/api\/documents\/preview\?id=/);
  assert.match(dashboard, /"template-evidence-image"/);
  assert.match(dashboard, /"template-evidence-pdf"/);
  assert.match(
    dashboard,
    /activeTemplateSession\?\.sourceFormat === "PDF_SCAN"/,
  );
  assert.match(dashboard, /PaddleOCR local/);
  assert.match(
    dashboard,
    /Dữ liệu được đọc trực tiếp bằng native parser, không dùng OCR/,
  );
  assert.match(dashboard, /\.docx,\.pdf/);
  assert.match(dashboard, /data-testid="local-document-input"/);
  assert.match(dashboard, /data-testid="template-document-preview"/);
  assert.match(dashboard, /data-testid="template-result-panel"/);
  assert.match(dashboard, /\/assets\/template-first-local-workflow\.png/);
  assert.match(css, /\.upload-mode-switch/);
  assert.match(css, /\.upload-workspace/);
  assert.match(css, /\.template-document-preview/);
  assert.match(css, /\.hero-workflow-visual/);
  assert.match(css, /\.template-field-grid/);
  assert.match(css, /\.template-json/);
  assert.match(css, /\.template-evidence-field-row/);
  assert.match(dashboard, /data-testid="product-showcase"/);
  assert.match(css, /\.product-showcase/);
  assert.match(envExample, /^VITE_SHOW_LEGACY_UPLOAD=false$/m);
});

test("shows the reviewed Phase 14 recognizer decision", async () => {
  const [dashboard, css, api] = await Promise.all([
    readFile(new URL("../app/Dashboard.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/globals.css", import.meta.url), "utf8"),
    readFile(
      new URL("../../api/serve_dashboard_api.py", import.meta.url),
      "utf8",
    ),
  ]);

  assert.match(dashboard, /vietocr_best_crop/);
  assert.match(dashboard, /controlled pilot/);
  assert.match(dashboard, /productionDecision/);
  assert.match(dashboard, /\/user\/controlled-pilot/);
  assert.match(dashboard, /\/user\/phase14-2-result/);
  assert.match(dashboard, /PHASE 14\.2 \/ CONTROLLED OCR PILOT/);
  assert.match(dashboard, /controlledPilot/);
  assert.match(dashboard, /Auto-accepted/);
  assert.match(dashboard, /phase14_3/);
  assert.match(dashboard, /Crop recovery ceiling/);
  assert.match(dashboard, /PHASE 14\.4 \/ GROUND TRUTH EXPANSION/);
  assert.match(dashboard, /groundTruthExpansion/);
  assert.match(dashboard, /secondRecognizer/);
  assert.match(dashboard, /weight local đã sẵn sàng/);
  assert.match(dashboard, /blindedPrecompute/);
  assert.match(dashboard, /Prediction đang được ẩn/);
  assert.match(dashboard, /phase14PendingCases/);
  assert.match(dashboard, /resumePendingReview/);
  assert.match(dashboard, /Còn \{phase14CaseIndex \+ 1\}/);
  assert.match(dashboard, /secondRecognizerBenchmark/);
  assert.match(dashboard, /309\/309 Ground Truth đã xác nhận/);
  assert.match(css, /\.phase14-evaluation-grid/);
  assert.match(api, /PHASE14_REVIEWED_EVALUATION\.json/);
  assert.match(api, /CONTROLLED_PILOT_SUMMARY\.json/);
  assert.match(api, /PHASE14_3_EVALUATION\.json/);
  assert.match(api, /review_queue_private\.json/);
  assert.match(api, /SECOND_RECOGNIZER_EVALUATION\.json/);
  assert.match(api, /run_controlled_pilot_phase14_2\.py/);
  assert.match(api, /recommendedConfiguration/);
});

test("resumes after 172 persisted reviews instead of returning to the first crop", () => {
  const cases = Array.from({ length: 309 }, (_, index) => ({
    caseId: `LINE-${String(index + 1).padStart(3, "0")}`,
    groundTruth: `synthetic-${index + 1}`,
  }));
  const lineReviews = Object.fromEntries(
    cases.slice(0, 172).map((item) => [
      item.caseId,
      { groundTruth: item.groundTruth },
    ]),
  );

  const resume = resumePendingReview(cases, lineReviews);

  assert.equal(resume.pending.length, 137);
  assert.equal(resume.index, 0);
  assert.equal(resume.active.caseId, "LINE-173");
  assert.equal(pendingReviewCases(cases, lineReviews)[0].caseId, "LINE-173");
});

test("returns an empty queue after all crops are verified", () => {
  const cases = [
    { caseId: "LINE-001", groundTruth: "synthetic-a" },
    { caseId: "LINE-002", groundTruth: "synthetic-b" },
  ];
  const reviews = Object.fromEntries(
    cases.map((item) => [item.caseId, { groundTruth: item.groundTruth }]),
  );

  const resume = resumePendingReview(cases, reviews);

  assert.deepEqual(resume.pending, []);
  assert.equal(resume.active, null);
});

test("keeps mentor localhost evidence scoped behind private flags", async () => {
  const [overview, dashboard, envExample, starter] = await Promise.all([
    readFile(new URL("../app/LocalEvidenceOverview.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/Dashboard.tsx", import.meta.url), "utf8"),
    readFile(new URL("../.env.example", import.meta.url), "utf8"),
    readFile(new URL("../../api/start_dashboard.ps1", import.meta.url), "utf8"),
  ]);

  assert.match(overview, /\.\.\.\(SHOW_HELDOUT \? \[/);
  assert.match(overview, /SHOW_GROUND_TRUTH_REVIEW \? <article/);
  assert.match(overview, /SHOW_EXTERNAL_DATASET_REVIEW \? <article/);
  assert.match(dashboard, /SHOW_GROUND_TRUTH_REVIEW \? \(/);
  assert.match(
    dashboard,
    /SHOW_EXTERNAL_DATASET_REVIEW && evidenceMode === "external-dataset-prediction"/,
  );
  assert.match(envExample, /^VITE_SHOW_EXTERNAL_DATASET_REVIEW=false$/m);
  assert.doesNotMatch(starter, /VITE_SHOW_EXTERNAL_DATASET_REVIEW\s*=\s*"true"/);
});
