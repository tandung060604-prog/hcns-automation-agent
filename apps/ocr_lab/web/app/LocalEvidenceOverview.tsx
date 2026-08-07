"use client";

import { useEffect, useMemo, useState } from "react";

const API_BASE = "http://127.0.0.1:8765";
const SHOW_GROUND_TRUTH_REVIEW =
  import.meta.env.VITE_SHOW_GROUND_TRUTH_REVIEW === "true";
const SHOW_EXTERNAL_DATASET_REVIEW =
  import.meta.env.VITE_SHOW_EXTERNAL_DATASET_REVIEW === "true";
const SHOW_OCR_HO_SHADOW_UAT =
  import.meta.env.VITE_SHOW_OCR_HO_SHADOW_UAT === "true";

type EvidenceMode =
  | "templates"
  | "cccd"
  | "external-dataset"
  | "external-dataset-prediction"
  | "ocr-ho-v2-shadow";

type JsonRecord = Record<string, unknown>;

function object(value: unknown): JsonRecord {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as JsonRecord)
    : {};
}

type LocalEvidenceOverviewProps = {
  onOpen: (mode: EvidenceMode) => void;
};

type EndpointState = {
  key: string;
  payload: JsonRecord | null;
  error: string;
};

const ENDPOINTS: Array<{ key: string; path: string }> = [
  { key: "templates", path: "/api/documents/sessions" },
  ...(SHOW_GROUND_TRUTH_REVIEW
    ? [{ key: "cccd", path: "/cccd-heldout/review/summary" }]
    : []),
  ...(SHOW_OCR_HO_SHADOW_UAT
    ? [{ key: "shadow", path: "/ocr-ho-v2/shadow/summary" }]
    : []),
  ...(SHOW_EXTERNAL_DATASET_REVIEW
    ? [
        { key: "external", path: "/external-dataset/typed/summary" },
        {
          key: "externalPrediction",
          path: "/external-dataset/prediction/summary",
        },
      ]
    : []),
];

function percent(value: unknown, digits = 1): string {
  const number = Number(value);
  return Number.isFinite(number) ? `${(number * 100).toFixed(digits)}%` : "—";
}

function integer(value: unknown): string {
  const number = Number(value);
  return Number.isFinite(number) ? number.toLocaleString("vi-VN") : "—";
}

function errorLabel(error: string): string {
  return error.includes("404") ? "CHƯA NỐI ARTIFACT" : "KHÔNG ĐỌC ĐƯỢC";
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <span className="local-evidence-metric">
      <small>{label}</small>
      <strong>{value}</strong>
    </span>
  );
}

