import type { Metadata } from "next";
import Dashboard from "./Dashboard";
import results from "./data/results.json";

export const metadata: Metadata = {
  title: "HR Document Intelligence Lab | OCR tiếng Việt",
  description:
    "OCR và IDP tài liệu HCNS tiếng Việt với bằng chứng từng trường, human review và xử lý hoàn toàn trên máy local.",
};

export default function Home() {
  return <Dashboard data={results} />;
}
