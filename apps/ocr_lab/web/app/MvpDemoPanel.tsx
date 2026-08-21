"use client";
import { useCallback, useEffect, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8765";
const CAMUNDA_URL = import.meta.env.VITE_CAMUNDA_URL ?? "http://127.0.0.1:8080";

type Session = {
  token: string;
  username: string;
  role: string;
  roleLabel: string;
  displayName: string;
};

export type MvpSession = Session;

type QueueTask = {
  taskId: string;
  role: "employee" | "hr";
  taskDefinitionKey?: string;
  actionable?: boolean;
  pending?: boolean;
  statusLabel?: string;
  taskName: string;
  documentId: string;
  documentType: string;
  documentTypeLabel?: string;
  applicationId?: string;
  submittedBy?: string;
  created: string;
  inspectable: boolean;
  extractedFields?: Record<string, unknown>;
  sourceFile?: string;
};

type SubmissionDetail = {
  applicationId?: string;
  documentId: string;
  documentType?: string;
  documentTypeLabel?: string;
  owner?: string;
  extractedFields: Record<string, unknown>;
  sourceFile?: string;
  submittedAt?: string;
};

type ArchiveItem = {
  applicationId: string;
  documentId: string;
  documentType: string;
  documentTypeLabel?: string;
  owner: string;
  ownerDisplayName?: string;
  managedByHr?: string;
  extractedFields: Record<string, unknown>;
  sourceFile?: string;
  sourceFormat?: string;
  status: string;
  decision?: string;
  submittedAt: string;
  submittedDate?: string;
  submittedTime?: string;
  decidedAt?: string;
  decidedDate?: string;
  decidedTime?: string;
  reviewedBy?: string;
  reviewedByDisplayName?: string;
  canDownload?: boolean;
};

type OrgTree = {
  admin: { username: string; displayName: string };
  hrNodes: Array<{
    username: string;
    displayName: string;
    role: string;
    active: boolean;
    users: Array<{ username: string; displayName: string; role: string; active: boolean }>;
  }>;
  unassignedUsers: Array<{
    username: string;
    displayName: string;
    role: string;
    active: boolean;
  }>;
};

type Notification = {
  id: string;
  message: string;
  kind?: string;
  applicationId?: string;
  documentId?: string;
  read: boolean;
  createdAt: string;
};

type DetectionResult = {
  documentId: string;
  documentType: string;
  documentTypeLabel: string;
  templateId: string;
  templateVersion: string;
  camundaEligible: boolean;
  detection: { detectionConfidence: number; matchedAnchors: string[] };
  data: Record<string, unknown>;
  quality: {
    missingFields: string[];
    validationErrors: string[];
    confidence: number;
    recommendedAction: string;
  };
};

type StreamEvent = {
  seq: number;
  kind: "NOTIFICATION" | "QUEUE_CHANGED" | "TIMELINE";
  payload: { notification?: Notification; applicationId?: string };
};

type TimelineEvent = {
  at: string;
  event: string;
  detail: string;
  actor: string;
};

type AuthSessionResponse = {
  session?: Session;
  user?: Session;
  error?: string;
  errorCode?: string;
};

const ROLE_LABELS: Record<string, string> = {
  ADMIN: "ADMIN",
  HR_REVIEWER: "HR",
  USER: "USER",
};

const DECISION_LABELS: Record<string, string> = {
  CONFIRMED: "Chấp nhận",
  UNRESOLVED: "Không xác nhận được",
  REQUEST_REUPLOAD: "Yêu cầu nộp lại",
  CORRECTED: "Đã sửa",
  REJECTED: "Từ chối",
};

const NOTIFICATION_KIND_LABELS: Record<string, string> = {
  SUBMITTED: "Đơn mới",
  CONFIRMED: "Đã duyệt",
  REQUEST_REUPLOAD: "Yêu cầu nộp lại",
  REJECTED: "Từ chối",
  INFO: "Thông báo",
};

function notificationKindLabel(kind: string | undefined): string {
  if (!kind) return "Thông báo";
  return NOTIFICATION_KIND_LABELS[kind] ?? "Thông báo";
}

function kindTone(kind?: string): string {
  const key = (kind || "info").toLowerCase().replace(/_/g, "-");
  if (key.includes("reject") || key.includes("unresolved")) return "danger";
  if (key.includes("confirm")) return "ok";
  if (key.includes("reupload") || key.includes("request")) return "warn";
  if (key.includes("submit")) return "info";
  return "info";
}

function decisionButtonClass(decision: string): string {
  if (decision === "CONFIRMED") return "mvp-btn mvp-btn-ok";
  if (decision === "REQUEST_REUPLOAD") return "mvp-btn mvp-btn-warn";
  if (decision === "REJECTED") return "mvp-btn mvp-btn-danger";
  return "mvp-btn";
}

const ARCHIVE_STATUS_LABELS: Record<string, string> = {
  SUBMITTED: "Đã nộp · chờ duyệt",
  CONFIRMED: "Đã chấp nhận",
  REQUEST_REUPLOAD: "Yêu cầu nộp lại",
  REJECTED: "Đã từ chối",
};

const UPLOAD_ERROR_LABELS: Record<string, string> = {
  SUPPORTED_TEMPLATE_FORMAT_REQUIRED: "Chỉ nhận DOCX, PDF, PNG hoặc JPG.",
  UNSUPPORTED_TEMPLATE: "Không nhận diện được đây là loại đơn nào trong danh mục HCNS.",
  OCR_RUNTIME_UNAVAILABLE: "OCR chưa sẵn sàng, thử lại sau ít phút.",
  INVALID_UPLOAD_SIZE: "File rỗng hoặc vượt quá 50 MB.",
};

const FIELD_LABELS: Record<string, string> = {
  // Leave / overtime (camelCase)
  employeeName: "Họ và tên",
  employeeId: "Mã nhân viên",
  jobTitle: "Chức vụ",
  department: "Bộ phận",
  organization: "Đơn vị",
  requestDate: "Ngày làm đơn",
  startDate: "Từ ngày",
  endDate: "Đến ngày",
  leaveDays: "Số ngày nghỉ",
  reason: "Lý do",
  expectedReturnDate: "Ngày đi làm lại",
  handoverTo: "Bàn giao cho",
  handoverTasks: "Nội dung bàn giao",
  phone: "Điện thoại",
  address: "Địa chỉ",
  laborContractNumber: "Số HĐLĐ",
  laborContractDate: "Ngày ký HĐLĐ",
  standardWorkSchedule: "Giờ làm chuẩn",
  overtimeHoursPerDay: "Giờ OT/ngày",
  overtimeStartTime: "Bắt đầu OT",
  overtimeEndTime: "Kết thúc OT",
  totalOvertimeHours: "Tổng giờ OT",
  workContent: "Nội dung công việc",
  formNumber: "Số phiếu",
  // CV v2 (snake_case từ main)
  full_name: "Họ và tên",
  headline: "Tiêu đề / headline",
  email: "Email",
  phone_number: "Điện thoại",
  desired_role: "Vị trí mong muốn",
  years_experience: "Số năm kinh nghiệm",
  experience: "Kinh nghiệm",
  skills: "Kỹ năng",
  education: "Học vấn",
  // IELTS / chứng chỉ
  recipient_name: "Họ tên thí sinh",
  credential_id: "Mã chứng chỉ",
  credential_type: "Loại chứng chỉ",
  overall_score: "Điểm tổng",
  issue_date: "Ngày cấp",
  // Hợp đồng thử việc / lao động
  contract_number: "Số hợp đồng",
  contract_sign_date: "Ngày ký HĐ",
  effective_date: "Ngày hiệu lực",
  probation_end_date: "Hết thử việc",
  employer_name: "Bên A (công ty)",
  employer_representative: "Người đại diện",
  employee_name: "Bên B (nhân viên)",
  employee_id_number: "CMND/CCCD",
  professional_title: "Chức danh chuyên môn",
  role_title: "Chức danh vai trò",
  job_title: "Chức danh công việc",
  workplace: "Nơi làm việc",
  weekly_hours: "Giờ/tuần",
  probation_salary_monthly: "Lương thử việc",
  allowances_summary: "Phụ cấp",
  // CCCD / identity card
  idNumber: "Số CCCD",
  fullName: "Họ và tên",
  dateOfBirth: "Ngày sinh",
  sex: "Giới tính",
  nationality: "Quốc tịch",
  placeOfOrigin: "Quê quán",
  placeOfResidence: "Nơi thường trú",
};

const DEMO_TEMPLATE_DOWNLOADS = [
  {
    label: "Đơn nghỉ phép",
    href: "/templates/leave-request-v1.docx",
    detail: "LEAVE",
  },
  {
    label: "Đơn tăng ca",
    href: "/templates/overtime-request-v1.docx",
    detail: "OT",
  },
  {
    label: "CV ứng viên",
    href: "/templates/cv-v2.docx",
    detail: "CV",
  },
  {
    label: "Hợp đồng thử việc",
    href: "/templates/probation-contract-v2.docx",
    detail: "CONTRACT",
  },
] as const;

const HIDDEN_FIELDS = new Set([
  "missingFields",
  "validationErrors",
  "confidence",
  "recommendedAction",
  "documentId",
  "documentType",
  "templateId",
  "templateVersion",
  "documentTitle",
  "sourceFile",
  "schemaVersion",
]);

const STORAGE_KEY = "mvp-demo-session";
export const MVP_DEMO_STORAGE_KEY = STORAGE_KEY;

function readStoredSession(): Session | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Session) : null;
  } catch {
    return null;
  }
}

