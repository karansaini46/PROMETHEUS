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
import { IconCheck, IconSettings } from "../components/Icons";

export default function SettingsPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null);
  const [probing, setProbing] = useState(false);

  // Settings form states
  const [apiUrl, setApiUrl] = useState(API_URL);
  const [apiKey, setApiKey] = useState("");
  const [showApiKey, setShowApiKey] = useState(false);
  const [timeoutSec, setTimeoutSec] = useState(300);
  const [maxIterations, setMaxIterations] = useState(15);
  const [demoActive, setDemoActive] = useState(false);
  const [autoRunTests, setAutoRunTests] = useState(true);

  // Permitted Providers state
  const [providers, setProviders] = useState({
    anthropic: true,
    openai: true,
    deepseek: true,
    google: true,
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
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.25rem" }}>
            <h1 className="page-title">System Settings & Providers</h1>
            <span className="badge badge-pending">
              PLATFORM CONFIGURATION
            </span>
          </div>
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
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.25rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <IconSettings size={18} color="var(--accent)" />
            <h2 style={{ fontSize: "1rem", fontWeight: 600, color: "var(--text-primary)" }}>
              Authoritative Control Plane Status
            </h2>
          </div>
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
            <div className="metric-label">FastAPI Gateway</div>
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
                <span className="badge-dot" aria-hidden="true" />
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
                <span className="badge-dot" aria-hidden="true" />
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
                  gap: "0.6rem",
                  padding: "0.65rem 0.95rem",
                  backgroundColor: enabled ? "var(--bg-elevated)" : "var(--bg-card)",
                  borderRadius: "8px",
                  cursor: "pointer",
                  border: `1px solid ${enabled ? "var(--accent)" : "var(--border-subtle)"}`,
                  transition: "all 0.15s ease",
                }}
              >
                <input
                  type="checkbox"
                  checked={enabled}
                  onChange={() => handleToggleProvider(providerName as keyof typeof providers)}
                  style={{ accentColor: "var(--accent)" }}
                />
                <span style={{ fontSize: "0.85rem", textTransform: "capitalize", fontWeight: enabled ? 600 : 400 }}>
                  {providerName}
                </span>
              </label>
            ))}
          </div>
        </div>

        {/* Execution Constraints */}
        <div className="form-grid" style={{ marginBottom: "2rem" }}>
          <div className="form-group">
            <label htmlFor="settings-timeout" className="form-label">
              Sandbox Execution Timeout (seconds)
            </label>
            <input
              id="settings-timeout"
              type="number"
              className="form-input"
              value={timeoutSec}
              onChange={(e) => setTimeoutSec(Number(e.target.value))}
            />
          </div>

          <div className="form-group">
            <label htmlFor="settings-max-iter" className="form-label">
              Maximum Agent Reasoning Iterations
            </label>
            <input
              id="settings-max-iter"
              type="number"
              className="form-input"
              value={maxIterations}
              onChange={(e) => setMaxIterations(Number(e.target.value))}
            />
          </div>

          <div className="form-group">
            <label htmlFor="settings-api-key" className="form-label">
              Admin & Service API Key
            </label>
            <div style={{ display: "flex", gap: "0.4rem" }}>
              <input
                id="settings-api-key"
                type={showApiKey ? "text" : "password"}
                className="form-input"
                style={{ flex: 1 }}
                placeholder="Optional Bearer token"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
              />
              <button
                type="button"
                className="btn btn-sm btn-secondary"
                onClick={() => setShowApiKey(!showApiKey)}
              >
                {showApiKey ? "Hide" : "Show"}
              </button>
            </div>
          </div>
        </div>

        {/* Toggles */}
        <div style={{ display: "flex", flexDirection: "column", gap: "1rem", marginBottom: "2rem" }}>
          <label style={{ display: "flex", alignItems: "center", gap: "0.75rem", cursor: "pointer" }}>
            <input
              type="checkbox"
              checked={demoActive}
              onChange={(e) => setDemoActive(e.target.checked)}
              style={{ accentColor: "var(--accent)", width: "16px", height: "16px" }}
            />
            <div>
              <span style={{ fontSize: "0.85rem", fontWeight: 600, color: "var(--text-primary)" }}>
                Enable Sample Demo Mode
              </span>
              <p style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                Overrides live backend queries with realistic SWE-bench verification fixtures for offline presentations.
              </p>
            </div>
          </label>

          <label style={{ display: "flex", alignItems: "center", gap: "0.75rem", cursor: "pointer" }}>
            <input
              type="checkbox"
              checked={autoRunTests}
              onChange={(e) => setAutoRunTests(e.target.checked)}
              style={{ accentColor: "var(--accent)", width: "16px", height: "16px" }}
            />
            <div>
              <span style={{ fontSize: "0.85rem", fontWeight: 600, color: "var(--text-primary)" }}>
                Auto-execute Dual Test Oracles (FAIL_TO_PASS + PASS_TO_PASS)
              </span>
              <p style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                Immediately apply synthesized patches inside isolated containers and execute regression suites.
              </p>
            </div>
          </label>
        </div>

        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <button type="submit" className="btn btn-primary btn-sm">
            Save System Preferences
          </button>
        </div>
      </form>
    </div>
  );
}
