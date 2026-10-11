# AGENTS.md — Guidance for AI & Autonomous Coding Assistants

Welcome, Agent! This document provides structured instructions, architectural invariants, code conventions, and testing practices for AI assistants (such as Claude Code, Cursor, Antigravity, GitHub Copilot Workspace, and LLM automation tools) working within the **TeslaMate Digest** codebase.

---

## 🧭 Project Purpose

**TeslaMate Digest** is an automated personal email digest service and web management UI that connects to an existing [TeslaMate](https://github.com/teslamate-org/teslamate) PostgreSQL database. It extracts raw vehicle telemetry, computes financial analytics (TOU electric charging costs, ICE gasoline comparisons), analyzes battery degradation, tracks TPMS tire pressures and rotations, highlights notable road trips, surfaces Home Assistant solar self-consumption, and delivers beautiful, mobile-responsive HTML emails.

---

## 📁 Repository Layout

```
├── app/
│   ├── analytics/              # Analytical calculation modules
│   │   ├── achievements.py     # 45+ milestone badges & unlocking logic
│   │   ├── battery_health.py   # 100% rated capacity degradation & fleet baselines
│   │   ├── charts.py           # Headless Matplotlib high-DPI chart generators (base64)
│   │   ├── insights.py         # Anomaly detection, tire warnings, vampire drain
│   │   ├── tpms.py             # 4-corner tire pressure calibration & balance logic
│   │   └── work_mileage.py     # Business commute route matching & IRS deductions
│   ├── services/
│   │   ├── geofences.py        # Location matching & Grafana dashboard auto-discovery
│   │   ├── homeassistant.py    # Home Assistant WebSocket / REST solar telemetry sync
│   │   └── gas_prices.py       # Live EIA / local gas price fallback API
│   ├── templates/              # Jinja2 templates
│   │   ├── digest.html         # Main monthly/weekly responsive HTML email template
│   │   ├── wrapped.html        # Annual "Year in Review" retrospective template
│   │   └── web/                # FastAPI web dashboard templates (preview, settings)
│   ├── static/                 # CSS/JS assets for the Web UI
│   ├── config.py               # Pydantic models (rates, SMTP, schedule, routes, geofences)
│   ├── db.py                   # Asyncpg PostgreSQL database connector (read-only queries)
│   ├── mailer.py               # SMTP dispatch engine with CRLF injection protections
│   ├── main.py                 # FastAPI application routes, web UI, auth middleware
│   ├── report.py               # Telemetry aggregation, MoM deltas, chart rendering
│   ├── scheduler.py            # APScheduler automated cron dispatch service
│   ├── storage.py              # SQLite storage layer (/app/data/teslamate_digest.db)
│   └── themes.py               # Built-in email theme color token palettes
├── docs/                       # Architecture diagrams and documentation
├── tests/                      # Automated hermetic pytest suite
├── Dockerfile                  # Multi-stage production build (non-root appuser:appgroup)
├── docker-compose.yml          # Standalone test/dev compose stack
├── docker-compose.addon.yml    # Drop-in addon snippet for existing TeslaMate deployments
├── pyproject.toml              # Project metadata & pytest configuration (pythonpath = ["."])
└── requirements.txt            # Runtime & test dependencies
```

---

## 🛡️ Critical Invariants & Guardrails

When modifying or adding code, you **must** preserve these invariants:

### 1. TeslaMate PostgreSQL is Strictly Read-Only
- **Rule**: Never run `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, or schema-altering queries against PostgreSQL.
- **Reason**: TeslaMate is an independent open-source service and the single source of truth for telemetry. Digest must never mutate TeslaMate tables.
- **Implementation**: All mutable application state (settings, maintenance logs, schedule overrides, work route configurations, geofences, dispatch history) is stored in SQLite via `app/storage.py`.

### 2. Hermetic, Non-Database Unit Tests
- **Rule**: All tests in `tests/` must pass completely without requiring a live PostgreSQL instance or network connection.
- **Reason**: Tests run in GitHub Actions CI where PostgreSQL is not running.
- **Pattern**:
  - Always mock database calls (`db.get_cars`, `db.fetch`, `db.fetchrow`) using `unittest.mock.AsyncMock` or `MagicMock`.
  - The test suite isolates storage through `tests/conftest.py`'s `isolate_test_data_dir` fixture using `tmp_path`.
  - In `app/main.py`, the `lifespan` handler respects existing `app.state.db` instances and does not overwrite mocks set by test cases.

### 3. Security & Least Privilege
- **SSRF Defense**: Whenever performing outbound HTTP/WebSocket requests based on user input (e.g. Home Assistant URL, Grafana URL), validate the URL using `is_safe_url()` in `app/storage.py`. Reject loopback/link-local/internal networks unless explicitly allowed.
- **Timing Attacks**: Verify passwords and tokens using `secrets.compare_digest()`.
- **CRLF Injection**: Any user-controlled text inserted into email headers or subjects must be stripped of `\r` and `\n` characters before passing to `smtplib`.
- **Non-Root Docker Execution**: The Docker container runs as unprivileged user `appuser:appgroup` (UID 1000). Files written to `/app/data` must respect restrictive umasks (`0o027`).

---

## 🧪 Testing Instructions for Agents

### Running the Test Suite
Always verify tests pass before concluding any work:
```bash
# Direct local run:
pytest -v

# Inside running local Docker container:
docker exec teslamate-digest pytest -v

# Clean container simulation (identical to GitHub Actions CI):
docker run --rm -v $(pwd):/repo -w /repo python:3.12-slim bash -c "
apt-get update && apt-get install -y --no-install-recommends libpq-dev gcc python3-dev > /dev/null 2>&1
pip install -r requirements.txt > /dev/null 2>&1
pytest -v
"
```

### Adding New Tests
- Place tests in `tests/test_<feature>.py`.
- Ensure async test methods are marked or use AnyIO/asyncio appropriately.
- If adding routes, test both HTTP status codes and error responses using FastAPI's `TestClient(app)`.

---

## 🎨 Email Template Design Rules

1. **Table-Based Layouts**: Email clients (especially Outlook and Gmail mobile) do not support modern CSS grid or flexbox in email bodies. All structural layouts in `digest.html` and `wrapped.html` must use HTML tables with inline styles.
2. **Inline Theming**: Color palettes are dynamically injected from `app/themes.py`. Always provide valid hex fallback colors alongside CSS variables.
3. **Responsive Queries**: Mobile adjustments must be placed in a `<style>` block with `@media only screen and (max-width: 600px)` while keeping critical styling inlined on elements.
4. **Embedded Base64 Images**: Charts generated by `app/analytics/charts.py` are embedded directly as base64 PNG data URIs (`data:image/png;base64,...`) to avoid external image hosting or broken remote image links.

---

## 📝 Commit & PR Conventions

- Follow **Conventional Commits**: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`.
- Ensure all 80+ existing tests pass.
- Update `README.md` and `feature-requests.md` if user-facing configuration, endpoints, or environment variables change.