export async function restoreMvpDemoSession(apiBase: string): Promise<Session | null> {
  const stored = readStoredSession();
  if (!stored?.token) return null;
  try {
    const response = await fetch(`${apiBase}/api/auth/me`, {
      headers: { Authorization: `Bearer ${stored.token}` },
    });
    if (!response.ok) {
      window.localStorage.removeItem(STORAGE_KEY);
      return null;
    }
    const payload = (await response.json()) as AuthSessionResponse;
    const profile = payload.session ?? payload.user;
    if (!profile) {
      window.localStorage.removeItem(STORAGE_KEY);
      return null;
    }
    const merged: Session = {
      ...stored,
      ...profile,
      token: stored.token,
    };
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(merged));
    return merged;
  } catch {
    return stored;
  }
}

function nowLabel(iso: string): string {
  try {
    return new Date(iso).toLocaleString("vi-VN", {
      timeZone: "Asia/Ho_Chi_Minh",
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return iso;
  }
}

/** Prefer full ISO (`decidedAt` / `submittedAt`); fallback to date+time fields. */
function archiveDateTime(iso?: string, date?: string, time?: string): string {
  if (iso) return nowLabel(iso);
  if (date) return `${date}${time ? ` ${time}` : ""}`;
  return "—";
}

function sourceFormatLabel(sourceFile?: string, sourceFormat?: string): string {
  if (sourceFormat) return sourceFormat.toUpperCase();
  if (!sourceFile) return "";
  const match = /\.([a-z0-9]+)$/i.exec(sourceFile);
  return match ? match[1].toUpperCase() : "";
}

function fieldString(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}

function editableFieldEntries(data: Record<string, unknown>) {
  return Object.entries(data).filter(([key, value]) => {
    if (HIDDEN_FIELDS.has(key)) return false;
    // Prefer known labels; allow camelCase and snake_case business fields (CV/IELTS/contract).
    if (
      !(key in FIELD_LABELS) &&
      !/^[a-z][A-Za-z0-9]*$/.test(key) &&
      !/^[a-z][a-z0-9_]*$/.test(key)
    ) {
      return false;
    }
    return ["string", "number", "boolean"].includes(typeof value) || value === null;
  });
}

export default function MvpDemoPanel({
  onSessionChange,
}: {
  onSessionChange?: (session: MvpSession | null) => void;
}) {
  const [session, setSession] = useState<Session | null>(null);
  const [authBootstrapping, setAuthBootstrapping] = useState(true);
  const [username, setUsername] = useState("user");
  const [password, setPassword] = useState("user123");
  const [loginError, setLoginError] = useState("");
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<
    "submit" | "queue" | "notify" | "history" | "archive" | "admin"
  >("submit");

  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [detection, setDetection] = useState<DetectionResult | null>(null);
  const [detectStatus, setDetectStatus] = useState("");
  const [detecting, setDetecting] = useState(false);
  const [toast, setToast] = useState<{ message: string; kind: string } | null>(null);
  const [live, setLive] = useState(false);

  const [submitResult, setSubmitResult] = useState("");
  const [activeApplicationId, setActiveApplicationId] = useState("");
  const [activeDocumentId, setActiveDocumentId] = useState("");
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [queue, setQueue] = useState<QueueTask[]>([]);
  const [queueStatus, setQueueStatus] = useState("");
  const [detailTaskId, setDetailTaskId] = useState<string | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailSubmission, setDetailSubmission] = useState<SubmissionDetail | null>(null);
  const [originalPreview, setOriginalPreview] = useState<{
    url: string;
    contentType: string;
    label: string;
  } | null>(null);
  const [originalLoading, setOriginalLoading] = useState(false);
  const [originalError, setOriginalError] = useState("");
  const [archive, setArchive] = useState<ArchiveItem[]>([]);
  const [archiveStatus, setArchiveStatus] = useState("");
  const [historyDetailId, setHistoryDetailId] = useState<string | null>(null);
  const [orgTree, setOrgTree] = useState<OrgTree | null>(null);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [users, setUsers] = useState<Array<{ username: string; role: string; displayName: string; active: boolean }>>(
    [],
  );
  const [audit, setAudit] = useState<Array<{ at: string; action: string; actor: string; detail: string }>>([]);
  const [notice, setNotice] = useState("");
  const [serviceStatus, setServiceStatus] = useState<{
    camunda: boolean | null;
    api: boolean | null;
  }>({ camunda: null, api: null });

  const authHeaders = useCallback(
    () => ({ "Content-Type": "application/json", Authorization: `Bearer ${session?.token ?? ""}` }),
    [session?.token],
  );

  const persist = (value: Session | null) => {
    setSession(value);
    if (value) window.localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
    else window.localStorage.removeItem(STORAGE_KEY);
    onSessionChange?.(value);
  };

  useEffect(() => {
    let cancelled = false;
    void restoreMvpDemoSession(API_BASE).then((restored) => {
      if (cancelled) return;
      setSession(restored);
      setAuthBootstrapping(false);
      onSessionChange?.(restored);
    });
    return () => {
      cancelled = true;
    };
  }, [onSessionChange]);

  const login = async () => {
    setLoginError("");
    setBusy(true);
    try {
      const response = await fetch(`${API_BASE}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      const payload = (await response.json()) as AuthSessionResponse;
      if (!response.ok || !payload.session) {
        setLoginError(payload.error ?? "Đăng nhập thất bại");
        return;
      }
      persist(payload.session);
    } catch {
      setLoginError("Không kết nối được API xử lý hồ sơ");
    } finally {
      setBusy(false);
    }
  };

  const logout = async () => {
    try {
      await fetch(`${API_BASE}/api/auth/logout`, {
        method: "POST",
        headers: authHeaders(),
      });
    } catch {
      // ignore
    }
    persist(null);
    setQueue([]);
    setNotifications([]);
    setTimeline([]);
  };

  const scanUpload = async () => {
    if (!session || !uploadFile) return;
    setDetection(null);
    setDetectStatus("");
    setSubmitResult("");
    setDetecting(true);
    const formData = new FormData();
    formData.append("file", uploadFile);
    try {
      const response = await fetch(`${API_BASE}/api/documents/process`, {
        method: "POST",
        headers: { Authorization: `Bearer ${session.token}` },
        body: formData,
      });
      const payload = (await response.json()) as DetectionResult & {
        error?: string;
        errorCode?: string;
      };
      if (!response.ok) {
        const label =
          (payload.errorCode && UPLOAD_ERROR_LABELS[payload.errorCode]) ||
          payload.error ||
          "Không quét được tài liệu";
        setDetectStatus(label);
        return;
      }
      setDetection(payload);
      setActiveDocumentId(payload.documentId);
      setDetectStatus(
        `Đã nhận diện: ${payload.documentTypeLabel} · độ tin cậy ${Math.round(
          (payload.detection?.detectionConfidence ?? 0) * 100,
        )}%`,
      );
    } catch {
      setDetectStatus("Lỗi kết nối API khi quét tài liệu");
    } finally {
      setDetecting(false);
    }
  };

  const updateDetectedField = (field: string, value: string) => {
    setDetection((current) =>
      current
        ? {
            ...current,
            data: { ...current.data, [field]: value },
          }
        : current,
    );
  };

  const submitDetectedDocument = async () => {
    if (!session || !detection) return;
    setSubmitResult("");
    setBusy(true);
    try {
      const corrections = Object.fromEntries(
        editableFieldEntries(detection.data).map(([key, value]) => [
          key,
          fieldString(value),
        ]),
      );
      const response = await fetch(`${API_BASE}/api/camunda/start`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ documentId: detection.documentId, corrections }),
      });
      const payload = (await response.json()) as {
        status?: string;
        applicationId?: string;
        documentId?: string;
        documentTypeLabel?: string;
        processInstanceId?: string;
        hrNotified?: boolean;
        hrQueueReady?: boolean;
        error?: string;
      };
      if (!response.ok) {
        setSubmitResult(payload.error ?? "Không nộp được tài liệu đã quét");
        return;
      }
      setActiveApplicationId(payload.applicationId ?? "");
      setActiveDocumentId(payload.documentId ?? detection.documentId);
      setSubmitResult(
        payload.hrQueueReady
          ? `${payload.documentTypeLabel ?? detection.documentTypeLabel} đã vào hàng đợi HR.`
          : `${payload.documentTypeLabel ?? detection.documentTypeLabel} đã nộp. HR có thể duyệt ngay (đồng bộ workflow nền).`,
      );
      setTab("notify");
      void refreshQueue();
      void refreshNotifications();
      void refreshArchive();
      void loadTimeline(payload.applicationId ?? "");
    } catch {
      setSubmitResult("Lỗi kết nối API khi nộp sang HR");
    } finally {
      setBusy(false);
    }
  };

  const loadTimeline = async (applicationId: string) => {
    if (!applicationId) return;
    try {
      const response = await fetch(
        `${API_BASE}/api/documents/timeline?applicationId=${encodeURIComponent(applicationId)}`,
        { headers: authHeaders() },
      );
      if (!response.ok) return;
      const payload = (await response.json()) as { timeline?: TimelineEvent[] };
      setTimeline(payload.timeline ?? []);
    } catch {
      setTimeline([]);
    }
  };

  const refreshQueue = useCallback(async (options?: { silent?: boolean }) => {
    if (!session) return;
    try {
      const response = await fetch(`${API_BASE}/api/camunda/queue`, { headers: authHeaders() });
      if (!response.ok) {
        const payload = (await response.json().catch(() => ({}))) as { error?: string };
        setQueue([]);
        if (!options?.silent) {
          setQueueStatus(payload.error ?? `Không đọc được hàng đợi (HTTP ${response.status})`);
        }
        return;
      }
      const payload = (await response.json()) as { queue?: QueueTask[] };
      setQueue(payload.queue ?? []);
      if (!options?.silent) {
        setQueueStatus("");
      }
    } catch {
      setQueue([]);
      if (!options?.silent) {
        setQueueStatus("Chưa kết nối được hàng đợi xử lý.");
      }
    }
  }, [authHeaders, session]);

  const refreshNotifications = useCallback(async () => {
    if (!session) return;
    try {
      const response = await fetch(`${API_BASE}/api/notifications`, { headers: authHeaders() });
      if (!response.ok) return;
      const payload = (await response.json()) as { notifications?: Notification[] };
      setNotifications(payload.notifications ?? []);
    } catch {
      setNotifications([]);
    }
  }, [authHeaders, session]);

  const refreshArchive = useCallback(async () => {
    if (!session || session.role === "ADMIN") return;
    try {
      const response = await fetch(`${API_BASE}/api/archive`, { headers: authHeaders() });
      if (!response.ok) {
        const payload = (await response.json().catch(() => ({}))) as { error?: string };
        setArchive([]);
        setArchiveStatus(payload.error ?? "Không đọc được bằng chứng đã lưu");
        return;
      }
      const payload = (await response.json()) as { archive?: ArchiveItem[] };
      setArchive(payload.archive ?? []);
      setArchiveStatus("");
    } catch {
      setArchive([]);
      setArchiveStatus("Lỗi kết nối khi đọc bằng chứng.");
    }
  }, [authHeaders, session]);

  const downloadArchiveFile = async (applicationId: string, sourceFile?: string) => {
    try {
      const response = await fetch(
        `${API_BASE}/api/archive/download?applicationId=${encodeURIComponent(applicationId)}`,
        { headers: { Authorization: `Bearer ${session?.token ?? ""}` } },
      );
      if (!response.ok) {
        const payload = (await response.json().catch(() => ({}))) as { error?: string };
        setArchiveStatus(payload.error ?? "Không tải được file gốc");
        setQueueStatus(payload.error ?? "Không tải được file gốc");
        return;
      }
      const blob = await response.blob();
      const href = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = href;
      anchor.download = sourceFile || `ho-so-${applicationId.slice(0, 12)}`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(href);
    } catch {
      setArchiveStatus("Lỗi kết nối khi tải file.");
    }
  };

  const reviewTask = async (task: QueueTask, decision: string) => {
    setQueueStatus("Đang gửi quyết định...");
    try {
      const response = await fetch(`${API_BASE}/api/camunda/review`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ taskId: task.taskId, role: task.role, decision }),
      });
      const payload = (await response.json()) as { status?: string; error?: string };
      if (!response.ok) {
        setQueueStatus(payload.error ?? "Không hoàn thành được task");
        return;
      }
      const decisionLabel = DECISION_LABELS[decision];
      let statusMsg =
        task.role === "hr"
          ? `Đã ${decisionLabel.toLowerCase()}. Hệ thống đang cập nhật cho người nộp.`
          : `Đã ${decisionLabel.toLowerCase()}. Bạn sẽ nhận thông báo khi HR xử lý.`;
      if (
        task.taskDefinitionKey === "UserReview" &&
        decision === "REJECTED" &&
        task.role === "hr"
      ) {
        statusMsg =
          "Đơn đã chuyển sang bước HCNS kiểm tra. Bấm Từ chối lại trên task HCNS để hoàn tất.";
      }
      setQueueStatus(statusMsg);
      setDetailTaskId(null);
      setDetailSubmission(null);
      await new Promise((resolve) => setTimeout(resolve, 800));
      await refreshQueue({ silent: false });
      await refreshNotifications();
      await refreshArchive();
      if (activeApplicationId) await loadTimeline(activeApplicationId);
    } catch {
      setQueueStatus("Lỗi kết nối hàng đợi xử lý.");
    }
  };

  const openSubmissionDetail = async (task: QueueTask) => {
    if (detailTaskId === task.taskId) {
      setDetailTaskId(null);
      setDetailSubmission(null);
      if (originalPreview?.url) URL.revokeObjectURL(originalPreview.url);
      setOriginalPreview(null);
      setOriginalError("");
      return;
    }
    setDetailTaskId(task.taskId);
    setDetailLoading(true);
    setDetailSubmission(null);
    if (originalPreview?.url) URL.revokeObjectURL(originalPreview.url);
    setOriginalPreview(null);
    setOriginalError("");
    try {
      const params = new URLSearchParams();
      if (task.applicationId) params.set("applicationId", task.applicationId);
      if (task.documentId) params.set("documentId", task.documentId);
      const response = await fetch(
        `${API_BASE}/api/camunda/submission?${params.toString()}`,
        { headers: authHeaders() },
      );
      const payload = (await response.json()) as SubmissionDetail & { error?: string };
      if (!response.ok) {
        // Fall back to queue-embedded extract if detail API is unavailable.
        if (task.extractedFields && Object.keys(task.extractedFields).length) {
          setDetailSubmission({
            applicationId: task.applicationId,
            documentId: task.documentId,
            documentType: task.documentType,
            documentTypeLabel: task.documentTypeLabel,
            owner: task.submittedBy,
            extractedFields: task.extractedFields,
            sourceFile: task.sourceFile,
            submittedAt: task.created,
          });
          setQueueStatus("");
          return;
        }
        setQueueStatus(payload.error ?? "Không đọc được chi tiết đơn nộp");
        setDetailTaskId(null);
        return;
      }
      setDetailSubmission(payload);
    } catch {
      setQueueStatus("Lỗi kết nối khi mở chi tiết đơn.");
      setDetailTaskId(null);
    } finally {
      setDetailLoading(false);
    }
  };

  const closeOriginalPreview = () => {
    if (originalPreview?.url) URL.revokeObjectURL(originalPreview.url);
    setOriginalPreview(null);
    setOriginalError("");
  };

  const viewOriginalDocument = async (task: QueueTask) => {
    const documentId = detailSubmission?.documentId || task.documentId;
    const applicationId = detailSubmission?.applicationId || task.applicationId || "";
    if (!documentId && !applicationId) {
      setOriginalError("Thiếu mã tài liệu để mở file gốc");
      return;
    }
    setOriginalLoading(true);
    setOriginalError("");
    try {
      const params = new URLSearchParams();
      if (documentId) params.set("id", documentId);
      if (applicationId) params.set("applicationId", applicationId);
      const auth = { Authorization: `Bearer ${session?.token ?? ""}` };
      const labelGuess =
        detailSubmission?.sourceFile ||
        task.sourceFile ||
        `tai-lieu-${(documentId || applicationId).slice(0, 12)}`;
      const ext = (/\.([a-z0-9]+)$/i.exec(labelGuess)?.[1] || "").toLowerCase();
      const isDocx = ext === "docx";

      // DOCX: skip preview (browser cannot render); go straight to source download blob.
      let response = isDocx
        ? await fetch(`${API_BASE}/api/documents/source?${params.toString()}`, {
            headers: auth,
          })
        : await fetch(`${API_BASE}/api/documents/preview?${params.toString()}`, {
            headers: auth,
          });
      if (!response.ok && !isDocx) {
        response = await fetch(`${API_BASE}/api/documents/source?${params.toString()}`, {
          headers: auth,
        });
      }
      if (!response.ok) {
        const payload = (await response.json().catch(() => ({}))) as { error?: string };
        setOriginalError(payload.error ?? "Không mở được tài liệu gốc");
        return;
      }
      const headerType = (response.headers.get("Content-Type") || "")
        .split(";")[0]
        .trim()
        .toLowerCase();
      const blob = await response.blob();
      let contentType = (blob.type || headerType || "").toLowerCase();
      if (!contentType || contentType === "application/octet-stream") {
        if (ext === "pdf") contentType = "application/pdf";
        else if (ext === "png") contentType = "image/png";
        else if (ext === "jpg" || ext === "jpeg") contentType = "image/jpeg";
        else if (ext === "docx") {
          contentType =
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
        }
      }
      if (originalPreview?.url) URL.revokeObjectURL(originalPreview.url);
      const url = URL.createObjectURL(
        contentType && contentType !== blob.type
          ? new Blob([blob], { type: contentType })
          : blob,
      );
      setOriginalPreview({
        url,
        contentType: contentType || "application/octet-stream",
        label: labelGuess,
      });
    } catch {
      setOriginalError("Lỗi kết nối khi tải tài liệu gốc");
    } finally {
      setOriginalLoading(false);
    }
  };

  const readNotifications = async () => {
    try {
      await fetch(`${API_BASE}/api/notifications/read`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({}),
      });
      await refreshNotifications();
    } catch {
      // ignore
    }
  };

  const exportDocument = async (documentId: string, format: "docx" | "pdf") => {
    const url = `${API_BASE}/api/documents/export?documentId=${encodeURIComponent(documentId)}&format=${format}`;
    const response = await fetch(url, { headers: authHeaders() });
    if (!response.ok) {
      setNotice(`Tải ${format.toUpperCase()} thất bại (HTTP ${response.status})`);
      return;
    }
    const blob = await response.blob();
    const href = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = href;
    anchor.download = `don-xin-nghi-phep.${format}`;
    anchor.click();
    URL.revokeObjectURL(href);
    setNotice(`Đã tải file ${format.toUpperCase()}`);
  };

  const loadAdminData = async () => {
    if (!session) return;
    try {
      const [userRes, auditRes, treeRes] = await Promise.all([
        fetch(`${API_BASE}/api/admin/users`, { headers: authHeaders() }),
        fetch(`${API_BASE}/api/admin/audit`, { headers: authHeaders() }),
        fetch(`${API_BASE}/api/admin/org-tree`, { headers: authHeaders() }),
      ]);
      if (userRes.ok) {
        const payload = (await userRes.json()) as { users?: typeof users };
        setUsers(payload.users ?? []);
      }
      if (auditRes.ok) {
        const payload = (await auditRes.json()) as { audit?: typeof audit };
        setAudit(payload.audit ?? []);
      }
      if (treeRes.ok) {
        const payload = (await treeRes.json()) as { tree?: OrgTree };
        setOrgTree(payload.tree ?? null);
      }
    } catch {
      // ignore
    }
  };

  useEffect(() => {
    if (!session) return;
    void refreshQueue();
    void refreshNotifications();
    void refreshArchive();
  }, [session, refreshQueue, refreshNotifications, refreshArchive]);

  useEffect(() => {
    if (!session || typeof window === "undefined") return;
    let cursor = 0;
    let cancelled = false;

    const handleStreamEvent = (payload: StreamEvent) => {
      cursor = Math.max(cursor, payload.seq ?? 0);
      if (payload.kind === "NOTIFICATION" && payload.payload.notification) {
        const notification = payload.payload.notification;
        setNotifications((current) => [
          notification,
          ...current.filter((item) => item.id !== notification.id),
        ]);
        setToast({ message: notification.message, kind: notification.kind ?? "INFO" });
        setQueueStatus("");
        if (
          session?.role === "USER" &&
          notification.kind &&
          ["CONFIRMED", "REJECTED", "REQUEST_REUPLOAD"].includes(notification.kind)
        ) {
          setTab("notify");
        }
        if (
          (session?.role === "HR_REVIEWER" || session?.role === "ADMIN") &&
          notification.kind === "SUBMITTED"
        ) {
          setTab("queue");
          void refreshQueue();
        }
      }
      if (payload.kind === "QUEUE_CHANGED") {
        void refreshQueue({
          silent: session?.role === "USER",
        });
        void refreshArchive();
      }
      if (
        payload.kind === "TIMELINE" &&
        payload.payload.applicationId === activeApplicationId
      ) {
        void loadTimeline(activeApplicationId);
      }
    };

    const pullEvents = async () => {
      try {
        const response = await fetch(`${API_BASE}/api/events?cursor=${cursor}`, {
          headers: authHeaders(),
        });
        if (!response.ok) {
          if (!cancelled) setLive(false);
          return;
        }
        const payload = (await response.json()) as {
          events?: StreamEvent[];
          cursor?: number;
        };
        if (!cancelled) setLive(true);
        cursor = payload.cursor ?? cursor;
        for (const event of payload.events ?? []) {
          handleStreamEvent(event);
        }
      } catch {
        if (!cancelled) setLive(false);
      }
    };

    void pullEvents();
    const timer = window.setInterval(() => void pullEvents(), 3000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
      setLive(false);
    };
    // loadTimeline is intentionally not memoized; this effect only needs the
    // current active application id and realtime/poll refresh callbacks.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeApplicationId, authHeaders, refreshNotifications, refreshQueue, session]);

  useEffect(() => {
    let cancelled = false;
    const fetchOk = async (url: string, timeoutMs = 1200) => {
      const controller = new AbortController();
      const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
      try {
        const response = await fetch(url, {
          cache: "no-store",
          signal: controller.signal,
        });
        return response.ok || response.status === 401;
      } catch {
        return false;
      } finally {
        window.clearTimeout(timeout);
      }
    };
    const check = async () => {
      const [api, workflow] = await Promise.all([
        fetchOk(`${API_BASE}/health`),
        fetchOk(`${API_BASE}/health`).then((ok) =>
          ok ? true : fetchOk(`${CAMUNDA_URL}/engine-rest/engine/`),
        ),
      ]);
      if (!cancelled) setServiceStatus({ camunda: workflow, api });
    };
    void check();
    const timer = window.setInterval(() => void check(), 10000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  const isAdmin = session?.role === "ADMIN";
  const isHr = session?.role === "HR_REVIEWER" || isAdmin;
  const isArchiveViewer = session?.role === "USER" || session?.role === "HR_REVIEWER";
  const historyItems = archive;
  const evidenceItems = archive.filter((item) => item.status === "CONFIRMED");
  const tabs = [
    ["submit", "Nộp đơn"],
    ["queue", `Hàng đợi (${queue.length})`],
    ["notify", `Thông báo (${notifications.filter((n) => !n.read).length})`],
    ...(isArchiveViewer
      ? ([
          ["history", `Lịch sử (${historyItems.length})`],
          ["archive", `Bằng chứng (${evidenceItems.length})`],
        ] as [string, string][])
      : []),
    ...(isAdmin ? ([["admin", "Admin"]] as [string, string][]) : []),
  ] as [string, string][];

  return (
    <section className="section mvp-demo-panel" id="mvp-demo">
      <div className="mvp-shell">
        <header className="mvp-hero">
          <div className="mvp-hero-copy">
            <p className="mvp-kicker">VinHRIS · Workspace</p>
            <h2>Hồ sơ vào nhẹ. Duyệt rõ ràng.</h2>
            <p className="mvp-hero-lead">
              Quét file, chỉnh vài trường nếu cần, gửi HR và xem lại bản gốc trước khi quyết định.
            </p>
          </div>
          <div className="mvp-hero-meta" aria-label="Trạng thái dịch vụ">
            <StatusPill label="API" ok={serviceStatus.api} />
            <StatusPill label="Workflow" ok={serviceStatus.camunda} />
            {session ? (
              <button className="mvp-btn mvp-btn-ghost" type="button" onClick={() => void logout()}>
                Đăng xuất
              </button>
            ) : null}
          </div>
        </header>

        <ol className="mvp-flow" aria-label="Các bước xử lý">
          <li>
            <span>01</span>
            <strong>Đăng nhập</strong>
            <small>{session ? session.displayName : "admin · hr · user"}</small>
          </li>
          <li>
            <span>02</span>
            <strong>Quét & trích xuất</strong>
            <small>DOCX native · PDF/ảnh OCR</small>
          </li>
          <li>
            <span>03</span>
            <strong>Nộp HR</strong>
            <small>Hàng đợi kiểm tra</small>
          </li>
          <li>
            <span>04</span>
            <strong>Duyệt</strong>
            <small>Đối chiếu bản gốc</small>
          </li>
        </ol>

      {authBootstrapping ? (
        <div className="mvp-surface mvp-login">
          <p className="mvp-muted">Đang khôi phục phiên đăng nhập…</p>
        </div>
      ) : !session ? (
        <div className="mvp-surface mvp-login">
          <header className="mvp-surface-head">
            <p className="mvp-kicker">Tài khoản demo</p>
            <h3>Đăng nhập workspace</h3>
            <p className="mvp-muted">admin/admin123 · hr/hr123 · user/user123</p>
          </header>
          <div className="mvp-login-form">
            <label>
              Username
              <input
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                autoComplete="username"
              />
            </label>
            <label>
              Mật khẩu
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="current-password"
              />
            </label>
            {loginError ? <p className="mvp-error">{loginError}</p> : null}
            <button className="mvp-btn mvp-btn-primary" type="button" onClick={() => void login()} disabled={busy}>
              {busy ? "Đang đăng nhập…" : "Vào workspace"}
            </button>
          </div>
        </div>
      ) : (
        <div className="mvp-workspace">
          <div className="mvp-session">
            <div className="mvp-session-identity">
              <strong>{session.displayName}</strong>
              <span className="mvp-role">{ROLE_LABELS[session.role] ?? session.role}</span>
              <span className="mvp-muted">@{session.username}</span>
            </div>
            <div className="mvp-session-actions">
              {activeDocumentId ? (
                <>
                  <button className="mvp-btn mvp-btn-ghost" type="button" onClick={() => void exportDocument(activeDocumentId, "docx")}>
                    Tải DOCX
                  </button>
                  <button className="mvp-btn mvp-btn-ghost" type="button" onClick={() => void exportDocument(activeDocumentId, "pdf")}>
                    Tải PDF
                  </button>
                </>
              ) : null}
              <button className="mvp-btn mvp-btn-ghost" type="button" onClick={() => void logout()}>
                Đăng xuất
              </button>
            </div>
          </div>

          <nav className="mvp-tabs" aria-label="Khu vực làm việc">
            {([...tabs] as const).map(([key, label]) => (
              <button
                key={key}
                type="button"
                className={tab === key ? "mvp-tab is-active" : "mvp-tab"}
                onClick={() => {
                  setTab(
                    key as "submit" | "queue" | "notify" | "history" | "archive" | "admin",
                  );
                  if (key === "admin") void loadAdminData();
                  if (key === "queue") void refreshQueue();
                  if (key === "notify") void refreshNotifications();
                  if (key === "archive" || key === "history") void refreshArchive();
                }}
              >
                {label}
              </button>
            ))}
          </nav>

          {notice ? <p className="mvp-notice">{notice}</p> : null}
          {toast ? (
            <div className={`mvp-toast mvp-toast-${kindTone(toast.kind)}`}>
              <strong>{notificationKindLabel(toast.kind)}</strong>
              <span>{toast.message}</span>
              <button className="mvp-btn mvp-btn-ghost" type="button" onClick={() => setToast(null)}>
                Đóng
              </button>
            </div>
          ) : null}
          <p className={live ? "mvp-live is-on" : "mvp-live"}>
            {live ? "Realtime đang bật" : "Đang kết nối realtime…"}
          </p>

          {tab === "submit" ? (
            <div className="mvp-surface role-review-card">
              <header className="mvp-surface-head">
                <p className="mvp-kicker">Quét tài liệu</p>
                <h3>Nộp đơn từ file đã có</h3>
                <p className="mvp-muted">
                  Upload DOCX/PDF/ảnh → nhận diện Leave / OT / CV / Hợp đồng / IELTS / CCCD → chỉnh form → nộp HR.
                </p>
              </header>
              <div className="mvp-pad mvp-stack">
                <div className="mvp-stack-tight">
                  <small className="mvp-meta-label">
                    Tải mẫu blank (CV / Contract / Leave / OT) — điền rồi upload lại để quét:
                  </small>
                  <div className="role-actions mvp-row">
                    {DEMO_TEMPLATE_DOWNLOADS.map((item) => (
                      <a
                        key={item.href}
                        className="text-button"
                        href={item.href}
                        download
                      >
                        {item.label} ({item.detail})
                      </a>
                    ))}
                  </div>
                </div>
                <div className="mvp-upload-row">
                  <label>
                    Tài liệu đơn
                    <input
                      type="file"
                      accept=".docx,.pdf,.png,.jpg,.jpeg"
                      onChange={(event) => {
                        setUploadFile(event.target.files?.[0] ?? null);
                        setDetection(null);
                        setDetectStatus("");
                        setSubmitResult("");
                      }}
                      style={inputStyle}
                    />
                  </label>
                  <button
                    className="mvp-btn mvp-btn-primary"
                    type="button"
                    onClick={() => void scanUpload()}
                    disabled={!uploadFile || detecting || busy}
                  >
                    {detecting ? "Đang quét…" : "Quét & điền form"}
                  </button>
                </div>
                {detectStatus ? <p className="mvp-detect-status">{detectStatus}</p> : null}
                {detection ? (
                  <div className="mvp-detect-result">
                    <div className="mvp-detect-summary">
                      <strong>{detection.documentTypeLabel}</strong>
                      <p>
                        Template {detection.templateId} · thiếu{" "}
                        {detection.quality.missingFields.length} trường · lỗi kiểm tra{" "}
                        {detection.quality.validationErrors.length}
                      </p>
                    </div>
                    <div className="mvp-field-grid">
                      {editableFieldEntries(detection.data).map(([field, value]) => (
                        <label key={field}>
                          {FIELD_LABELS[field] ?? field}
                          <input
                            value={fieldString(value)}
                            onChange={(event) =>
                              updateDetectedField(field, event.target.value)
                            }
                            style={inputStyle}
                          />
                        </label>
                      ))}
                    </div>
                    {!detection.camundaEligible ? (
                      <p className="mvp-error">
                        Loại tài liệu này đã quét được nhưng chưa bật luồng nộp HR.
                      </p>
                    ) : null}
                    <button
                      className="mvp-btn mvp-btn-primary"
                      type="button"
                      onClick={() => void submitDetectedDocument()}
                      disabled={busy || !detection.camundaEligible}
                    >
                      {busy ? "Đang nộp sang HR…" : "Nộp đơn này cho HR"}
                    </button>
                  </div>
                ) : null}
                {submitResult ? <p className="mvp-detect-status">{submitResult}</p> : null}
                {activeApplicationId ? (
                  <div>
                    <strong>Timeline {activeApplicationId.slice(0, 12)}…</strong>
                    <div style={{ display: "grid", gap: 4, marginTop: 8 }}>
                      {timeline.length ? (
                        timeline.map((event, index) => (
                          <div key={`${event.at}-${index}`} style={{ display: "flex", gap: 8 }}>
                            <code>{nowLabel(event.at)}</code>
                            <strong>{event.event}</strong>
                            <span className="mvp-meta-label">{event.detail}</span>
                          </div>
                        ))
                      ) : (
                        <small>Chưa có sự kiện.</small>
                      )}
                    </div>
                  </div>
                ) : null}
              </div>
            </div>
          ) : null}

          {tab === "queue" ? (
            <div className="mvp-stack">
              {queueStatus ? <p className="camunda-queue-status" style={{ margin: 0, padding: 0 }}>{queueStatus}</p> : null}
              {queue.length === 0 ? (
                <p className="role-empty">Chưa có task ở bước này.</p>
              ) : (
                queue.map((task) => (
                  <div className="role-review-card" key={task.taskId}>
                    <header>
                      <span>{task.role === "employee" ? "USER" : "HR"}</span>
                      <div>
                        <h3>{task.taskName}</h3>
                        <p>
                          {task.documentTypeLabel ?? task.documentType} ·{" "}
                          {task.submittedBy ? `@${task.submittedBy} · ` : ""}
                          {nowLabel(task.created)}
                          {task.applicationId ? (
                            <>
                              {" "}
                              · <code>{task.applicationId}</code>
                            </>
                          ) : null}
                        </p>
                      </div>
                    </header>
                    <div className="mvp-pad-sm">
                      {Object.keys(task.extractedFields ?? {}).length ? (
                        <div className="mvp-soft-box mvp-stack-tight">
                          <strong>Thông tin extract từ tài liệu</strong>
                          <div className="mvp-field-grid">
                            {editableFieldEntries(task.extractedFields ?? {})
                              .slice(0, 6)
                              .map(([field, value]) => (
                                <div key={field}>
                                  <small className="mvp-meta-label">
                                    {FIELD_LABELS[field] ?? field}
                                  </small>
                                  <span>{fieldString(value) || "—"}</span>
                                </div>
                              ))}
                          </div>
                          {editableFieldEntries(task.extractedFields ?? {}).length > 6 ? (
                            <small className="mvp-meta-label">
                              +{editableFieldEntries(task.extractedFields ?? {}).length - 6} trường
                              khác — mở Xem chi tiết
                            </small>
                          ) : null}
                        </div>
                      ) : (
                        <p className="mvp-muted" style={{ margin: 0 }}>
                          Chưa có thông tin extract kèm theo đơn này.
                        </p>
                      )}
                      {isHr &&
                      (task.actionable === true ||
                        task.taskDefinitionKey === "HRReview" ||
                        task.taskDefinitionKey === "PENDING") ? (
                        <div className="role-actions mvp-row">
                          {(
                            [
                              ["CONFIRMED", "Chấp nhận"],
                              ["REQUEST_REUPLOAD", "Yêu cầu nộp lại"],
                              ["REJECTED", "Từ chối"],
                            ] as const
                          ).map(([decision, label]) => (
                            <button
                              type="button"
                              className={decisionButtonClass(decision)}
                              key={decision}
                              disabled={busy}
                              onClick={() =>
                                void reviewTask({ ...task, role: "hr" }, decision)
                              }
                            >
                              {label}
                            </button>
                          ))}
                          <button
                            type="button"
                            className="mvp-btn mvp-btn-info"
                            disabled={busy || detailLoading}
                            onClick={() => void openSubmissionDetail(task)}
                          >
                            {detailTaskId === task.taskId ? "Đóng chi tiết" : "Xem chi tiết"}
                          </button>
                          {task.pending || task.taskDefinitionKey === "PENDING" ? (
                            <small className="mvp-meta-label">
                              Duyệt local ngay (IELTS/scan chưa cần chờ Camunda)
                            </small>
                          ) : null}
                        </div>
                      ) : (
                        <div className="mvp-stack-tight">
                          <p className="mvp-muted" style={{ margin: 0 }}>
                            <strong>{task.statusLabel ?? "Đang xử lý"}</strong>
                            {task.pending ? (
                              <span> · Đang đồng bộ workflow nền</span>
                            ) : null}
                            {task.applicationId ? (
                              <span>
                                {" "}
                                · mã đơn <code>{task.applicationId}</code>
                              </span>
                            ) : null}
                          </p>
                          <div className="role-actions mvp-row">
                            <button
                              type="button"
                              className="mvp-btn mvp-btn-info"
                              disabled={busy || detailLoading}
                              onClick={() => void openSubmissionDetail(task)}
                            >
                              {detailTaskId === task.taskId ? "Đóng chi tiết" : "Xem chi tiết"}
                            </button>
                          </div>
                        </div>
                      )}
                      {detailTaskId === task.taskId ? (
                        <div className="mvp-soft-box-info mvp-stack-tight">
                          <strong>Chi tiết thông tin user đã nộp</strong>
                          {detailLoading ? (
                            <p className="mvp-muted" style={{ margin: 0 }}>Đang tải chi tiết…</p>
                          ) : detailSubmission ? (
                            <>
                              <p className="mvp-muted" style={{ margin: 0 }}>
                                {detailSubmission.documentTypeLabel ??
                                  task.documentTypeLabel ??
                                  task.documentType}
                                {detailSubmission.owner || task.submittedBy
                                  ? ` · @${detailSubmission.owner || task.submittedBy}`
                                  : ""}
                                {detailSubmission.sourceFile
                                  ? ` · file ${detailSubmission.sourceFile}`
                                  : ""}
                                {detailSubmission.submittedAt
                                  ? ` · ${nowLabel(detailSubmission.submittedAt)}`
                                  : ""}
                              </p>
                              <div className="role-actions mvp-row">
                                <button
                                  type="button"
                                  disabled={originalLoading || busy}
                                  onClick={() => void viewOriginalDocument(task)}
                                >
                                  {originalLoading
                                    ? "Đang mở file gốc…"
                                    : originalPreview
                                      ? "Tải lại tài liệu gốc"
                                      : "Xem tài liệu gốc"}
                                </button>
                                {originalPreview ? (
                                  <button type="button" onClick={closeOriginalPreview}>
                                    Đóng bản gốc
                                  </button>
                                ) : null}
                              </div>
                              {originalError ? (
                                <p className="mvp-error">{originalError}</p>
                              ) : null}
                              {originalPreview ? (
                                <div className="mvp-preview-frame">
                                  <small className="mvp-meta-label">
                                    Bản gốc chưa qua OCR · {originalPreview.label} ·{" "}
                                    {originalPreview.contentType}
                                  </small>
                                  <div className="mvp-row">
                                    {(originalPreview.contentType.startsWith("image/") ||
                                      originalPreview.contentType === "application/pdf") && (
                                      <a href={originalPreview.url} target="_blank" rel="noreferrer">
                                        Mở tab mới
                                      </a>
                                    )}
                                    <a href={originalPreview.url} download={originalPreview.label}>
                                      Tải file gốc
                                    </a>
                                  </div>
                                  {originalPreview.contentType.startsWith("image/") ? (
                                    <img
                                      src={originalPreview.url}
                                      alt={`Tài liệu gốc ${originalPreview.label}`}
                                    />
                                  ) : originalPreview.contentType === "application/pdf" ? (
                                    <iframe
                                      title={`PDF gốc ${originalPreview.label}`}
                                      src={originalPreview.url}
                                    />
                                  ) : (
                                    <p className="mvp-muted" style={{ margin: 0 }}>
                                      File DOCX/Office không xem inline — dùng nút tải ở trên (Word
                                      trên máy).
                                    </p>
                                  )}
                                </div>
                              ) : null}
                              <div
                                className="mvp-field-grid"
                              >
                                {editableFieldEntries(detailSubmission.extractedFields).length ? (
                                  editableFieldEntries(detailSubmission.extractedFields).map(
                                    ([field, value]) => (
                                      <div key={field}>
                                        <small className="mvp-meta-label">
                                          {FIELD_LABELS[field] ?? field}
                                        </small>
                                        <strong>{fieldString(value) || "—"}</strong>
                                      </div>
                                    ),
                                  )
                                ) : (
                                  <p style={{ margin: 0 }}>Không có trường extract.</p>
                                )}
                              </div>
                            </>
                          ) : (
                            <p style={{ margin: 0 }}>Không có dữ liệu chi tiết.</p>
                          )}
                        </div>
                      ) : null}
                    </div>
                  </div>
                ))
              )}
            </div>
          ) : null}

          {tab === "notify" ? (
            <div className="role-review-card">
              <header>
                <span>Thông báo</span>
                <div>
                  <h3>Cập nhật cho người nộp</h3>
                  <p>Nhận tin khi hồ sơ được duyệt, yêu cầu nộp lại hoặc từ chối.</p>
                </div>
              </header>
              <div className="mvp-pad-sm">
                {notifications.length ? (
                  notifications.map((notification) => (
                    <div
                      key={notification.id}
                      className={`mvp-notify-item mvp-tone-${kindTone(notification.kind)}${
                        notification.read ? " is-read" : ""
                      }`}
                    >
                      <div className="mvp-row">
                        <span className={`mvp-kind-badge mvp-tone-${kindTone(notification.kind)}`}>
                          {notificationKindLabel(notification.kind)}
                        </span>
                        <strong>{notification.message}</strong>
                      </div>
                      <span className="mvp-meta-label">{nowLabel(notification.createdAt)}</span>
                    </div>
                  ))
                ) : (
                  <p className="role-empty">Chưa có thông báo.</p>
                )}
                {notifications.some((n) => !n.read) ? (
                  <button type="button" className="mvp-btn mvp-btn-info" onClick={() => void readNotifications()}>
                    Đánh dấu đã đọc
                  </button>
                ) : null}
              </div>
            </div>
          ) : null}

          {tab === "history" && isArchiveViewer ? (
            <div className="mvp-stack">
              <div className="role-review-card">
                <header>
                  <span>Lịch sử</span>
                  <div>
                    <h3>Lịch sử đơn</h3>
                    <p>
                      Các đơn đã nộp, xếp mới nhất trước. Xem field đã extract; tải file gốc sau khi HR chấp nhận.
                    </p>
                  </div>
                </header>
              </div>
              {archiveStatus ? <p style={{ margin: 0 }}>{archiveStatus}</p> : null}
              {historyItems.length === 0 ? (
                <p className="role-empty">Chưa có lịch sử đơn.</p>
              ) : (
                historyItems.map((item) => {
                  const open = historyDetailId === item.applicationId;
                  const formatLabel = sourceFormatLabel(item.sourceFile, item.sourceFormat);
                  return (
                    <div className="role-review-card" key={`history-${item.applicationId}`}>
                      <header>
                        <span className={`mvp-kind-badge mvp-tone-${kindTone(item.status)}`}>
                          {ARCHIVE_STATUS_LABELS[item.status] ?? item.status}
                        </span>
                        <div>
                          <h3>{item.documentTypeLabel ?? item.documentType}</h3>
                          <p>
                            Người nộp: <strong>@{item.ownerDisplayName || item.owner}</strong>
                            {item.managedByHr ? ` · HR phụ trách: ${item.managedByHr}` : ""}
                            {item.sourceFile ? ` · file ${item.sourceFile}` : ""}
                          </p>
                        </div>
                      </header>
                      <div className="mvp-pad-sm">
                        <div
                          className="mvp-meta-grid"
                        >
                          <div>
                            <small className="mvp-meta-label">Ngày giờ nộp</small>
                            <div>
                              <strong>
                                {archiveDateTime(
                                  item.submittedAt,
                                  item.submittedDate,
                                  item.submittedTime,
                                )}
                              </strong>
                            </div>
                          </div>
                          <div>
                            <small className="mvp-meta-label">Ngày giờ duyệt</small>
                            <div>
                              <strong>
                                {item.decision
                                  ? archiveDateTime(
                                      item.decidedAt,
                                      item.decidedDate,
                                      item.decidedTime,
                                    )
                                  : "Chưa duyệt"}
                              </strong>
                            </div>
                          </div>
                          <div>
                            <small className="mvp-meta-label">HR chấp nhận</small>
                            <div>
                              <strong>
                                {item.reviewedBy
                                  ? `@${item.reviewedBy}${
                                      item.reviewedByDisplayName &&
                                      item.reviewedByDisplayName !== item.reviewedBy
                                        ? ` (${item.reviewedByDisplayName})`
                                        : ""
                                    }`
                                  : "—"}
                              </strong>
                            </div>
                          </div>
                        </div>
                        <div className="role-actions mvp-row">
                          <button
                            type="button"
                            className="mvp-btn mvp-btn-info"
                            onClick={() =>
                              setHistoryDetailId(open ? null : item.applicationId)
                            }
                          >
                            {open ? "Đóng chi tiết" : "Xem chi tiết"}
                          </button>
                          {item.canDownload ? (
                            <button
                              type="button"
                              className="mvp-btn mvp-btn-ok"
                              onClick={() =>
                                void downloadArchiveFile(
                                  item.applicationId,
                                  item.sourceFile,
                                )
                              }
                            >
                              Tải file gốc{formatLabel ? ` (${formatLabel})` : ""}
                            </button>
                          ) : (
                            <small className="mvp-meta-label">
                              Tải DOCX/PDF gốc mở sau khi HR chấp nhận
                            </small>
                          )}
                        </div>
                        {open ? (
                          <div className="mvp-soft-box-info mvp-stack-tight">
                            <strong>Chi tiết thông tin đã nộp</strong>
                            <p className="mvp-muted" style={{ margin: 0 }}>
                              Mã đơn <code>{item.applicationId}</code>
                              {item.sourceFile ? ` · ${item.sourceFile}` : ""}
                            </p>
                            <div
                              className="mvp-field-grid"
                            >
                              {editableFieldEntries(item.extractedFields).length ? (
                                editableFieldEntries(item.extractedFields).map(
                                  ([field, value]) => (
                                    <div key={field}>
                                      <small className="mvp-meta-label">
                                        {FIELD_LABELS[field] ?? field}
                                      </small>
                                      <strong>{fieldString(value) || "—"}</strong>
                                    </div>
                                  ),
                                )
                              ) : (
                                <p style={{ margin: 0 }}>Không có trường extract.</p>
                              )}
                            </div>
                          </div>
                        ) : null}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          ) : null}

          {tab === "archive" && isArchiveViewer ? (
            <div className="mvp-stack">
              <div className="role-review-card">
                <header>
                  <span>EVIDENCE</span>
                  <div>
                    <h3>Bằng chứng đã chấp nhận</h3>
                    <p>
                      Chỉ các đơn HR đã <strong>Chấp nhận</strong>. File gốc user gửi kèm được lưu
                      tại <code>~/private-data/mvp_demo/archive_files/</code>.
                    </p>
                  </div>
                </header>
              </div>
              {archiveStatus ? <p style={{ margin: 0 }}>{archiveStatus}</p> : null}
              {evidenceItems.length === 0 ? (
                <p className="role-empty">Chưa có đơn được chấp nhận để lưu bằng chứng.</p>
              ) : (
                evidenceItems.map((item) => (
                  <div className="role-review-card" key={item.applicationId}>
                    <header>
                      <span className={`mvp-kind-badge mvp-tone-${kindTone(item.status)}`}>
                        {ARCHIVE_STATUS_LABELS[item.status] ?? item.status}
                      </span>
                      <div>
                        <h3>{item.documentTypeLabel ?? item.documentType}</h3>
                        <p>
                          @{item.ownerDisplayName || item.owner}
                          {item.managedByHr ? ` · HR ${item.managedByHr}` : ""}
                          {item.reviewedBy ? ` · duyệt bởi @${item.reviewedBy}` : ""}
                          {item.decidedAt || item.decidedDate
                            ? ` · ${archiveDateTime(
                                item.decidedAt,
                                item.decidedDate,
                                item.decidedTime,
                              )}`
                            : ""}
                        </p>
                      </div>
                    </header>
                    <div className="mvp-pad-sm">
                      <div
                        className="mvp-meta-grid"
                      >
                        <div>
                          <small className="mvp-meta-label">Ngày nộp</small>
                          <div>
                            <strong>{item.submittedDate || nowLabel(item.submittedAt).slice(0, 10)}</strong>
                          </div>
                        </div>
                        <div>
                          <small className="mvp-meta-label">Giờ nộp</small>
                          <div>
                            <strong>
                              {item.submittedTime ||
                                nowLabel(item.submittedAt).split(" ").slice(-1)[0] ||
                                "—"}
                            </strong>
                          </div>
                        </div>
                        <div>
                          <small className="mvp-meta-label">Ngày duyệt</small>
                          <div>
                            <strong>
                              {item.decidedAt
                                ? nowLabel(item.decidedAt).split(",")[0]?.trim() ||
                                  item.decidedDate ||
                                  "—"
                                : item.decidedDate || "—"}
                            </strong>
                          </div>
                        </div>
                        <div>
                          <small className="mvp-meta-label">Giờ duyệt</small>
                          <div>
                            <strong>
                              {item.decidedAt
                                ? nowLabel(item.decidedAt).split(",").slice(-1)[0]?.trim() ||
                                  item.decidedTime ||
                                  "—"
                                : item.decidedTime || "—"}
                            </strong>
                          </div>
                        </div>
                        <div>
                          <small className="mvp-meta-label">HR duyệt</small>
                          <div>
                            <strong>
                              {item.reviewedBy ? `@${item.reviewedBy}` : "—"}
                            </strong>
                          </div>
                        </div>
                      </div>
                      <div
                        style={{
                          display: "grid",
                          gap: 6,
                          gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
                        }}
                      >
                        {editableFieldEntries(item.extractedFields)
                          .slice(0, 8)
                          .map(([field, value]) => (
                            <div key={field}>
                              <small className="mvp-meta-label">
                                {FIELD_LABELS[field] ?? field}
                              </small>
                              <span>{fieldString(value) || "—"}</span>
                            </div>
                          ))}
                      </div>
                      <div className="role-actions mvp-row">
                        {item.canDownload ? (
                          <button
                            type="button"
                            className="mvp-btn mvp-btn-ok"
                            onClick={() =>
                              void downloadArchiveFile(item.applicationId, item.sourceFile)
                            }
                          >
                            Tải file gốc
                          </button>
                        ) : (
                          <small className="mvp-meta-label">
                            {item.status === "CONFIRMED"
                              ? "File chưa sẵn sàng"
                              : "Tải file chỉ mở sau khi HR chấp nhận"}
                          </small>
                        )}
                        <code style={{ alignSelf: "center" }}>{item.applicationId}</code>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          ) : null}

          {tab === "admin" && isAdmin ? (
            <div className="mvp-stack-loose">
              <div className="role-review-card">
                <header>
                  <span>ORG TREE</span>
                  <div>
                    <h3>Sơ đồ Admin → HR → User</h3>
                    <p>
                      Admin track HR nào quản lý user nào. Không cần giữ bản bằng chứng đơn — xem
                      audit là đủ.
                    </p>
                  </div>
                </header>
                <div className="mvp-pad-sm">
                  {orgTree ? (
                    <>
                      <div>
                        <strong>Admin</strong> · {orgTree.admin.displayName} (
                        <code>{orgTree.admin.username}</code>)
                      </div>
                      {orgTree.hrNodes.map((hrNode) => (
                        <div
                          key={hrNode.username}
                          className="mvp-tree-branch mvp-stack-tight"
                        >
                          <div>
                            <strong>HR</strong> · {hrNode.displayName} (
                            <code>{hrNode.username}</code>)
                            {!hrNode.active ? " · disabled" : ""}
                          </div>
                          {hrNode.users.length ? (
                            hrNode.users.map((managed) => (
                              <div
                                key={managed.username}
                                className="mvp-tree-child"
                              >
                                └ User · {managed.displayName} (
                                <code>{managed.username}</code>)
                                {!managed.active ? " · disabled" : ""}
                              </div>
                            ))
                          ) : (
                            <div className="mvp-tree-child">
                              └ (chưa gán user)
                            </div>
                          )}
                        </div>
                      ))}
                      {orgTree.unassignedUsers.length ? (
                        <div className="mvp-tree-branch is-muted">
                          <strong>User chưa gán HR</strong>
                          {orgTree.unassignedUsers.map((managed) => (
                            <div key={managed.username} style={{ paddingLeft: 16 }}>
                              └ {managed.displayName} (<code>{managed.username}</code>)
                            </div>
                          ))}
                        </div>
                      ) : null}
                    </>
                  ) : (
                    <p className="role-empty">Chưa tải được sơ đồ.</p>
                  )}
                </div>
              </div>
              <div className="role-review-card">
                <header>
                  <span>Người dùng</span>
                  <div>
                    <h3>Danh sách tài khoản</h3>
                    <p>Chỉ ADMIN mới xem được danh sách và audit.</p>
                  </div>
                </header>
                <div className="mvp-pad-sm">
                  {users.map((user) => (
                    <div key={user.username} style={{ display: "flex", gap: 8 }}>
                      <code>{user.username}</code>
                      <strong>{user.displayName}</strong>
                      <span>{ROLE_LABELS[user.role] ?? user.role}</span>
                      <span className="mvp-meta-label">{user.active ? "active" : "disabled"}</span>
                    </div>
                  ))}
                </div>
              </div>
              <div className="role-review-card">
                <header>
                  <span>Nhật ký</span>
                  <div>
                    <h3>Nhật ký hành động</h3>
                    <p>Login, tạo tài khoản, nộp đơn, duyệt và gán HR↔User.</p>
                  </div>
                </header>
                <div className="mvp-pad-sm">
                  {audit.map((entry, index) => (
                    <div key={`${entry.at}-${index}`} style={{ display: "flex", gap: 8 }}>
                      <code>{nowLabel(entry.at)}</code>
                      <strong>{entry.action}</strong>
                      <span>{entry.actor}</span>
                      <span className="mvp-meta-label">{entry.detail}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : null}
        </div>
      )}
      </div>
    </section>
  );
}

const inputStyle: React.CSSProperties = {
  width: "100%",
  minWidth: 0,
  minHeight: 46,
  boxSizing: "border-box",
  padding: "11px 14px",
  border: "1px solid rgba(42, 48, 56, 0.08)",
  borderRadius: 12,
  fontFamily: "inherit",
  fontSize: 15,
  lineHeight: 1.5,
  background: "rgba(255,255,255,0.95)",
};

function StatusPill({ label, ok }: { label: string; ok: boolean | null }) {
  const state = ok === null ? "pending" : ok ? "ok" : "down";
  const text = ok === null ? "đang kiểm tra" : ok ? "sẵn sàng" : "chưa kết nối";
  return (
    <span className={`mvp-status mvp-status-${state}`}>
      <i />
      {label} · {text}
    </span>
  );
}
