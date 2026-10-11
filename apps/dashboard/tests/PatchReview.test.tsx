import { describe, it, expect, beforeEach } from "vitest";
import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import PatchReviewPage from "../app/patch-review/page";

describe("Patch Review Workflow", () => {
  beforeEach(() => {
    localStorage.setItem("prometheus_demo_mode", "true");
  });

  it("renders diff viewer with syntax lines and affected files", async () => {
    render(<PatchReviewPage />);

    expect(
      await screen.findByText("Patch Review & Verification")
    ).toBeInTheDocument();

    expect(
      await screen.findByText(/Affected Files/i)
    ).toBeInTheDocument();

    expect(
      await screen.findByText(/Explicit Gatekeeper Controls/i)
    ).toBeInTheDocument();
  });

  it("handles explicit patch rejection and approval controls", async () => {
    render(<PatchReviewPage />);

    // Patch 0 is initial, click Reject Patch
    const rejectBtn = await screen.findByRole("button", {
      name: /Reject Patch/i,
    });
    fireEvent.click(rejectBtn);

    await waitFor(() => {
      expect(
        screen.getByText(/REJECTED. Review notes recorded./i)
      ).toBeInTheDocument();
    });

    // Switch to patch tab 1 (task-ast-104) which is pending approval
    const tab1 = screen.getByText("task-ast-104");
    fireEvent.click(tab1);

    const approveBtn = await screen.findByRole("button", {
      name: /Approve & Permit Merge/i,
    });
    fireEvent.click(approveBtn);

    await waitFor(() => {
      expect(
        screen.getByText(/explicitly APPROVED for branch integration/i)
      ).toBeInTheDocument();
    });
  });
});
