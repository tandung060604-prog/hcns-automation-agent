"use client";

import { useEffect, useMemo, useState } from "react";

const API_BASE = "http://127.0.0.1:8765";
type RecordValue = Record<string, unknown>;
type Summary = {
  status: string;
  documentCount: number;
  reportAvailable: boolean;
  documents: Array<{ caseId: string; category: string; sourceFormat: string; sourceFile: string; evaluationIncluded?: boolean; ocrScope?: string; recommendedAction?: string }>;
  report?: RecordValue;
};
type Props = { version?: "data12" | "data13" | "data29" | "data31" | "policy-v2" };
type Data29Category = "contract" | "cv" | "ielts";

const DATA29_CATEGORIES: Array<{ id: Data29Category; label: string }> = [
  { id: "contract", label: "Contract" },
  { id: "cv", label: "CV" },
  { id: "ielts", label: "IELTS" },
];

function object(value: unknown): RecordValue {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as RecordValue) : {};
}

export default function ExternalDatasetPrediction({ version = "data12" }: Props) {
  const endpoint = version === "data13"
    ? "/external-dataset/prediction-v13"
    : version === "policy-v2"
      ? "/external-dataset/policy-v2"
      : "/external-dataset/prediction";
  const [summary, setSummary] = useState<Summary | null>(null);
  const [activeCase, setActiveCase] = useState("");
  const [activeCategory, setActiveCategory] = useState<Data29Category>("contract");
  const [detail, setDetail] = useState<RecordValue | null>(null);
  const [error, setError] = useState("");
  const visibleDocuments = useMemo(
    () =>
      summary?.documents.filter(
        (item) => !["data29", "data31"].includes(version) || item.category === activeCategory,
      ) ?? [],
    [activeCategory, summary, version],
  );

  useEffect(() => {
    fetch(`${API_BASE}${endpoint}/summary`)
      .then(async (response) => {
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error ?? "DATA-12 chưa sẵn sàng");
        return payload as Summary;
      })
      .then((payload) => {
        setSummary(payload);
        setActiveCase(payload.documents.find(
          (item) => !["data29", "data31"].includes(version) || item.category === "contract",
        )?.caseId ?? "");
      })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Không đọc được DATA-12"));
  }, [endpoint, version]);

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

  const active = useMemo(() => visibleDocuments.find((item) => item.caseId === activeCase) ?? null, [visibleDocuments, activeCase]);
  const prediction = object(detail?.prediction);
  const fields = object(prediction.fields);
  const comparison = object(detail?.comparison);
  const hasComparison = Object.keys(comparison).length > 0;
  const report = object(summary?.report);
  const metrics = object(report.metrics);
  const comparedFields = Object.values(comparison).map(object);
  const exactFields = comparedFields.filter((item) => item.exact === true).length;
  const acceptedFields = comparedFields.filter((item) => item.match === true).length;

  return (
    <section className="external-review-panel data12-prediction" data-testid="external-dataset-prediction">
      {version === "policy-v2" ? <div className="external-review-message">DATA-25 Policy v2 post-hoc audit · DATA-24 official evaluate-once remains immutable</div> : null}
      <div className="external-review-heading">
        <div><span>{version === "data31" ? "DATA-31 R7 · LOCAL SHADOW" : version === "data29" ? "DATA-29 · HISTORICAL BASELINE" : version === "data13" ? "DATA-13 · OCR SCOPE" : "DATA-12 · LOCAL-ONLY"}</span><h2>Prediction ↔ Ground Truth</h2></div>
        <strong>{summary?.status ?? "LOADING"}</strong>
      </div>
      {summary && !hasComparison ? <div className="external-review-message">Prediction-only: Ground Truth not supplied; Field exact not evaluated.</div> : null}
      {error ? <div className="external-review-message">{error}</div> : null}
      {summary ? (
        <>
          <div className="local-evidence-metrics">
            {version === "policy-v2" ? <span className="local-evidence-metric"><small>Canonical exact</small><strong>{metrics.fieldExactMatchRate !== undefined ? `${(Number(metrics.fieldExactMatchRate) * 100).toFixed(1)}%` : "—"}</strong></span> : null}
            {version === "policy-v2" ? <span className="local-evidence-metric"><small>Raw exact</small><strong>{metrics.fieldRawExactMatchRate !== undefined ? `${(Number(metrics.fieldRawExactMatchRate) * 100).toFixed(1)}%` : "—"}</strong></span> : null}
            <span className="local-evidence-metric"><small>Tài liệu đang show</small><strong>{["data29", "data31"].includes(version) ? `${visibleDocuments.length}/${summary.documentCount}` : summary.documentCount}</strong></span>
            <span className="local-evidence-metric"><small>Field exact (toàn corpus)</small><strong>{metrics.fieldExactMatchCount !== undefined ? `${String(metrics.fieldExactMatchCount)}/${String(report.fieldCount ?? "—")}` : "—"}</strong></span>
            <span className="local-evidence-metric"><small>Field accepted (toàn corpus)</small><strong>{metrics.fieldAcceptedMatchCount !== undefined ? `${String(metrics.fieldAcceptedMatchCount)}/${String(report.fieldCount ?? "—")}` : "—"}</strong></span>
            <span className="local-evidence-metric"><small>Schema errors</small><strong>{metrics ? String(report.schemaErrors ?? "—") : "—"}</strong></span>
            <span className="local-evidence-metric"><small>Decision</small><strong>{String(report.decision ?? "HOLD")}</strong></span>
          </div>
          {["data29", "data31"].includes(version) ? (
            <div className="data29-category-switch" role="tablist" aria-label={`Loại tài liệu ${version === "data31" ? "DATA-31" : "DATA-29"}`}>
              {DATA29_CATEGORIES.map((category) => {
                const documents = summary.documents.filter((item) => item.category === category.id);
                return (
                  <button
                    className={activeCategory === category.id ? "active" : ""}
                    key={category.id}
                    onClick={() => {
                      setActiveCategory(category.id);
                      setActiveCase(documents[0]?.caseId ?? "");
                    }}
                    role="tab"
                    aria-selected={activeCategory === category.id}
                    type="button"
                  >
                    {category.label} <strong>{documents.length}</strong>
                  </button>
                );
              })}
            </div>
          ) : null}
          <div className="external-review-grid">
            <div className="external-review-list" role="list">
              {visibleDocuments.map((item) => (
                <button className={item.caseId === activeCase ? "active" : ""} key={item.caseId} onClick={() => setActiveCase(item.caseId)} type="button">
                  <small>{item.evaluationIncluded === false ? "UNSUPPORTED_FORMAT · MANUAL_REVIEW" : item.recommendedAction === "MANUAL_REVIEW" ? "MANUAL_REVIEW" : item.ocrScope ?? "—"}</small>
                  <span>{item.caseId}</span><strong>{item.category.toUpperCase()}</strong><small>{item.sourceFormat} · {item.sourceFile}</small>
                </button>
              ))}
            </div>
            <div className="external-review-source">
              {active?.evaluationIncluded === false ? (
                <div className="native-heldout-file">
                  <strong>{active.sourceFile}</strong>
                  <p>UNSUPPORTED_FORMAT → MANUAL_REVIEW. Không gọi OCR và không tính metric.</p>
                </div>
              ) : active && !["DOCX", "PLAIN_TEXT"].includes(active.sourceFormat) ? (
                active.sourceFormat === "PDF_SCAN" || active.sourceFormat === "PDF_TEXT" ?
                  <iframe title={`Preview ${active.caseId}`} src={`${API_BASE}/external-dataset/review/document?id=${encodeURIComponent(active.caseId)}&mode=preview`} /> :
                  // eslint-disable-next-line @next/next/no-img-element -- loopback-only source preview.
                  <img src={`${API_BASE}/external-dataset/review/document?id=${encodeURIComponent(active.caseId)}&mode=preview`} alt={active.sourceFile} />
              ) : <div className="native-heldout-file"><strong>{active?.sourceFile}</strong><p>Native source; prediction lấy từ parser local.</p></div>}
            </div>
            <div className="external-review-form">
              <div className="external-review-form-heading"><div><span>FIELD-LEVEL EVIDENCE</span><strong>{activeCase}</strong></div><small>{hasComparison ? `${exactFields}/${comparedFields.length} exact · ${acceptedFields}/${comparedFields.length} accepted` : detail?.predictionBlind === false ? "PREDICTION + GT" : "PREDICTION ONLY"}</small></div>
              {active?.evaluationIncluded === false ? <div className="external-review-message">Ảnh/PDF scan ngoài CCCD hoặc chứng chỉ bị loại theo DATA-13; hệ thống không gọi OCR và không tính metric.</div> : null}
              {Object.entries(fields).map(([name, field]) => {
                const item = object(field);
                const pair = object(comparison[name]);
                if (!hasComparison) {
                  const sourceSpan = object(item.sourceSpan);
                  return <div className="external-review-field" key={name}>
                    <span>{name}</span>
                    <strong>{String(item.value ?? "â€”")}</strong>
                    <small>Prediction only · status: {String(item.status ?? "not_found")}</small>
                    {item.method ? <small>method: {String(item.method)}{item.reviewReason ? ` · ${String(item.reviewReason)}` : ""}</small> : null}
                    {Object.keys(sourceSpan).length > 0 ? <small>sourceSpan: {JSON.stringify(sourceSpan)}</small> : null}
                  </div>;
                }
                const status = pair.match === true
                  ? String(pair.matchType ?? (pair.exact === true ? "EXACT" : "ACCEPTED"))
                  : String(pair.matchType ?? "MISMATCH");
                const evidence = Object.keys(object(item.sourceSpan)).length > 0
                  ? object(item.sourceSpan)
                  : object(item.evidence);
                return <div className="external-review-field" key={name}>
                  <span>{name}</span>
                  <strong>{String(item.value ?? "—")}</strong>
                  <small>Ground Truth: {String(pair.groundTruth ?? "—")} · Prediction: {String(pair.prediction ?? "—")} · {status}</small>
                  {String(pair.matchType ?? "").startsWith("PARTIAL") && pair.coverage !== undefined ? <small>Text coverage: {`${(Number(pair.coverage) * 100).toFixed(1)}%`}</small> : null}
                  {version === "policy-v2" && pair.normalizationReason ? <small>Normalization: {String(pair.normalizationReason)}</small> : null}
                  {version === "policy-v2" && pair.overExtraction === true ? <small>Over-extraction: accepted partial, not exact</small> : null}
                  {pair.diagnosis ? <small>Diagnosis: {String(pair.diagnosis)}</small> : null}
                  {Object.keys(evidence).length > 0 ? <small>Evidence: {JSON.stringify(evidence)}</small> : null}
                </div>;
              })}
            </div>
          </div>
        </>
      ) : null}
    </section>
  );
}
