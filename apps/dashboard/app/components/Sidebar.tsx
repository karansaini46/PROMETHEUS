"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

interface NavItem {
  href: string;
  label: string;
  icon: string;
}

const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "Overview", icon: "⎈" },
  { href: "/projects", label: "Projects", icon: "◈" },
  { href: "/tasks", label: "Task Workspace", icon: "⚡" },
  { href: "/runs", label: "Execution Inspector", icon: "▶" },
  { href: "/patch-review", label: "Patch Review", icon: "⌥" },
  { href: "/models", label: "Model Laboratory", icon: "⌬" },
  { href: "/evaluations", label: "Evaluation Lab", icon: "⌖" },
  { href: "/memory", label: "Memory Explorer", icon: "☵" },
  { href: "/settings", label: "Settings", icon: "⚙" },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="sidebar" aria-label="Main Navigation">
      <div className="sidebar-brand">
        <div className="brand-glyph" aria-hidden="true">P</div>
        <div>
          <div className="brand-title">PROMETHEUS</div>
          <div className="brand-env">Control Center</div>
        </div>
      </div>

      <nav className="sidebar-nav">
        {NAV_ITEMS.map((item) => {
          const isActive =
            item.href === "/"
              ? pathname === "/"
              : pathname.startsWith(item.href);

          return (
            <Link
              key={item.href}
              href={item.href}
              className={`nav-link ${isActive ? "active" : ""}`}
              aria-current={isActive ? "page" : undefined}
            >
              <span className="nav-icon" aria-hidden="true">
                {item.icon}
              </span>
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>

      <div className="sidebar-footer">
        <div>Engine: Python 3.12 / LangGraph</div>
        <div>Persistence: PostgreSQL 16</div>
      </div>
    </aside>
  );
}