export default function LocalEvidenceOverview({ onOpen }: LocalEvidenceOverviewProps) {
  const [states, setStates] = useState<EndpointState[]>(
    ENDPOINTS.map(({ key }) => ({ key, payload: null, error: "" })),
  );

  useEffect(() => {
    let cancelled = false;
    Promise.all(
      ENDPOINTS.map(async ({ key, path }) => {
        try {
          const response = await fetch(`${API_BASE}${path}`);
          if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
          return { key, payload: (await response.json()) as JsonRecord, error: "" };
        } catch (error) {
          return {
            key,
            payload: null,
            error: error instanceof Error ? error.message : "request failed",
          };
        }
      }),
    ).then((next) => {
      if (!cancelled) setStates(next);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const byKey = useMemo(
    () => Object.fromEntries(states.map((state) => [state.key, state])),
    [states],
  ) as Record<string, EndpointState>;
  const cccd = object(byKey.cccd?.payload);
  const shadow = object(byKey.shadow?.payload);
  const external = object(byKey.external?.payload);
  const externalPrediction = object(byKey.externalPrediction?.payload);
  const templates = object(byKey.templates?.payload);
  const cccdMetrics = object(object(object(cccd.evaluation).metrics).phase11_6);
  const shadowCandidateMetrics = object(object(shadow.metrics).ocr_ho_v2_014);
  const externalNormalization = object(external.normalization);
  const externalScope = object(external.scope);
  const templateSessions = Array.isArray(templates.sessions) ? templates.sessions : [];
  const cccdPerField = object(cccdMetrics.perField);
  const weakestCccdFields = Object.entries(cccdPerField)
    .sort(([, left], [, right]) => Number(object(left).exactMatch ?? 0) - Number(object(right).exactMatch ?? 0))
    .slice(0, 3)
    .map(([name, metric]) => `${name} ${percent(object(metric).exactMatch)}`);

  return (
    <div className="local-evidence-overview" data-testid="local-evidence-overview">
      <div className="local-evidence-overview-banner">
        <div>
          <span className="eyebrow">LOCAL-ONLY · PREDICTION ↔ GROUND TRUTH</span>
          <h3>Đối chiếu thật trước khi mở Camunda</h3>
          <p>
            Prediction chỉ lấy từ artifact/runtime hiện có. Ground Truth chỉ dùng để
            tính chênh lệch sau khi prediction đã có; dữ liệu không được dùng để điền ngược.
          </p>
        </div>
        <strong>NO CAMUNDA</strong>
      </div>

      <div className="local-evidence-cards">
        {SHOW_GROUND_TRUTH_REVIEW ? <article className="local-evidence-card">
          <header>
            <span>CCCD MẶT TRƯỚC</span>
            <strong>{byKey.cccd?.payload ? "EVALUATE-ONCE" : errorLabel(byKey.cccd?.error ?? "")}</strong>
          </header>
          {byKey.cccd?.payload ? (
            <>
              <div className="local-evidence-metrics">
                <Metric label="Ảnh in-scope" value={integer(cccd.documentCount)} />
                <Metric label="Strict exact" value={percent(cccdMetrics.strictFieldExactMatch)} />
                <Metric label="Field presence" value={percent(cccdMetrics.fieldPresence)} />
                <Metric label="DER" value={percent(cccdMetrics.der)} />
              </div>
              <p>Field yếu nhất: {weakestCccdFields.join(" · ") || "chưa có per-field metric"}.</p>
            </>
          ) : <p>{byKey.cccd?.error || "Chưa có response."}</p>}
          <button type="button" onClick={() => onOpen("cccd")}>Mở CCCD evidence</button>
        </article> : null}

        {SHOW_OCR_HO_SHADOW_UAT ? <article className="local-evidence-card">
          <header>
            <span>OCR-HO-V2 v11.10.0</span>
            <strong>{byKey.shadow?.payload ? "SHADOW-ONLY" : errorLabel(byKey.shadow?.error ?? "")}</strong>
          </header>
          {byKey.shadow?.payload ? (
            <>
              <div className="local-evidence-metrics">
                <Metric label="Ảnh dev" value={integer(shadow.documentCount)} />
                <Metric label="Strict exact" value={percent(shadowCandidateMetrics.strictFieldExactMatch)} />
                <Metric label="DER" value={percent(shadowCandidateMetrics.der)} />
                <Metric label="Promotion" value={object(shadow.promotionGate).productionPromotionAllowed ? "ALLOW" : "HOLD"} />
              </div>
              <p>Ground Truth loaded: {String(shadow.groundTruthLoaded ?? false)} · mọi output vẫn MANUAL_REVIEW.</p>
            </>
          ) : <p>{byKey.shadow?.error || "Artifact shadow chưa nối vào process hiện tại."}</p>}
          <button type="button" onClick={() => onOpen("ocr-ho-v2-shadow")}>Mở shadow inspector</button>
        </article> : null}

        {SHOW_EXTERNAL_DATASET_REVIEW ? <article className="local-evidence-card">
          <header>
            <span>CV · IELTS · CONTRACT</span>
            <strong>{externalPrediction.reportAvailable ? "PREDICTION + GT" : byKey.externalPrediction?.payload ? "PREDICTION READY" : byKey.external?.payload ? "GROUND TRUTH ONLY" : errorLabel(byKey.external?.error ?? "")}</strong>
          </header>
          {byKey.external?.payload ? (
            <>
              <div className="local-evidence-metrics">
                <Metric label="Tài liệu active" value={integer(externalScope.activeDocumentCount)} />
                <Metric label="Field" value={integer(externalScope.activeFieldCount)} />
                <Metric label="Normalized" value={percent(Number(externalNormalization.normalizedFieldCount ?? 0) / Math.max(1, Number(externalScope.activeFieldCount ?? 0)))} />
                <Metric label="Missing" value={integer(externalNormalization.missingFieldCount)} />
              </div>
              <p>{externalPrediction.reportAvailable ? "DATA-12 đã evaluate-once; mở field inspector để xem giá trị thật và chẩn đoán." : "Prediction artifact chưa evaluate; số trên vẫn là typed Ground Truth, không phải OCR accuracy."}</p>
            </>
          ) : <p>{byKey.external?.error || "Chưa có response."}</p>}
          <button type="button" onClick={() => onOpen("external-dataset")}>Mở dataset review</button>
          <button type="button" onClick={() => onOpen("external-dataset-prediction")}>Mở prediction inspector</button>
        </article> : null}

        <article className="local-evidence-card">
          <header>
            <span>NGHỈ PHÉP · TĂNG CA</span>
            <strong>{byKey.templates?.payload ? "RUNTIME AVAILABLE" : errorLabel(byKey.templates?.error ?? "")}</strong>
          </header>
          {byKey.templates?.payload ? (
            <>
              <div className="local-evidence-metrics">
                <Metric label="Session" value={integer(templateSessions.length)} />
                <Metric label="Loại" value={integer(new Set(templateSessions.map((item) => object(item).documentType)).size)} />
                <Metric label="Manual review" value={templateSessions.length ? "ON" : "—"} />
                <Metric label="Schema" value={templateSessions.length ? "0 lỗi runtime" : "—"} />
              </div>
              <p>Full UAT đã ghi nhận riêng theo format; mở từng session để xem prediction, missing và JSON.</p>
            </>
          ) : <p>{byKey.templates?.error || "Chưa có response."}</p>}
          <button type="button" onClick={() => onOpen("templates")}>Mở template inspector</button>
        </article>
      </div>

      <div className="local-evidence-verdict">
        <strong>Verdict hiện tại: OCR chưa đủ gate để mở Camunda.</strong>
        <span>Template-first đạt gate riêng; CCCD và nhóm CV/IELTS/contract vẫn cần prediction artifact + đối chiếu field-level.</span>
      </div>
    </div>
  );
}
