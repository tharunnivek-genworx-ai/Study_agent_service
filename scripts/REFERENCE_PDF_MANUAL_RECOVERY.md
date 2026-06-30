# Reference PDF manual recovery

One-time cleanup when a topic node has **stacked active `reference_materials` rows** (ghost PDFs after delete/replace) or a **stuck `generation_runs` row** holding the per-node generation lock.

## Symptoms

- Deleting the visible reference PDF makes an older upload reappear.
- Generate/regenerate fails with "Could not acquire generation lock".
- UI pill/blue dot out of sync until a full page reload.

## Option A — UI-only (no DB access)

1. Open the reference PDF modal on the affected topic.
2. Delete PDFs one at a time until the pill shows **Add reference PDF** (several passes if rows were stacked).
3. If generation is blocked by a lock, wait a few minutes and retry, or use Option B/C.
4. Hard-refresh the browser (`Ctrl+Shift+R`) after cleanup.

## Option B — Automated script (recommended)

From `study_agent_service/` with Postgres reachable (Docker stack up or `database_hostname` in `.env` pointing at your DB).

**Prerequisites:** install deps once with `uv sync` (creates `study_agent_service/.venv`). If Docker Desktop is running, start the stack with `docker compose up -d postgres` and set `database_hostname=localhost` in `.env` for host-side scripts, or use **Option C** SQL via `docker compose exec postgres psql ...`.

```powershell
# Inspect only (no writes; omit --apply)
.\.venv\Scripts\python.exe scripts/cleanup_reference_materials_and_generation_runs.py --node-title "Calculus"

# Or with explicit node id
.\.venv\Scripts\python.exe scripts/cleanup_reference_materials_and_generation_runs.py --node-id <topic-node-uuid>

# Apply: keep newest PDF, soft-delete older stacked rows, cancel stuck study_material runs
.\.venv\Scripts\python.exe scripts/cleanup_reference_materials_and_generation_runs.py --node-id <topic-node-uuid> --apply

# Start with zero active reference PDFs (single remaining row also removed)
.\.venv\Scripts\python.exe scripts/cleanup_reference_materials_and_generation_runs.py --node-id <topic-node-uuid> --apply --delete-all-reference-materials
```

Then hard-refresh the mentor UI.

### What the script does

| Step | Action |
|------|--------|
| List | All active `referencematerials` where `nodeid = <node>` and `scope = 'node'` |
| List | `generationruns` where `resourceid = <node>`, `pipeline = 'study_material'`, status `running` or `failed` |
| Fix PDFs | Soft-delete all but the **newest** active row (or all with `--delete-all-reference-materials`) |
| Fix lock | Mark stuck runs `cancelled` so a new generate can acquire the advisory lock |

## Option C — Raw SQL

Replace `<node_id>` with the topic's UUID.

```sql
-- Inspect stacked rows
SELECT materialid, title, createdat, deletedat
FROM referencematerials
WHERE nodeid = '<node_id>' AND scope = 'node'
ORDER BY createdat DESC;

-- Soft-delete all active rows except the newest (run once per extra row, or use script)
UPDATE referencematerials
SET deletedat = NOW(), updatedat = NOW()
WHERE nodeid = '<node_id>'
  AND scope = 'node'
  AND deletedat IS NULL
  AND materialid NOT IN (
    SELECT materialid FROM referencematerials
    WHERE nodeid = '<node_id>' AND scope = 'node' AND deletedat IS NULL
    ORDER BY createdat DESC
    LIMIT 1
  );

-- Inspect stuck generation runs
SELECT runid, status, generationmode, createdat, errormessage
FROM generationruns
WHERE resourceid = '<node_id>' AND pipeline = 'study_material'
ORDER BY createdat DESC;

-- Cancel running/failed runs (or POST /generation-runs/{run_id}/cancel via API)
UPDATE generationruns
SET status = 'cancelled',
    errormessage = 'Cancelled manually',
    errortype = 'cancelled',
    completedat = NOW(),
    updatedat = NOW()
WHERE resourceid = '<node_id>'
  AND pipeline = 'study_material'
  AND status IN ('running', 'failed');
```

## API alternative for generation lock

If you know the `run_id`:

```http
POST /generation-runs/{run_id}/cancel
```

(study-agent-service, port 8001 by default)

## After cleanup

1. Hard-refresh the space detail page.
2. Confirm the reference pill matches DB (`GET .../reference-materials/nodes/{node_id}/latest` should return one row or 404).
3. Fresh generate from page 1 uses the current upload (or no PDF). Regenerate/Improve on an existing draft require the frozen source PDF to still exist — if it was removed, upload a new PDF or discard drafts and generate fresh.
