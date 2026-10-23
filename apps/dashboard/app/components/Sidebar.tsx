"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  IconEvaluations,
  IconMemory,
  IconModels,
  IconOverview,
  IconPatchReview,
  IconProjects,
  IconRuns,
  IconSettings,
  IconTasks,
} from "./Icons";

interface NavItem {
  href: string;
  label: string;
  IconComponent: React.ComponentType<{ size?: number; className?: string }>;
}

const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "Overview", IconComponent: IconOverview },
  { href: "/projects", label: "Projects", IconComponent: IconProjects },
  { href: "/tasks", label: "Task Workspace", IconComponent: IconTasks },
  { href: "/runs", label: "Execution Runs", IconComponent: IconRuns },
  { href: "/patch-review", label: "Patch Review", IconComponent: IconPatchReview },
  { href: "/models", label: "Model Registry", IconComponent: IconModels },
  { href: "/evaluations", label: "Evaluations", IconComponent: IconEvaluations },
  { href: "/memory", label: "Memory Graph", IconComponent: IconMemory },
  { href: "/settings", label: "Settings", IconComponent: IconSettings },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="sidebar" aria-label="Main Navigation">
      <div className="sidebar-brand">
        <Link href="/" className="brand-title">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#EDEDED" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
          </svg>
          <span>PROMETHEUS</span>
        </Link>
        <span className="brand-badge">v0.1.0</span>
      </div>

      <nav className="sidebar-nav">
        {NAV_ITEMS.map((item) => {
          const isActive =
            item.href === "/"
              ? pathname === "/"
              : pathname.startsWith(item.href);

          const { IconComponent } = item;

          return (
            <Link
              key={item.href}
              href={item.href}
              className={`nav-link ${isActive ? "active" : ""}`}
              aria-current={isActive ? "page" : undefined}
            >
              <span className="nav-icon" aria-hidden="true">
                <IconComponent size={15} />
              </span>
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>

      <div className="sidebar-footer">
        <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
          <span className="pulse-dot" />
          <span>Core Daemon</span>
        </div>
        <span>online</span>
      </div>
    </aside>
  );
}
