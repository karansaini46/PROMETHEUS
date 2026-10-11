import { describe, it, expect, beforeEach, vi } from "vitest";
import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import TaskWorkspacePage from "../app/tasks/page";

// Mock next/navigation
vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
  }),
}));

describe("Task Workspace Workflow", () => {
  beforeEach(() => {
    localStorage.setItem("prometheus_demo_mode", "true");
  });

  it("renders task list and search filter correctly", async () => {
    render(<TaskWorkspacePage />);

    expect(await screen.findByText("Task Workspace")).toBeInTheDocument();
    expect(await screen.findByText(/Registered Tasks/)).toBeInTheDocument();

    // Check for demo task title
    expect(
      await screen.findByText(/Fix off-by-one token boundary/i)
    ).toBeInTheDocument();
  });

  it("opens modal and submits a new debugging issue", async () => {
    render(<TaskWorkspacePage />);

    // Click "+ Submit Debugging Task" button
    const openBtn = await screen.findByRole("button", {
      name: /\+ Submit Debugging Task/i,
    });
    fireEvent.click(openBtn);

    // Form inputs should be visible
    expect(screen.getByLabelText(/Issue Title \*/i)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/Issue Title \*/i), {
      target: { value: "Test Circular Import in compiler" },
    });
    fireEvent.change(
      screen.getByLabelText(/Problem Statement & Reproduction Evidence \*/i),
      {
        target: { value: "RecursionError when importing cycle a -> b -> a" },
      }
    );

    const submitBtn = screen.getByRole("button", { name: /Enqueue Task/i });
    fireEvent.click(submitBtn);

    // Verify confirmation
    await waitFor(() => {
      expect(
        screen.getByText(/submitted to engineering queue/i)
      ).toBeInTheDocument();
    });
  });

  it("opens dispatch run modal when clicking Run on a task", async () => {
    render(<TaskWorkspacePage />);

    const runButtons = await screen.findAllByRole("button", { name: /▶ Run/i });
    expect(runButtons.length).toBeGreaterThan(0);

    fireEvent.click(runButtons[0]);

    // Dispatch modal should open
    expect(
      await screen.findByText(/Dispatch Autonomous Agent/i)
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/Select Model Configuration/i)).toBeInTheDocument();
  });
});
