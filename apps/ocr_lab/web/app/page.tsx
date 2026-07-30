import type { Metadata } from "next";
import Dashboard from "./Dashboard";

export const metadata: Metadata = {
  title: "HR Document Intelligence Lab | OCR tiếng Việt",
  description:
    "OCR và IDP tài liệu HCNS tiếng Việt với bằng chứng từng trường, human review và xử lý hoàn toàn trên máy local.",
};

export default function Home() {
  return (
    <Dashboard
      data={{
        phases: [],
        nextSteps: [],
        processing: {
          engine: "Paddle detector + VietOCR verifier policy",
          ocrVersion: "Phase 14.8 locked",
          language: "vi",
          device: "cpu",
        },
        summary: {
          nativeJsonCount: 0,
          ocrSuccessCount: 0,
          groundTruthDocumentCount: 0,
          matchedGroundTruthDocumentCount: 0,
          evaluatedSampleCount: 0,
          evaluatedFieldInstanceCount: 0,
          cer: 0,
          wer: 0,
          exactMatchRate: 0,
          fieldPresenceRate: 0,
          durationMs: { total: 0, mean: 0, p50: 0, p95: 0 },
        },
        baselineSummary: {
          nativeJsonCount: 0,
          ocrSuccessCount: 0,
          cer: 0,
          wer: 0,
          exactMatchRate: 0,
          fieldPresenceRate: 0,
          durationMs: { total: 0, mean: 0, p50: 0, p95: 0 },
        },
        samples: [],
      }}
    />
  );
}
