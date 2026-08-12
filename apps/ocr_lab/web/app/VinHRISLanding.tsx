import { VinHRISLogo } from "./VinHRISLogo";
import VinHRISHeroVideo from "./VinHRISHeroVideo";
import VinHRISJourneyProgress from "./VinHRISJourneyProgress";
import VinHRISWorkflowDemo from "./VinHRISWorkflowDemo";

const journey = [
  { id: "01", title: "Tiếp nhận hồ sơ", body: "DOCX, PDF và ảnh scan được đưa vào một nơi xử lý thống nhất.", detail: "Ưu tiên dữ liệu gốc. Chỉ dùng OCR khi cần đọc nội dung trên ảnh.", tone: "red" },
  { id: "02", title: "Nhận diện biểu mẫu", body: "Hệ thống xác định loại tài liệu và chọn mẫu trích xuất phù hợp.", detail: "Chỉ xử lý những biểu mẫu đã có quy tắc rõ ràng.", tone: "gold" },
  { id: "03", title: "Trích xuất thông tin", body: "Thông tin được gắn với nguồn nhận diện và mức độ tin cậy.", detail: "Người kiểm tra có cơ sở để đối chiếu lại tài liệu ban đầu.", tone: "ink" },
  { id: "04", title: "Kiểm tra nghiệp vụ", body: "Những trường chưa rõ được chuyển đến đúng vai trò để xác nhận.", detail: "Hệ thống gợi ý. Người có thẩm quyền đưa ra quyết định.", tone: "warm" },
  { id: "05", title: "Bàn giao theo quy trình", body: "Dữ liệu đã kiểm tra được chuyển tiếp vào workflow và giữ lại lịch sử xử lý.", detail: "Camunda điều phối công việc, không thay thế quyết định của con người.", tone: "red" },
];

