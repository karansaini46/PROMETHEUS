import { describe, it, expect } from "vitest";
import React from "react";
import { render, screen } from "@testing-library/react";
import DashboardPage from "../app/page";

describe("Dashboard Control Plane Page", () => {
  it("renders the PROMETHEUS title and section cards", async () => {
    const Component = await DashboardPage();
    render(Component);

    expect(screen.getByText("PROMETHEUS")).toBeInTheDocument();
    expect(screen.getByText("Control Plane")).toBeInTheDocument();
    expect(screen.getByText("🤖 AI Agent Orchestrator")).toBeInTheDocument();
    expect(screen.getByText("🛡️ Execution Sandbox")).toBeInTheDocument();
    expect(screen.getByText("🗄️ Persistence & State")).toBeInTheDocument();
  });
});
