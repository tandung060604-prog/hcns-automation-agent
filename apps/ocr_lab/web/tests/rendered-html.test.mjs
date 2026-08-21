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
  assert.match(
    html,
    /<title>VinHRIS \| Cổng tác nghiệp Hành chính - Nhân sự<\/title>/i,
  );
  assert.match(html, /VinHRIS/);
  assert.match(html, /CỔNG TÁC NGHIỆP HÀNH CHÍNH - NHÂN SỰ/);
  assert.match(html, /Hồ sơ rõ ràng\. Quy trình có kiểm soát\./);
  assert.match(html, /Business JSON/);
  assert.match(html, /template-first-local-workflow\.png/);
  assert.match(html, /Vào khu vực làm việc/);
  assert.match(html, /vinhris-hero-source\.mp4/);
  assert.match(html, /Bật âm thanh/);
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
  assert.match(layout, /VinHRIS \| Cổng tác nghiệp Hành chính - Nhân sự/);
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

test("keeps the VinHRIS workspace information architecture and local boundaries visible", async () => {
  const [dashboard, css] = await Promise.all([
    readFile(new URL("../app/Dashboard.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/globals.css", import.meta.url), "utf8"),
  ]);

  assert.match(dashboard, /Hồ sơ vào một chỗ\./);
  assert.match(dashboard, /Quy trình đi đúng nơi\./);
  assert.match(dashboard, /Intake/);
  assert.match(dashboard, /Human Review/);
  assert.match(dashboard, /104<span>\/109<\/span>/);
  assert.match(dashboard, /Chưa phải bằng chứng production/);
  assert.match(dashboard, /http:\/\/localhost:8080\/camunda\/app\/tasklist\/default\//);
  assert.match(dashboard, /Nội dung file không đi vào process variables/);
  assert.match(dashboard, /hr-document-intelligence-context\.webp/);
  assert.match(css, /--ops-navy: #061a28/);
  assert.match(css, /--ops-cyan: #25c6c8/);
  assert.match(css, /\.operations-site \.topbar nav::-webkit-scrollbar/);
  assert.match(css, /scroll-margin-top: 108px/);
  assert.match(css, /prefers-reduced-motion: reduce/);
});

test("exposes the Phase 15 multi-format IDP and field review flow", async () => {
  const [dashboard, css] = await Promise.all([
    readFile(new URL("../app/Dashboard.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/globals.css", import.meta.url), "utf8"),
  ]);

  assert.match(dashboard, /\.docx,\.pdf/);
  assert.match(dashboard, /CV\/Hợp đồng: DOCX, PDF · IELTS\/CCCD: PDF, PNG, JPG\/JPEG/);
  assert.match(dashboard, /CV \/ hồ sơ ứng viên/);
  assert.match(dashboard, /Hợp đồng lao động/);
  assert.match(dashboard, /phase12\?:/);
  assert.match(dashboard, /phase15\?:/);
  assert.match(dashboard, /PHASE 15 \/ UNIFIED INTAKE/);
  assert.match(dashboard, /SYSTEM \/ ALGORITHM VERSION/);
  assert.match(dashboard, /runtimeHealth/);
  assert.match(dashboard, /runtime-pipeline-grid/);
  assert.match(dashboard, /templateOcrProfile/);
  assert.match(dashboard, /SHOW_ADVANCED_DIAGNOSTICS &&/);
  assert.match(
    dashboard,
    /\{SHOW_LEGACY_UPLOAD \? \(\s*<section className="section" id="legacy-recognition-policy">/s,
  );
  assert.match(dashboard, /Tài liệu gắn trực tiếp với metric/);
  assert.match(dashboard, /CCCD đã Ground Truth/);
  assert.match(dashboard, /\/user\/source/);
  assert.match(dashboard, /EvidenceInspector/);
  assert.doesNotMatch(dashboard, /upload HCNS local/);
  assert.doesNotMatch(dashboard, /Tài liệu đã xử lý/);
  assert.match(dashboard, /CCCD Phase \$\{phase11Label/);
  assert.match(dashboard, /NGUỒN PREDICTION/);
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

test("does not expose the deleted legacy held-out corpus", async () => {
  const [dashboard, envExample] = await Promise.all([
    readFile(new URL("../app/Dashboard.tsx", import.meta.url), "utf8"),
    readFile(new URL("../.env.example", import.meta.url), "utf8"),
  ]);

  assert.doesNotMatch(dashboard, /SHOW_HELDOUT|\/heldout\//);
  assert.doesNotMatch(envExample, /VITE_SHOW_HELDOUT/);
  assert.match(
    dashboard,
    /const SHOW_GROUND_TRUTH_REVIEW = SHOW_ADVANCED_DIAGNOSTICS &&\s+import\.meta\.env\.VITE_SHOW_GROUND_TRUTH_REVIEW === "true"/,
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

test("exposes the OCR-HO-V2-014 local shadow UAT inspector behind a private flag", async () => {
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

test("exposes prediction-blind OCR-HO Ground Truth mapping behind a private flag", async () => {
  const [dashboard, component, envExample, api] = await Promise.all([
    readFile(new URL("../app/Dashboard.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/OcrHoDiagnostic.tsx", import.meta.url), "utf8"),
    readFile(new URL("../.env.example", import.meta.url), "utf8"),
    readFile(new URL("../../api/serve_dashboard_api.py", import.meta.url), "utf8"),
  ]);
  assert.match(dashboard, /VITE_SHOW_OCR_HO_DIAGNOSTIC_GT === "true"/);
  assert.match(envExample, /^VITE_SHOW_OCR_HO_DIAGNOSTIC_GT=false$/m);
  assert.match(component, /\/ocr-ho-v2\/diagnostic\/summary/);
  assert.match(component, /predictionOpened: false/);
  assert.match(component, /lineIds/);
  assert.match(component, /diagnostic-line-inputs/);
  assert.match(component, /line đã chọn/);
  assert.match(component, /diagnostic-overlay/);
  assert.match(component, /mode=preview/);
  assert.match(component, /diagnostic\/draft/);
  assert.match(component, /Lưu bản nháp local/);
  assert.match(component, /DRAFT SAVED/);
  assert.match(api, /\/ocr-ho-v2\/diagnostic\/document/);
  assert.match(api, /\/ocr-ho-v2\/diagnostic\/draft/);
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
  assert.match(envExample, /^VITE_SHOW_LEGACY_EXPLORER_TABS=false$/m);
  assert.match(dashboard, /<ExternalDatasetReview \/>/);
  assert.match(component, /\/external-dataset\/review/);
  assert.match(component, /reviewBase/);
  assert.match(component, /\/lock/);
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

test("exposes the private DATA-31 coverage decision panel", async () => {
  const [dashboard, component, envExample, api, starter] = await Promise.all([
    readFile(new URL("../app/Dashboard.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/ExternalDatasetReview.tsx", import.meta.url), "utf8"),
    readFile(new URL("../.env.example", import.meta.url), "utf8"),
    readFile(new URL("../../api/serve_dashboard_api.py", import.meta.url), "utf8"),
    readFile(new URL("../../api/start_dashboard.ps1", import.meta.url), "utf8"),
  ]);
  assert.match(dashboard, /VITE_SHOW_DATA31_COVERAGE_REVIEW === "true"/);
  assert.match(dashboard, /<ExternalDatasetReview data31 \/>/);
  assert.match(component, /\/data31\/coverage/);
  assert.match(component, /DATA-31 · GROUND TRUTH COVERAGE DECISION/);
  assert.match(component, /OUT_OF_SCOPE/);
  assert.match(component, /ielts-semantics/);
  assert.match(component, /Mã TRF\/credential/);
  assert.match(api, /\/data31\/coverage\/summary/);
  assert.match(api, /\/data31\/coverage\/save/);
  assert.match(api, /--external-dataset-coverage-decision/);
  assert.match(starter, /VITE_SHOW_DATA31_COVERAGE_REVIEW/);
  assert.match(envExample, /^VITE_SHOW_DATA31_COVERAGE_REVIEW=false$/m);
});

test("exposes one Template-first upload with source preview and structured results", async () => {
  const [dashboard, data29, css, envExample] = await Promise.all([
    readFile(new URL("../app/Dashboard.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/ExternalDatasetPrediction.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/globals.css", import.meta.url), "utf8"),
    readFile(new URL("../.env.example", import.meta.url), "utf8"),
  ]);

  assert.match(dashboard, /\/api\/templates/);
  assert.match(
    dashboard,
    /return response\.json\(\) as Promise<\{ userUpload: RuntimeHealth \}>/,
  );
  assert.match(dashboard, /runtime-system-panel/);
  assert.match(dashboard, /pipeline\.parserId/);
  assert.match(dashboard, /\/api\/documents\/process/);
  assert.doesNotMatch(dashboard, /\/api\/documents\/sessions/);
  assert.match(dashboard, /\/api\/documents\/result\?id=/);
  assert.match(dashboard, /\/api\/documents\/source\?id=/);
  assert.match(dashboard, /useState<"template" \| "legacy">\("template"\)/);
  assert.match(dashboard, /SHOW_LEGACY_UPLOAD/);
  assert.match(dashboard, /Tải tài liệu HCNS/);
  assert.match(dashboard, /Trích xuất tài liệu/);
  assert.match(dashboard, /CV\/Hợp đồng: DOCX, PDF · IELTS\/CCCD: PDF, PNG, JPG\/JPEG/);
  assert.match(dashboard, /\.docx,\.pdf,\.png,\.jpg,\.jpeg/);
  assert.match(dashboard, /Xem JSON đầy đủ/);
  assert.match(dashboard, /Không có trong tài liệu/);
  assert.match(dashboard, /TemplateResultPanel/);
  assert.match(dashboard, /"CV", "CERTIFICATE", "EMPLOYMENT_CONTRACT"/);
  assert.match(dashboard, /\/api\/camunda\/case\?id=/);
  assert.match(dashboard, /processInstanceId/);
  assert.match(dashboard, /Cập nhật trạng thái/);
  assert.match(dashboard, /TemplateComparisonPanel/);
  assert.match(dashboard, /\/api\/documents\/compare/);
  assert.match(dashboard, /\/api\/documents\/comparison\?id=/);
  assert.match(dashboard, /Prediction và Ground Truth theo từng field/);
  assert.match(dashboard, /data-testid="compare-current-file-button"/);
  assert.match(dashboard, /DATA-31 R7 · 13 tài liệu metric · 4 Contract · 5 CV · 4 IELTS/);
  assert.match(dashboard, /<ExternalDatasetPrediction version="data31"/);
  assert.match(dashboard, /ExternalDatasetPrediction version="data31"/);
  assert.match(data29, /DATA29_CATEGORIES/);
  assert.match(data29, /Contract/);
  assert.match(data29, /IELTS/);
  assert.match(data29, /item\.category === activeCategory/);
  assert.doesNotMatch(data29, /DATA29_SHOWCASE_CASES/);
  assert.doesNotMatch(dashboard, /DEVELOPMENT_AGGREGATE/);
  assert.match(dashboard, /templateParserVersion/);
  assert.match(dashboard, /ocrModels/);
  assert.match(dashboard, /TemplateDocumentPreview/);
  assert.match(dashboard, /inspectCamundaDocument/);
  assert.match(dashboard, /Đang mở bản gốc và JSON local/);
  assert.match(dashboard, /window\.location\.hash = "upload"/);
  assert.match(dashboard, /\.docx,\.pdf/);
  assert.match(dashboard, /data-testid="local-document-input"/);
  assert.match(dashboard, /data-testid="template-document-preview"/);
  assert.match(dashboard, /data-testid="template-result-panel"/);
  assert.match(dashboard, /\/assets\/hr-document-intelligence-context\.webp/);
  assert.match(css, /\.upload-mode-switch/);
  assert.match(css, /\.upload-workspace/);
  assert.match(css, /\.template-document-preview/);
  assert.match(css, /\.hero-workflow-visual/);
  assert.match(css, /\.template-field-grid/);
  assert.match(css, /\.template-comparison/);
  assert.match(css, /\.comparison-field-row/);
  assert.match(css, /\.comparison-status\.mismatch/);
  assert.match(css, /\.template-json/);
  assert.match(css, /\.data29-category-switch/);
  assert.match(css, /\.camunda-case-status/);
  assert.match(dashboard, /data-testid="product-showcase"/);
  assert.match(css, /\.product-showcase/);
  assert.match(envExample, /^VITE_SHOW_LEGACY_UPLOAD=false$/m);
  assert.match(envExample, /^VITE_ADVANCED_DIAGNOSTICS=false$/m);
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

  assert.doesNotMatch(overview, /SHOW_HELDOUT|\/heldout\//);
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

test("renders the document benchmark as a visual flow and card grid", async () => {
  const [component, css, api] = await Promise.all([
    readFile(new URL("../app/LocalBenchmarkPanel.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/globals.css", import.meta.url), "utf8"),
    readFile(new URL("../../api/serve_dashboard_api.py", import.meta.url), "utf8"),
  ]);
  assert.match(component, /local-benchmark-flow/);
  assert.match(component, /ScoreRing/);
  assert.match(component, /local-benchmark-visual-grid/);
  assert.match(component, /prediction-only/);
  assert.match(css, /\.local-benchmark-ring/);
  assert.match(css, /\.local-benchmark-flow/);
  assert.match(api, /\/benchmark\/summary/);
});
