import { VinHRISLogo } from "./VinHRISLogo";
import VinHRISHeroVideo from "./VinHRISHeroVideo";
import VinHRISJourneyProgress from "./VinHRISJourneyProgress";
import VinHRISWorkflowDemo from "./VinHRISWorkflowDemo";

const journey = [
  { id: "01", title: "Tiếp nhận tài liệu", body: "DOCX, PDF và ảnh scan đi vào một intake duy nhất, được giữ trong phiên local.", detail: "Native parser trước. OCR chỉ dùng khi nguồn cần đọc hình ảnh.", tone: "red" },
  { id: "02", title: "Hiểu đúng biểu mẫu", body: "VinHRIS nhận diện loại tài liệu và chọn template, schema, parser phù hợp.", detail: "Không rơi về extractor chung khi template chưa được hỗ trợ.", tone: "gold" },
  { id: "03", title: "Trích xuất có bằng chứng", body: "Mỗi trường dữ liệu đi cùng trang, text, confidence và vùng bằng chứng.", detail: "Kết quả có thể kiểm tra thay vì chỉ trả về một con số confidence.", tone: "ink" },
  { id: "04", title: "Human Review khi cần", body: "Bất đồng và trường chưa chắc chắn được đưa cho người có thẩm quyền xác nhận.", detail: "Agent đề xuất. Camunda điều phối. Con người quyết định.", tone: "warm" },
  { id: "05", title: "Business JSON sẵn sàng", body: "Dữ liệu có cấu trúc đi tiếp vào workflow HRM/BPM mà không làm mất dấu vết.", detail: "Tích hợp hiện tại giữ loopback và policy approval làm ranh giới an toàn.", tone: "red" },
];

const audiences = [
  ["Doanh nghiệp", "Chuẩn hóa hồ sơ, biểu mẫu và các bước kiểm duyệt trong một luồng."],
  ["Công ty tuyển dụng", "Giảm thao tác nhập liệu lặp lại mà vẫn giữ người kiểm tra ở điểm quan trọng."],
  ["Phòng nhân sự", "Từ tài liệu rời rạc đến dữ liệu có cấu trúc, có nguồn và có thể truy vết."],
];

