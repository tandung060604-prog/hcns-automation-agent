import type { Metadata } from "next";
import { Be_Vietnam_Pro, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";

// Be Vietnam Pro covers Vietnamese diacritics; stick to real weights only (400–700).
const sans = Be_Vietnam_Pro({
  variable: "--font-sans",
  subsets: ["latin", "vietnamese"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
});

const mono = IBM_Plex_Mono({
  variable: "--font-mono",
  subsets: ["latin", "vietnamese"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "VinHRIS | Cổng tác nghiệp Hành chính - Nhân sự",
  description:
    "Tiếp nhận hồ sơ, trích xuất thông tin và phối hợp kiểm tra tài liệu HCNS trong môi trường nội bộ.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="vi">
      <body className={`${sans.variable} ${mono.variable} ${sans.className}`}>{children}</body>
    </html>
  );
}
