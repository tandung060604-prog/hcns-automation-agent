import { useEffect, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8765";

type SmokeReport = {
  milestone: string;
  evaluationKind: string;
  mode: string;
  passed: boolean;
  fixtureCount: number;
  getRequestCount: number;
  postRequestCount: number;
  httpMethodPolicy: string;
  phase15BridgeProjectionCount: number;
  manualReviewCount: number;
  autoContinueCount: number;
  scalarOnly: boolean;
  opaqueReferenceOnly: boolean;
  schemaWhitelistErrorCount: number;
  nonScalarValueCount: number;
  sourceMutationCount: number;
  camundaProcessStartAttempts: number;
  hrisSideEffectCount: number;
  notificationSideEffectCount: number;
  groundTruthUsed: boolean;
  evaluateOnceArtifactTouched: boolean;
  realCohortOpened: boolean;
  containsRawFieldValues: boolean;
  promotionAllowed: boolean;
};

function Metric({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="local-benchmark-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Flag({ label, value }: { label: string; value: boolean }) {
  return (
    <span className={`m5-cam-006-flag ${value ? "is-on" : "is-off"}`}>
      {label}: {String(value)}
    </span>
  );
}

export default function M5Cam006SmokePanel() {
  const [report, setReport] = useState<SmokeReport | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(`${API_BASE}/m5/cam-006/summary`)
      .then(async (response) => {
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error ?? "Smoke aggregate unavailable");
        return payload as SmokeReport;
      })
      .then((payload) => {
        setReport(payload);
        setError("");
      })
      .catch(() => setError("M5-CAM-006 smoke aggregate unavailable"));
  }, []);

  return (
    <section className="section local-shadow-section m5-cam-006-section" id="m5-cam-006-smoke">
      <div className="section-heading local-benchmark-heading">
        <div>
          <p className="eyebrow">M5-CAM-007 · READ-ONLY LOCAL</p>
          <h2>Phase15 bridge smoke aggregate</h2>
        </div>
        <p>Chỉ hiển thị counter an toàn từ smoke report local. Endpoint chỉ đọc; không mở Camunda hoặc side effect.</p>
      </div>
      {error ? <div className="api-warning">{error}</div> : null}
      {!report && !error ? <div className="local-benchmark-loading"><span /><span /><span /></div> : null}
      {report ? (
        <>
          <div className="local-shadow-banner">
            <strong>{report.passed ? "PASS · READ-ONLY" : "HOLD"}</strong>
            <span>{report.fixtureCount} fixture · {report.httpMethodPolicy} · promotionAllowed=false</span>
          </div>
          <div className="local-benchmark-metrics local-shadow-gates">
            <Metric label="Fixture count" value={report.fixtureCount} />
            <Metric label="GET requests" value={report.getRequestCount} />
            <Metric label="Bridge projections" value={report.phase15BridgeProjectionCount} />
            <Metric label="Scalar-only" value={String(report.scalarOnly)} />
            <Metric label="Opaque references" value={String(report.opaqueReferenceOnly)} />
            <Metric label="Manual review" value={report.manualReviewCount} />
            <Metric label="Auto-continue" value={report.autoContinueCount} />
            <Metric label="Source mutations" value={report.sourceMutationCount} />
            <Metric label="Camunda starts" value={report.camundaProcessStartAttempts} />
            <Metric label="HRIS side effects" value={report.hrisSideEffectCount} />
            <Metric label="Notification effects" value={report.notificationSideEffectCount} />
            <Metric label="Whitelist errors" value={report.schemaWhitelistErrorCount} />
          </div>
          <div className="m5-cam-006-flags" aria-label="M5-CAM-006 safety flags">
            <Flag label="POST requests" value={report.postRequestCount > 0} />
            <Flag label="Non-scalar values" value={report.nonScalarValueCount > 0} />
            <Flag label="Ground Truth used" value={report.groundTruthUsed} />
            <Flag label="Evaluate-once touched" value={report.evaluateOnceArtifactTouched} />
            <Flag label="Real cohort opened" value={report.realCohortOpened} />
            <Flag label="Raw values exposed" value={report.containsRawFieldValues} />
            <Flag label="Promotion allowed" value={report.promotionAllowed} />
          </div>
        </>
      ) : null}
    </section>
  );
}
