import type { Metadata } from "next";
import Dashboard from "../Dashboard";

export const metadata: Metadata = {
  title: "VinHRIS Workspace | Xử lý tài liệu HR local",
  description: "Workspace local-first của VinHRIS cho intake tài liệu, evidence, structured result và Human Review.",
};

export default function WorkspacePage() {
  return (
    <Dashboard data={{
      phases: [], nextSteps: [],
      processing: { engine: "Paddle detector + VietOCR verifier policy", ocrVersion: "Phase 14.8 locked", language: "vi", device: "cpu" },
      summary: { nativeJsonCount: 0, ocrSuccessCount: 0, groundTruthDocumentCount: 0, matchedGroundTruthDocumentCount: 0, evaluatedSampleCount: 0, evaluatedFieldInstanceCount: 0, cer: 0, wer: 0, exactMatchRate: 0, fieldPresenceRate: 0, durationMs: { total: 0, mean: 0, p50: 0, p95: 0 } },
      baselineSummary: { nativeJsonCount: 0, ocrSuccessCount: 0, cer: 0, wer: 0, exactMatchRate: 0, fieldPresenceRate: 0, durationMs: { total: 0, mean: 0, p50: 0, p95: 0 } },
      samples: [],
    }} />
  );
}
