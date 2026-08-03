"use client";

/* The review panel synchronizes local queue state with a loopback API. */
/* eslint-disable react-hooks/set-state-in-effect */
/* eslint-disable react-hooks/exhaustive-deps */

import { useEffect, useMemo, useState } from "react";

const API_BASE = "http://127.0.0.1:8765";

type ReviewDocument = {
  caseId: string;
  category: string;
  documentType: string;
  sourceFormat: string;
  sourceFile: string;
  pageCount: number;
  fields: Record<string, { value: string | null; reviewStatus: string; sensitive: boolean }>;
  reviewStatus: string;
};

type ReviewSummary = {
  datasetId: string;
  datasetVersion: string;
  documentCount: number;
  pageCount: number;
  fieldCount: number;
  groundTruthStatus: string;
  reviewStatus: string;
  predictionsHiddenDuringReview: boolean;
  localOnly: boolean;
  canLock: boolean;
  documents: Array<{
    caseId: string;
    category: string;
    documentType: string;
    sourceFormat: string;
    sourceFile: string;
    pageCount: number;
    reviewStatus: string;
    reviewedFieldCount: number;
    fieldCount: number;
  }>;
};

const TEXT_FORMATS = new Set(["PLAIN_TEXT", "TXT", "DOCX", "PPTX"]);
type ReviewCategory = "contract" | "cv" | "ielts";
const FIELD_LABELS: Record<string, string> = {
  full_name: "Họ và tên",
  skills: "Kỹ năng",
  education: "Học vấn",
  contract_number: "Số hợp đồng",
  contract_sign_date: "Ngày ký hợp đồng",
  effective_date: "Ngày hiệu lực",
  probation_end_date: "Ngày kết thúc thử việc",
  employer_name: "Tên doanh nghiệp",
  employer_representative: "Đại diện doanh nghiệp",
  employee_name: "Tên nhân viên",
  employee_id_number: "Số CCCD nhân viên",
  job_title: "Chức danh chuyên môn",
  workplace: "Địa điểm làm việc",
  weekly_hours: "Số giờ làm việc mỗi tuần",
  probation_salary_monthly: "Lương thử việc mỗi tháng",
  allowances_summary: "Phụ cấp và hỗ trợ",
  salary_payment_schedule: "Lịch trả lương",
  recipient_name: "Tên người nhận",
  credential_id: "Mã chứng chỉ",
  credential_type: "Loại chứng chỉ",
  overall_score: "Điểm tổng",
  issue_date: "Ngày cấp",
};

function categoryLabel(category: string): string {
  return { cv: "CV", contract: "Hợp đồng", ielts: "IELTS" }[category] ?? category;
}