export default function VinHRISLanding() {
  return (
    <main className="vinhris-site">
      <header className="vinhris-nav">
        <a className="vinhris-nav-brand" href="#top" aria-label="VinHRIS, về đầu trang"><VinHRISLogo /></a>
        <nav aria-label="Điều hướng VinHRIS">
          <a href="#journey">Cách vận hành</a>
          <a href="#proof">Sản phẩm</a>
          <a href="#solutions">Giải pháp</a>
          <a href="#trust">An toàn dữ liệu</a>
        </nav>
        <a className="vinhris-nav-cta" href="/workspace">Mở workspace <span aria-hidden="true">↗</span></a>
      </header>

      <section className="vinhris-hero" id="top">
        <VinHRISHeroVideo />
        <div className="vinhris-hero-content">
          <div className="vinhris-hero-copy">
            <p className="vinhris-kicker">AI DOCUMENT OPERATIONS FOR HR</p>
            <h1>Để hồ sơ nhân sự đi đúng đường.</h1>
            <p className="vinhris-hero-lead">VinHRIS biến tài liệu HR thành dữ liệu có bằng chứng, có người kiểm duyệt và sẵn sàng đi vào workflow.</p>
            <div className="vinhris-hero-direction">
              <small>THAM CHIẾU TINH THẦN PHÁT TRIỂN</small>
              <p>“Kiến tạo một cuộc sống tốt đẹp hơn cho mọi người.”</p>
              <span>Công nghệ · hạ tầng · năng lượng xanh · con người</span>
            </div>
            <div className="vinhris-hero-actions">
              <a className="vinhris-button vinhris-button-primary" href="/workspace">Mở workspace</a>
              <a className="vinhris-text-link" href="#journey">Xem hành trình <span aria-hidden="true">↓</span></a>
            </div>
            <div className="vinhris-hero-proof" aria-label="Các nguyên tắc của VinHRIS">
              <span>Local-first</span><span>Evidence-led</span><span>Human-approved</span>
            </div>
          </div>
          <div className="vinhris-hero-visual" aria-label="Luồng xử lý tài liệu HR của VinHRIS">
            <div className="vinhris-orbit vinhris-orbit-one" /><div className="vinhris-orbit vinhris-orbit-two" />
            <div className="vinhris-hero-panel">
              <div className="vinhris-panel-topline"><span>VINHRIS / INTAKE</span><span className="vinhris-status"><i /> LOCAL</span></div>
              <div className="vinhris-document-stack">
                <div className="vinhris-document vinhris-document-back"><span>PDF</span><strong>Hồ sơ nhân sự</strong></div>
                <div className="vinhris-document vinhris-document-mid"><span>DOCX</span><strong>Đơn nghỉ phép</strong></div>
                <div className="vinhris-document vinhris-document-front"><span>OCR</span><strong>Đang kiểm tra trường dữ liệu</strong><em>12 / 18 fields</em></div>
              </div>
              <div className="vinhris-panel-foot"><span>Evidence attached</span><b>Human review ready</b></div>
            </div>
            <p className="vinhris-visual-caption">Một pipeline rõ ràng từ tài liệu đến quyết định.</p>
          </div>
        </div>
      </section>

      <section className="vinhris-intro-band" aria-label="Tuyên ngôn VinHRIS"><p>HR không thiếu dữ liệu. HR cần một luồng làm việc đáng tin.</p><span>V</span></section>

      <section className="vinhris-journey" id="journey">
        <div className="vinhris-section-heading"><p className="vinhris-kicker">THE HR DOCUMENT JOURNEY</p><h2>Từ tài liệu thô đến Business JSON có thể kiểm tra.</h2><p>Scroll theo từng lớp của quy trình. Mỗi bước làm một việc rõ ràng và để lại dấu vết cho bước kế tiếp.</p></div>
        <div className="vinhris-journey-layout">
          <div className="vinhris-journey-track">
            {journey.map((step) => (
              <article className={`vinhris-journey-scene vinhris-journey-${step.tone}`} data-step={step.id} id={`journey-step-${step.id}`} key={step.id}>
                <div className="vinhris-scene-index">{step.id}</div>
                <div className="vinhris-scene-copy"><h3>{step.title}</h3><p>{step.body}</p><small>{step.detail}</small></div>
                <div className="vinhris-scene-art" aria-hidden="true"><span className="vinhris-scene-line" /><span className="vinhris-scene-node vinhris-node-one" /><span className="vinhris-scene-node vinhris-node-two" /><span className="vinhris-scene-node vinhris-node-three" /><strong>{step.id}</strong></div>
              </article>
            ))}
          </div>
          <VinHRISJourneyProgress />
        </div>
      </section>

      <section className="vinhris-proof" id="proof">
        <div className="vinhris-proof-visual">
          <div className="vinhris-proof-bar"><span>WORKSPACE PROOF / TEMPLATE-FIRST</span><b>LOCAL ONLY</b></div>
          <img src="/assets/template-first-local-workflow.png" alt="Sơ đồ workflow template-first, structured result và human review trong workspace VinHRIS" />
          <small>Sơ đồ product flow hiện có trong repository — không phải số liệu hiệu suất production.</small>
        </div>
        <div className="vinhris-proof-copy"><p className="vinhris-kicker">PRODUCT PROOF</p><h2>Landing page kể đúng những gì workspace đang làm.</h2><p>VinHRIS không bắt đầu bằng một dashboard giả. Sản phẩm thật bắt đầu từ một tài liệu, một schema phù hợp và một kết quả có thể truy vết.</p><ul><li><span>01</span><div><b>Template-first intake</b><small>DOCX, PDF và ảnh scan đi vào cùng một luồng.</small></div></li><li><span>02</span><div><b>Structured result</b><small>Field, evidence và metadata được giữ cùng nhau.</small></div></li><li><span>03</span><div><b>Human Review</b><small>Trường bất định không bị tự động hóa quá mức.</small></div></li></ul><a className="vinhris-button vinhris-button-dark" href="/workspace">Mở workspace thật <span aria-hidden="true">↗</span></a></div>
      </section>

      <VinHRISWorkflowDemo />

      <section className="vinhris-solutions" id="solutions">
        <div className="vinhris-section-heading vinhris-section-heading-compact"><p className="vinhris-kicker">BUILT FOR PEOPLE OPERATIONS</p><h2>Đủ rõ cho văn phòng. Đủ chắc cho doanh nghiệp.</h2></div>
        <div className="vinhris-audience-grid">
          {audiences.map(([title, body], index) => <article key={title} className={`vinhris-audience-card vinhris-audience-card-${index + 1}`}><span>0{index + 1}</span><h3>{title}</h3><p>{body}</p><a href="/workspace">Xem workspace <span aria-hidden="true">↗</span></a></article>)}
        </div>
      </section>

      <section className="vinhris-trust" id="trust">
        <div className="vinhris-trust-visual"><img src="/assets/hr-document-intelligence-context.webp" alt="Bối cảnh xử lý tài liệu và dữ liệu có bằng chứng của VinHRIS" /></div>
        <div className="vinhris-trust-copy"><p className="vinhris-kicker">TRUST IS A PRODUCT FEATURE</p><h2>Con người vẫn ở đúng điểm quyết định.</h2><p>VinHRIS giữ dữ liệu và bằng chứng trong phiên local, tách rõ đề xuất của agent khỏi quyết định của người duyệt.</p><ul><li><span>01</span> Không upload cloud trong runtime hiện tại.</li><li><span>02</span> Trường bất định đi vào needs_review.</li><li><span>03</span> Camunda nhận metadata và reference theo policy.</li></ul><a className="vinhris-button vinhris-button-dark" href="/workspace">Mở workspace</a></div>
      </section>

      <section className="vinhris-closing"><VinHRISLogo inverse /><h2>Một nền tảng HR bắt đầu từ một tài liệu được hiểu đúng.</h2><a className="vinhris-button vinhris-button-light" href="/workspace">Bắt đầu với workspace <span aria-hidden="true">↗</span></a></section>
      <footer className="vinhris-footer"><VinHRISLogo /><span>AI document operations for HR</span><a href="#top">Về đầu trang ↑</a></footer>
    </main>
  );
}
