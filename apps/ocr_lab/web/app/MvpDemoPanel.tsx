"use client";
import { useCallback, useEffect, useState } from "react";

const API_BASE = "http://127.0.0.1:8765";

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
  taskName: string;
  documentId: string;
  documentType: string;
  created: string;
  inspectable: boolean;
};

type Notification = {
  id: string;
  message: string;
  read: boolean;
  createdAt: string;
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
  REQUEST_REUPLOAD: "Yêu cầu tải lại",
  CORRECTED: "Đã sửa",
  REJECTED: "Từ chối",
};

const STORAGE_KEY = "mvp-demo-session";

function readStoredSession(): Session | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Session) : null;
  } catch {
    return null;
  }
}

function nowLabel(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString("vi-VN");
  } catch {
    return iso;
  }
}

export default function MvpDemoPanel({
  onSessionChange,
}: {
  onSessionChange?: (session: MvpSession | null) => void;
}) {
  const [session, setSession] = useState<Session | null>(() => readStoredSession());
  const [username, setUsername] = useState("user");
  const [password, setPassword] = useState("user123");
  const [loginError, setLoginError] = useState("");
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<"submit" | "queue" | "notify" | "admin">("submit");

  const [leaveForm, setLeaveForm] = useState({
    employeeName: "Nguyễn Văn An",
    startDate: "2026-03-01",
    endDate: "2026-03-05",
    reason: "Nghỉ phép năm",
  });
  const [submitResult, setSubmitResult] = useState("");
  const [activeApplicationId, setActiveApplicationId] = useState("");
  const [activeDocumentId, setActiveDocumentId] = useState("");
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [queue, setQueue] = useState<QueueTask[]>([]);
  const [queueStatus, setQueueStatus] = useState("");
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
      setLoginError("Không kết nối được API local (127.0.0.1:8765)");
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

  const submitLeave = async () => {
    if (!session) return;
    setSubmitResult("");
    setBusy(true);
    try {
      const response = await fetch(`${API_BASE}/api/documents/leave`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify(leaveForm),
      });
      const payload = (await response.json()) as {
        status?: string;
        applicationId?: string;
        documentId?: string;
        processInstanceId?: string;
        error?: string;
      };
      if (!response.ok) {
        setSubmitResult(payload.error ?? "Không nộp được đơn");
        return;
      }
      setActiveApplicationId(payload.applicationId ?? "");
      setActiveDocumentId(payload.documentId ?? "");
      setSubmitResult(
        `Đã nộp (${payload.status}) · Process ${(payload.processInstanceId ?? "").slice(0, 8)}…`,
      );
      refreshQueue();
      loadTimeline(payload.applicationId ?? "");
    } catch {
      setSubmitResult("Lỗi kết nối API");
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

  const refreshQueue = useCallback(async () => {
    if (!session) return;
    try {
      const response = await fetch(`${API_BASE}/api/camunda/queue`, { headers: authHeaders() });
      if (!response.ok) {
        setQueue([]);
        setQueueStatus("Không đọc được hàng đợi");
        return;
      }
      const payload = (await response.json()) as { queue?: QueueTask[] };
      setQueue(payload.queue ?? []);
      setQueueStatus("");
    } catch {
      setQueue([]);
      setQueueStatus("Chưa kết nối được Camunda local.");
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

  const reviewTask = async (task: QueueTask, decision: string) => {
    setQueueStatus("Đang gửi quyết định sang Camunda local...");
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
      setQueueStatus(
        task.role === "hr"
          ? `Đã duyệt ${DECISION_LABELS[decision]}. Camunda đang điều phối bước tiếp theo.`
          : `Đã ghi nhận ${DECISION_LABELS[decision]}. Camunda đang điều phối bước tiếp theo.`,
      );
      await new Promise((resolve) => setTimeout(resolve, 1500));
      await refreshQueue();
      await refreshNotifications();
      if (activeApplicationId) await loadTimeline(activeApplicationId);
    } catch {
      setQueueStatus("Lỗi kết nối Camunda local.");
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
      const [userRes, auditRes] = await Promise.all([
        fetch(`${API_BASE}/api/admin/users`, { headers: authHeaders() }),
        fetch(`${API_BASE}/api/admin/audit`, { headers: authHeaders() }),
      ]);
      if (userRes.ok) {
        const payload = (await userRes.json()) as { users?: typeof users };
        setUsers(payload.users ?? []);
      }
      if (auditRes.ok) {
        const payload = (await auditRes.json()) as { audit?: typeof audit };
        setAudit(payload.audit ?? []);
      }
    } catch {
      // ignore
    }
  };

  useEffect(() => {
    if (!session) return;
    void refreshQueue();
    void refreshNotifications();
  }, [session, refreshQueue, refreshNotifications]);

  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      let camunda = false;
      let api = false;
      try {
        const engine = await fetch(`${API_BASE}/health`).catch(() => null);
        camunda = engine?.ok ?? false;
      } catch {
        camunda = false;
      }
      try {
        const rest = await fetch(`http://127.0.0.1:8080/engine-rest/engine/`).catch(() => null);
        camunda = camunda || (rest?.ok ?? false);
      } catch {
        // ignore
      }
      try {
        const app = await fetch(`${API_BASE}/api/auth/me`).catch(() => null);
        api = app !== null;
      } catch {
        api = false;
      }
      if (!cancelled) setServiceStatus({ camunda, api });
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
  const tabs = [
    ["submit", "Nộp đơn nghỉ phép"],
    ["queue", `Hàng đợi (${queue.length})`],
    ["notify", `Thông báo (${notifications.filter((n) => !n.read).length})`],
    ...(isAdmin ? ([["admin", "Admin"]] as [string, string][]) : []),
  ] as [string, string][];

  return (
    <section className="section role-review-section" id="mvp-demo" style={{ marginTop: 0 }}>
      <div className="section-heading">
        <div>
          <p className="eyebrow">MV</p>
          <h2>MVP Demo: Đơn xin nghỉ phép qua Camunda + Human-in-the-loop</h2>
        </div>
        <p>
          Luồng làm việc đầy đủ trên máy nội bộ: nộp đơn → trích xuất dữ liệu → human review → duyệt → tải kết quả.
        </p>
      </div>

      <div
        className="role-review-card"
        style={{ padding: "16px 20px", marginBottom: 16 }}
      >
        <div style={{ display: "flex", gap: 24, flexWrap: "wrap", alignItems: "center" }}>
          <div style={{ display: "grid", gap: 4 }}>
            <strong>Trạng thái hệ thống</strong>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <StatusPill label="API demo (8765)" ok={serviceStatus.api} />
              <StatusPill label="Camunda (8080)" ok={serviceStatus.camunda} />
              <a href="http://127.0.0.1:8080/camunda/app/tasklist/default/" target="_blank" rel="noreferrer">
                Mở Tasklist →
              </a>
            </div>
          </div>
          <div style={{ flex: 1 }} />
          <button type="button" onClick={() => logout()}>
            {session ? `Đăng xuất (${session.username})` : "Đăng xuất"}
          </button>
        </div>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
          gap: 10,
          marginBottom: 16,
        }}
      >
        <StepCard n={1} title="Đăng nhập" text={session ? `${session.displayName} (${session.roleLabel})` : "admin / hr / user"} />
        <StepCard n={2} title="Nộp đơn" text="Người nộp điền và gửi đơn nghỉ phép" />
        <StepCard n={3} title="Trích xuất" text="Worker đọc DOCX, Camunda tạo UserReview task" />
        <StepCard n={4} title="Xác nhận" text="User/HR duyệt trong Tasklist hoặc panel này" />
        <StepCard n={5} title="Kết quả" text="Notification + tải DOCX/PDF" />
      </div>

      {!session ? (
        <div className="role-review-card" style={{ maxWidth: 480 }}>
          <header>
            <span>ACCOUNT</span>
            <div>
              <h3>Đăng nhập demo</h3>
              <p>admin/admin123 · hr/hr123 · user/user123</p>
            </div>
          </header>
          <div style={{ display: "grid", gap: 12, padding: "16px 20px" }}>
            <label>
              Username
              <input
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                style={inputStyle}
              />
            </label>
            <label>
              Mật khẩu
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                style={inputStyle}
              />
            </label>
            {loginError ? <small style={{ color: "#c62828" }}>{loginError}</small> : null}
            <button className="primary-button" type="button" onClick={() => void login()} disabled={busy}>
              {busy ? "Đang đăng nhập…" : "Đăng nhập"}
            </button>
          </div>
        </div>
      ) : (
        <div style={{ display: "grid", gap: 16 }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 12,
              flexWrap: "wrap",
              background: "#fff",
              border: "1px solid var(--border, #dfe3e8)",
              borderRadius: 12,
              padding: "12px 16px",
            }}
          >
            <strong>{session.displayName}</strong>
            <span className="role-badge">{ROLE_LABELS[session.role] ?? session.role}</span>
            <span style={{ color: "var(--muted, #6b7280)" }}>@{session.username}</span>
            <span style={{ flex: 1 }} />
            {activeDocumentId ? (
              <>
                <button type="button" onClick={() => void exportDocument(activeDocumentId, "docx")}>
                  DOCX
                </button>
                <button type="button" onClick={() => void exportDocument(activeDocumentId, "pdf")}>
                  PDF
                </button>
              </>
            ) : null}
            <button type="button" onClick={() => void logout()}>
              Đăng xuất
            </button>
          </div>

          <div
            style={{
              display: "flex",
              gap: 8,
              flexWrap: "wrap",
            }}
          >
            {([...tabs] as const).map(([key, label]) => (
              <button
                key={key}
                type="button"
                className={tab === key ? "primary-button" : ""}
                onClick={() => {
                  setTab(key as "submit" | "queue" | "notify" | "admin");
                  if (key === "admin") void loadAdminData();
                  if (key === "queue") void refreshQueue();
                  if (key === "notify") void refreshNotifications();
                }}
              >
                {label}
              </button>
            ))}
          </div>

          {notice ? (
            <p style={{ color: "#1565c0", margin: 0 }}>{notice}</p>
          ) : null}

          {tab === "submit" ? (
            <div className="role-review-card">
              <header>
                <span>FORM</span>
                <div>
                  <h3>Đơn xin nghỉ phép (leave-request-v1)</h3>
                  <p>Nộp đơn → Camunda khởi tạo process → worker trích xuất → UserReview.</p>
                </div>
              </header>
              <div style={{ display: "grid", gap: 12, padding: "16px 20px", gridTemplateColumns: "1fr 1fr" }}>
                <label>
                  Họ và tên
                  <input
                    value={leaveForm.employeeName}
                    onChange={(event) => setLeaveForm((c) => ({ ...c, employeeName: event.target.value }))}
                    style={inputStyle}
                  />
                </label>
                <label>
                  Lý do
                  <input
                    value={leaveForm.reason}
                    onChange={(event) => setLeaveForm((c) => ({ ...c, reason: event.target.value }))}
                    style={inputStyle}
                  />
                </label>
                <label>
                  Ngày bắt đầu
                  <input
                    type="date"
                    value={leaveForm.startDate}
                    onChange={(event) => setLeaveForm((c) => ({ ...c, startDate: event.target.value }))}
                    style={inputStyle}
                  />
                </label>
                <label>
                  Ngày kết thúc
                  <input
                    type="date"
                    value={leaveForm.endDate}
                    onChange={(event) => setLeaveForm((c) => ({ ...c, endDate: event.target.value }))}
                    style={inputStyle}
                  />
                </label>
              </div>
              <div style={{ padding: "0 20px 20px", display: "grid", gap: 12 }}>
                <button className="primary-button" type="button" onClick={() => void submitLeave()} disabled={busy}>
                  {busy ? "Đang nộp…" : "Nộp đơn"}
                </button>
                {submitResult ? <p style={{ margin: 0 }}>{submitResult}</p> : null}
                {activeApplicationId ? (
                  <div>
                    <strong>Timeline {activeApplicationId.slice(0, 12)}…</strong>
                    <div style={{ display: "grid", gap: 4, marginTop: 8 }}>
                      {timeline.length ? (
                        timeline.map((event, index) => (
                          <div key={`${event.at}-${index}`} style={{ display: "flex", gap: 8 }}>
                            <code>{nowLabel(event.at)}</code>
                            <strong>{event.event}</strong>
                            <span style={{ color: "var(--muted, #6b7280)" }}>{event.detail}</span>
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
            <div style={{ display: "grid", gap: 12 }}>
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
                          {task.documentType} · {nowLabel(task.created)} · {task.taskId.slice(0, 8)}…
                        </p>
                      </div>
                    </header>
                    <div className="role-actions" style={{ padding: "0 20px 20px" }}>
                      {(
                        task.role === "employee"
                          ? [
                              ["CONFIRMED", "Chấp nhận"],
                              ["UNRESOLVED", "Không xác nhận được"],
                              ["REQUEST_REUPLOAD", "Yêu cầu tải lại"],
                            ]
                          : [
                              ["CONFIRMED", "Chấp nhận"],
                              ["REQUEST_REUPLOAD", "Yêu cầu tải lại"],
                              ["REJECTED", "Từ chối"],
                            ]
                      ).map(([decision, label]) => (
                        <button
                          type="button"
                          key={decision}
                          disabled={busy}
                          onClick={() => void reviewTask(task, decision)}
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                  </div>
                ))
              )}
            </div>
          ) : null}

          {tab === "notify" ? (
            <div className="role-review-card">
              <header>
                <span>NOTIFICATION</span>
                <div>
                  <h3>Thông báo cho người nộp</h3>
                  <p>Nhận cảnh báo khi hồ sơ được xử lý (ví dụ: “Đã duyệt”).</p>
                </div>
              </header>
              <div style={{ padding: "0 20px 20px", display: "grid", gap: 8 }}>
                {notifications.length ? (
                  notifications.map((notification) => (
                    <div
                      key={notification.id}
                      style={{
                        display: "flex",
                        gap: 8,
                        alignItems: "center",
                        opacity: notification.read ? 0.6 : 1,
                      }}
                    >
                      {notification.read ? null : <span style={{ color: "#c62828" }}>●</span>}
                      <strong>{notification.message}</strong>
                      <span style={{ color: "var(--muted, #6b7280)" }}>{nowLabel(notification.createdAt)}</span>
                    </div>
                  ))
                ) : (
                  <p className="role-empty">Chưa có thông báo.</p>
                )}
                {notifications.some((n) => !n.read) ? (
                  <button type="button" onClick={() => void readNotifications()}>
                    Đánh dấu đã đọc
                  </button>
                ) : null}
              </div>
            </div>
          ) : null}

          {tab === "admin" && isAdmin ? (
            <div style={{ display: "grid", gap: 16 }}>
              <div className="role-review-card">
                <header>
                  <span>USERS</span>
                  <div>
                    <h3>Danh sách tài khoản</h3>
                    <p>Chỉ ADMIN mới xem được danh sách và audit.</p>
                  </div>
                </header>
                <div style={{ padding: "0 20px 20px", display: "grid", gap: 4 }}>
                  {users.map((user) => (
                    <div key={user.username} style={{ display: "flex", gap: 8 }}>
                      <code>{user.username}</code>
                      <strong>{user.displayName}</strong>
                      <span>{ROLE_LABELS[user.role] ?? user.role}</span>
                      <span style={{ color: "var(--muted, #6b7280)" }}>{user.active ? "active" : "disabled"}</span>
                    </div>
                  ))}
                </div>
              </div>
              <div className="role-review-card">
                <header>
                  <span>AUDIT</span>
                  <div>
                    <h3>Nhật ký hành động</h3>
                    <p>Login, tạo tài khoản và các sự kiện ghi vết.</p>
                  </div>
                </header>
                <div style={{ padding: "0 20px 20px", display: "grid", gap: 4 }}>
                  {audit.map((entry, index) => (
                    <div key={`${entry.at}-${index}`} style={{ display: "flex", gap: 8 }}>
                      <code>{nowLabel(entry.at)}</code>
                      <strong>{entry.action}</strong>
                      <span>{entry.actor}</span>
                      <span style={{ color: "var(--muted, #6b7280)" }}>{entry.detail}</span>
                    </div>
                  ))}
                </div>
              </div>
              {isHr ? <p>HR_REVIEWER có quyền truy cập hồ sơ để xác nhận, nhưng không quản lý tài khoản.</p> : null}
            </div>
          ) : null}
        </div>
      )}
    </section>
  );
}

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "8px 10px",
  border: "1px solid #dfe3e8",
  borderRadius: 8,
  fontFamily: "inherit",
  fontSize: 14,
};

function StatusPill({ label, ok }: { label: string; ok: boolean | null }) {
  const color = ok === null ? "#9e9e9e" : ok ? "#2e7d32" : "#c62828";
  const text = ok === null ? "đang kiểm tra" : ok ? "sẵn sàng" : "chưa kết nối";
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        fontSize: 12,
        color: color,
        border: `1px solid ${color}`,
        borderRadius: 999,
        padding: "2px 10px",
      }}
    >
      <i
        style={{
          width: 8,
          height: 8,
          borderRadius: "50%",
          background: color,
          display: "inline-block",
        }}
      />
      {label} · {text}
    </span>
  );
}

function StepCard({ n, title, text }: { n: number; title: string; text: string }) {
  return (
    <div
      style={{
        background: "#fff",
        border: "1px solid var(--border, #dfe3e8)",
        borderRadius: 12,
        padding: "12px 14px",
        display: "grid",
        gap: 4,
      }}
    >
      <strong style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span
          style={{
            width: 22,
            height: 22,
            borderRadius: "50%",
            background: "#1565c0",
            color: "#fff",
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 12,
          }}
        >
          {n}
        </span>
        {title}
      </strong>
      <small style={{ color: "var(--muted, #6b7280)" }}>{text}</small>
    </div>
  );
}
