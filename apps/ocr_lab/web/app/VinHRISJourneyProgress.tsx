"use client";

import { useEffect, useState } from "react";

const steps = [
  ["01", "Tiếp nhận"],
  ["02", "Biểu mẫu"],
  ["03", "Evidence"],
  ["04", "Review"],
  ["05", "JSON"],
] as const;

export default function VinHRISJourneyProgress() {
  const [activeStep, setActiveStep] = useState("01");

  useEffect(() => {
    const scenes = Array.from(document.querySelectorAll<HTMLElement>(".vinhris-journey-scene"));
    if (!scenes.length) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        const nextStep = visible?.target.getAttribute("data-step");
        if (nextStep) setActiveStep(nextStep);
      },
      { rootMargin: "-34% 0px -46%", threshold: [0.15, 0.45, 0.8] },
    );

    scenes.forEach((scene) => observer.observe(scene));
    return () => observer.disconnect();
  }, []);

  return (
    <aside className="vinhris-journey-progress" aria-label="Tiến độ hành trình xử lý tài liệu">
      <div className="vinhris-progress-label"><span>PIPELINE</span><b>05 bước</b></div>
      <div className="vinhris-progress-list" role="list">
        {steps.map(([id, label]) => (
          <a
            className={`vinhris-progress-step${activeStep === id ? " is-active" : ""}`}
            href={`#journey-step-${id}`}
            aria-current={activeStep === id ? "step" : undefined}
            key={id}
          >
            <span className="vinhris-progress-node">{id}</span>
            <span>{label}</span>
          </a>
        ))}
      </div>
      <p>Cuộn để xem từng lớp dữ liệu.</p>
    </aside>
  );
}
