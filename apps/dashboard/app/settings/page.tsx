"use client";

import React, { useEffect, useState } from "react";
import {
  API_URL,
  getHealth,
  getReadiness,
  isDemoMode,
  setDemoMode,
} from "../../lib/api";
import type { HealthResponse, ReadinessResponse } from "@prometheus/shared-types";

export default function SettingsPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null);
  const [probing, setProbing] = useState(false);

  // Settings form states
  const [apiUrl, setApiUrl] = useState(API_URL);
  const [apiKey, setApiKey] = useState("");
  const [timeoutSec, setTimeoutSec] = useState(300);
  const [maxIterations, setMaxIterations] = useState(15);
  const [demoActive, setDemoActive] = useState(false);
  const [autoRunTests, setAutoRunTests] = useState(true);

  // Permitted Providers state
  const [providers, setProviders] = useState({
    anthropic: true,
    openai: true,
    deepseek: true,
    google: false,
    ollama: true,
    vllm: false,
  });

  const [savedMessage, setSavedMessage] = useState<string | null>(null);

  useEffect(() => {
    setDemoActive(isDemoMode());
    if (typeof window !== "undefined") {
      const storedKey = localStorage.getItem("prometheus_api_key") || "";
      const storedTimeout = localStorage.getItem("prometheus_timeout");
      const storedMaxIter = localStorage.getItem("prometheus_max_iter");
      const storedProviders = localStorage.getItem("prometheus_providers");

      setApiKey(storedKey);
      if (storedTimeout) setTimeoutSec(parseInt(storedTimeout, 10));
      if (storedMaxIter) setMaxIterations(parseInt(storedMaxIter, 10));
      if (storedProviders) {
        try {
          setProviders(JSON.parse(storedProviders));
        } catch {}
      }
    }

    checkDiagnostics();
  }, []);

  const checkDiagnostics = async () => {
    setProbing(true);
    try {
      const [h, r] = await Promise.all([getHealth(), getReadiness()]);
      setHealth(h);
      setReadiness(r);
    } catch {
      // offline
    } finally {
      setProbing(false);
    }
  };

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    if (typeof window !== "undefined") {
      localStorage.setItem("prometheus_api_key", apiKey);
      localStorage.setItem("prometheus_timeout", String(timeoutSec));
      localStorage.setItem("prometheus_max_iter", String(maxIterations));
      localStorage.setItem("prometheus_providers", JSON.stringify(providers));
    }
    setDemoMode(demoActive);

    setSavedMessage("Configuration preferences saved successfully.");
    setTimeout(() => setSavedMessage(null), 3000);
  };

  const handleToggleProvider = (key: keyof typeof providers) => {
    setProviders((prev) => ({
      ...prev,
      [key]: !prev[key],
    }));
  };

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">System Settings & Providers</h1>
          <p className="page-description">
            Configure permitted model providers, execution timeouts, authorization credentials, and simulation modes.
          </p>
        </div>
      </div>

      {savedMessage && (
        <div
          className="state-box"
          style={{ padding: "0.85rem 1.25rem", marginBottom: "1.5rem", borderColor: "var(--success)" }}
          role="status"
        >
          <p style={{ color: "var(--success)", fontWeight: 600 }}>✓ {savedMessage}</p>
        </div>
      )}

      {/* Diagnostics Panel */}
      <div className="metric-card" style={{ marginBottom: "2rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
          <h2 style={{ fontSize: "1rem", fontWeight: 600, color: "var(--text-primary)" }}>
            Authoritative Control Plane Status
          </h2>
          <button
            type="button"
            className="btn btn-sm btn-secondary"
            onClick={checkDiagnostics}
            disabled={probing}
          >
            {probing ? "Probing..." : "↻ Test Connectivity"}
          </button>
        </div>

        <div className="form-grid">
          <div>
            <div className="metric-label">FastAPI Endpoint</div>
            <div className="table-mono" style={{ fontSize: "0.85rem", color: "var(--accent)" }}>
              {apiUrl}
            </div>
            <div className="metric-subtext">Version: {health?.version || "0.1.0"}</div>
          </div>

          <div>
            <div className="metric-label">Database Connection</div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
              <span
                className={`badge ${
                  health?.database === "connected" ? "badge-resolved" : "badge-running"
                }`}
              >
                {health?.database?.toUpperCase() || "DISCONNECTED"}
              </span>
            </div>
            <div className="metric-subtext">PostgreSQL 16 state engine</div>
          </div>

          <div>
            <div className="metric-label">Docker Sandbox Engine</div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
              <span
                className={`badge ${
                  health?.sandbox_available ? "badge-resolved" : "badge-pending"
                }`}
              >
                {health?.sandbox_available ? "READY (CONTAINERIZED)" : "STANDBY (MOCK)"}
              </span>
            </div>
            <div className="metric-subtext">gVisor / Docker container isolation</div>
          </div>
        </div>
      </div>

      {/* Main Settings Form */}
      <form className="form-card" onSubmit={handleSave} aria-label="System Settings Form">
        <h2 style={{ fontSize: "1.1rem", marginBottom: "1.25rem", color: "var(--text-primary)" }}>
          Application & Execution Preferences
        </h2>

        {/* Permitted Model Providers */}
        <div style={{ marginBottom: "2rem" }}>
          <label className="form-label" style={{ marginBottom: "0.75rem", display: "block" }}>
            Permitted Model Providers
          </label>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
              gap: "0.75rem",
            }}
          >
            {Object.entries(providers).map(([providerName, enabled]) => (
              <label
                key={providerName}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "0.5rem",
                  padding: "0.6rem 0.85rem",
                  backgroundColor: "var(--bg-elevated)",
                  borderRadius: "6px",
                  cursor: "pointer",
                  border: "1px solid var(--border-subtle)",
                }}
              >
                <input
                  type="checkbox"
                  checked={enabled}
                  onChange={() => handleToggleProvider(providerName as keyof typeof providers)}
                />
                <span className="table-mono" style={{ textTransform: "uppercase", fontSize: "0.8rem" }}>
                  {providerName}
                </span>
              </label>
            ))}
          </div>
        </div>

        {/* Execution & Security Grid */}
        <div className="form-grid">
          <div className="form-group">
            <label htmlFor="settings-api-key" className="form-label">
              Admin API Key (X-API-Key)
            </label>
            <input
              id="settings-api-key"
              type="password"
              className="form-input"
              placeholder="Enter secret token for privileged operations..."
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
            />
          </div>

          <div className="form-group">
            <label htmlFor="settings-timeout" className="form-label">
              Sandbox Execution Timeout (seconds)
            </label>
            <input
              id="settings-timeout"
              type="number"
              className="form-input"
              min="30"
              max="3600"
              value={timeoutSec}
              onChange={(e) => setTimeoutSec(parseInt(e.target.value, 10))}
            />
          </div>

          <div className="form-group">
            <label htmlFor="settings-max-iter" className="form-label">
              Max Agent Iterations per Run
            </label>
            <input
              id="settings-max-iter"
              type="number"
              className="form-input"
              min="1"
              max="50"
              value={maxIterations}
              onChange={(e) => setMaxIterations(parseInt(e.target.value, 10))}
            />
          </div>
        </div>

        {/* Mode Toggles */}
        <div style={{ marginTop: "1.5rem", display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          <label style={{ display: "flex", alignItems: "center", gap: "0.6rem", cursor: "pointer", fontSize: "0.85rem" }}>
            <input
              type="checkbox"
              checked={autoRunTests}
              onChange={(e) => setAutoRunTests(e.target.checked)}
            />
            <span>Auto-run test verification in isolated container after synthesizing patch</span>
          </label>

          <label style={{ display: "flex", alignItems: "center", gap: "0.6rem", cursor: "pointer", fontSize: "0.85rem" }}>
            <input
              type="checkbox"
              checked={demoActive}
              onChange={(e) => setDemoActive(e.target.checked)}
            />
            <span>
              <strong>Labeled Demo Mode</strong> (Use sample datasets when backend is disconnected)
            </span>
          </label>
        </div>

        <div style={{ marginTop: "2rem" }}>
          <button type="submit" className="btn btn-primary">
            Save Preferences
          </button>
        </div>
      </form>
    </div>
  );
}
