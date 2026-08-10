import { useEffect, useState } from "react";

const API_BASE = "http://127.0.0.1:8765";

type ShadowReport = {
  milestone: string;
  evaluationKind: string;
  mode: string;
  passed: boolean;
  documentCount: number;
  manualReviewCount: number;
  scanManualReviewCount: number;
  unsupportedManualReviewCount: number;
  idempotencyMismatchCount: number;
  duplicateReferenceCount: number;
  rawExposureCount: number;
  autoContinueCount: number;
  camundaProcessStartAttempts: number;
  realSideEffectCount: number;
  groundTruthUsed: boolean;
  evaluateOnceArtifactTouched: boolean;
  containsRawFieldValues: boolean;
  promotionAllowed: boolean;
};

function Gate({ label, value }: { label: string; value: number }) {
  return (
    <div className="local-benchmark-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export default function M5LocalShadowPanel() {
  const [report, setReport] = useState<ShadowReport | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(`${API_BASE}/m5/local-shadow-review/summary`)
      .then(async (response) => {
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error ?? "M5 shadow report unavailable");
        return payload as ShadowReport;
      })
      .then((payload) => {
        setReport(payload);
        setError("");
      })
      .catch((reason: unknown) => {
        setError(reason instanceof Error ? reason.message : "M5 shadow report unavailable");
      });
  }, []);

  return (
    <section className="section local-shadow-section" id="m5-local-shadow-review">
      <div className="section-heading local-benchmark-heading">
        <div>
          <p className="eyebrow">M5-CAM-002 · UI-ONLY LOCAL</p>
          <h2>Local shadow review safety</h2>
        </div>
        <p>
          Chỉ hiển thị aggregate/reference từ projection private. Không gọi
          Camunda, không đọc Ground Truth và không tạo side effect.
        </p>
      </div>
      {error ? <div className="api-warning">{error}</div> : null}
      {!report && !error ? <div className="local-benchmark-loading"><span /><span /><span /></div> : null}
      {report ? (
        <>
          <div className="local-shadow-banner">
            <strong>{report.passed ? "PASS · MANUAL_REVIEW ONLY" : "HOLD"}</strong>
            <span>{report.documentCount} tài liệu · promotionAllowed=false · mode={report.mode}</span>
          </div>
          <div className="local-benchmark-metrics local-shadow-gates">
            <Gate label="Manual review" value={report.manualReviewCount} />
            <Gate label="Scan manual review" value={report.scanManualReviewCount} />
            <Gate label="Unsupported manual review" value={report.unsupportedManualReviewCount} />
            <Gate label="Idempotency mismatch" value={report.idempotencyMismatchCount} />
            <Gate label="Duplicate reference" value={report.duplicateReferenceCount} />
            <Gate label="Raw exposure" value={report.rawExposureCount} />
            <Gate label="Auto-continue" value={report.autoContinueCount} />
            <Gate label="Camunda process starts" value={report.camundaProcessStartAttempts} />
            <Gate label="Real side effects" value={report.realSideEffectCount} />
          </div>
          <small className="local-benchmark-card-source">
            Ground Truth used: {String(report.groundTruthUsed)} · evaluate-once touched: {String(report.evaluateOnceArtifactTouched)} · raw values exposed: {String(report.containsRawFieldValues)}
          </small>
        </>
      ) : null}
    </section>
  );
}
