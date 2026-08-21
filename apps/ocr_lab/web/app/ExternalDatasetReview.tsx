"use client";

/* The review panel synchronizes local queue state with a loopback API. */
/* eslint-disable react-hooks/set-state-in-effect */
/* eslint-disable react-hooks/exhaustive-deps */

import { useEffect, useMemo, useRef, useState } from "react";

const API_BASE = "http://127.0.0.1:8765";

type ReviewDocument = {
  caseId: string;
  category: string;
  documentType: string;
  sourceFormat: string;
  sourceFile: string;
  pageCount: number;
  fields: Record<string, {
    value: string | null;
    reviewStatus: string;
    sensitive: boolean;
    disposition?: string | null;
  }>;
  reviewStatus: string;
  reviewable: boolean;
  scopeStatus: string;
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
  decisionStatus?: string;
  missingFieldCount?: number;
  decidedFieldCount?: number;
  outOfScopeCount?: number;
  groundTruthIsImmutable?: boolean;
  ieltsSemantics?: Record<string, string>;
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
    reviewable: boolean;
    scopeStatus: string;
  }>;
};

type LocalReviewDraft = {
  values: Record<string, string>;
  absentFields: string[];
};

const TEXT_FORMATS = new Set(["PLAIN_TEXT", "TXT", "DOCX", "PPTX"]);
const DRAFT_STORAGE_PREFIX = "vinhris:data-08:review-draft:v2";
type ReviewCategory = "contract" | "cv" | "ielts";
const FIELD_LABELS: Record<string, string> = {
  full_name: "Họ và tên",
  headline: "Tiêu đề nghề nghiệp",
  email: "Email",
  phone_number: "Số điện thoại",
  address: "Địa chỉ",
  desired_role: "Vị trí mong muốn",
  years_experience: "Số năm kinh nghiệm",
  experience: "Kinh nghiệm làm việc",
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
  recipient_name: "Tên người nhận (Family name + First name)",
  credential_id: "Mã chứng chỉ",
  credential_type: "Loại chứng chỉ",
  overall_score: "Điểm tổng",
  issue_date: "Ngày cấp",
};
const FIELD_HINTS: Record<string, string> = {
  recipient_name:
    "Ghi nguyên chuỗi Family name + First name đúng thứ tự trên chứng chỉ; không tự đảo hoặc tách thành field khác.",
  credential_id:
    "Mã TRF/credential in trên chứng chỉ; giữ nguyên chữ, số và dấu; không dùng số CCCD.",
  credential_type:
    "Loại giấy tờ được in trên tài liệu, ví dụ IELTS Test Report Form; không phải điểm tổng.",
  overall_score:
    "Overall band score được in trên chứng chỉ, ví dụ 6.5; không thay bằng điểm từng kỹ năng.",
  issue_date:
    "Ngày cấp/ngày phát hành được in trên chứng chỉ; không tự dùng ngày thi nếu không có.",
};

function categoryLabel(category: string): string {
  return { cv: "CV", contract: "Hợp đồng", ielts: "IELTS" }[category] ?? category;
}

function categoryScopeLabel(
  summary: ReviewSummary | null,
  category: ReviewCategory,
): string {
  const documents =
    summary?.documents.filter((item) => item.category === category && item.reviewable) ?? [];
  const fields = documents.reduce((total, item) => total + item.fieldCount, 0);
  return `${categoryLabel(category)} · ${documents.length} case / ${fields} field`;
}

function draftStorageKey(caseId: string, data31: boolean): string {
  return `${data31 ? "vinhris:data31-coverage" : DRAFT_STORAGE_PREFIX}:${caseId}`;
}

function readLocalDraft(caseId: string, data31: boolean): LocalReviewDraft | null {
  try {
    const raw = window.localStorage.getItem(draftStorageKey(caseId, data31));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<LocalReviewDraft>;
    if (!parsed.values || typeof parsed.values !== "object") return null;
    return {
      values: Object.fromEntries(
        Object.entries(parsed.values).filter((entry): entry is [string, string] =>
          typeof entry[1] === "string",
        ),
      ),
      absentFields: Array.isArray(parsed.absentFields)
        ? parsed.absentFields.filter((name): name is string => typeof name === "string")
        : [],
    };
  } catch {
    return null;
  }
}

