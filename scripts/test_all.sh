#!/usr/bin/env bash
set -euo pipefail

echo "=========================================="
echo " Running PROMETHEUS Full Validation Suite "
echo "=========================================="

echo "--> 1. Python Ruff Format Check..."
.venv/bin/ruff format --check .

echo "--> 2. Python Ruff Lint Check..."
.venv/bin/ruff check .

echo "--> 3. Python Mypy Strict Type Check..."
.venv/bin/mypy services prometheus_ai tests

echo "--> 4. Python Pytest Suite..."
.venv/bin/pytest -v

echo "--> 5. Shared Types Build..."
(cd packages/shared-types && npm run build)

echo "--> 6. Next.js Dashboard ESLint..."
(cd apps/dashboard && npm run lint)

echo "--> 7. Next.js Dashboard TypeScript Check..."
(cd apps/dashboard && npm run type-check)

echo "--> 8. Next.js Dashboard Vitest..."
(cd apps/dashboard && npm run test)

echo "--> 9. Next.js Dashboard Production Build..."
(cd apps/dashboard && npm run build)

echo "=========================================="
echo " ✅ ALL CHECKS PASSED SUCCESSFULLY!       "
echo "=========================================="