const audiences = [
  ["Tiếp nhận hồ sơ", "Tập trung tài liệu vào một điểm xử lý để giảm thao tác tìm kiếm và nhập lại."],
  ["Kiểm tra dữ liệu", "Giữ người phụ trách tại những điểm cần đối chiếu và xác nhận."],
  ["Điều phối công việc", "Chuyển hồ sơ, quyết định và lịch sử xử lý theo đúng quy trình đã đặt ra."],
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
        <a className="vinhris-nav-cta" href="/workspace">Vào khu vực làm việc <span aria-hidden="true">↗</span></a>
      </header>

      <section className="vinhris-hero" id="top">
        <VinHRISHeroVideo />
        <div className="vinhris-hero-content">
          <div className="vinhris-hero-copy">
            <p className="vinhris-kicker">CỔNG TÁC NGHIỆP HÀNH CHÍNH - NHÂN SỰ</p>
            <h1>Hồ sơ rõ ràng. Quy trình có kiểm soát.</h1>
            <p className="vinhris-hero-lead">Tiếp nhận tài liệu HCNS, trích xuất thông tin và đưa hồ sơ đến đúng bước kiểm tra.</p>
            <div className="vinhris-hero-direction">
              <small>NHẬN DIỆN THAM CHIẾU</small>
              <p>Giao diện sử dụng hệ đỏ - vàng tiết chế, hướng tới trải nghiệm vận hành trang trọng và tin cậy.</p>
              <span>Không phải tuyên bố về quan hệ tài trợ hay liên kết thương mại.</span>
            </div>
            <div className="vinhris-hero-actions">
              <a className="vinhris-button vinhris-button-primary" href="/workspace">Vào khu vực làm việc</a>
              <a className="vinhris-text-link" href="#journey">Xem quy trình <span aria-hidden="true">↓</span></a>
            </div>
            <div className="vinhris-hero-proof" aria-label="Các nguyên tắc của VinHRIS">
              <span>Xử lý nội bộ</span><span>Có cơ sở đối chiếu</span><span>Người duyệt quyết định</span>
            </div>
          </div>
          <div className="vinhris-hero-visual" aria-label="Luồng xử lý tài liệu HR của VinHRIS">
            <div className="vinhris-orbit vinhris-orbit-one" /><div className="vinhris-orbit vinhris-orbit-two" />
            <div className="vinhris-hero-panel">
              <div className="vinhris-panel-topline"><span>VINHRIS / TIẾP NHẬN</span><span className="vinhris-status"><i /> SẴN SÀNG</span></div>
              <div className="vinhris-document-stack">
                <div className="vinhris-document vinhris-document-back"><span>PDF</span><strong>Hồ sơ nhân sự</strong></div>
                <div className="vinhris-document vinhris-document-mid"><span>DOCX</span><strong>Đơn nghỉ phép</strong></div>
                <div className="vinhris-document vinhris-document-front"><span>OCR</span><strong>Đang kiểm tra thông tin</strong><em>Cần người xác nhận</em></div>
              </div>
              <div className="vinhris-panel-foot"><span>Có nguồn đối chiếu</span><b>Sẵn sàng kiểm tra</b></div>
            </div>
            <p className="vinhris-visual-caption">Từ tài liệu đầu vào đến quyết định có lưu vết.</p>
          </div>
        </div>
      </section>

      <section className="vinhris-intro-band" aria-label="Giá trị vận hành"><p>Giảm nhập liệu lặp lại. Tăng khả năng kiểm tra khi xử lý hồ sơ.</p><span>V</span></section>

      <section className="vinhris-journey" id="journey">
        <div className="vinhris-section-heading"><p className="vinhris-kicker">QUY TRÌNH XỬ LÝ</p><h2>Từ tài liệu đầu vào đến dữ liệu có thể kiểm tra.</h2><p>Mỗi bước có trách nhiệm rõ ràng và để lại thông tin cần thiết cho bước tiếp theo.</p></div>
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
          <div className="vinhris-proof-copy"><p className="vinhris-kicker">CÁCH HỆ THỐNG HOẠT ĐỘNG</p><h2>Tài liệu, dữ liệu và bước kiểm tra được nối với nhau.</h2><p>Mỗi hồ sơ được xử lý theo mẫu phù hợp, tạo kết quả có cấu trúc và để người dùng đối chiếu trước khi đi tiếp.</p><ul><li><span>01</span><div><b>Tiếp nhận theo mẫu</b><small>DOCX/PDF có text ưu tiên đọc trực tiếp. Tài liệu scan dùng OCR khi cần.</small></div></li><li><span>02</span><div><b>Kết quả có cấu trúc</b><small>Thông tin trích xuất, nguồn và metadata được lưu cùng nhau.</small></div></li><li><span>03</span><div><b>Kiểm tra có trách nhiệm</b><small>Trường chưa chắc chắn được chuyển đến người phụ trách.</small></div></li></ul><a className="vinhris-button vinhris-button-dark" href="/workspace">Vào khu vực làm việc <span aria-hidden="true">↗</span></a></div>
      </section>

      <VinHRISWorkflowDemo />

      <section className="vinhris-solutions" id="solutions">
        <div className="vinhris-section-heading vinhris-section-heading-compact"><p className="vinhris-kicker">PHỤC VỤ VẬN HÀNH HCNS</p><h2>Rõ việc, rõ dữ liệu, rõ trách nhiệm.</h2></div>
        <div className="vinhris-audience-grid">
          {audiences.map(([title, body], index) => <article key={title} className={`vinhris-audience-card vinhris-audience-card-${index + 1}`}><span>0{index + 1}</span><h3>{title}</h3><p>{body}</p><a href="/workspace">Xem workspace <span aria-hidden="true">↗</span></a></article>)}
        </div>
      </section>

      <section className="vinhris-trust" id="trust">
        <div className="vinhris-trust-visual"><img src="/assets/hr-document-intelligence-context.webp" alt="Bối cảnh xử lý tài liệu và dữ liệu có bằng chứng của VinHRIS" /></div>
        <div className="vinhris-trust-copy"><p className="vinhris-kicker">KIỂM SOÁT DỮ LIỆU</p><h2>Người duyệt vẫn là người ra quyết định.</h2><p>VinHRIS tách rõ đề xuất của hệ thống khỏi quyết định của người kiểm tra, đồng thời lưu lại thông tin cần thiết để đối chiếu.</p><ul><li><span>01</span> Dữ liệu được xử lý trên môi trường nội bộ hiện tại.</li><li><span>02</span> Trường chưa chắc chắn được đưa vào hàng đợi kiểm tra.</li><li><span>03</span> Camunda nhận metadata và mã tham chiếu theo quy tắc xử lý.</li></ul><a className="vinhris-button vinhris-button-dark" href="/workspace">Vào khu vực làm việc</a></div>
      </section>

      <section className="vinhris-closing"><VinHRISLogo inverse /><h2>Một quy trình HCNS bắt đầu từ hồ sơ được kiểm tra đúng.</h2><a className="vinhris-button vinhris-button-light" href="/workspace">Vào khu vực làm việc <span aria-hidden="true">↗</span></a></section>
      <footer className="vinhris-footer"><VinHRISLogo /><span>Cổng tác nghiệp Hành chính - Nhân sự</span><a href="#top">Về đầu trang ↑</a></footer>
    </main>
  );
}
