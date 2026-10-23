"use client";

import React, { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { getProjects } from "../../lib/api";
import { EmptyState, ErrorState, LoadingState } from "../components/UIStates";
import type { Project } from "@prometheus/shared-types";
import { IconCopy, IconProjects, IconSearch } from "../components/Icons";

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // New project modal / form state
  const [showForm, setShowForm] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [projectName, setProjectName] = useState("");
  const [repoUrl, setRepoUrl] = useState("");
  const [branch, setBranch] = useState("main");
  const [submitting, setSubmitting] = useState(false);
  const [submitSuccess, setSubmitSuccess] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

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

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(text);
    setTimeout(() => setCopiedId(null), 1800);
  };

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

  const filteredProjects = useMemo(() => {
    const q = searchQuery.toLowerCase().trim();
    if (!q) return projects;
    return projects.filter(
      (p) =>
        p.name.toLowerCase().includes(q) ||
        (p.slug && p.slug.toLowerCase().includes(q)) ||
        (p.repository_url && p.repository_url.toLowerCase().includes(q))
    );
  }, [projects, searchQuery]);

  return (
    <div>
      <div className="page-header">
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.25rem" }}>
            <h1 className="page-title">Project Workspaces</h1>
            <span className="badge badge-pending">
              TARGET REPOSITORIES
            </span>
          </div>
          <p className="page-description">
            Registered target codebases, remote git mirrors, AST symbol index caches, and execution sandbox profiles.
          </p>
        </div>
        <div style={{ display: "flex", gap: "0.75rem" }}>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={loadProjects}
            title="Refresh workspaces"
          >
            ↻ Refresh
          </button>
          <button
            type="button"
            className="btn btn-primary btn-sm"
            onClick={() => setShowForm(!showForm)}
            aria-expanded={showForm}
          >
            {showForm ? "Cancel" : "+ Register Target Repository"}
          </button>
        </div>
      </div>

      {submitSuccess && (
        <div
          className="state-box"
          style={{ padding: "0.85rem 1.25rem", marginBottom: "1.5rem", borderColor: "var(--success)" }}
          role="status"
        >
          <p style={{ color: "var(--success)", fontWeight: 600 }}>✓ {submitSuccess}</p>
        </div>
      )}

      {/* Registration Form */}
      {showForm && (
        <form className="form-card" onSubmit={handleRegisterRepo} aria-label="Register Repository Form">
          <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", marginBottom: "1rem" }}>
            <IconProjects size={20} color="var(--accent)" />
            <h2 style={{ fontSize: "1.05rem", fontWeight: 600, color: "var(--text-primary)" }}>
              Register Target Git Repository
            </h2>
          </div>
          <div className="form-grid">
            <div className="form-group">
              <label htmlFor="proj-name" className="form-label">Project Workspace Name *</label>
              <input
                id="proj-name"
                type="text"
                className="form-input"
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
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => setShowForm(false)}>
              Cancel
            </button>
            <button type="submit" className="btn btn-primary btn-sm" disabled={submitting}>
              {submitting ? "Registering..." : "Save Project Registration"}
            </button>
          </div>
        </form>
      )}

      {/* Search and Filters */}
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
        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
          <div style={{ position: "relative" }}>
            <input
              type="text"
              className="form-input"
              style={{ width: "260px", paddingLeft: "2.1rem" }}
              aria-label="Search workspaces by name or URL"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
            <span
              style={{
                position: "absolute",
                left: "0.7rem",
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
              ✕ Clear
            </button>
          )}
        </div>

        <div style={{ fontSize: "0.825rem", color: "var(--text-muted)" }}>
          Total Workspaces: <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>{projects.length}</span>
        </div>
      </div>

      {loading ? (
        <LoadingState message="Loading registered projects..." />
      ) : error ? (
        <ErrorState title="Failed to load projects" message={error} onRetry={loadProjects} />
      ) : filteredProjects.length === 0 ? (
        <EmptyState
          title="No target repositories found"
          description={
            searchQuery
              ? "No workspace matches your search term."
              : "Register a repository above to enable worktree checkouts and autonomous debugging."
          }
          actionLabel="+ Register First Repository"
          onAction={() => setShowForm(true)}
        />
      ) : (
        <div className="table-container">
          <div className="table-header-bar">
            <h2 className="table-title">Registered Projects ({filteredProjects.length})</h2>
          </div>
          <table className="eng-table">
            <thead>
              <tr>
                <th>Workspace Identifier</th>
                <th>Project Name</th>
                <th>Git Repository Remote</th>
                <th>Branch</th>
                <th>Isolation Sandbox</th>
                <th>Registered Date</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredProjects.map((proj) => (
                <tr key={proj.id}>
                  <td>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                      <span className="table-mono" style={{ color: "var(--accent)", fontWeight: 600 }}>
                        {proj.slug || proj.id}
                      </span>
                      <button
                        type="button"
                        className="copy-pill"
                        onClick={() => copyToClipboard(proj.slug || proj.id)}
                        title="Copy slug"
                      >
                        {copiedId === (proj.slug || proj.id) ? "✓" : <IconCopy size={12} />}
                      </button>
                    </div>
                  </td>
                  <td style={{ fontWeight: 600, color: "var(--text-primary)" }}>{proj.name}</td>
                  <td>
                    <span className="table-mono" style={{ fontSize: "0.775rem", color: "var(--text-secondary)" }}>
                      {proj.repository_url || "Local File Bind"}
                    </span>
                  </td>
                  <td>
                    <span className="badge badge-pending">
                      {proj.default_branch || "main"}
                    </span>
                  </td>
                  <td>
                    <span className="badge badge-resolved">
                      <span className="badge-dot" aria-hidden="true" />
                      --cap-drop=ALL
                    </span>
                  </td>
                  <td className="table-mono" style={{ color: "var(--text-muted)", fontSize: "0.775rem" }}>
                    {new Date(proj.created_at).toLocaleDateString()}
                  </td>
                  <td>
                    <Link
                      href={`/tasks?project_id=${proj.id}`}
                      className="btn btn-sm btn-secondary"
                      title="View or create tasks for this project"
                    >
                      Tasks →
                    </Link>
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
