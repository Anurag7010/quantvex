# QuantVex — Repository Cleanup

## Step 1 — Audit first, delete second

Run this to get a full picture before touching anything:

```bash
find . -not -path './.git/*' -not -path './node_modules/*' -not -path './source/*' \
  | sort > /tmp/repo_audit.txt
cat /tmp/repo_audit.txt
```

Print the output. Do not delete anything until the audit is reviewed.

---

## Step 2 — Safe deletes (no business logic, confirmed removable)

```bash
# Python cache
find . -type d -name __pycache__ -not -path './.git/*' | xargs rm -rf
find . -name "*.pyc" -o -name "*.pyo" | xargs rm -f

# Test/debug artifacts
find . -name "*.log" -not -path './.git/*' | xargs rm -f
find . -name ".DS_Store" | xargs rm -f
find . -name "Thumbs.db" | xargs rm -f

# Jupyter/notebook artifacts
find . -name "*.ipynb_checkpoints" -type d | xargs rm -rf

# Temporary files
find . -name "*.tmp" -o -name "*.bak" -o -name "*.swp" | xargs rm -f
```

---

## Step 3 — Review and remove stale scripts

Open `scripts/` and check each file. Remove any that meet ALL of these:

- It was a one-time migration/setup script already run
- It has no `--help` flag or reusable logic
- It is not referenced in README or any other script

**Keep unconditionally:**

- `seed_production_data.py` — needed to bootstrap graph
- `verify_system.py` — useful for ops
- `e2e_pipeline.py` — useful for smoke testing

**Evaluate and remove if stale:**

- Any file named `test_*.py` inside `scripts/` (tests belong in `tests/`)
- Any file named `debug_*.py` or `scratch_*.py`
- Any `verify_ingest.py` if its functionality is covered by `verify_system.py`

---

## Step 4 — Clean up root directory

Root should contain only:

```
README.md
.env.example
.gitignore
docker-compose.yml
nebula-docker-compose.yml
Dockerfile
requirements.txt          (or pyproject.toml)
package.json              (frontend root if monorepo)
```

Move anything else:

- Extra `.md` files → `docs/`
- Extra shell scripts → `scripts/`
- Random config files → identify owner and move to correct module

---

## Step 5 — Enforce `.gitignore`

Replace `.gitignore` with this complete version:

```
# Python
__pycache__/
*.py[cod]
*.pyo
*.egg-info/
dist/
build/
.venv/
venv/
source/
*.egg

# Environment
.env
.env.local
.env.*.local

# Node
node_modules/
frontend/node_modules/
frontend/dist/
frontend/build/
.npm/

# Logs
*.log
logs/

# OS
.DS_Store
Thumbs.db

# IDE
.vscode/
.idea/
*.swp
*.swo

# Test artifacts
.pytest_cache/
.coverage
htmlcov/
coverage.xml

# Docker
*.override.yml

# Temp
*.tmp
*.bak
tmp/
scratch/
```

Run after updating:

```bash
git rm -r --cached .
git add .
```

This removes any previously tracked files that should now be ignored.

---

## Step 6 — Consolidate docs

Create a `docs/` folder at repo root if it doesn't exist.
Move into it (do not delete — just relocate):

- Any `.md` files in root other than `README.md`
- Any architecture diagrams
- Any old fix/patch documents

```
docs/
  architecture.md
  phase-evolution.md
  api-reference.md
```

---

## Step 7 — Verify repo structure looks like this when done

```
quantvex/
├── docs/
├── frontend/
│   ├── src/
│   ├── public/
│   ├── .env.example
│   └── package.json
├── mcp_server/
│   ├── invoke_handlers/
│   └── *.py
├── finance_mcp/
│   ├── reasoning/
│   ├── services/
│   └── *.py
├── connectors/
├── cache/
├── graph/
├── scripts/
├── tests/
├── infra/
├── .env.example
├── .gitignore
├── docker-compose.yml
├── nebula-docker-compose.yml
├── Dockerfile
├── requirements.txt
└── README.md
```

---

## Step 8 — Generate project summary for README

After cleanup is done, run:

```bash
# File count by module
echo "=== FILE COUNTS ===" && \
for d in mcp_server finance_mcp connectors cache graph frontend scripts tests; do
  echo "$d: $(find $d -type f 2>/dev/null | wc -l) files"
done

# Python line count
echo "=== PYTHON LOC ===" && \
find . -name "*.py" -not -path "*/node_modules/*" -not -path "*/source/*" \
  | xargs wc -l 2>/dev/null | tail -1

# TypeScript/TSX line count
echo "=== TYPESCRIPT LOC ===" && \
find frontend/src -name "*.ts" -o -name "*.tsx" \
  | xargs wc -l 2>/dev/null | tail -1

# Test count
echo "=== TEST COUNT ===" && \
grep -r "def test_" tests/ | wc -l

# List all exposed API endpoints
echo "=== API ENDPOINTS ===" && \
grep -n "@app\." mcp_server/server.py

# List all MCP tools
echo "=== MCP TOOLS ===" && \
python3 -c "import json; d=json.load(open('mcp_server/capabilities.json')); [print(' -',t['name']) for t in d['tools']]" 2>/dev/null

# Docker services
echo "=== DOCKER SERVICES ===" && \
grep "  [a-z].*:" docker-compose.yml | head -20
```

Copy the full output of this script. That is the raw material for the README generation prompt.

---

## Rules

- Do not delete any `.py` file inside `mcp_server/`, `finance_mcp/`, `connectors/`, `cache/`, `graph/`, `tests/` without reading it first
- Do not delete `requirements.txt` or `package.json`
- Do not touch `docker-compose.yml` or `nebula-docker-compose.yml`
- If unsure about a file — move it to `docs/` or `scripts/archive/`, never hard delete
