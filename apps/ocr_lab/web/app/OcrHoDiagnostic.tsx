"use client";

import { useEffect, useMemo, useState } from "react";

const API_BASE = "http://127.0.0.1:8765";
const FIELD_LIMITS = {
  fullName: 1,
  placeOfOrigin: 2,
  placeOfResidence: 2,
} as const;

type FieldName = keyof typeof FIELD_LIMITS;
type DiagnosticField = { value: string; lineIds: number[] };
type DiagnosticSummary = {
  documentCount: number;
  reviewedDocumentCount: number;
  documents: Array<{
    documentId: string;
    documentIndex: number;
    sourceFile: string;
    reviewed: boolean;
    drafted: boolean;
  }>;
};
type DiagnosticDetail = {
  documentId: string;
  sourceFile: string;
  fields: Record<FieldName, number>;
  imageSize?: [number, number];
  lines: Array<{ lineId: number; box: number[][] }>;
  review?: { fields?: Partial<Record<FieldName, DiagnosticField>> } | null;
};

const emptyFields = (): Record<FieldName, DiagnosticField> => ({
  fullName: { value: "", lineIds: [] },
  placeOfOrigin: { value: "", lineIds: [] },
  placeOfResidence: { value: "", lineIds: [] },
});

function parseLineIds(value: string): number[] {
  return value
    .split(",")
    .map((item) => Number(item.trim()))
    .filter((item, index, values) => Number.isInteger(item) && item >= 0 && values.indexOf(item) === index);
}

function linePoints(box: number[][]): string {
  return box.map(([x, y]) => `${x},${y}`).join(" ");
}

function updateLineId(field: DiagnosticField, index: number, value: string, limit: number): number[] {
  const parsed = parseLineIds(value);
  const next = [...field.lineIds];
  if (!parsed.length) next.splice(index, 1);
  else if (index === 0 && parsed.length > 1) return parsed.slice(0, limit);
  else next[index] = parsed[0];
  return [...new Set(next)].slice(0, limit);
}

