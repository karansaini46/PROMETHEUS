"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { createModel, getModels } from "../../lib/api";
import { EmptyState, ErrorState, LoadingState } from "../components/UIStates";
import type { ModelConfiguration } from "@prometheus/shared-types";
import { IconCopy, IconModels, IconSearch } from "../components/Icons";

export default function ModelLaboratoryPage() {
  const [models, setModels] = useState<ModelConfiguration[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filter state
  const [providerFilter, setProviderFilter] = useState<string>("");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [copiedId, setCopiedId] = useState<string | null>(null);

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

  const loadModels = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getModels();
      setModels(data);
    } catch (err: any) {
      setError(err?.message || "Failed to load model configurations.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadModels();
  }, [loadModels]);

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(text);
    setTimeout(() => setCopiedId(null), 1800);
  };

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

  const filteredModels = useMemo(() => {
    return models.filter((m) => {
      const matchesProvider = !providerFilter || m.provider.toLowerCase() === providerFilter.toLowerCase();
      const q = searchQuery.toLowerCase().trim();
      const matchesQuery = !q || m.name.toLowerCase().includes(q) || m.model_name.toLowerCase().includes(q);
      return matchesProvider && matchesQuery;
    });
  }, [models, providerFilter, searchQuery]);

  return (
    <div>
      <div className="page-header">
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.25rem" }}>
            <h1 className="page-title">Model Laboratory</h1>
            <span className="badge badge-resolved">
              MULTI-VENDOR ROUTER
            </span>
          </div>
          <p className="page-description">
            Configured LLM providers, token economics, context window boundaries, and checkpoint parameters.
          </p>
        </div>
        <div style={{ display: "flex", gap: "0.75rem" }}>
          <button type="button" className="btn btn-secondary btn-sm" onClick={loadModels}>
            Refresh
          </button>
          <button
            type="button"
            className="btn btn-primary btn-sm"
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
          style={{ padding: "0.85rem 1.25rem", marginBottom: "1.5rem", borderColor: "var(--success-border)" }}
          role="status"
        >
          <p style={{ color: "var(--success-text)", fontWeight: 500 }}>{formSuccess}</p>
        </div>
      )}

      {/* Model Registration Form */}
      {showAddModal && (
        <form
          className="form-card"
          onSubmit={handleCreateModel}
          aria-label="Register Model Configuration Form"
        >
          <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", marginBottom: "1.25rem" }}>
            <IconModels size={16} />
            <h2 style={{ fontSize: "0.9375rem", fontWeight: 600, color: "var(--text-primary)" }}>
              Register LLM Provider Configuration
            </h2>
          </div>

          {formError && (
            <div
              style={{
                color: "var(--danger-text)",
                backgroundColor: "var(--danger-bg)",
                border: "1px solid var(--danger-border)",
                padding: "0.6rem 0.85rem",
                borderRadius: "5px",
                marginBottom: "1rem",
                fontSize: "0.78125rem",
              }}
            >
              {formError}
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
                <option value="gemini">google gemini</option>
                <option value="deepseek">deepseek</option>
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
                placeholder="e.g. claude-3-5-sonnet-20241022 or gemini-2.5-flash"
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
                type="text"
                className="form-input"
                placeholder="e.g. http://localhost:11434/v1"
                value={formBaseUrl}
                onChange={(e) => setFormBaseUrl(e.target.value)}
              />
            </div>

            <div className="form-group">
              <label htmlFor="model-context" className="form-label">
                Context Window (tokens)
              </label>
              <input
                id="model-context"
                type="number"
                className="form-input"
                value={formContextWindow}
                onChange={(e) => setFormContextWindow(Number(e.target.value))}
              />
            </div>

            <div className="form-group">
              <label htmlFor="model-temp" className="form-label">
                Default Temperature (0.0 - 1.0)
              </label>
              <input
                id="model-temp"
                type="number"
                step="0.05"
                min="0"
                max="1"
                className="form-input"
                value={formTemp}
                onChange={(e) => setFormTemp(Number(e.target.value))}
              />
            </div>
          </div>

          <div style={{ marginTop: "1.25rem", display: "flex", gap: "0.75rem", justifyContent: "flex-end" }}>
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => setShowAddModal(false)}>
              Cancel
            </button>
            <button type="submit" className="btn btn-primary btn-sm" disabled={submitting}>
              {submitting ? "Saving..." : "Save Model Configuration"}
            </button>
          </div>
        </form>
      )}

      {/* Filter and Search Bar */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: "1rem",
          marginBottom: "1.5rem",
          flexWrap: "wrap",
        }}
      >
        <div className="chip-group">
          <button
            type="button"
            className={`chip ${providerFilter === "" ? "active" : ""}`}
            onClick={() => setProviderFilter("")}
          >
            All Providers <span className="chip-count">{models.length}</span>
          </button>
          {["anthropic", "openai", "gemini", "ollama"].map((prov) => {
            const count = models.filter((m) => m.provider.toLowerCase() === prov).length;
            if (count === 0 && providerFilter !== prov) return null;
            return (
              <button
                key={prov}
                type="button"
                className={`chip ${providerFilter === prov ? "active" : ""}`}
                onClick={() => setProviderFilter(providerFilter === prov ? "" : prov)}
              >
                {prov} <span className="chip-count">{count}</span>
              </button>
            );
          })}
        </div>

        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
          <div style={{ position: "relative" }}>
            <input
              type="text"
              className="form-input"
              style={{ width: "240px", paddingLeft: "2rem" }}
              placeholder="Search model configs..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
            <span
              style={{
                position: "absolute",
                left: "0.65rem",
                top: "50%",
                transform: "translateY(-50%)",
                opacity: 0.5,
                display: "flex",
                alignItems: "center",
              }}
            >
              <IconSearch size={14} />
            </span>
          </div>
          {searchQuery && (
            <button
              type="button"
              className="btn btn-sm btn-secondary"
              onClick={() => setSearchQuery("")}
            >
              ✕
            </button>
          )}
        </div>
      </div>

      {loading ? (
        <LoadingState message="Fetching registered model configurations..." />
      ) : error ? (
        <ErrorState title="Failed to load models" message={error} onRetry={loadModels} />
      ) : filteredModels.length === 0 ? (
        <EmptyState
          title="No model configurations match"
          description="Register an API provider or local inference endpoint above."
          actionLabel="+ Register First Model"
          onAction={() => setShowAddModal(true)}
        />
      ) : (
        <div className="table-container">
          <table className="eng-table">
            <thead>
              <tr>
                <th>Configuration Name</th>
                <th>Provider Family</th>
                <th>Model Identifier</th>
                <th>Context Window</th>
                <th>Rate / Cost ($/M)</th>
                <th>Temperature</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {filteredModels.map((m) => (
                <tr key={m.id}>
                  <td>
                    <div style={{ fontWeight: 600, color: "var(--text-primary)" }}>{m.name}</div>
                  </td>
                  <td>
                    <span className="badge badge-pending">{m.provider}</span>
                  </td>
                  <td>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                      <span className="table-mono" style={{ color: "var(--accent)" }}>{m.model_name}</span>
                      <button
                        type="button"
                        className="copy-pill"
                        onClick={() => copyToClipboard(m.model_name)}
                        title="Copy model identifier"
                      >
                        {copiedId === m.model_name ? "✓" : <IconCopy size={12} />}
                      </button>
                    </div>
                  </td>
                  <td className="table-mono">
                    {m.context_window.toLocaleString()} <span style={{ opacity: 0.6, fontSize: "0.75rem" }}>tok</span>
                  </td>
                  <td className="table-mono" style={{ color: "var(--success)" }}>
                    ${m.cost_per_million_input_tokens || 0} / ${m.cost_per_million_output_tokens || 0}
                  </td>
                  <td className="table-mono">{m.temperature}</td>
                  <td>
                    <span className="badge badge-resolved">
                      <span className="badge-dot" aria-hidden="true" />
                      ACTIVE
                    </span>
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
