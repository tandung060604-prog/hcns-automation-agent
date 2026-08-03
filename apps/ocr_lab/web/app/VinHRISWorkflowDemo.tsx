"use client";

import { useState } from "react";

const stages = [
  {
    id: "01",
    label: "Tiếp nhận",
    eyebrow: "LOCAL INTAKE",
    title: "Một tài liệu đi vào đúng phiên xử lý.",
    type: "PDF",
    meta: "Đơn xin nghỉ phép · 1 trang",
    highlight: "Nguồn tài liệu được giữ trong phiên local.",
    fields: [
      ["Định dạng", "PDF"],
      ["Template", "Chưa chọn"],
      ["Trạng thái", "Đang tiếp nhận"],
    ],
  },
  {
    id: "02",
    label: "Biểu mẫu",
    eyebrow: "TEMPLATE-FIRST",
    title: "Nhận diện biểu mẫu trước khi trích xuất.",
    type: "SCHEMA",
    meta: "hr.leave_request · template nội bộ",
    highlight: "Chọn đúng schema để không rơi về extractor chung.",
    fields: [
      ["Loại tài liệu", "Đơn nghỉ phép"],
      ["Schema", "hr.leave_request"],
      ["Parser", "Template-first"],
    ],
  },
  {
    id: "03",
    label: "Evidence",
    eyebrow: "EVIDENCE ATTACHED",
    title: "Mỗi trường đều có dấu vết để kiểm tra.",
    type: "FIELD",
    meta: "Trang 1 · vùng bằng chứng · confidence",
    highlight: "Ngày bắt đầu · “20/05/2025” · vùng 04.",
    fields: [
      ["Ngày bắt đầu", "20/05/2025"],
      ["Trang", "1"],
      ["Confidence", "Cao · cần đối chiếu"],
    ],
  },
  {
    id: "04",
    label: "Human Review",
    eyebrow: "NEEDS_REVIEW",
    title: "Điểm bất định được chuyển cho người duyệt.",
    type: "REVIEW",
    meta: "Agent đề xuất · con người quyết định",
    highlight: "Thiếu người duyệt — giữ lại để xác nhận thủ công.",
    fields: [
      ["Quyết định", "Chờ xác nhận"],
      ["Lý do", "Trường chưa chắc chắn"],
      ["Người duyệt", "Human Review"],
    ],
  },
  {
    id: "05",
    label: "Business JSON",
    eyebrow: "READY FOR WORKFLOW",
    title: "Dữ liệu có cấu trúc sẵn sàng đi tiếp.",
    type: "JSON",
    meta: "Business JSON · metadata · policy reference",
    highlight: "approval_status: pending · needs_review: true.",
    fields: [
      ["Output", "Business JSON"],
      ["Route", "hr.leave_request"],
      ["Approval", "pending"],
    ],
  },
] as const;

export default function VinHRISWorkflowDemo() {
  const [activeIndex, setActiveIndex] = useState(0);
  const stage = stages[activeIndex];

  return (
    <section className="vinhris-demo" id="demo" aria-labelledby="vinhris-demo-title">
      <div className="vinhris-section-heading vinhris-section-heading-demo">
        <p className="vinhris-kicker">TRY THE WORKFLOW</p>
        <h2 id="vinhris-demo-title">Xem một hồ sơ đi qua VinHRIS.</h2>
        <p>Dữ liệu dưới đây là mẫu minh họa ẩn danh, mô phỏng đúng các điểm kiểm soát đang có trong workspace local.</p>
      </div>
      <div className="vinhris-demo-shell">
        <div className="vinhris-demo-nav" role="tablist" aria-label="Các bước demo workflow">
          <div className="vinhris-demo-nav-top"><span>DEMO RUN / LOCAL</span><i>●</i></div>
          {stages.map((item, index) => (
            <button
              aria-selected={index === activeIndex}
              className={`vinhris-demo-tab${index === activeIndex ? " is-active" : ""}`}
              key={item.id}
              onClick={() => setActiveIndex(index)}
              role="tab"
              type="button"
            >
              <span>{item.id}</span><b>{item.label}</b><em>{index === activeIndex ? "Đang xem" : "Xem bước"}</em>
            </button>
          ))}
        </div>
        <div className="vinhris-demo-stage" role="tabpanel" aria-label={stage.label}>
          <div className="vinhris-demo-stage-head"><div><span>{stage.eyebrow}</span><h3>{stage.title}</h3></div><strong>{stage.id} / 05</strong></div>
          <div className="vinhris-demo-grid">
            <div className="vinhris-demo-document">
              <div className="vinhris-demo-document-head"><span>{stage.type}</span><small>{stage.meta}</small></div>
              <div className="vinhris-demo-document-sheet"><b>VINHRIS</b><span /><span /><span /><div className="vinhris-demo-highlight">{stage.highlight}</div><span /><span /></div>
              <small className="vinhris-demo-document-note">SAMPLE DOCUMENT · KHÔNG PHẢI PII THẬT</small>
            </div>
            <div className="vinhris-demo-result">
              <div className="vinhris-demo-result-head"><span>STRUCTURED RESULT</span><i>LOCAL</i></div>
              {stage.fields.map(([name, value]) => <div className="vinhris-demo-field" key={name}><span>{name}</span><b>{value}</b></div>)}
              <div className="vinhris-demo-result-foot"><span>Evidence attached</span><b>{stage.id === "04" ? "Human review" : "Có thể kiểm tra"}</b></div>
            </div>
          </div>
          <div className="vinhris-demo-stage-foot"><span>Không upload cloud trong runtime hiện tại.</span><a href="/workspace">Mở workspace ↗</a></div>
        </div>
      </div>
    </section>
  );
}
