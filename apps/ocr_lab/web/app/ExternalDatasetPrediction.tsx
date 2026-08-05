"use client";

import { useEffect, useMemo, useState } from "react";

const API_BASE = "http://127.0.0.1:8765";
type RecordValue = Record<string, unknown>;
type Summary = {
  status: string;
  documentCount: number;
  reportAvailable: boolean;
  documents: Array<{ caseId: string; category: string; sourceFormat: string; sourceFile: string; evaluationIncluded?: boolean; ocrScope?: string }>;
  report?: RecordValue;
};
type Props = { version?: "data12" | "data13" };

function object(value: unknown): RecordValue {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as RecordValue) : {};
}

export default function ExternalDatasetPrediction({ version = "data12" }: Props) {
  const endpoint = version === "data13"
    ? "/external-dataset/prediction-v13"
    : "/external-dataset/prediction";
  const [summary, setSummary] = useState<Summary | null>(null);
  const [activeCase, setActiveCase] = useState("");
  const [detail, setDetail] = useState<RecordValue | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(`${API_BASE}${endpoint}/summary`)
      .then(async (response) => {
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error ?? "DATA-12 chưa sẵn sàng");
        return payload as Summary;
      })
      .then((payload) => {
        setSummary(payload);
        setActiveCase(payload.documents[0]?.caseId ?? "");
      })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Không đọc được DATA-12"));
  }, [endpoint]);

  useEffect(() => {
    if (!activeCase) return;
    fetch(`${API_BASE}${endpoint}/document?id=${encodeURIComponent(activeCase)}`)
      .then(async (response) => {
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error ?? "Không đọc được prediction");
        return payload as RecordValue;
      })
      .then(setDetail)
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Không đọc được prediction"));
  }, [activeCase, endpoint]);

  const active = useMemo(() => summary?.documents.find((item) => item.caseId === activeCase) ?? null, [summary, activeCase]);
  const prediction = object(detail?.prediction);
  const fields = object(prediction.fields);
  const comparison = object(detail?.comparison);
  const report = object(summary?.report);
  const metrics = object(report.metrics);

  return (
    <section className="external-review-panel data12-prediction" data-testid="external-dataset-prediction">
      <div className="external-review-heading">
        <div><span>{version === "data13" ? "DATA-13 · OCR SCOPE" : "DATA-12 · LOCAL-ONLY"}</span><h2>Prediction ↔ Ground Truth</h2></div>
        <strong>{summary?.status ?? "LOADING"}</strong>
      </div>
      {error ? <div className="external-review-message">{error}</div> : null}
      {summary ? (
        <>
          <div className="local-evidence-metrics">
            <span className="local-evidence-metric"><small>Tài liệu</small><strong>{summary.documentCount}</strong></span>
            <span className="local-evidence-metric"><small>Field exact</small><strong>{metrics.fieldExactMatchRate !== undefined ? `${(Number(metrics.fieldExactMatchRate) * 100).toFixed(1)}%` : "—"}</strong></span>
            <span className="local-evidence-metric"><small>Schema errors</small><strong>{metrics ? String(report.schemaErrors ?? "—") : "—"}</strong></span>
            <span className="local-evidence-metric"><small>Decision</small><strong>{String(report.decision ?? "HOLD")}</strong></span>
          </div>
          <div className="external-review-grid">
            <div className="external-review-list" role="list">
              {summary.documents.map((item) => (
                <button className={item.caseId === activeCase ? "active" : ""} key={item.caseId} onClick={() => setActiveCase(item.caseId)} type="button">
                  <small>{item.evaluationIncluded === false ? "UNSUPPORTED_NO_OCR · không tính metric" : item.ocrScope ?? "—"}</small>
                  <span>{item.caseId}</span><strong>{item.category.toUpperCase()}</strong><small>{item.sourceFormat} · {item.sourceFile}</small>
                </button>
              ))}
            </div>
            <div className="external-review-source">
              {active && !["DOCX", "PLAIN_TEXT"].includes(active.sourceFormat) ? (
                active.sourceFormat === "PDF_SCAN" || active.sourceFormat === "PDF_TEXT" ?
                  <iframe title={`Preview ${active.caseId}`} src={`${API_BASE}/external-dataset/review/document?id=${encodeURIComponent(active.caseId)}&mode=preview`} /> :
                  // eslint-disable-next-line @next/next/no-img-element -- loopback-only source preview.
                  <img src={`${API_BASE}/external-dataset/review/document?id=${encodeURIComponent(active.caseId)}&mode=preview`} alt={active.sourceFile} />
              ) : <div className="native-heldout-file"><strong>{active?.sourceFile}</strong><p>Native source; prediction lấy từ parser local.</p></div>}
            </div>
            <div className="external-review-form">
              <div className="external-review-form-heading"><div><span>FIELD-LEVEL EVIDENCE</span><strong>{activeCase}</strong></div><small>{detail?.predictionBlind === false ? "PREDICTION + GT" : "PREDICTION ONLY"}</small></div>
              {active?.evaluationIncluded === false ? <div className="external-review-message">Ảnh/PDF scan ngoài CCCD hoặc chứng chỉ bị loại theo DATA-13; hệ thống không gọi OCR và không tính metric.</div> : null}
              {Object.entries(fields).map(([name, field]) => {
                const item = object(field);
                const pair = object(comparison[name]);
                return <div className="external-review-field" key={name}><span>{name}</span><strong>{String(item.value ?? "—")}</strong><small>Ground Truth: {String(pair.groundTruth ?? "—")} · {pair.exact === true ? "EXACT" : "MISMATCH"}</small></div>;
              })}
            </div>
          </div>
        </>
      ) : null}
    </section>
  );
}
