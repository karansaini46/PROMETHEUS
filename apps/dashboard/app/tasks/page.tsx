"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  createRun,
  createTask,
  getModels,
  getProjects,
  getTasks,
} from "../../lib/api";
import { EmptyState, ErrorState, LoadingState, Pagination } from "../components/UIStates";
import type {
  ModelConfiguration,
  Project,
  Task,
  TaskPriority,
  TaskStatus,
  TaskType,
} from "@prometheus/shared-types";
import { IconCopy, IconSearch, IconTasks } from "../components/Icons";

export default function TaskWorkspacePage() {
  const router = useRouter();

  const [tasks, setTasks] = useState<Task[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [models, setModels] = useState<ModelConfiguration[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters & Pagination
  const [page, setPage] = useState(1);
  const [pageSize] = useState(10);
  const [totalPages, setTotalPages] = useState(1);
  const [totalItems, setTotalItems] = useState(0);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // Submit Issue Form State
  const [showSubmitModal, setShowSubmitModal] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [formSuccess, setFormSuccess] = useState<string | null>(null);

  const [formProjectId, setFormProjectId] = useState<string>("");
  const [formTitle, setFormTitle] = useState("");
  const [formProblem, setFormProblem] = useState("");
  const [formTaskType, setFormTaskType] = useState<TaskType>("BUG_FIX");
  const [formPriority, setFormPriority] = useState<TaskPriority>("HIGH");
  const [formBaseCommit, setFormBaseCommit] = useState("");
  const [formReproduceCmd, setFormReproduceCmd] = useState("");

  // Dispatch Run Modal State
  const [dispatchTask, setDispatchTask] = useState<Task | null>(null);
  const [selectedModel, setSelectedModel] = useState<string>("");
  const [dispatching, setDispatching] = useState(false);

  const loadData = useCallback(async (currentPage = 1, status = "", query = "") => {
    setLoading(true);
    setError(null);
    try {
      const [tasksRes, projectsRes, modelsRes] = await Promise.all([
        getTasks({
          page: currentPage,
          page_size: pageSize,
          status: status || undefined,
          search: query || undefined,
        }),
        getProjects(),
        getModels(),
      ]);

      setTasks(tasksRes.items);
      setTotalItems(tasksRes.total);
      setTotalPages(tasksRes.total_pages || Math.ceil(tasksRes.total / pageSize) || 1);
      setProjects(projectsRes);
      setModels(modelsRes);

      if (projectsRes.length > 0) {
        setFormProjectId((prev) => prev || projectsRes[0].id);
      }
      if (modelsRes.length > 0) {
        setSelectedModel((prev) => prev || modelsRes[0].provider + "/" + modelsRes[0].model_name);
      }
    } catch (err: any) {
      setError(err?.message || "Failed to load task workspace.");
    } finally {
      setLoading(false);
    }
  }, [pageSize]);

  useEffect(() => {
    loadData(1, statusFilter, searchQuery);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter, loadData]);

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(text);
    setTimeout(() => setCopiedId(null), 1800);
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    loadData(1, statusFilter, searchQuery);
  };

  const handlePageChange = (newPage: number) => {
    setPage(newPage);
    loadData(newPage, statusFilter, searchQuery);
  };

  const handleSubmitTask = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    if (!formTitle.trim() || !formProblem.trim()) {
      setFormError("Title and Problem Statement are required.");
      return;
    }

    setSubmitting(true);
    try {
      const newTask = await createTask({
        project_id: formProjectId || (projects[0]?.id ?? "proj-default"),
        title: formTitle.trim(),
        problem_statement: formProblem.trim(),
        task_type: formTaskType,
        priority: formPriority,
        base_commit: formBaseCommit.trim() || null,
        reproduce_command: formReproduceCmd.trim() || null,
      });

      setFormSuccess(`Task '${newTask.title}' submitted to engineering queue.`);
      setShowSubmitModal(false);
      setFormTitle("");
      setFormProblem("");
      setFormBaseCommit("");
      setFormReproduceCmd("");
      loadData(1, statusFilter, searchQuery);
    } catch (err: any) {
      setFormError(err?.message || "Failed to submit task.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleDispatchRun = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!dispatchTask) return;

    setDispatching(true);
    try {
      const run = await createRun({
        task_id: dispatchTask.id,
        model_provider: selectedModel || "anthropic/claude-3-5-sonnet-20241022",
      });
      setDispatchTask(null);
      router.push(`/runs/${run.id}`);
    } catch (err: any) {
      alert(`Failed to start execution run: ${err?.message || err}`);
    } finally {
      setDispatching(false);
    }
  };

  const getStatusBadge = (status: TaskStatus) => {
    switch (status) {
      case "OPEN":
        return <span className="badge badge-open">OPEN</span>;
      case "IN_PROGRESS":
        return <span className="badge badge-running"><span className="badge-dot" />IN PROGRESS</span>;
      case "RESOLVED":
        return <span className="badge badge-resolved">✓ RESOLVED</span>;
      case "CLOSED":
        return <span className="badge badge-pending">CLOSED</span>;
      case "CANCELLED":
        return <span className="badge badge-cancelled">CANCELLED</span>;
      default:
        return <span className="badge badge-pending">{status}</span>;
    }
  };

  const getPriorityBadge = (priority: TaskPriority) => {
    const colorMap: Record<string, string> = {
      CRITICAL: "var(--danger)",
      HIGH: "var(--warning)",
      MEDIUM: "var(--accent)",
      LOW: "var(--text-muted)",
    };
    return (
      <span
        style={{
          fontFamily: "var(--font-mono)",
          fontSize: "0.75rem",
          fontWeight: 700,
          color: colorMap[priority] || "var(--text-secondary)",
        }}
      >
        {priority}
      </span>
    );
  };

  return (
    <div>
      <div className="page-header">
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.25rem" }}>
            <h1 className="page-title">Task Workspace</h1>
            <span className="badge badge-pending">
              Registered Tasks ({totalItems})
            </span>
          </div>
          <p className="page-description">
            Submit software engineering issues, track autonomous reproduction lifecycles, and dispatch execution runs.
          </p>
        </div>
        <div style={{ display: "flex", gap: "0.75rem" }}>
          <button
            type="button"
            className="btn btn-primary btn-sm"
            onClick={() => setShowSubmitModal(!showSubmitModal)}
            aria-expanded={showSubmitModal}
          >
            {showSubmitModal ? "Cancel" : "+ Submit Debugging Task"}
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

      {/* Task Submission Form */}
      {showSubmitModal && (
        <form
          className="form-card"
          onSubmit={handleSubmitTask}
          aria-label="Submit Engineering Task Form"
        >
          <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", marginBottom: "1.25rem" }}>
            <IconTasks size={20} color="var(--accent)" />
            <h2 style={{ fontSize: "1.05rem", fontWeight: 600, color: "var(--text-primary)" }}>
              New Engineering Issue / Target
            </h2>
          </div>

          {formError && (
            <div
              style={{
                color: "var(--danger)",
                backgroundColor: "var(--danger-subtle)",
                padding: "0.6rem 0.85rem",
                borderRadius: "6px",
                marginBottom: "1rem",
                fontSize: "0.825rem",
              }}
            >
              ⚠ {formError}
            </div>
          )}

          <div className="form-grid">
            <div className="form-group">
              <label htmlFor="task-project" className="form-label">
                Target Project Workspace *
              </label>
              <select
                id="task-project"
                className="form-select"
                value={formProjectId}
                onChange={(e) => setFormProjectId(e.target.value)}
              >
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} ({p.default_branch})
                  </option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label htmlFor="task-type" className="form-label">
                Task Classification *
              </label>
              <select
                id="task-type"
                className="form-select"
                value={formTaskType}
                onChange={(e) => setFormTaskType(e.target.value as TaskType)}
              >
                <option value="BUG_FIX">BUG_FIX (Reproduction & Root Cause)</option>
                <option value="FEATURE">FEATURE (Specification & Code Gen)</option>
                <option value="REFACTOR">REFACTOR (Structural & Performance)</option>
                <option value="BENCHMARK_EVAL">BENCHMARK_EVAL (SWE-bench Case)</option>
              </select>
            </div>

            <div className="form-group">
              <label htmlFor="task-priority" className="form-label">
                Priority
              </label>
              <select
                id="task-priority"
                className="form-select"
                value={formPriority}
                onChange={(e) => setFormPriority(e.target.value as TaskPriority)}
              >
                <option value="CRITICAL">CRITICAL</option>
                <option value="HIGH">HIGH</option>
                <option value="MEDIUM">MEDIUM</option>
                <option value="LOW">LOW</option>
              </select>
            </div>

            <div className="form-group">
              <label htmlFor="task-commit" className="form-label">
                Base Git Commit Hash
              </label>
              <input
                id="task-commit"
                type="text"
                className="form-input"
                placeholder="e.g. 7f3b890d (defaults to HEAD)"
                value={formBaseCommit}
                onChange={(e) => setFormBaseCommit(e.target.value)}
              />
            </div>
          </div>

          <div className="form-group" style={{ marginTop: "1rem" }}>
            <label htmlFor="task-title" className="form-label">
              Issue Title *
            </label>
            <input
              id="task-title"
              type="text"
              className="form-input"
              placeholder="e.g. ZeroDivisionError when calculating discount ratio in checkout service"
              value={formTitle}
              onChange={(e) => setFormTitle(e.target.value)}
              required
            />
          </div>

          <div className="form-group" style={{ marginTop: "1rem" }}>
            <label htmlFor="task-problem" className="form-label">
              Problem Statement & Reproduction Evidence *
            </label>
            <textarea
              id="task-problem"
              className="form-textarea"
              rows={4}
              placeholder="Describe defect behavior, stack traces, and minimal failing reproduction assertions..."
              value={formProblem}
              onChange={(e) => setFormProblem(e.target.value)}
              required
            />
          </div>

          <div className="form-group" style={{ marginTop: "1rem" }}>
            <label htmlFor="task-reproduce-cmd" className="form-label">
              Reproduction Test Command (Optional)
            </label>
            <input
              id="task-reproduce-cmd"
              type="text"
              className="form-input"
              placeholder="e.g. pytest tests/test_checkout.py -k test_zero_division"
              value={formReproduceCmd}
              onChange={(e) => setFormReproduceCmd(e.target.value)}
            />
          </div>

          <div style={{ marginTop: "1.5rem", display: "flex", gap: "0.75rem", justifyContent: "flex-end" }}>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => setShowSubmitModal(false)}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="btn btn-primary btn-sm"
              disabled={submitting}
            >
              {submitting ? "Submitting..." : "Enqueue Task"}
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
            className={`chip ${statusFilter === "" ? "active" : ""}`}
            onClick={() => setStatusFilter("")}
          >
            All Statuses
          </button>
          {["OPEN", "IN_PROGRESS", "RESOLVED", "CLOSED"].map((st) => (
            <button
              key={st}
              type="button"
              className={`chip ${statusFilter === st ? "active" : ""}`}
              onClick={() => setStatusFilter(statusFilter === st ? "" : st)}
            >
              {st}
            </button>
          ))}
        </div>

        <form onSubmit={handleSearchSubmit} style={{ display: "flex", gap: "0.5rem" }}>
          <div style={{ position: "relative" }}>
            <input
              type="text"
              className="form-input"
              style={{ width: "240px", paddingLeft: "2rem" }}
              placeholder="Search tasks..."
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
          <button type="submit" className="btn btn-secondary btn-sm">
            Search
          </button>
        </form>
      </div>

      {loading ? (
        <LoadingState message="Querying task workspace records..." />
      ) : error ? (
        <ErrorState title="Failed to load tasks" message={error} onRetry={() => loadData(page)} />
      ) : tasks.length === 0 ? (
        <EmptyState
          title="No engineering tasks found"
          description="Submit a software defect or feature specification above to initialize autonomous localization."
          actionLabel="+ Submit Debugging Task"
          onAction={() => setShowSubmitModal(true)}
        />
      ) : (
        <div className="table-container">
          <table className="eng-table" aria-label="Tasks Table">
            <thead>
              <tr>
                <th scope="col">Task Identifier</th>
                <th scope="col">Issue Title</th>
                <th scope="col">Type</th>
                <th scope="col">Priority</th>
                <th scope="col">Status</th>
                <th scope="col">Runs</th>
                <th scope="col">Created</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {tasks.map((task) => (
                <tr key={task.id}>
                  <td>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                      <span className="table-mono" style={{ color: "var(--accent)", fontWeight: 600 }}>
                        {task.id}
                      </span>
                      <button
                        type="button"
                        className="copy-pill"
                        onClick={() => copyToClipboard(task.id)}
                        title="Copy task ID"
                      >
                        {copiedId === task.id ? "✓" : <IconCopy size={12} />}
                      </button>
                    </div>
                  </td>
                  <td>
                    <div style={{ fontWeight: 600, color: "var(--text-primary)" }}>{task.title}</div>
                    <div style={{ fontSize: "0.775rem", color: "var(--text-muted)", marginTop: "0.2rem", maxWidth: "340px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {task.problem_statement}
                    </div>
                  </td>
                  <td>
                    <span className="badge badge-pending" style={{ fontSize: "0.7rem" }}>
                      {task.task_type}
                    </span>
                  </td>
                  <td>{getPriorityBadge(task.priority)}</td>
                  <td>{getStatusBadge(task.status)}</td>
                  <td className="table-mono">
                    {task.runs_count || 0}
                  </td>
                  <td style={{ fontSize: "0.775rem", color: "var(--text-muted)" }}>
                    {new Date(task.created_at).toLocaleDateString()}
                  </td>
                  <td>
                    <div style={{ display: "flex", gap: "0.4rem" }}>
                      <button
                        type="button"
                        className="btn btn-sm btn-secondary"
                        onClick={() => setDispatchTask(task)}
                        title="Dispatch autonomous debugging run"
                      >
                        ▶ Run
                      </button>
                      <Link
                        href={`/runs?task_id=${task.id}`}
                        className="btn btn-sm btn-secondary"
                        title="View run history for this task"
                      >
                        Runs →
                      </Link>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <Pagination
            page={page}
            totalPages={totalPages}
            totalItems={totalItems}
            onPageChange={handlePageChange}
          />
        </div>
      )}

      {/* Dispatch Run Modal */}
      {dispatchTask && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: "rgba(0, 0, 0, 0.75)",
            backdropFilter: "blur(6px)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 100,
          }}
          role="dialog"
          aria-modal="true"
        >
          <div
            className="form-card"
            style={{ width: "100%", maxWidth: "520px", margin: "1rem", backgroundColor: "var(--bg-surface-solid)" }}
          >
            <h2 style={{ fontSize: "1.1rem", marginBottom: "0.5rem", color: "var(--text-primary)" }}>
              Dispatch Autonomous Agent
            </h2>
            <p style={{ fontSize: "0.825rem", color: "var(--text-secondary)", marginBottom: "1.25rem" }}>
              Launch cyclic LangGraph workflow for <strong style={{ color: "var(--text-primary)" }}>{dispatchTask.id}</strong> in capability-stripped Docker sandbox.
            </p>

            <form onSubmit={handleDispatchRun}>
              <div className="form-group" style={{ marginBottom: "1.25rem" }}>
                <label htmlFor="model-select" className="form-label">
                  Select Model Configuration
                </label>
                <select
                  id="model-select"
                  className="form-select"
                  value={selectedModel}
                  onChange={(e) => setSelectedModel(e.target.value)}
                >
                  {models.map((m) => (
                    <option key={m.id} value={`${m.provider}/${m.model_name}`}>
                      {m.name} ({m.provider} - {m.model_name})
                    </option>
                  ))}
                  {models.length === 0 && (
                    <option value="anthropic/claude-3-5-sonnet-20241022">
                      Claude 3.5 Sonnet (Default Mock)
                    </option>
                  )}
                </select>
              </div>

              <div style={{ display: "flex", gap: "0.75rem", justifyContent: "flex-end" }}>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => setDispatchTask(null)}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn-primary btn-sm"
                  disabled={dispatching}
                >
                  {dispatching ? "Starting..." : "Launch Run"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
