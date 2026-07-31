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

test("server-renders the Vietnamese OCR dashboard", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>HR Document Intelligence Lab \| OCR tiếng Việt<\/title>/i);
  assert.match(html, /LOCAL PRIVATE OCR/);
  assert.match(html, /Đọc tài liệu/);
  assert.match(html, /Giữ bằng chứng/);
  assert.match(html, /Một luồng xử lý, bằng chứng đi cùng dữ liệu/);
  assert.match(html, /hr-document-intelligence-context\.webp/);
  assert.match(html, /Đưa tài liệu thật vào/);
  assert.match(html, /Không upload cloud/);
  assert.doesNotMatch(html, /Your site is taking shape|Building your site/);
});

test("keeps Phase 11.4 CCCD controls in the local upload flow", async () => {
  const [dashboard, css, page, layout] = await Promise.all([
    readFile(new URL("../app/Dashboard.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/globals.css", import.meta.url), "utf8"),
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
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
  assert.match(page, /<Dashboard/);
  assert.match(layout, /HR Document Intelligence Lab/);
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

  assert.match(dashboard, /\.png,\.jpg,\.jpeg,\.pdf,\.docx,\.xlsx/);
  assert.match(dashboard, /PNG, JPG, JPEG, PDF, DOCX, XLSX/);
  assert.match(dashboard, /phase12\?:/);
  assert.match(dashboard, /phase15\?:/);
  assert.match(dashboard, /PHASE 15 \/ UNIFIED INTAKE/);
  assert.match(dashboard, /Kết quả trên 18 tài liệu thật/);
  assert.match(dashboard, /Phương pháp nào đang thực sự chạy/);
  assert.match(dashboard, /primaryProfile=vietocr_vgg_seq2seq/);
  assert.match(dashboard, /Không auto-switch fallback/);
  assert.match(dashboard, /Tài liệu HCNS và CCCD đã review/);
  assert.match(dashboard, /CCCD đã Ground Truth/);
  assert.match(dashboard, /\/user\/source/);
  assert.match(dashboard, /\/heldout\/evidence/);
  assert.match(dashboard, /EvidenceInspector/);
  assert.match(dashboard, /upload HCNS local/);
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
    /SHOW_HELDOUT \? "heldout" : "uploads"/,
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
});

test("exposes Template-first upload and structured result inspection", async () => {
  const [dashboard, css] = await Promise.all([
    readFile(new URL("../app/Dashboard.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/globals.css", import.meta.url), "utf8"),
  ]);

  assert.match(dashboard, /\/api\/templates/);
  assert.match(dashboard, /\/api\/documents\/process/);
  assert.match(dashboard, /useState<"template" \| "legacy">\("template"\)/);
  assert.match(dashboard, /Mẫu chuẩn/);
  assert.match(dashboard, /DOCX · không OCR/);
  assert.match(dashboard, /Thông tin trích xuất từ biểu mẫu chuẩn/);
  assert.match(dashboard, /Xem JSON đầy đủ/);
  assert.match(dashboard, /Không có trong tài liệu/);
  assert.match(dashboard, /TemplateResultPanel/);
  assert.match(dashboard, /data-testid="local-document-input"/);
  assert.match(dashboard, /data-testid="template-result-panel"/);
  assert.match(css, /\.upload-mode-switch/);
  assert.match(css, /\.template-field-grid/);
  assert.match(css, /\.template-json/);
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
