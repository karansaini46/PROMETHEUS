import type { Metadata } from "next";
import "./globals.css";
import { Sidebar } from "./components/Sidebar";
import { TopBar } from "./components/TopBar";

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
      <body>
        <div className="app-shell">
          <Sidebar />
          <div className="main-content">
            <TopBar />
            <div className="page-container">{children}</div>
          </div>
        </div>
      </body>
    </html>
  );
}
