import { describe, it, expect } from "vitest";
import React from "react";
import { render, screen } from "@testing-library/react";
import DashboardPage from "../app/page";

describe("Dashboard Control Plane Page", () => {
  it("renders the PROMETHEUS title and section cards", async () => {
    localStorage.setItem("prometheus_demo_mode", "true");
    render(<DashboardPage />);

    expect(await screen.findByText("Engineering Overview")).toBeInTheDocument();
  });
});
