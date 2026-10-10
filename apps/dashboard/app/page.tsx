import React from "react";
import type { HealthResponse } from "@prometheus/shared-types";

async function getHealth(): Promise<HealthResponse> {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  try {
    const res = await fetch(`${apiUrl}/api/v1/health`, {
      cache: "no-store",
    });
    if (res.ok) {
      return await res.json();
    }
  } catch {
    // API is unreachable or offline
  }

  return {
    status: "degraded",
    version: "0.1.0",
    environment: process.env.NODE_ENV || "development",
    timestamp: new Date().toISOString(),
    database: "disconnected",
    sandbox_available: false,
  };
}

export default async function DashboardPage() {
  const health = await getHealth();

  return (
    <main className="container">
      <header>
        <div className="logo-group">
          <div className="logo-badge">PROMETHEUS</div>
          <div>
            <h1>Control Plane</h1>
            <p className="subtitle">Autonomous AI Software Engineering & Debugging Platform</p>
          </div>
        </div>
        <div
          className="status-pill"
          style={{
            color: health.status === "healthy" ? "#10b981" : "#f59e0b",
            borderColor: health.status === "healthy" ? "rgba(16, 185, 129, 0.3)" : "rgba(245, 158, 11, 0.3)",
            backgroundColor: health.status === "healthy" ? "rgba(16, 185, 129, 0.1)" : "rgba(245, 158, 11, 0.1)",
          }}
        >
          <span className="status-dot" />
          System Status: {health.status.toUpperCase()}
        </div>
      </header>

      <section className="grid">
        <div className="card">
          <h2 className="card-title">🤖 AI Agent Orchestrator</h2>
          <p className="card-desc">LangGraph cyclic state machine with PostgreSQL checkpoint persistence.</p>
          <div className="meta-row">
            <span className="meta-label">Engine</span>
            <span className="meta-val">Python 3.12 / LangGraph</span>
          </div>
          <div className="meta-row">
            <span className="meta-label">Resumability</span>
            <span className="meta-val">PostgresSaver Enabled</span>
          </div>
          <div className="meta-row">
            <span className="meta-label">Status</span>
            <span className="meta-val">Configured</span>
          </div>
        </div>

        <div className="card">
          <h2 className="card-title">🛡️ Execution Sandbox</h2>
          <p className="card-desc">Hardened Docker containers with zero-network isolation and capability dropping.</p>
          <div className="meta-row">
            <span className="meta-label">Isolation</span>
            <span className="meta-val">--cap-drop=ALL, no-new-priv</span>
          </div>
          <div className="meta-row">
            <span className="meta-label">Network Mode</span>
            <span className="meta-val">--network=none</span>
          </div>
          <div className="meta-row">
            <span className="meta-label">Host Daemon</span>
            <span className="meta-val">{health.sandbox_available ? "Ready" : "Standby"}</span>
          </div>
        </div>

        <div className="card">
          <h2 className="card-title">🗄️ Persistence & State</h2>
          <p className="card-desc">Authoritative relational storage with optional HNSW semantic vector indexes.</p>
          <div className="meta-row">
            <span className="meta-label">Database</span>
            <span className="meta-val">PostgreSQL 16 + pgvector</span>
          </div>
          <div className="meta-row">
            <span className="meta-label">Connection</span>
            <span className="meta-val">{health.database}</span>
          </div>
          <div className="meta-row">
            <span className="meta-label">Schema Migrations</span>
            <span className="meta-val">Alembic Tracked</span>
          </div>
        </div>

        <div className="card">
          <h2 className="card-title">🔌 Model Provider Router</h2>
          <p className="card-desc">Multi-vendor abstraction supporting Anthropic, OpenAI, and local Ollama/vLLM.</p>
          <div className="meta-row">
            <span className="meta-label">Provider Layer</span>
            <span className="meta-val">LiteLLM Protocol</span>
          </div>
          <div className="meta-row">
            <span className="meta-label">Local Fallback</span>
            <span className="meta-val">Ollama / vLLM (CPU/MPS)</span>
          </div>
          <div className="meta-row">
            <span className="meta-label">Telemetry</span>
            <span className="meta-val">OpenTelemetry OTLP</span>
          </div>
        </div>
      </section>

      <section className="card" style={{ marginTop: "1rem" }}>
        <h2 className="card-title">System Runtime Telemetry</h2>
        <div className="terminal-box">
          <code>
            {JSON.stringify(
              {
                service: "prometheus-dashboard",
                backend_probe: health,
                architecture: "modular_monolith",
                environment: health.environment,
                timestamp: health.timestamp,
              },
              null,
              2
            )}
          </code>
        </div>
      </section>
    </main>
  );
}
