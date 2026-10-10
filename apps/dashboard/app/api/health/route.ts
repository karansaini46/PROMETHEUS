import { NextResponse } from "next/server";
import type { HealthResponse } from "@prometheus/shared-types";

export async function GET() {
  const healthData: HealthResponse = {
    status: "healthy",
    version: "0.1.0",
    environment: process.env.NODE_ENV || "development",
    timestamp: new Date().toISOString(),
    database: "disabled", // Dashboard is presentation plane; state managed by FastAPI backend
    sandbox_available: false,
  };

  return NextResponse.json(healthData);
}