export default function ExternalDatasetReview() {
  const [summary, setSummary] = useState<ReviewSummary | null>(null);
  const [reviewCategory, setReviewCategory] = useState<ReviewCategory>("contract");
  const [activeCaseId, setActiveCaseId] = useState("");
  const [document, setDocument] = useState<ReviewDocument | null>(null);
  const [values, setValues] = useState<Record<string, string | null>>({});
  const [previewText, setPreviewText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [locking, setLocking] = useState(false);

  const activeItem = useMemo(
    () =>
      summary?.documents.find(
        (item) => item.category === reviewCategory && item.caseId === activeCaseId,
      ) ?? null,
    [summary, reviewCategory, activeCaseId],
  );
  const scopedDocuments = useMemo(
    () => summary?.documents.filter((item) => item.category === reviewCategory) ?? [],
    [summary, reviewCategory],
  );
  const scopedFieldCount = scopedDocuments.reduce((total, item) => total + item.fieldCount, 0);
  const scopedReviewedFieldCount = scopedDocuments.reduce(
    (total, item) => total + item.reviewedFieldCount,
    0,
  );
  const previewUrl = activeCaseId
    ? `${API_BASE}/external-dataset/review/document?id=${encodeURIComponent(
        activeCaseId,
      )}&mode=preview`
    : "";

  async function refreshSummary(selectFirst = false) {
    const response = await fetch(`${API_BASE}/external-dataset/review/summary`);
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error ?? "Không đọc được queue review");
    setSummary(payload);
    if (selectFirst || !activeCaseId) {
      setActiveCaseId(
        payload.documents?.find(
          (item: ReviewSummary["documents"][number]) => item.category === reviewCategory,
        )?.caseId ?? "",
      );
    }
  }

  useEffect(() => {
    refreshSummary(true).catch((reason: unknown) =>
      setError(reason instanceof Error ? reason.message : "API review chưa sẵn sàng"),
    );
  }, []);

  useEffect(() => {
    if (!scopedDocuments.some((item) => item.caseId === activeCaseId)) {
      setActiveCaseId(scopedDocuments[0]?.caseId ?? "");
    }
  }, [scopedDocuments, activeCaseId]);

  useEffect(() => {
    if (!activeCaseId) {
      setDocument(null);
      return;
    }
    setLoading(true);
    setError("");
    Promise.all([
      fetch(
        `${API_BASE}/external-dataset/review/document?id=${encodeURIComponent(
          activeCaseId,
        )}&mode=detail`,
      ),
      fetch(
        `${API_BASE}/external-dataset/review/document?id=${encodeURIComponent(
          activeCaseId,
        )}&mode=preview`,
      ),
    ])
      .then(async ([detailResponse, previewResponse]) => {
        const detailPayload = await detailResponse.json();
        if (!detailResponse.ok) throw new Error(detailPayload.error ?? "Không đọc được tài liệu");
        setDocument(detailPayload);
        setValues(
          Object.fromEntries(
            Object.entries(detailPayload.fields ?? {}).map(([name, field]) => [
              name,
              (field as { value: string | null }).value,
            ]),
          ),
        );
        if (previewResponse.headers.get("content-type")?.includes("application/json")) {
          const previewPayload = await previewResponse.json();
          setPreviewText(previewPayload.text ?? "");
        } else {
          setPreviewText("");
        }
      })
      .catch((reason: unknown) =>
        setError(reason instanceof Error ? reason.message : "Không tải được tài liệu"),
      )
      .finally(() => setLoading(false));
  }, [activeCaseId]);

  async function save() {
    if (!document) return;
    setMessage("");
    setError("");
    const fields = Object.fromEntries(
      Object.entries(values).map(([name, value]) => [name, { value }]),
    );
    const response = await fetch(
      `${API_BASE}/external-dataset/review/save?id=${encodeURIComponent(document.caseId)}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ fields, reviewer: "local_user" }),
      },
    );
    const payload = await response.json();
    if (!response.ok) {
      setError(payload.error ?? "Không lưu được review");
      return;
    }
    setMessage(`Đã xác nhận ${payload.reviewedFieldCount} field cho ${document.caseId}.`);
    await refreshSummary();
  }

  async function lock() {
    if (!summary?.canLock || locking) return;
    if (!window.confirm("SEALED queue này? Sau đó không thể sửa Ground Truth.")) return;
    setLocking(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE}/external-dataset/review/lock`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirm: true }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error ?? "Không thể SEALED queue");
      setMessage("Đã SEALED Ground Truth. Predictions vẫn chưa được mở.");
      await refreshSummary();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không thể SEALED queue");
    } finally {
      setLocking(false);
    }
  }

  return (
    <section className="external-review-panel" data-testid="external-dataset-review">
      <div className="external-review-header">
        <div>
          <span className="eyebrow">DATA-08 · INDEPENDENT CONTRACT REVIEW</span>
          <h3>Review hợp đồng thử việc</h3>
          <p>
            Mở từng DOCX/PDF, đối chiếu nguồn và xác nhận 14 field cho mỗi hợp đồng. Ảnh đời thực
            sẽ được xử lý ở workstream sau; OCR/prediction bị ẩn trong suốt review.
          </p>
        </div>
        <div className="external-review-status">
          <strong>{summary?.groundTruthStatus ?? "CHƯA KẾT NỐI"}</strong>
          <span>
            {scopedDocuments.length} tài liệu · {scopedReviewedFieldCount}/{scopedFieldCount} field ·
            local-only
          </span>
        </div>
      </div>
      <div className="external-review-scope">
        <label>
          Phạm vi review
          <select
            value={reviewCategory}
            onChange={(event) => setReviewCategory(event.target.value as ReviewCategory)}
          >
            <option value="contract">Contract · 4 case / 56 field</option>
            <option value="cv">CV · review riêng</option>
            <option value="ielts">IELTS · review riêng</option>
          </select>
        </label>
      </div>
      {error ? <div className="ground-truth-review-error">{error}</div> : null}
      {message ? <div className="external-review-message">{message}</div> : null}
      <div className="external-review-grid">
        <div className="external-review-list" role="list">
          {scopedDocuments.map((item) => (
            <button
              className={item.caseId === activeCaseId ? "active" : ""}
              key={item.caseId}
              onClick={() => setActiveCaseId(item.caseId)}
              role="listitem"
              type="button"
            >
              <span>{item.caseId}</span>
              <strong>{categoryLabel(item.category)}</strong>
              <small>
                {item.sourceFormat} · {item.reviewedFieldCount}/{item.fieldCount} field · {item.reviewStatus}
              </small>
            </button>
          ))}
        </div>
        <div className="external-review-source">
          {activeItem && !TEXT_FORMATS.has(activeItem.sourceFormat) ? (
            activeItem.sourceFormat === "PDF_SCAN" || activeItem.sourceFormat === "PDF_TEXT" ? (
              <iframe title={`Preview ${activeItem.caseId}`} src={previewUrl} />
            ) : (
              // eslint-disable-next-line @next/next/no-img-element -- loopback-only source preview.
              <img src={previewUrl} alt={`Nguồn ${activeItem.sourceFile}`} />
            )
          ) : previewText ? (
            <pre>{previewText}</pre>
          ) : (
            <div className="native-heldout-file">
              <strong>{activeItem?.sourceFile ?? "Chọn tài liệu"}</strong>
              <p>{loading ? "Đang mở file…" : "Preview native chưa có nội dung."}</p>
            </div>
          )}
          {activeItem ? (
            <div className="heldout-preview-actions">
              <div>
                <strong>{activeItem.sourceFile}</strong>
                <span>{activeItem.documentType} · {activeItem.pageCount} trang</span>
              </div>
              <a
                href={`${API_BASE}/external-dataset/review/document?id=${encodeURIComponent(
                  activeItem.caseId,
                )}&mode=source`}
              >
                Mở / tải file gốc
              </a>
            </div>
          ) : null}
        </div>
        <div className="external-review-form">
          <div className="external-review-form-heading">
            <div>
              <span>Independent reviewer</span>
              <strong>{document?.caseId ?? "—"}</strong>
            </div>
            <small>{document?.reviewStatus ?? "PENDING"}</small>
          </div>
          {(document ? Object.keys(document.fields) : []).map((name) => {
            const absent = values[name] === null;
            return (
              <label className="external-review-field" key={name}>
                <span>{FIELD_LABELS[name] ?? name}</span>
                <input
                  value={values[name] ?? ""}
                  onChange={(event) =>
                    setValues((current) => ({ ...current, [name]: event.target.value }))
                  }
                  disabled={summary?.groundTruthStatus === "SEALED"}
                  placeholder={name}
                />
                <small>
                  <input
                    type="checkbox"
                    checked={absent}
                    onChange={(event) =>
                      setValues((current) => ({
                        ...current,
                        [name]: event.target.checked ? null : "",
                      }))
                    }
                    disabled={summary?.groundTruthStatus === "SEALED"}
                  />
                  Không có / không đọc được
                </small>
              </label>
            );
          })}
          <div className="external-review-actions">
            <button type="button" onClick={save} disabled={!document || summary?.groundTruthStatus === "SEALED"}>
              Lưu xác nhận tài liệu
            </button>
            <button type="button" onClick={lock} disabled={!summary?.canLock || locking}>
              {locking ? "Đang SEALED…" : `SEALED đủ ${summary?.fieldCount ?? 0} field`}
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}