export default function OcrHoDiagnostic() {
  const [summary, setSummary] = useState<DiagnosticSummary | null>(null);
  const [activeId, setActiveId] = useState("");
  const [detail, setDetail] = useState<DiagnosticDetail | null>(null);
  const [fields, setFields] = useState<Record<FieldName, DiagnosticField>>(emptyFields);
  const [assertions, setAssertions] = useState({
    comparedWithSource: false,
    allTextChecked: false,
    linesChecked: false,
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [draftSaved, setDraftSaved] = useState(false);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_BASE}/ocr-ho-v2/diagnostic/summary`)
      .then((response) => {
        if (!response.ok) throw new Error("Prediction-blind Ground Truth unavailable");
        return response.json() as Promise<DiagnosticSummary>;
      })
      .then((payload) => {
        if (cancelled) return;
        setSummary(payload);
        setActiveId((current) =>
          payload.documents.some((item) => item.documentId === current)
            ? current
            : payload.documents[0]?.documentId ?? "",
        );
        setError("");
      })
      .catch((reason) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Không đọc được Ground Truth local.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!activeId) {
      return;
    }
    let cancelled = false;
    fetch(`${API_BASE}/ocr-ho-v2/diagnostic/document?id=${encodeURIComponent(activeId)}`)
      .then((response) => {
        if (!response.ok) throw new Error("Diagnostic document unavailable");
        return response.json() as Promise<DiagnosticDetail>;
      })
      .then((payload) => {
        if (cancelled) return;
        setDetail(payload);
        setSaved(false);
        setDraftSaved(false);
        setDirty(false);
        const next = emptyFields();
        for (const name of Object.keys(next) as FieldName[]) {
          const existing = payload.review?.fields?.[name];
          if (existing) next[name] = { value: existing.value ?? "", lineIds: existing.lineIds ?? [] };
        }
        setFields(next);
        const review = payload.review as { assertions?: typeof assertions } | null | undefined;
        setAssertions(review?.assertions ?? { comparedWithSource: false, allTextChecked: false, linesChecked: false });
      })
      .catch((reason) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Không đọc được tài liệu local.");
      });
    return () => {
      cancelled = true;
    };
  }, [activeId]);

  const validLineIds = useMemo(() => new Set(detail?.lines.map((line) => line.lineId) ?? []), [detail]);
  const canSave = Boolean(
    detail &&
      Object.entries(fields).every(([name, field]) => {
        const limit = FIELD_LIMITS[name as FieldName];
        return field.value.trim() && field.lineIds.length > 0 && field.lineIds.length <= limit && field.lineIds.every((id) => validLineIds.has(id));
      }) &&
      Object.values(assertions).every(Boolean),
  );

  const hasDraftData = Boolean(
    detail &&
      (Object.values(fields).some((field) => field.value.trim() || field.lineIds.length > 0) ||
        Object.values(assertions).some(Boolean)),
  );

  const saveDraft = async (): Promise<boolean> => {
    if (!activeId || !hasDraftData || saving) return !dirty;
    setSaving(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE}/ocr-ho-v2/diagnostic/draft?id=${encodeURIComponent(activeId)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ fields, assertions, predictionOpened: false, draft: true }),
      });
      const payload = (await response.json()) as { error?: string };
      if (!response.ok) throw new Error(payload.error ?? "KhÃ´ng lÆ°u Ä‘Æ°á»£c báº£n nhÃ¡p Ground Truth");
      setDirty(false);
      setDraftSaved(true);
      setSummary((current) => current && { ...current, documents: current.documents.map((item) => item.documentId === activeId ? { ...item, drafted: true } : item) });
      return true;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "KhÃ´ng lÆ°u Ä‘Æ°á»£c báº£n nhÃ¡p local.");
      return false;
    } finally {
      setSaving(false);
    }
  };

  const selectDocument = async (nextId: string) => {
    if (nextId === activeId) return;
    if (dirty && !(await saveDraft())) return;
    setActiveId(nextId);
  };

  const save = async () => {
    if (!activeId || !canSave || saving) return;
    setSaving(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE}/ocr-ho-v2/diagnostic/review?id=${encodeURIComponent(activeId)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ fields, assertions, predictionOpened: false }),
      });
      const payload = (await response.json()) as { error?: string };
      if (!response.ok) throw new Error(payload.error ?? "Không lưu được Ground Truth");
      setSaved(true);
      setDraftSaved(false);
      setDirty(false);
      setSummary((current) => current && { ...current, reviewedDocumentCount: current.documents.filter((item) => item.reviewed || item.documentId === activeId).length, documents: current.documents.map((item) => item.documentId === activeId ? { ...item, reviewed: true } : item) });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không lưu được Ground Truth local.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="heldout-evidence-grid shadow-uat-grid diagnostic-gt-grid">
      <div className="heldout-document-list" role="list">
        {summary?.documents.map((document) => (
          <button className={document.documentId === activeId ? "active" : ""} key={document.documentId} onClick={() => void selectDocument(document.documentId)} role="listitem">
            <span>DEV-{String(document.documentIndex).padStart(2, "0")}</span>
            <strong>{document.sourceFile}</strong>
            <small>{document.reviewed ? "LINES CHECKED" : document.drafted ? "DRAFT SAVED" : "PENDING"} · prediction-blind</small>
          </button>
        ))}
        {!summary?.documents.length && !loading ? <div className="evidence-inspector-state">{error || "Chưa có tài liệu development."}</div> : null}
      </div>
      <div className="heldout-preview">
        {activeId ? <div className="diagnostic-preview-stage">
          <img src={`${API_BASE}/ocr-ho-v2/diagnostic/document?id=${encodeURIComponent(activeId)}&mode=preview`} alt="Ảnh nguồn Ground Truth prediction-blind" />
          {detail ? <svg className="diagnostic-overlay" viewBox={`0 0 ${detail.imageSize?.[0] ?? 2000} ${detail.imageSize?.[1] ?? 1261}`} role="img" aria-label="Overlay line ID detector">
            {detail.lines.map((line) => <g key={line.lineId}><polygon points={linePoints(line.box)} /><text x={line.box[0]?.[0] ?? 0} y={Math.max(14, (line.box[0]?.[1] ?? 0) - 4)}>{line.lineId}</text></g>)}
          </svg> : null}
        </div> : <div className="native-heldout-file"><strong>Chưa chọn tài liệu</strong></div>}
        {detail ? <div className="diagnostic-line-list"><strong>Line ID được detector trả về</strong>{detail.lines.map((line) => <span key={line.lineId}>line {line.lineId}: [{line.box.join(", ")}]</span>)}</div> : null}
      </div>
      <aside className="evidence-inspector shadow-uat-inspector diagnostic-gt-inspector" data-testid="ocr-ho-diagnostic-inspector">
        <header><div><span>PREDICTION-BLIND · LOCAL-ONLY</span><strong>GROUND TRUTH LINE MAPPING</strong></div><small>Không nạp baseline, candidate hoặc prediction</small></header>
        <div className="shadow-uat-banner"><strong>Ảnh nguồn → giá trị xác nhận → line ID</strong><span>Chỉ nhập nội dung nhìn thấy trên ảnh. Mỗi field phải có line ID hợp lệ.</span></div>
        {detail ? <div className="diagnostic-fields">{(Object.keys(FIELD_LIMITS) as FieldName[]).map((name) => <label key={name}><span>{name} · tối đa {FIELD_LIMITS[name]} dòng</span><input value={fields[name].value} onChange={(event) => { setDirty(true); setDraftSaved(false); setFields((current) => ({ ...current, [name]: { ...current[name], value: event.target.value } })); }} placeholder="Nhập đúng nội dung trên ảnh" /><div className="diagnostic-line-inputs">{Array.from({ length: FIELD_LIMITS[name] }, (_, index) => <input key={index} value={fields[name].lineIds[index] ?? ""} onChange={(event) => { setDirty(true); setDraftSaved(false); setFields((current) => ({ ...current, [name]: { ...current[name], lineIds: updateLineId(current[name], index, event.target.value, FIELD_LIMITS[name]) } })); }} placeholder={`Line ID dòng ${index + 1}${index ? " (nếu có)" : ""}`} inputMode="numeric" />)}</div><small>{fields[name].lineIds.length} line đã chọn{fields[name].lineIds.length ? `: ${fields[name].lineIds.join(" + ")}` : ""}</small></label>)}</div> : null}
        <div className="shadow-uat-assertions">{(["comparedWithSource", "allTextChecked", "linesChecked"] as const).map((name) => <label key={name}><input type="checkbox" checked={assertions[name]} onChange={(event) => { setDirty(true); setDraftSaved(false); setAssertions((current) => ({ ...current, [name]: event.target.checked })); }} />{name === "comparedWithSource" ? "Đã đối chiếu ảnh nguồn" : name === "allTextChecked" ? "Đã kiểm tra toàn bộ chữ" : "Đã xác nhận đủ line ID"}</label>)}</div>
        {error ? <small className="shadow-uat-error">{error}</small> : null}
        <div className="diagnostic-actions"><button type="button" className="diagnostic-draft-button" onClick={() => void saveDraft()} disabled={!hasDraftData || saving}>{saving ? "Đang lưu…" : draftSaved ? "Đã lưu bản nháp" : "Lưu bản nháp local"}</button><button type="button" onClick={() => void save()} disabled={!canSave || saving}>{saving ? "Đang lưu…" : saved ? "Đã lưu line mapping" : "Lưu Ground Truth local"}</button></div>
      </aside>
    </div>
  );
}
