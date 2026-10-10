import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PROMETHEUS — Autonomous AI Engineering Control Plane",
  description: "Next-generation autonomous software engineering and debugging platform",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
