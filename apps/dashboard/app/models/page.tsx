"use client";

import React, { useEffect, useState } from "react";
import { createModel, getModels } from "../../lib/api";
import { EmptyState, ErrorState, LoadingState } from "../components/UIStates";
import type { ModelConfiguration } from "@prometheus/shared-types";

export default function ModelLaboratoryPage() {
  const [models, setModels] = useState<ModelConfiguration[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filter state
  const [providerFilter, setProviderFilter] = useState<string>("");
  const [activeOnly, setActiveOnly] = useState<boolean>(false);

  // New Model Registration Form
  const [showAddModal, setShowAddModal] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [formSuccess, setFormSuccess] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  const [formName, setFormName] = useState("");
  const [formProvider, setFormProvider] = useState("anthropic");
  const [formModelName, setFormModelName] = useState("");
  const [formBaseUrl, setFormBaseUrl] = useState("");
  const [formTemp, setFormTemp] = useState(0.0);
  const [formMaxTokens, setFormMaxTokens] = useState(4096);
  const [formContextWindow, setFormContextWindow] = useState(128000);
  const [formInputCost, setFormInputCost] = useState(3.0);
  const [formOutputCost, setFormOutputCost] = useState(15.0);

  const loadModels = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getModels({
        provider: providerFilter || undefined,
        is_active: activeOnly ? true : undefined,
      });
      setModels(data);
    } catch (err: any) {
      setError(err?.message || "Failed to load model configurations.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadModels();
  }, [providerFilter, activeOnly]);

  const handleCreateModel = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    if (!formName.trim() || !formModelName.trim()) {
      setFormError("Configuration name and model name are required.");
      return;
    }

    setSubmitting(true);
    try {
      const newModel = await createModel({
        name: formName.trim(),
        provider: formProvider.trim(),
        model_name: formModelName.trim(),
        api_base_url: formBaseUrl.trim() || null,
        temperature: Number(formTemp),
        max_tokens: Number(formMaxTokens),
        context_window: Number(formContextWindow),
        cost_per_million_input_tokens: Number(formInputCost),
        cost_per_million_output_tokens: Number(formOutputCost),
        is_active: true,
      });

      setFormSuccess(`Model configuration '${newModel.name}' registered successfully.`);
      setShowAddModal(false);
      setFormName("");
      setFormModelName("");
      setFormBaseUrl("");
      await loadModels();
    } catch (err: any) {
      setFormError(err?.message || "Failed to register model configuration.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Model Laboratory</h1>
          <p className="page-description">
            Configured LLM providers, token economics, context window boundaries, and checkpoint parameters.
          </p>
        </div>
        <div>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => setShowAddModal(!showAddModal)}
            aria-expanded={showAddModal}
          >
            {showAddModal ? "Cancel" : "+ Register Model Configuration"}
          </button>
        </div>
      </div>

      {formSuccess && (
        <div
          className="state-box"
          style={{ padding: "0.85rem 1.25rem", marginBottom: "1.5rem", borderColor: "var(--success)" }}
          role="status"
        >
          <p style={{ color: "var(--success)", fontWeight: 600 }}>✓ {formSuccess}</p>
        </div>
      )}

      {/* Model Registration Form */}
      {showAddModal && (
        <form
          className="form-card"
          onSubmit={handleCreateModel}
          aria-label="Register Model Configuration Form"
        >
          <h2 style={{ fontSize: "1.1rem", marginBottom: "1rem", color: "var(--text-primary)" }}>
            Register LLM Provider Configuration
          </h2>

          {formError && (
            <div
              style={{
                color: "var(--danger)",
                backgroundColor: "var(--danger-subtle)",
                padding: "0.6rem 0.85rem",
                borderRadius: "4px",
                marginBottom: "1rem",
                fontSize: "0.825rem",
              }}
            >
              ⚠ {formError}
            </div>
          )}

          <div className="form-grid">
            <div className="form-group">
              <label htmlFor="model-cfg-name" className="form-label">
                Configuration Display Name *
              </label>
              <input
                id="model-cfg-name"
                type="text"
                className="form-input"
                placeholder="e.g. Claude 3.5 Sonnet (Production)"
                value={formName}
                onChange={(e) => setFormName(e.target.value)}
                required
              />
            </div>

            <div className="form-group">
              <label htmlFor="model-provider" className="form-label">
                Provider Family *
              </label>
              <select
                id="model-provider"
                className="form-select"
                value={formProvider}
                onChange={(e) => setFormProvider(e.target.value)}
              >
                <option value="anthropic">anthropic</option>
                <option value="openai">openai</option>
                <option value="deepseek">deepseek</option>
                <option value="google">google</option>
                <option value="ollama">ollama (local)</option>
                <option value="vllm">vllm (self-hosted)</option>
              </select>
            </div>

            <div className="form-group">
              <label htmlFor="model-id" className="form-label">
                Model Identifier *
              </label>
              <input
                id="model-id"
                type="text"
                className="form-input"
                placeholder="e.g. claude-3-5-sonnet-20241022 or gpt-4o"
                value={formModelName}
                onChange={(e) => setFormModelName(e.target.value)}
                required
              />
            </div>

            <div className="form-group">
              <label htmlFor="model-api-base" className="form-label">
                Custom API Base URL (Optional)
              </label>
              <input
                id="model-api-base"
                type="url"
                className="form-input"
                placeholder="https://api.openai.com/v1 or http://localhost:11434"
                value={formBaseUrl}
                onChange={(e) => setFormBaseUrl(e.target.value)}
              />
            </div>

            <div className="form-group">
              <label htmlFor="model-temp" className="form-label">
                Temperature (0.0 - 1.0)
              </label>
              <input
                id="model-temp"
                type="number"
                step="0.05"
                min="0"
                max="1"
                className="form-input"
                value={formTemp}
                onChange={(e) => setFormTemp(parseFloat(e.target.value))}
              />
            </div>

            <div className="form-group">
              <label htmlFor="model-context" className="form-label">
                Context Window (Tokens)
              </label>
              <input
                id="model-context"
                type="number"
                className="form-input"
                value={formContextWindow}
                onChange={(e) => setFormContextWindow(parseInt(e.target.value, 10))}
              />
            </div>

            <div className="form-group">
              <label htmlFor="model-max-tokens" className="form-label">
                Max Output Tokens
              </label>
              <input
                id="model-max-tokens"
                type="number"
                className="form-input"
                value={formMaxTokens}
                onChange={(e) => setFormMaxTokens(parseInt(e.target.value, 10))}
              />
            </div>

            <div className="form-group">
              <label htmlFor="model-input-cost" className="form-label">
                Cost / Million Input Tokens ($)
              </label>
              <input
                id="model-input-cost"
                type="number"
                step="0.1"
                className="form-input"
                value={formInputCost}
                onChange={(e) => setFormInputCost(parseFloat(e.target.value))}
              />
            </div>

            <div className="form-group">
              <label htmlFor="model-output-cost" className="form-label">
                Cost / Million Output Tokens ($)
              </label>
              <input
                id="model-output-cost"
                type="number"
                step="0.1"
                className="form-input"
                value={formOutputCost}
                onChange={(e) => setFormOutputCost(parseFloat(e.target.value))}
              />
            </div>
          </div>

          <div style={{ marginTop: "1.25rem", display: "flex", gap: "0.75rem" }}>
            <button type="submit" className="btn btn-primary" disabled={submitting}>
              {submitting ? "Registering..." : "Save Configuration"}
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => setShowAddModal(false)}
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      {/* Filter Row */}
      <div
        style={{
          display: "flex",
          gap: "1rem",
          alignItems: "center",
          marginBottom: "1.5rem",
          flexWrap: "wrap",
        }}
      >
        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
          <label htmlFor="filter-prov" className="form-label" style={{ margin: 0 }}>
            Provider:
          </label>
          <select
            id="filter-prov"
            className="form-select"
            style={{ width: "auto" }}
            value={providerFilter}
            onChange={(e) => setProviderFilter(e.target.value)}
          >
            <option value="">All Providers</option>
            <option value="anthropic">anthropic</option>
            <option value="openai">openai</option>
            <option value="deepseek">deepseek</option>
            <option value="google">google</option>
            <option value="ollama">ollama</option>
          </select>
        </div>

        <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.85rem", cursor: "pointer" }}>
          <input
            type="checkbox"
            checked={activeOnly}
            onChange={(e) => setActiveOnly(e.target.checked)}
          />
          Active Only
        </label>
      </div>

      {/* Model Cards / Table */}
      {loading ? (
        <LoadingState message="Fetching registered model configurations..." />
      ) : error ? (
        <ErrorState title="Failed to load models" message={error} onRetry={loadModels} />
      ) : models.length === 0 ? (
        <EmptyState
          title="No model configurations registered"
          description="Register a model provider endpoint and token pricing to dispatch agent runs."
          actionLabel="+ Register Model Configuration"
          onAction={() => setShowAddModal(true)}
        />
      ) : (
        <div className="table-container">
          <div className="table-header-bar">
            <h2 className="table-title">Model Configurations ({models.length})</h2>
          </div>

          <table className="eng-table" aria-label="Model Configurations Table">
            <thead>
              <tr>
                <th scope="col">Name & ID</th>
                <th scope="col">Provider / Model ID</th>
                <th scope="col">Context Window</th>
                <th scope="col">Max Output</th>
                <th scope="col">Temp</th>
                <th scope="col">Input ($/1M)</th>
                <th scope="col">Output ($/1M)</th>
                <th scope="col">Status</th>
              </tr>
            </thead>
            <tbody>
              {models.map((m) => (
                <tr key={m.id}>
                  <td>
                    <div style={{ fontWeight: 600, color: "var(--text-primary)" }}>{m.name}</div>
                    <div className="table-mono" style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>
                      {m.id}
                    </div>
                  </td>
                  <td>
                    <div className="table-mono" style={{ color: "var(--accent)", fontWeight: 600 }}>
                      {m.provider}
                    </div>
                    <div className="table-mono" style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                      {m.model_name}
                    </div>
                  </td>
                  <td>
                    <span className="table-mono">
                      {(m.context_window || 0).toLocaleString()} tok
                    </span>
                  </td>
                  <td>
                    <span className="table-mono">
                      {(m.max_tokens || 0).toLocaleString()}
                    </span>
                  </td>
                  <td>
                    <span className="table-mono">{m.temperature}</span>
                  </td>
                  <td>
                    <span className="table-mono" style={{ color: "var(--text-primary)" }}>
                      ${m.cost_per_million_input_tokens?.toFixed(2)}
                    </span>
                  </td>
                  <td>
                    <span className="table-mono" style={{ color: "var(--text-primary)" }}>
                      ${m.cost_per_million_output_tokens?.toFixed(2)}
                    </span>
                  </td>
                  <td>
                    {m.is_active ? (
                      <span className="badge badge-resolved">ACTIVE</span>
                    ) : (
                      <span className="badge badge-pending">INACTIVE</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
