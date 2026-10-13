# PROMETHEUS — Security Isolation Guarantees & Threat Limitations

**Document Version:** 1.0.0  
**Target Subsystem:** Repository Tools & Isolated Execution Layer (`prometheus_ai.execution`, `prometheus_ai.tools`)  
**Status:** Approved Security Architecture  

---

## 1. Executive Summary & Security Model

Autonomous AI software engineering agents process untrusted data from repositories, execute test suites, and generate code patches. A single vulnerability in isolation or input sanitization could allow hostile code to compromise the host system, exfiltrate secrets, or exhaust system resources.

PROMETHEUS implements a **defense-in-depth isolation layer** designed around three foundational axioms:

1. **Untrusted Data Axiom:** All repository content, README instructions, code comments, issue descriptions, and tool output are treated as untrusted data. Repository instructions **must never** be allowed to override or relax system-level security constraints.
2. **Deny-by-Default Execution:** Network connectivity, root access, Linux capabilities, and arbitrary command execution are denied by default.
3. **Defense-in-Depth:** Security does not rely on a single defensive barrier; layered controls prevent single-point-of-failure compromises across paths, processes, containers, and repositories.

---

## 2. Isolation Guarantees

### 2.1 Path Security & File System Boundaries

All repository inspection, file reading, and patch operations enforce strict canonical path validation:

* **Canonical Path Resolution:** Target paths are resolved using `os.path.realpath` and `Path.resolve()`, validating that the resulting path strictly satisfies `is_relative_to(workspace_base)`.
* **Path Traversal Protection:** Relative escape sequences (`../`, `..\\`), absolute paths (`/etc/passwd`), and encoded traversal tricks are detected and rejected with `PathTraversalError`.
* **Symlink Escapes:** Symlinks pointing outside the repository boundary, broken symlink chains, and recursive symlink loops are detected and rejected with `SymlinkEscapeError`.
* **Protected File Blacklist:** Sensitive files and directories are forbidden from access by tools, even if located within the repository root:
  * Environment & secrets: `.env`, `.env.*`, `*credentials*`, `*secrets*`
  * SSH & Keys: `id_rsa`, `id_ed25519`, `*.pem`, `*.key`, `*.pfx`, `.ssh/`
  * Cloud credentials: `.aws/`, `.docker/config.json`
  * Git configuration: `.git/config`, `.git/hooks/`
  * Shell histories: `.bash_history`, `.zsh_history`, `.netrc`
* **Filename Sanitization:** Filenames containing null bytes (`\0`) or ASCII control characters (0–31, 127) are rejected immediately.
* **Bounded Consumption:** File reads are capped at a maximum byte limit (default: 2 MB), search results are capped (default: 200 matches), directory traversal depth is capped (default: 20 levels), and output is automatically truncated with an explicit warning banner if bounded sizes are reached.

### 2.2 Git Security & Worktree Engine

Repository operations run with strict host-hardening policies:

* **Hooks Disabled Everywhere:** All git commands executed on the host enforce:
  ```bash
  git -c core.hooksPath=/dev/null ...
  ```
  This ensures that hostile repositories cannot execute malicious code via `.git/hooks` (`post-checkout`, `pre-commit`, etc.) on the host.
* **Isolated Concurrent Worktrees:** Work is performed in detached, ephemeral git worktrees located in a dedicated scratch directory (`prometheus_worktrees/`), preventing accidental modifications or pollution of the primary branch.
* **Safe Patch Application:** Unified diff patches are pre-scanned to ensure headers (`--- a/...`, `+++ b/...`) do not contain traversal paths (`../`) or target protected files. Patches undergo a dry-run check (`git apply --check`) before application.
* **Lifecycle Teardown:** Worktrees are registered with unique identifiers and automatically pruned and deleted during cleanup.

### 2.3 Containerized Sandbox Hardening

Untrusted commands (e.g. test suites, linters) are executed inside disposable containers with aggressive constraints:

* **Non-Root Execution:** Containers execute exclusively as an unprivileged user (`uid=1000, gid=1000`). Root privileges are never granted.
* **Complete Linux Capabilities Drop:** The container runs with `--cap-drop=ALL`, dropping all Linux capabilities (including `CAP_SYS_ADMIN`, `CAP_NET_RAW`, `CAP_DAC_OVERRIDE`, and `CAP_PTRACE`).
* **No New Privileges:** Containers enforce `--security-opt=no-new-privileges:true`, preventing setuid binaries from escalating privileges.
* **Read-Only Root Filesystem:** The root container filesystem is mounted read-only (`--read-only`). Ephemeral write space is provided only via bounded `tmpfs` mounts (`/tmp` with `noexec,nosuid` and explicit size limits).
* **Resource Limits:**
  * **Process Limit:** `--pids-limit=256` halts fork-bombs (`:(){ :|:& };:`) immediately without starving the host.
  * **Memory Limit:** Strict 4 GB RAM ceiling with matched swap limit (`--memory=4g --memory-swap=4g`), preventing host OOM conditions.
  * **CPU Limit:** Hard allocation cap (`--cpus=2.0`).
  * **Wall-Clock Timeouts:** Hard timeouts (default: 300s) trigger automatic container SIGKILL and teardown.
* **Sterile Environment Whitelist:** Host environment variables and application secrets are **never** inherited by the container. The environment contains only a sterile whitelist:
  ```json
  {
    "PATH": "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
    "PYTHONPATH": "/workspace",
    "LANG": "C.UTF-8",
    "HOME": "/workspace",
    "PYTHONDONTWRITEBYTECODE": "1"
  }
  ```
* **Docker Socket Isolation:** The host Docker socket (`/var/run/docker.sock`) is **strictly forbidden** from being mounted into the sandbox. Mount configurations targeting the socket fail with a critical `SecurityException`.
* **Zero-Network Mode (Deny-by-Default):** Untrusted test commands run with `--network=none`. Outbound sockets, DNS queries, and loopback scans to host ports or cloud metadata endpoints (`169.254.169.254`) are physically disabled by the Linux network namespace.

---

## 3. Critical Security Notice: Remaining Risks & Container Limitations

> [!WARNING]
> **Docker containers are NOT an impermeable security boundary.**  
> Standard Linux containers rely on shared kernel namespaces and cgroups. PROMETHEUS **does NOT** claim that containerization makes executing arbitrary, hostile malware 100% safe.

Organizations deploying PROMETHEUS on untrusted or adversarial repositories must understand the following inherent limitations:

### 3.1 Shared Kernel Attack Surface
Containers share the host operating system kernel. A zero-day or unpatched privilege escalation vulnerability in the host Linux kernel (such as Dirty COW, Dirty Pipe, or netfilter vulnerability chains) could allow code running inside an unprivileged container to compromise the host kernel and achieve full host breakout.

### 3.2 `/proc` and `/sys` Information Disclosure
Even with `--read-only` and dropped capabilities, certain pseudo-filesystems (`/proc` and `/sys`) reveal information about host memory layout, CPU architecture, and kernel version. This information can be leveraged by sophisticated adversaries to craft target-specific kernel exploits.

### 3.3 Microarchitectural & Hardware Side-Channels
Speculative execution attacks (e.g., Spectre, Meltdown, Downfall) operate across physical CPU cores and cache hierarchies. A container sharing physical host cores cannot be completely isolated from side-channel timing analysis that observes host cache states.

### 3.4 Kernel Resource Starvation
While cgroups constrain memory, CPU, and pids, certain kernel-space resources (e.g. kernel slab caches, open file descriptors, epoll instances) are managed globally. A malicious test fixture designed to exhaust kernel memory structures could cause host degradation.

---

## 4. Swappable Backend Roadmap (High-Assurance Isolation)

To eliminate the shared-kernel risks of standard Docker containers in high-threat environments, PROMETHEUS implements the `BaseSandboxRunner` interface. This allows zero-code-change replacement with stronger isolation backends:

```
┌────────────────────────────────────────────────────────┐
│               BaseSandboxRunner Interface              │
└───────────────────────────┬────────────────────────────┘
                            │
       ┌────────────────────┼────────────────────┐
       ▼                    ▼                    ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│    Docker    │     │    gVisor    │     │ Firecracker  │
│ Container    │     │   (runsc)    │     │   MicroVM    │
│  (Current)   │     │ (Application │     │  (Hardware   │
│              │     │  Syscall GM) │     │ Virtualized) │
└──────────────┘     └──────────────┘     └──────────────┘
```

1. **gVisor (`runsc` runtime):** Replaces the host kernel interface with an unprivileged, memory-safe (Go) application kernel that intercepts and handles all Linux syscalls in user-space.
2. **Firecracker MicroVMs:** Launches a dedicated, minimal KVM-virtualized virtual machine per task with its own guest kernel, achieving true hardware virtualization boundaries.
