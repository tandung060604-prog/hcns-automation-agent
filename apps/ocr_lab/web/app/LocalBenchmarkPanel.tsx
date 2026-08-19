import { useEffect, useState, type CSSProperties } from "react";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8765";

type BenchmarkRow = {
  key: string;
  label: string;
  benchmarkDocumentCount: number;
  benchmarkSampleCount: number;
  fieldCount: number | null;
  exactMatchRate: number | null;
  fieldPresenceRate: number | null;
  acceptedRate: number | null;
  acceptedLabel: string | null;
  cer: number | null;
  wer: number | null;
  localDocumentCount: number;
  status: "current" | "confirmed" | "baseline" | "prediction-only" | "unavailable";
  source: string;
  note: string;
  ocrAggregate?: string;
};

type BenchmarkPayload = {
  rows: BenchmarkRow[];
  notes: string[];
  evidence?: {
    displayOnly: boolean;
    reportConfigured: boolean;
    manifestConfigured: boolean;
    reportSchemaVersion: string | null;
    datasetId: string | null;
    reportDigest: string | null;
    manifestDigest: string | null;
    decision: string;
    promotionAllowed: boolean;
    containsRawFieldValues: boolean;
    groundTruthUsedForScoringOnly: boolean;
  };
};

function percent(value: number | null) {
  return value === null ? "Chưa có" : `${(value * 100).toFixed(1)}%`;
}

function statusLabel(status: BenchmarkRow["status"]) {
  return {
    current: "Đánh giá mới",
    confirmed: "CCCD đã xác nhận",
    baseline: "Baseline OCR",
    "prediction-only": "Prediction-only · chưa chấm",
    unavailable: "Chưa có điểm",
  }[status];
}

function ScoreRing({ value }: { value: number | null }) {
  const style = value === null
    ? undefined
    : ({ "--score": `${value * 100}%` } as CSSProperties);
  return (
    <div
      className={`local-benchmark-ring ${value === null ? "muted" : ""}`}
      style={style}
      aria-label={`Field exact ${percent(value)}`}
    >
      <strong>{percent(value)}</strong>
      <small>exact field</small>
    </div>
  );
}

function Metric({ label, value, suffix = "" }: { label: string; value: number | null; suffix?: string }) {
  return (
    <div className="local-benchmark-metric">
      <span>{label}</span>
      <strong>{percent(value)}{suffix}</strong>
    </div>
  );
}

function BenchmarkCard({ row }: { row: BenchmarkRow }) {
  return (
    <article className={`local-benchmark-card ${row.status}`}>
      <header>
        <div>
          <span className="local-benchmark-card-status">{statusLabel(row.status)}</span>
          <h3>{row.label}</h3>
        </div>
        <ScoreRing value={row.exactMatchRate} />
      </header>
      <div className="local-benchmark-metrics">
        <Metric label="Presence" value={row.fieldPresenceRate} />
        <Metric label="CER" value={row.cer} />
        <Metric label="WER" value={row.wer} />
      </div>
      <div className="local-benchmark-card-foot">
        <div>
          <strong>{row.benchmarkDocumentCount}</strong>
          <span>tài liệu benchmark</span>
        </div>
        <div>
          <strong>{row.localDocumentCount}</strong>
          <span>tài liệu local</span>
        </div>
        <div>
          <strong>{row.fieldCount ?? "Chưa có"}</strong>
          <span>field được chấm</span>
        </div>
        <div>
          <strong>{row.benchmarkSampleCount}</strong>
          <span>mẫu tính field</span>
        </div>
      </div>
      <p className="local-benchmark-card-note">{row.note}</p>
      {row.ocrAggregate && <small className="local-benchmark-ocr">{row.ocrAggregate}</small>}
      <small className="local-benchmark-card-source">{row.source}</small>
      {row.acceptedRate !== null && (
        <small className="local-benchmark-accepted">
          Accepted {percent(row.acceptedRate)} {row.acceptedLabel}
        </small>
      )}
    </article>
  );
}

function LoadingBenchmark() {
  return (
    <div className="local-benchmark-loading" aria-label="Đang tải benchmark">
      <span />
      <span />
      <span />
    </div>
  );
}

type LocalBenchmarkPanelProps = {
  embedded?: boolean;
};

export default function LocalBenchmarkPanel({ embedded = false }: LocalBenchmarkPanelProps) {
  const [payload, setPayload] = useState<BenchmarkPayload | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(`${API_BASE}/benchmark/summary`)
      .then((response) => {
        if (!response.ok) throw new Error("Benchmark local chưa sẵn sàng");
        return response.json() as Promise<BenchmarkPayload>;
      })
      .then((nextPayload) => {
        setPayload(nextPayload);
        setError("");
      })
      .catch((fetchError) => {
        setError(
          fetchError instanceof Error
            ? fetchError.message
            : "Không đọc được benchmark local.",
        );
      });
  }, []);

  return (
    <section className={`section local-benchmark-section${embedded ? " local-benchmark-section-embedded" : ""}`} id="local-benchmark">
      <div className="section-heading local-benchmark-heading">
        <div>
          <p className="eyebrow">SÁU FAMILY ACTIVE · LOCAL EVIDENCE</p>
          <h2>Đối chiếu đủ sáu loại tài liệu</h2>
        </div>
        <p>
          Mỗi card tách rõ mẫu benchmark, tài liệu local và số field được chấm.
          Số liệu thiếu trong nguồn giữ nguyên trạng thái chưa có.
        </p>
      </div>
      <div className="local-benchmark-flow" aria-label="Luồng tạo benchmark local">
        <div className="local-benchmark-flow-node">
          <span>Chọn mẫu</span>
          <strong>Tài liệu gốc</strong>
          <small>Đếm tài liệu duy nhất, không cộng nhầm biến thể ảnh.</small>
        </div>
        <div className="local-benchmark-flow-link" aria-hidden="true" />
        <div className="local-benchmark-flow-node active">
          <span>So khớp field</span>
          <strong>Prediction với Ground Truth</strong>
          <small>Exact, Presence, CER và WER chỉ hiện khi nguồn có tính.</small>
        </div>
        <div className="local-benchmark-flow-link" aria-hidden="true" />
        <div className="local-benchmark-flow-node">
          <span>Quyết định review</span>
          <strong>Local và Human Review</strong>
          <small>Tách điểm benchmark khỏi số tài liệu đang chạy trong local.</small>
        </div>
      </div>
      {error ? (
        <div className="api-warning">{error}</div>
      ) : !payload ? (
        <LoadingBenchmark />
      ) : (
        <>
          {payload.evidence && (
            <div className="local-benchmark-evidence" data-testid="benchmark-evidence">
              <strong>
                {payload.evidence.reportConfigured && payload.evidence.manifestConfigured
                  ? `Evidence aggregate-only · ${payload.evidence.decision}`
                  : "Evidence report chưa được cấu hình"}
              </strong>
              <span>
                {payload.evidence.datasetId ?? "Chưa có dataset"} · display-only · promotion disabled
              </span>
            </div>
          )}
          <div className="local-benchmark-visual-grid">
            {payload.rows.map((row) => <BenchmarkCard key={row.key} row={row} />)}
          </div>
          <div className="local-benchmark-notes">
            {payload.notes.map((note) => <span key={note}>{note}</span>)}
          </div>
        </>
      )}
    </section>
  );
}