export default function ExternalDatasetReview({ data31 = false }: { data31?: boolean } = {}) {
  const reviewBase = data31 ? "/data31/coverage" : "/external-dataset/review";
  const suppressDraftPersistence = useRef(false);
  const [summary, setSummary] = useState<ReviewSummary | null>(null);
  const [reviewCategory, setReviewCategory] = useState<ReviewCategory>("contract");
  const [activeCaseId, setActiveCaseId] = useState("");
  const [document, setDocument] = useState<ReviewDocument | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [absentFields, setAbsentFields] = useState<string[]>([]);
  const [previewText, setPreviewText] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [locking, setLocking] = useState(false);
  const [confirmedForSave, setConfirmedForSave] = useState(false);

  const activeItem = useMemo(
    () =>
      summary?.documents.find(
        (item) =>
          item.category === reviewCategory && item.reviewable && item.caseId === activeCaseId,
      ) ?? null,
    [summary, reviewCategory, activeCaseId],
  );
  const scopedDocuments = useMemo(
    () =>
      summary?.documents.filter(
        (item) => item.category === reviewCategory && item.reviewable,
      ) ?? [],
    [summary, reviewCategory],
  );
  const scopedFieldCount = scopedDocuments.reduce((total, item) => total + item.fieldCount, 0);
  const scopedReviewedFieldCount = scopedDocuments.reduce(
    (total, item) => total + item.reviewedFieldCount,
    0,
  );
  const fieldNames = document ? Object.keys(document.fields) : [];
  const completedFieldCount = fieldNames.filter(
    (name) => absentFields.includes(name) || Boolean(values[name]?.trim()),
  ).length;
  const allFieldsCompleted = fieldNames.length > 0 && completedFieldCount === fieldNames.length;
  const canSave = Boolean(
    document &&
      (dirty || document.reviewStatus !== "CONFIRMED") &&
      allFieldsCompleted &&
      confirmedForSave &&
      !saving &&
      summary?.groundTruthStatus !== "SEALED",
  );
  const previewUrl = activeCaseId
    ? `${API_BASE}${reviewBase}/document?id=${encodeURIComponent(
        activeCaseId,
      )}&mode=preview`
    : "";

  async function refreshSummary(selectFirst = false) {
    const response = await fetch(`${API_BASE}${reviewBase}/summary`);
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error ?? "Không đọc được queue review");
    setSummary(payload);
    if (selectFirst || !activeCaseId) {
      setActiveCaseId(
        payload.documents?.find(
          (item: ReviewSummary["documents"][number]) =>
            item.category === reviewCategory && item.reviewable,
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
      setConfirmedForSave(false);
      setDirty(false);
      return;
    }
    setConfirmedForSave(false);
    setDirty(false);
    setValues({});
    setAbsentFields([]);
    setLoading(true);
    setError("");
    Promise.all([
      fetch(
        `${API_BASE}${reviewBase}/document?id=${encodeURIComponent(
          activeCaseId,
        )}&mode=detail`,
      ),
      fetch(
        `${API_BASE}${reviewBase}/document?id=${encodeURIComponent(
          activeCaseId,
        )}&mode=preview`,
      ),
    ])
      .then(async ([detailResponse, previewResponse]) => {
        const detailPayload = await detailResponse.json();
        if (!detailResponse.ok) throw new Error(detailPayload.error ?? "Không đọc được tài liệu");
        const names = Object.keys(detailPayload.fields ?? {});
        const serverValues = Object.fromEntries(
          Object.entries(detailPayload.fields ?? {}).map(([name, field]) => [
            name,
            (field as { value: string | null }).value ?? "",
          ]),
        );
        const serverAbsentFields = Object.entries(detailPayload.fields ?? {})
          .filter(
            ([, field]) =>
              (field as { value: string | null; reviewStatus: string }).value === null &&
              (field as { value: string | null; reviewStatus: string }).reviewStatus === "CONFIRMED",
          )
          .map(([name]) => name);
        const localDraft = readLocalDraft(activeCaseId, data31);
        const restoredValues = localDraft
          ? {
              ...serverValues,
              ...Object.fromEntries(
                Object.entries(localDraft.values).filter(([name]) => names.includes(name)),
              ),
            }
          : serverValues;
        const restoredAbsentFields = localDraft
          ? localDraft.absentFields.filter((name) => names.includes(name))
          : serverAbsentFields;
        setDocument(detailPayload);
        setValues(restoredValues);
        setAbsentFields(restoredAbsentFields);
        setDirty(Boolean(localDraft));
        if (localDraft) {
          setMessage(`Đã khôi phục bản nháp chưa lưu của ${activeCaseId}.`);
        }
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
  }, [activeCaseId, data31, reviewBase]);

  useEffect(() => {
    if (suppressDraftPersistence.current) {
      suppressDraftPersistence.current = false;
      return;
    }
    if (!dirty || !document) return;
    window.localStorage.setItem(
      draftStorageKey(document.caseId, data31),
      JSON.stringify({ values, absentFields } satisfies LocalReviewDraft),
    );
  }, [dirty, values, absentFields, document]);

  useEffect(() => {
    if (!dirty) return;
    const preventUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", preventUnload);
    return () => window.removeEventListener("beforeunload", preventUnload);
  }, [dirty]);

  function updateFieldValue(name: string, value: string) {
    setValues((current) => ({ ...current, [name]: value }));
    setAbsentFields((current) => current.filter((fieldName) => fieldName !== name));
    setDirty(true);
    setConfirmedForSave(false);
    setMessage("");
    setError("");
  }

  function updateAbsentField(name: string, absent: boolean) {
    setAbsentFields((current) =>
      absent
        ? Array.from(new Set([...current, name]))
        : current.filter((fieldName) => fieldName !== name),
    );
    setDirty(true);
    setConfirmedForSave(false);
    setMessage("");
    setError("");
  }

  function selectCase(caseId: string) {
    if (caseId === activeCaseId) return;
    if (dirty) {
      setError(
        `Bạn còn dữ liệu chưa lưu ở ${activeCaseId}. Hãy bấm “Lưu review hiện tại” hoặc bỏ bản nháp trước khi chuyển case.`,
      );
      return;
    }
    setError("");
    setMessage("");
    setActiveCaseId(caseId);
  }

  function selectCategory(category: ReviewCategory) {
    if (category === reviewCategory) return;
    if (dirty) {
      setError(
        `Bạn còn dữ liệu chưa lưu ở ${activeCaseId}. Hãy lưu hoặc bỏ bản nháp trước khi đổi phạm vi.`,
      );
      return;
    }
    setError("");
    setMessage("");
    setReviewCategory(category);
  }

  function discardDraft() {
    if (!document || !dirty) return;
    suppressDraftPersistence.current = true;
    setValues(
      Object.fromEntries(
        Object.entries(document.fields).map(([name, field]) => [name, field.value ?? ""]),
      ),
    );
    setAbsentFields(
      Object.entries(document.fields)
        .filter(([, field]) => field.value === null && field.reviewStatus === "CONFIRMED")
        .map(([name]) => name),
    );
    window.localStorage.removeItem(draftStorageKey(document.caseId, data31));
    setDirty(false);
    setConfirmedForSave(false);
    setError("");
    setMessage(`Đã bỏ bản nháp của ${document.caseId}.`);
  }

  async function save() {
    if (!document) return;
    if (!allFieldsCompleted) {
      setError(`Còn ${fieldNames.length - completedFieldCount} field chưa điền hoặc chưa đánh dấu không có.`);
      return;
    }
    if (!confirmedForSave) {
      setError("Hãy tick xác nhận đã đối chiếu đủ field trước khi lưu.");
      return;
    }
    setMessage("");
    setError("");
    setSaving(true);
    const fields = Object.fromEntries(
      fieldNames.map((name) => [
        name,
        {
          value: absentFields.includes(name) ? null : values[name]?.trim() ?? "",
          ...(data31
            ? {
                disposition: absentFields.includes(name) ? "OUT_OF_SCOPE" : "GROUND_TRUTH",
              }
            : {}),
        },
      ]),
    );
    try {
      const response = await fetch(
        `${API_BASE}${reviewBase}/save?id=${encodeURIComponent(document.caseId)}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ fields, reviewer: "local_user" }),
        },
      );
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error ?? "Không lưu được review");
      setMessage(
        `Đã lưu ${payload.reviewedFieldCount} field cho ${document.caseId}. Bạn có thể chuyển sang case tiếp theo.`,
      );
      setDocument((current) =>
        current
          ? {
              ...current,
              reviewStatus: payload.reviewStatus ?? "CONFIRMED",
              fields: Object.fromEntries(
                Object.entries(current.fields).map(([name, field]) => [
                  name,
                  {
                    ...field,
                    value: (fields[name] as { value: string | null }).value,
                    reviewStatus: "CONFIRMED",
                  },
                ]),
              ),
            }
          : current,
      );
      suppressDraftPersistence.current = true;
      window.localStorage.removeItem(draftStorageKey(document.caseId, data31));
      setDirty(false);
      setConfirmedForSave(false);
      await refreshSummary();
    } catch (reason) {
      setError(
        reason instanceof Error
          ? `Không lưu được review: ${reason.message}`
          : "Không lưu được review. Kiểm tra Local API rồi thử lại.",
      );
    } finally {
      setSaving(false);
    }
  }

  async function lock() {
    if (!summary?.canLock || locking) return;
    if (!window.confirm("SEALED queue này? Sau đó không thể sửa Ground Truth.")) return;
    setLocking(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE}${reviewBase}/lock`, {
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
    <section
      className="external-review-panel"
      data-testid={data31 ? "data31-coverage-review" : "external-dataset-review"}
    >
      <div className="external-review-header">
        <div>
          <span className="eyebrow">
            {data31 ? "DATA-31 · GROUND TRUTH COVERAGE DECISION" : "EXTERNAL DATASET · INDEPENDENT REVIEW"}
          </span>
          <h3>
            {data31
              ? "Bổ sung GT còn thiếu hoặc loại field khỏi phạm vi đo"
              : "Review CV, hợp đồng và IELTS"}
          </h3>
          <p>
            {data31
              ? "Baseline DATA-31 đã SEALED và không bị sửa. Chọn từng tài liệu, mở file thật, điền các ô còn thiếu hoặc đánh dấu OUT_OF_SCOPE; quyết định chỉ lưu trong private storage."
              : "Chọn từng phạm vi, mở nguồn và xác nhận field trực tiếp từ tài liệu. CV dạng text/PPTX đang nằm ngoài active review; OCR/prediction bị ẩn trong suốt review."}
          </p>
        </div>
        <div className="external-review-status">
          <strong>
            {data31
              ? summary?.decisionStatus ?? "CHƯA KẾT NỐI"
              : summary?.groundTruthStatus ?? "CHƯA KẾT NỐI"}
          </strong>
          <span>
            {data31
              ? `${summary?.decidedFieldCount ?? scopedReviewedFieldCount}/${summary?.missingFieldCount ?? scopedFieldCount} ô đã quyết định · ${summary?.outOfScopeCount ?? 0} OUT_OF_SCOPE · private-only`
              : `${scopedDocuments.length} tài liệu · ${scopedReviewedFieldCount}/${scopedFieldCount} field · local-only`}
          </span>
        </div>
      </div>
      <div className="external-review-scope">
        <label>
          Phạm vi review
          <select
            value={reviewCategory}
            onChange={(event) => selectCategory(event.target.value as ReviewCategory)}
          >
            <option value="contract">{categoryScopeLabel(summary, "contract")}</option>
            <option value="cv">{categoryScopeLabel(summary, "cv")}</option>
            <option value="ielts">{categoryScopeLabel(summary, "ielts")}</option>
          </select>
        </label>
      </div>
      {data31 && reviewCategory === "ielts" ? (
        <div className="external-review-message" data-testid="ielts-semantics">
          <strong>Semantics IELTS đã khóa</strong>
          <div className="external-review-semantics">
            {Object.entries(summary?.ieltsSemantics ?? FIELD_HINTS).map(([name, meaning]) => (
              <div key={name}>
                <strong>{FIELD_LABELS[name] ?? name}</strong>
                <span>{meaning}</span>
              </div>
            ))}
          </div>
          <span>
            IELTS hiện không có field thiếu GT trong DATA-31; không cần điền lại và không tự suy diễn
            ngày thi thành ngày cấp.
          </span>
        </div>
      ) : null}
      {error ? <div className="ground-truth-review-error">{error}</div> : null}
      {message ? <div className="external-review-message">{message}</div> : null}
      <div className="external-review-grid">
        <div className="external-review-list" role="list">
          {scopedDocuments.map((item) => (
            <button
              className={item.caseId === activeCaseId ? "active" : ""}
              key={item.caseId}
              onClick={() => selectCase(item.caseId)}
              role="listitem"
              type="button"
            >
              <span>{item.caseId}</span>
              <strong>{categoryLabel(item.category)}</strong>
              <small>
                {item.sourceFormat} ·{" "}
                {item.caseId === activeCaseId && dirty
                  ? completedFieldCount
                  : item.reviewedFieldCount}
                /{item.fieldCount} field ·{" "}
                {item.caseId === activeCaseId && dirty ? "BẢN NHÁP" : item.reviewStatus}
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
                href={`${API_BASE}${reviewBase}/document?id=${encodeURIComponent(
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
            <small>{dirty ? "BẢN NHÁP CHƯA LƯU" : document?.reviewStatus ?? "PENDING"}</small>
          </div>
          <div className={`external-review-save-bar${dirty ? " is-dirty" : ""}`} aria-live="polite">
            <div className="external-review-save-progress">
              <strong>
                {completedFieldCount}/{fieldNames.length || 0} field đã điền
              </strong>
              <span>
                {dirty
                  ? "Bản nháp đang được giữ trên trình duyệt; bấm Lưu để ghi vào Ground Truth."
                  : document?.reviewStatus === "CONFIRMED"
                    ? "Case này đã được lưu vào Ground Truth."
                    : "Điền đủ field hoặc đánh dấu Không có / không đọc được."}
              </span>
            </div>
            <label className="external-review-confirmation">
              <input
                type="checkbox"
                checked={confirmedForSave}
                onChange={(event) => {
                  setConfirmedForSave(event.target.checked);
                  setError("");
                }}
                disabled={
                  !document ||
                  !allFieldsCompleted ||
                  summary?.groundTruthStatus === "SEALED"
                }
              />
              <span>Tôi đã đối chiếu đủ field với tài liệu gốc.</span>
            </label>
            <button
              className="external-review-primary-save"
              data-testid="save-current-external-review"
              type="button"
              onClick={save}
              disabled={!canSave}
            >
              {saving ? "Đang lưu…" : "Lưu review hiện tại"}
            </button>
          </div>
          {(document ? Object.keys(document.fields) : []).map((name) => {
            const absent = absentFields.includes(name);
            return (
              <label className="external-review-field" key={name}>
                <span>{FIELD_LABELS[name] ?? name}</span>
                {FIELD_HINTS[name] ? <small>{FIELD_HINTS[name]}</small> : null}
                <input
                  value={values[name] ?? ""}
                  onChange={(event) => updateFieldValue(name, event.target.value)}
                  disabled={summary?.groundTruthStatus === "SEALED" || absent}
                  placeholder={name}
                />
                <small>
                  <input
                    type="checkbox"
                    checked={absent}
                    onChange={(event) => updateAbsentField(name, event.target.checked)}
                    disabled={summary?.groundTruthStatus === "SEALED"}
                  />
                  {data31 ? "Loại khỏi phạm vi đo (OUT_OF_SCOPE)" : "Không có / không đọc được"}
                </small>
              </label>
            );
          })}
          {data31 && document && fieldNames.length === 0 ? (
            <div className="external-review-message">
              Case này không còn field thiếu Ground Truth. Chỉ cần kiểm tra file nguồn và semantics
              IELTS (nếu đang ở phạm vi IELTS).
            </div>
          ) : null}
          <div className="external-review-actions">
            <button
              className="external-review-primary-save"
              type="button"
              onClick={save}
              disabled={!canSave}
            >
              {saving ? "Đang lưu…" : `Xác nhận & lưu ${fieldNames.length || 0} field`}
            </button>
            {dirty ? (
              <button className="secondary-action" type="button" onClick={discardDraft}>
                Bỏ bản nháp
              </button>
            ) : null}
            {!data31 ? (
              <button type="button" onClick={lock} disabled={!summary?.canLock || locking}>
                {locking ? "Đang SEALED…" : `SEALED đủ ${summary?.fieldCount ?? 0} field`}
              </button>
            ) : null}
          </div>
        </div>
      </div>
    </section>
  );
}
