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
      setFormError("Task title and problem statement are required.");
      return;
    }

    setSubmitting(true);
    try {
      const created = await createTask({
        project_id: formProjectId || projects[0]?.id || "proj-ast-engine",
        title: formTitle.trim(),
        problem_statement: formProblem.trim(),
        task_type: formTaskType,
        priority: formPriority,
        base_commit: formBaseCommit.trim() || undefined,
        reproduce_command: formReproduceCmd.trim() || undefined,
      });

      setFormSuccess(`Task ${created.id} submitted to engineering queue.`);
      setShowSubmitModal(false);
      setFormTitle("");
      setFormProblem("");
      setFormBaseCommit("");
      setFormReproduceCmd("");
      // reload
      await loadData(1, statusFilter, searchQuery);
    } catch (err: any) {
      setFormError(err?.message || "Failed to submit task.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleTriggerRun = async () => {
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
        return <span className="badge badge-running">IN PROGRESS</span>;
      case "RESOLVED":
        return <span className="badge badge-resolved">RESOLVED</span>;
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
          fontWeight: 600,
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
          <h1 className="page-title">Task Workspace</h1>
          <p className="page-description">
            Submit software engineering issues, track autonomous reproduction lifecycles, and dispatch execution runs.
          </p>
        </div>
        <div style={{ display: "flex", gap: "0.75rem" }}>
          <button
            type="button"
            className="btn btn-primary"
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
          <h2 style={{ fontSize: "1.1rem", marginBottom: "1rem", color: "var(--text-primary)" }}>
            New Engineering Issue / Target
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
              placeholder="e.g. RecursionError in ast_indexer on cyclic module imports"
              value={formTitle}
              onChange={(e) => setFormTitle(e.target.value)}
              required
            />
          </div>

          <div className="form-group" style={{ marginTop: "1rem" }}>
            <label htmlFor="task-desc" className="form-label">
              Problem Statement & Reproduction Evidence *
            </label>
            <textarea
              id="task-desc"
              className="form-textarea"
              rows={5}
              placeholder="Provide exact traceback, stack trace, expected behavior, or failing assertion..."
              value={formProblem}
              onChange={(e) => setFormProblem(e.target.value)}
              required
            />
          </div>

          <div className="form-group" style={{ marginTop: "1rem" }}>
            <label htmlFor="task-cmd" className="form-label">
              Reproduction Test Command
            </label>
            <input
              id="task-cmd"
              type="text"
              className="form-input"
              placeholder="e.g. pytest tests/test_ast.py -k test_circular_ref"
              value={formReproduceCmd}
              onChange={(e) => setFormReproduceCmd(e.target.value)}
            />
          </div>

          <div style={{ marginTop: "1.25rem", display: "flex", gap: "0.75rem" }}>
            <button type="submit" className="btn btn-primary" disabled={submitting}>
              {submitting ? "Submitting Task..." : "Enqueue Task"}
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => setShowSubmitModal(false)}
            >
              Cancel
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
        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
          <label htmlFor="filter-status" className="form-label" style={{ margin: 0 }}>
            Status:
          </label>
          <select
            id="filter-status"
            className="form-select"
            style={{ width: "auto" }}
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="">All Statuses</option>
            <option value="OPEN">OPEN</option>
            <option value="IN_PROGRESS">IN PROGRESS</option>
            <option value="RESOLVED">RESOLVED</option>
            <option value="CLOSED">CLOSED</option>
            <option value="CANCELLED">CANCELLED</option>
          </select>
        </div>

        <form onSubmit={handleSearchSubmit} style={{ display: "flex", gap: "0.5rem" }}>
          <input
            type="search"
            className="form-input"
            style={{ width: "260px" }}
            placeholder="Search issues, titles, commit..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            aria-label="Search tasks"
          />
          <button type="submit" className="btn btn-secondary">
            Search
          </button>
        </form>
      </div>

      {/* Content Rendering */}
      {loading ? (
        <LoadingState message="Fetching engineering tasks..." />
      ) : error ? (
        <ErrorState title="Failed to retrieve tasks" message={error} onRetry={() => loadData()} />
      ) : tasks.length === 0 ? (
        <EmptyState
          title="No tasks found"
          description={
            statusFilter || searchQuery
              ? "No tasks match the active filters or search query."
              : "No engineering issues submitted yet. Enqueue a task to begin."
          }
          actionLabel="+ Submit Debugging Task"
          onAction={() => setShowSubmitModal(true)}
        />
      ) : (
        <div className="table-container">
          <div className="table-header-bar">
            <h2 className="table-title">Registered Tasks ({totalItems})</h2>
            <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
              Page {page} of {totalPages}
            </span>
          </div>

          <table className="eng-table" aria-label="Tasks List">
            <thead>
              <tr>
                <th scope="col">Task ID</th>
                <th scope="col">Title & Issue Statement</th>
                <th scope="col">Type</th>
                <th scope="col">Priority</th>
                <th scope="col">Status</th>
                <th scope="col">Runs</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {tasks.map((task) => (
                <tr key={task.id}>
                  <td>
                    <span className="table-mono" style={{ color: "var(--accent)" }}>
                      {task.id}
                    </span>
                    {task.base_commit && (
                      <div
                        className="table-mono"
                        style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}
                      >
                        commit: {task.base_commit.slice(0, 8)}
                      </div>
                    )}
                  </td>
                  <td style={{ maxWidth: "420px" }}>
                    <div
                      style={{
                        fontWeight: 600,
                        color: "var(--text-primary)",
                        marginBottom: "0.25rem",
                      }}
                    >
                      {task.title}
                    </div>
                    <div
                      style={{
                        fontSize: "0.775rem",
                        color: "var(--text-secondary)",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        display: "-webkit-box",
                        WebkitLineClamp: 2,
                        WebkitBoxOrient: "vertical",
                      }}
                    >
                      {task.problem_statement}
                    </div>
                  </td>
                  <td>
                    <span className="table-mono" style={{ fontSize: "0.75rem" }}>
                      {task.task_type}
                    </span>
                  </td>
                  <td>{getPriorityBadge(task.priority)}</td>
                  <td>{getStatusBadge(task.status)}</td>
                  <td>
                    <span className="table-mono">
                      {task.runs_count || 0} run{(task.runs_count || 0) === 1 ? "" : "s"}
                    </span>
                    {task.latest_run_status && (
                      <div style={{ marginTop: "0.2rem" }}>
                        <span
                          className={`badge ${
                            task.latest_run_status === "RESOLVED"
                              ? "badge-resolved"
                              : task.latest_run_status === "RUNNING"
                              ? "badge-running"
                              : "badge-pending"
                          }`}
                          style={{ fontSize: "0.65rem", padding: "0.1rem 0.4rem" }}
                        >
                          {task.latest_run_status}
                        </span>
                      </div>
                    )}
                  </td>
                  <td>
                    <div style={{ display: "flex", gap: "0.4rem" }}>
                      <button
                        type="button"
                        className="btn btn-sm btn-primary"
                        onClick={() => setDispatchTask(task)}
                        title="Dispatch an autonomous execution run for this issue"
                      >
                        ▶ Run
                      </button>
                      <Link
                        href={`/runs?task_id=${task.id}`}
                        className="btn btn-sm btn-secondary"
                        title="View runs for this task"
                      >
                        Runs
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
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 100,
          }}
          role="dialog"
          aria-modal="true"
          aria-labelledby="dispatch-dialog-title"
        >
          <div
            className="form-card"
            style={{ width: "100%", maxWidth: "520px", margin: "1rem" }}
          >
            <h2 id="dispatch-dialog-title" style={{ fontSize: "1.1rem", marginBottom: "0.5rem" }}>
              Dispatch Autonomous Agent
            </h2>
            <p style={{ fontSize: "0.85rem", color: "var(--text-secondary)", marginBottom: "1.25rem" }}>
              Target Issue: <strong style={{ color: "var(--text-primary)" }}>{dispatchTask.title}</strong> (
              <span className="table-mono">{dispatchTask.id}</span>)
            </p>

            <div className="form-group" style={{ marginBottom: "1.25rem" }}>
              <label htmlFor="select-model" className="form-label">
                Select Model Configuration
              </label>
              <select
                id="select-model"
                className="form-select"
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
              >
                {models.map((m) => (
                  <option key={m.id} value={`${m.provider}/${m.model_name}`}>
                    {m.name} ({m.provider}/{m.model_name})
                  </option>
                ))}
                {models.length === 0 && (
                  <option value="anthropic/claude-3-5-sonnet-20241022">
                    Claude 3.5 Sonnet (anthropic)
                  </option>
                )}
              </select>
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem" }}>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setDispatchTask(null)}
                disabled={dispatching}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={handleTriggerRun}
                disabled={dispatching}
              >
                {dispatching ? "Starting Agent..." : "Launch Execution Run"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
