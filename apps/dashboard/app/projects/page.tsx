"use client";

import React, { useEffect, useState } from "react";
import { getProjects } from "../../lib/api";
import { EmptyState, ErrorState, LoadingState } from "../components/UIStates";
import type { Project } from "@prometheus/shared-types";

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // New project modal / form state
  const [showForm, setShowForm] = useState(false);
  const [projectName, setProjectName] = useState("");
  const [repoUrl, setRepoUrl] = useState("");
  const [branch, setBranch] = useState("main");
  const [submitting, setSubmitting] = useState(false);
  const [submitSuccess, setSubmitSuccess] = useState<string | null>(null);

  const loadProjects = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getProjects();
      setProjects(data);
    } catch (err: any) {
      setError(err?.message || "Failed to load projects.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadProjects();
  }, []);

  const handleRegisterRepo = (e: React.FormEvent) => {
    e.preventDefault();
    if (!projectName.trim() || !repoUrl.trim()) return;

    setSubmitting(true);
    setTimeout(() => {
      const newProj: Project = {
        id: `proj-${Date.now()}`,
        name: projectName.trim(),
        slug: projectName.trim().toLowerCase().replace(/[^a-z0-9]/g, "-"),
        repository_url: repoUrl.trim(),
        default_branch: branch,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      setProjects([newProj, ...projects]);
      setProjectName("");
      setRepoUrl("");
      setBranch("main");
      setSubmitting(false);
      setShowForm(false);
      setSubmitSuccess(`Repository '${newProj.name}' registered successfully.`);
    }, 400);
  };

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Project Workspaces</h1>
          <p className="page-description">
            Registered target codebases, remote git mirrors, and sandbox execution configurations.
          </p>
        </div>
        <div>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => setShowForm(!showForm)}
            aria-expanded={showForm}
          >
            {showForm ? "Cancel" : "+ Register Target Repository"}
          </button>
        </div>
      </div>

      {submitSuccess && (
        <div className="state-box" style={{ padding: "1rem", marginBottom: "1.5rem", borderColor: "var(--success)" }} role="status">
          <p style={{ color: "var(--success)", fontWeight: 600 }}>✓ {submitSuccess}</p>
        </div>
      )}

      {/* Registration Form */}
      {showForm && (
        <form className="form-card" onSubmit={handleRegisterRepo} aria-label="Register Repository Form">
          <h2 style={{ fontSize: "1.1rem", marginBottom: "1rem", color: "var(--text-primary)" }}>
            Register Target Git Repository
          </h2>
          <div className="form-grid">
            <div className="form-group">
              <label htmlFor="proj-name" className="form-label">Project Workspace Name *</label>
              <input
                id="proj-name"
                type="text"
                className="form-input"
                placeholder="e.g. Django Core Web Framework"
                value={projectName}
                onChange={(e) => setProjectName(e.target.value)}
                required
              />
            </div>

            <div className="form-group">
              <label htmlFor="repo-url" className="form-label">Git Remote URL *</label>
              <input
                id="repo-url"
                type="url"
                className="form-input"
                placeholder="https://github.com/organization/repo.git"
                value={repoUrl}
                onChange={(e) => setRepoUrl(e.target.value)}
                required
              />
            </div>

            <div className="form-group">
              <label htmlFor="default-branch" className="form-label">Baseline Branch</label>
              <input
                id="default-branch"
                type="text"
                className="form-input"
                value={branch}
                onChange={(e) => setBranch(e.target.value)}
              />
            </div>

            <div className="form-group">
              <label htmlFor="sandbox-profile" className="form-label">Execution Sandbox Profile</label>
              <select id="sandbox-profile" className="form-select" defaultValue="python312">
                <option value="python312">Debian 12 / Python 3.12 (Strict Isolation)</option>
                <option value="nodejs20">Debian 12 / Node.js 20 LTS</option>
                <option value="rust">Rust 1.80 / Cargo Minimal</option>
              </select>
            </div>
          </div>

          <div style={{ marginTop: "1.25rem", display: "flex", gap: "0.75rem", justifyContent: "flex-end" }}>
            <button type="button" className="btn btn-secondary" onClick={() => setShowForm(false)}>
              Cancel
            </button>
            <button type="submit" className="btn btn-primary" disabled={submitting}>
              {submitting ? "Registering..." : "Save Project Registration"}
            </button>
          </div>
        </form>
      )}

      {loading ? (
        <LoadingState message="Loading registered projects..." />
      ) : error ? (
        <ErrorState title="Failed to load projects" message={error} onRetry={loadProjects} />
      ) : projects.length === 0 ? (
        <EmptyState
          title="No target repositories registered"
          description="Register a repository above to enable worktree checkouts and autonomous debugging."
          actionLabel="+ Register First Repository"
          onAction={() => setShowForm(true)}
        />
      ) : (
        <div className="table-container">
          <div className="table-header-bar">
            <h2 className="table-title">Registered Projects ({projects.length})</h2>
          </div>
          <table className="eng-table">
            <thead>
              <tr>
                <th>Workspace Identifier</th>
                <th>Project Name</th>
                <th>Git Repository Remote</th>
                <th>Branch</th>
                <th>Isolation Status</th>
                <th>Registered Date</th>
              </tr>
            </thead>
            <tbody>
              {projects.map((proj) => (
                <tr key={proj.id}>
                  <td className="table-mono" style={{ color: "var(--accent)" }}>{proj.slug || proj.id}</td>
                  <td style={{ fontWeight: 600, color: "var(--text-primary)" }}>{proj.name}</td>
                  <td className="table-mono" style={{ fontSize: "0.8rem" }}>{proj.repository_url || "Local File Bind"}</td>
                  <td className="table-mono">{proj.default_branch || "main"}</td>
                  <td>
                    <span className="badge badge-resolved">
                      <span className="badge-dot" aria-hidden="true" />
                      --cap-drop=ALL
                    </span>
                  </td>
                  <td className="table-mono" style={{ color: "var(--text-muted)" }}>
                    {new Date(proj.created_at).toLocaleDateString()}
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
