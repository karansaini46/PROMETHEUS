import { describe, it, expect, beforeEach, vi } from "vitest";
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import RunInspectorPage from "../app/runs/[id]/page";

// Mock useParams
vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "run_94a8f102c91448b18a38b1d9" }),
}));

describe("Execution Inspector Workflow", () => {
  beforeEach(() => {
    localStorage.setItem("prometheus_demo_mode", "true");
  });

  it("renders run telemetry, token tally, and status badge", async () => {
    render(<RunInspectorPage />);

    expect(
      await screen.findByText("run_94a8f102c91448b18a38b1d9")
    ).toBeInTheDocument();

    expect(await screen.findByText(/Token Footprint/i)).toBeInTheDocument();
    expect(screen.getByText(/Estimated Cost/i)).toBeInTheDocument();
    expect(screen.getByText(/Iterations/i)).toBeInTheDocument();
  });

  it("renders ordered execution events: steps, tools, and observations", async () => {
    render(<RunInspectorPage />);

    // Should display sequence steps and tool invocations
    const initializedElements = await screen.findAllByText(/INITIALIZED/i);
    expect(initializedElements.length).toBeGreaterThan(0);

    const grepElements = await screen.findAllByText(/grep_search/i);
    expect(grepElements.length).toBeGreaterThan(0);

    const localizeElements = await screen.findAllByText(/LOCALIZE_FAULT/i);
    expect(localizeElements.length).toBeGreaterThan(0);

    // Verify tool observation is present
    expect(
      screen.getByText(/Found expiry comparison check/i)
    ).toBeInTheDocument();
  });

  it("filters events by event type", async () => {
    render(<RunInspectorPage />);

    const filterSelect = await screen.findByLabelText(/Filter events by type/i);
    fireEvent.change(filterSelect, { target: { value: "TOOL_INVOCATION" } });

    // Should still display tool invocation
    const toolItems = screen.getAllByText(/grep_search/i);
    expect(toolItems.length).toBeGreaterThan(0);
  });
});
