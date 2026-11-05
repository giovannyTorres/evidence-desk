import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "Evidence Desk — Answers you can trace",
  description:
    "A documentary research workspace with verifiable citations. Original synthetic demonstration.",
};
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
