# ⚡ TeslaMate Digest

[![Python](https://img.shields.io/badge/python-3.12-blue?style=flat-square)](https://www.python.org/)
[![Docker Ready](https://img.shields.io/badge/docker-ready-2496ED?style=flat-square)](https://www.docker.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

A modern, self-hosted Python web application and automated email digest service built on top of your [TeslaMate](https://github.com/teslamate-org/teslamate) telemetry data.

Delivering financial charging clarity, battery health tracking, maintenance monitoring, and celebratory annual retrospectives directly to your inbox.

---

## 📸 Preview

![TeslaMate Digest Preview](docs/screenshots/preview.png)

---

## ✨ Features

- **⚡ Charging & Electric Spend Breakdown**: Detailed financial accounting of home charging across Time-of-Use (TOU) tiers (Off-Peak vs. Shoulder vs. On-Peak), Superchargers, and net savings vs. gasoline.
- **🔋 Battery Health & Degradation**: 100% rated range tracking, BMS capacity degradation curves over time, and individual vehicle baselines for multi-car fleets.
- **🛠️ Telemetry & Maintenance**: Visual 4-corner TPMS tire pressure monitoring with color-coded balance alerts, dynamic tire rotation progress bar, and firmware update logs.
- **📍 Driving Highlights & Places**: Tracks your longest road trips, most-visited destinations, mountain elevation gain, and regenerative braking energy recapture.
- **🌙 Phantom / Standby Loss**: Monitors parked sleep efficiency, vampire drain kWh, and idle costs.
- **🏆 Gamification & Year in Review**: 45+ unlockable driving and charging milestone badges plus a celebratory Spotify-style **Year in Review (Wrapped)** retrospective.
- **☀️ Solar & Home Assistant Sync**: Connect with Home Assistant to track solar charging coverage and self-consumption.
- **💻 Interactive Web Dashboard & Previewer**: Clean browser UI on port `8660` with desktop and mobile email simulators, color themes, and one-click test sends.

---

## 🎨 Tesla Paint Themes & Customization

Match your email digest to your garage! TeslaMate Digest includes **12 built-in themes** styled after Tesla's factory paint finishes and design aesthetics:

| Theme | Inspiration / Style | Color Palette & Accents |
| :--- | :--- | :--- |
| **Pearl White** | Multi-Coat White | Crisp light canvas, slate cards, razor-sharp Tesla red accents |
| **Obsidian Black** | Metallic Black | Deep stealth dark mode, graphite layers, emerald & crimson accents |
| **Stealth Gray** | Gunmetal Gray | Dark titanium finish, cold gray tones, vibrant status badges |
| **Ultra Red** | Deep Multi-Coat Candy | High-vividness candy luster, crimson highlights, dark contrast |
| **Quicksilver** | Liquid Metal | Dynamic metallic silver, high-gloss chrome borders, modern typography |
| **Marine Blue** | Deep Blue Metallic | Deep oceanic navy, electric sapphire & cyan accents |
| **Frost Blue** | Glacier Metallic | Light metallic ice blue, silver tones, cool arctic card styling |
| **Midnight Cherry** | European Giga Berlin Paint | Deep European cherry burgundy, rose gold & warm accents |
| **Cybertruck** | Cold-Rolled Stainless | Raw angular aesthetic (0px border-radius), cyber-monospace styling |
| **Cybercab** | Autonomous Robotaxi | Metallic champagne gold, rich bronze, and futuristic dark accents |
| **Eco-Green** | Clean Energy & Sustainability | Natural forest greens, evergreen cards, clean solar styling |
| **Dark Modern** | Minimalist Dark Slate | Ultra-clean dark theme with high-contrast data visualization |

### 🛠️ Create Your Own Themes & Templates

Want a completely personalized look or tailored layout?
- **Interactive Template Builder**: Navigate to `http://<your-server-ip>:8660/builder` to visually customize email layouts. Pick any factory theme as a starter, reorder modules, tweak CSS styling tokens, and preview changes live.
- **Custom Template Files**: Drop your custom Jinja2 templates into `./custom_templates` (mounted to `/app/custom_templates`). The service automatically detects them and makes them selectable in your delivery schedules.
- **Full Telemetry Context**: Custom templates have full access to all aggregated telemetry, including per-drive stats, Home Assistant solar metrics, battery health baselines, and Matplotlib chart objects.

---

## 📋 Requirements

### Core Requirements (Mandatory)
- **[TeslaMate](https://github.com/teslamate-org/teslamate)** (v1.27+ or v4.x+): A running TeslaMate instance with its PostgreSQL database. TeslaMate Digest **hard depends on TeslaMate** and directly reads vehicle status, telemetry, charging sessions, drives, positions, and battery states from TeslaMate's database (`DATABASE_HOST`, `DATABASE_PORT`, `DATABASE_USER`, `DATABASE_PASS`, `DATABASE_NAME`).
- **PostgreSQL Connectivity**: Direct TCP network access from TeslaMate Digest to your TeslaMate PostgreSQL database (either co-located in the same Docker Compose stack, connected via an internal Docker network such as `teslamate_default`, or through an exposed host port).
- **Docker & Docker Compose**: Recommended for quick containerized deployment (or Python 3.12+ for bare-metal deployments).

### Optional Requirements & Integrations
- **[TeslaMate Achievements](https://github.com/crstian19/teslamate-achievements) Dashboard**:
  - TeslaMate Digest natively evaluates and calculates 45+ driving milestone badges, unlock percentages, and category points directly from your TeslaMate database.
  - Installing the optional **TeslaMate Achievements** Grafana dashboard provides an interactive web "Trophy Room", and TeslaMate Digest automatically deep-links to it in your email reports and web dashboard via `grafana_achievements_url`.
- **[Grafana](https://grafana.com/)** (included with TeslaMate): Enables one-click deep links in your email digest cards directly to your TeslaMate Grafana dashboards (Drives, Charging Stats, Efficiency, Battery Health, Vampire Drain, etc.).
- **[Home Assistant](https://www.home-assistant.io/)**: (Optional) Ingests live solar generation, grid export, and home battery storage telemetry to track solar self-consumption during home charging sessions.
- **SMTP Account**: For automated scheduled email dispatch (e.g., Gmail with [App Passwords](https://myaccount.google.com/apppasswords), SendGrid, Mailgun, Postmark, AWS SES, or any standard SMTP relay). The web dashboard, live previewer, and template builder operate fully without SMTP configured.

---

## 🚀 Installation & Usage

### Option 1: Add to Existing TeslaMate `docker-compose.yml` (Recommended)

If you already manage TeslaMate with Docker Compose, add the `teslamate-digest` service directly into your existing `docker-compose.yml`:

```yaml
services:
  teslamate-digest:
    container_name: teslamate-digest
    image: ghcr.io/brombomb/teslamate-digest:latest
    restart: unless-stopped
    ports:
      - "8660:8660"
    environment:
      - TZ=America/Denver
      - DATABASE_HOST=database          # Name of your TeslaMate postgres service in docker-compose
      - DATABASE_PORT=5432
      - DATABASE_USER=teslamate
      - DATABASE_PASS=your_postgres_password
      - DATABASE_NAME=teslamate
      - GRAFANA_URL=http://grafana:3000 # Your internal or external Grafana URL
      - DATA_DIR=/app/data
    volumes:
      - ./addons/teslamate-digest/data:/app/data
      - ./addons/teslamate-digest/custom_templates:/app/custom_templates
    depends_on:
      - database
```

Start the service:
```bash
docker compose up -d teslamate-digest
```

### Option 2: Standalone Compose (External Network)

If you prefer to run TeslaMate Digest from its own directory or cloned repository, attach it to your existing TeslaMate Docker network (typically `teslamate_default`):

```yaml
services:
  teslamate-digest:
    container_name: teslamate-digest
    image: ghcr.io/brombomb/teslamate-digest:latest
    restart: unless-stopped
    ports:
      - "8660:8660"
    environment:
      - TZ=America/Denver
      - DATABASE_HOST=teslamate-db      # Hostname or container name of your TeslaMate postgres database
      - DATABASE_PORT=5432
      - DATABASE_USER=teslamate
      - DATABASE_PASS=your_postgres_password
      - DATABASE_NAME=teslamate
      - GRAFANA_URL=http://grafana:3000
      - DATA_DIR=/app/data
    volumes:
      - ./data:/app/data
      - ./custom_templates:/app/custom_templates
    networks:
      - teslamate_default

networks:
  teslamate_default:
    external: true
```

### Option 3: Docker CLI

```bash
docker run -d \
  --name=teslamate-digest \
  --network=teslamate_default \
  -p 8660:8660 \
  -e TZ=America/Denver \
  -e DATABASE_HOST=teslamate-db \
  -e DATABASE_PORT=5432 \
  -e DATABASE_USER=teslamate \
  -e DATABASE_PASS=your_postgres_password \
  -e DATABASE_NAME=teslamate \
  -e GRAFANA_URL=http://grafana:3000 \
  -e DATA_DIR=/app/data \
  -v /path/to/data:/app/data \
  --restart unless-stopped \
  ghcr.io/brombomb/teslamate-digest:latest
```

---

## 🏆 Optional Installation: TeslaMate Achievements Dashboard

TeslaMate Digest natively calculates and displays 45+ unlockable driving badges and milestone achievements directly from your telemetry data. 

To enable the interactive **Trophy Room &rarr;** links in your emails and dashboard, you can optionally provision the [TeslaMate Achievements](https://github.com/crstian19/teslamate-achievements) Grafana dashboard:

1. **Clone the Achievements Repository**:
   In your TeslaMate stack directory (e.g., `/data/docker/teslamate` or `~/teslamate`):
   ```bash
   git clone https://github.com/crstian19/teslamate-achievements.git addons/teslamate-achievements
   ```

2. **Mount Dashboard Provisioning into Grafana**:
   In your TeslaMate `docker-compose.yml`, mount the provisioning YAML and dashboards directory into the `grafana` service:
   ```yaml
   services:
     grafana:
       image: teslamate/grafana:latest
       # ...
       volumes:
         - teslamate-grafana-data:/var/lib/grafana
         - ./addons/teslamate-achievements/dashboard.yml:/etc/grafana/provisioning/dashboards/achievements.yml:ro
         - ./addons/teslamate-achievements/dashboards:/TeslaMateAchievements:ro
   ```

3. **Restart Grafana**:
   ```bash
   docker compose up -d grafana
   ```

4. **Verify in TeslaMate Digest**:
   - Open the web dashboard at `http://<your-server-ip>:8660`.
   - Navigate to **Settings $\rightarrow$ Integrations $\rightarrow$ Service URLs & Dashboards**.
   - The default UID (`c6020bdb-a2c7-4b1c-ab2c-fd34ab836c6e/achievements`) matches the provisioned dashboard automatically.
   - *(Optional)* Supply a Grafana API / Service Account token and click **Scan / Discover Dashboards** to auto-detect all installed dashboard UIDs.

---

## ⚙️ Parameters

### Ports

| Port | Description |
| :--- | :--- |
| `8660` | Web UI, Live Previewer, and Settings Dashboard |

### Environment Variables

| Variable | Default | Description |
| :--- | :--- | :--- |
| `DATABASE_HOST` | `database` | Hostname or IP of your TeslaMate PostgreSQL database |
| `DATABASE_PORT` | `5432` | Port of your PostgreSQL database |
| `DATABASE_USER` | `teslamate` | TeslaMate database username |
| `DATABASE_PASS` | `your_postgres_password` | TeslaMate database password |
| `DATABASE_NAME` | `teslamate` | Database name |
| `TZ` | `UTC` | Timezone for reports and schedules (e.g. `America/Denver`, `Europe/London`) |
| `PORT` | `8660` | Application web port inside container |
| `GRAFANA_URL` | `http://grafana:3000` | Optional Grafana URL for deep-linking in emails (drives, charging stats, trophy room) |
| `DATA_DIR` | `/app/data` | Internal persistent storage directory |
| `WEB_AUTH_USERNAME` | *(Optional)* | HTTP Basic Auth username for web dashboard access |
| `WEB_AUTH_PASSWORD` | *(Optional)* | HTTP Basic Auth password for web dashboard access |

### Volume Mappings

| Volume | Description |
| :--- | :--- |
| `/app/data` | Persistent storage for settings, maintenance records, and dispatch history |
| `/app/custom_templates` | *(Optional)* Directory to mount custom Jinja2 email templates |

---

## 🏁 Getting Started

1. **Access the Dashboard**: Open `http://<your-server-ip>:8660` in your web browser.
2. **Configure Delivery**:
   - Go to **Settings $\rightarrow$ Delivery**.
   - Enter your SMTP credentials (e.g., Gmail with a 16-character [Google App Password](https://myaccount.google.com/apppasswords)) and your recipient email.
   - Click **Send Test Email** to verify your inbox receives the digest.
3. **Configure Electricity Rates & Integrations**:
   - In **Settings $\rightarrow$ Integrations**, select your utility tariff (Time-of-Use or Tiered/Flat rates) and your local ZIP code for automatic gas price comparisons.
   - *(Optional)* Connect your Home Assistant instance to track solar production and grid flow.
   - *(Optional)* Verify your Grafana URL and dashboard paths (such as the Achievements Trophy Room).
4. **Schedule & Enjoy**:
   - Choose your preferred frequency (Monthly, Semi-Monthly, Weekly, or Daily) and theme.
   - Click **Live Preview** anytime to view your generated reports across desktop and mobile simulator modes!

---

## 🔒 Security

- **Non-Root Execution**: Runs as an unprivileged user (`appuser`, UID `1000`, GID `1000`) with restrictive `0600` file permissions.
- **Zero-Exposure Credentials**: Passwords and access tokens are never reflected back in plaintext and are preserved securely across saves.
- **Optional Native Auth**: Protect your dashboard with `WEB_AUTH_USERNAME` and `WEB_AUTH_PASSWORD` without requiring an upstream reverse proxy.

---

## 🤝 Contributing

Contributions of all kinds are welcome! Whether you are fixing a bug, adding a new analytical metric, building email themes, or contributing with the help of an AI assistant, check out our [Contributing Guide](CONTRIBUTING.md) (AI allowed) and [Agent Guidelines](AGENTS.md).

---

## 📄 License

This project is open-source under the [MIT License](LICENSE).

