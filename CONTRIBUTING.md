# Contributing to TeslaMate Digest

Thank you for your interest in contributing to **TeslaMate Digest**! We welcome and appreciate contributions of all kinds: bug fixes, new analytics modules, custom email themes, documentation improvements, and feature proposals.

---

## 🤖 AI & LLM Contributions Welcome ("AI Allowed")

**We explicitly and enthusiastically welcome contributions assisted or authored by Artificial Intelligence.**

Whether you are using Claude, Cursor, GitHub Copilot, OpenAI ChatGPT, Google Gemini, Antigravity, or any other agentic AI coding tool:
- **No Disclaimers Needed**: You do not need to hide or apologize for using AI tools.
- **Quality Over Origin**: We care about the quality, safety, readability, and effectiveness of your code, not whether a human or an LLM typed the keystrokes.
- **Your Responsibility**: As the human submitter, you are ultimately responsible for the changes you submit:
  1. Ensure you understand the code you are submitting.
  2. Verify all existing tests pass (`pytest -v`) and add tests for any new behavior or fixes.
  3. Ensure no security regressions, regressions in non-privileged container security, or credentials are introduced.
  4. Follow the architecture guidelines detailed below and in [`AGENTS.md`](AGENTS.md).

---

## 🛠️ Development Setup

TeslaMate Digest runs on **Python 3.12+** and is designed to run in Docker alongside an existing [TeslaMate](https://github.com/teslamate-org/teslamate) deployment.

### Local Python Environment

1. Clone the repository:
   ```bash
   git clone https://github.com/brombomb/teslamate-digest.git
   cd teslamate-digest
   ```

2. Create and activate a Python virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. Configure local environment variables:
   ```bash
   cp .env.example .env
   # Edit .env with your database credentials and settings
   ```

5. Run the development server:
   ```bash
   python -m uvicorn app.main:app --host 0.0.0.0 --port 8660 --reload
   ```

### Docker Compose Workflow

You can also run locally using Docker Compose:
```bash
docker compose up -d --build
```
Access the web dashboard and previewer at `http://localhost:8660`.

---

## 🧪 Testing

We require all pull requests to pass our automated test suite. Tests are hermetic and run cleanly without requiring an active PostgreSQL database.

### Running Pytest Locally
```bash
pytest -v
```

### Running Pytest inside the Docker Container
```bash
docker exec teslamate-digest pytest -v
```

### Writing Tests
- All test files reside in the `tests/` directory and follow the `test_*.py` naming convention.
- If adding a new telemetry calculation, chart generator, or API endpoint, add unit tests covering expected behavior, edge cases (e.g. empty database, zero drives), and boundary conditions.
- Test fixtures in `tests/conftest.py` automatically isolate the data directory so tests never touch user configuration or production databases.

---

## 📐 Architecture & Standards

### 1. Read-Only TeslaMate Database
The TeslaMate PostgreSQL database is **strictly read-only**. Never execute `INSERT`, `UPDATE`, or `DELETE` queries against TeslaMate tables. All application state (custom settings, tire maintenance logs, work commute tags, dispatch history) is stored in the local SQLite database (`/app/data/teslamate_digest.db`).

### 2. Security First
- **SSRF Prevention**: All user-provided external URLs (Home Assistant instance, Grafana dashboards) must pass validation through `is_safe_url()` before outgoing requests are initiated.
- **Timing-Safe Auth**: Basic authentication verifies credentials using `secrets.compare_digest()`.
- **CRLF Sanitization**: User-provided strings used in email subjects and SMTP headers must be sanitized against header injection attacks.
- **Least Privilege**: The Docker container drops privileges and executes as an unprivileged user (`appuser`, UID 1000).

### 3. Email Template Integrity
- Email templates live in `app/templates/digest.html` and `app/templates/wrapped.html`.
- Templates must be responsive and cross-client compatible (tested against Gmail, Apple Mail, and Outlook).
- Use table-based structures with inline styles and graceful fallback colors for dark/light themes.
- Generated charts are rendered headlessly via Matplotlib and embedded as self-contained base64 PNGs.

---

## 🚀 Pull Request Guidelines

1. **Create a Feature Branch**:
   ```bash
   git checkout -b feat/your-feature-name
   ```
2. **Follow Conventional Commits**:
   - `feat: add tire rotation alert email banner`
   - `fix: resolve time-of-use calculation boundary on daylight saving time`
   - `docs: update docker compose guide`
3. **Ensure Code Quality & Tests Pass**:
   Run `pytest -v` before submitting.
4. **Open a Pull Request**:
   Provide a concise description of the changes, any screenshots for UI or email template modifications, and reference relevant issues.

Thank you for helping make TeslaMate Digest even better! 🚀
