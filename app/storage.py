import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

def _secure_file_perms(path: Path, mode: int = 0o600) -> None:
    """Enforces restrictive permissions on sensitive configuration and database files."""
    try:
        if path.exists():
            os.chmod(path, mode)
    except (PermissionError, OSError):
        pass


DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data"))
try:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _secure_file_perms(DATA_DIR, 0o750)
except (PermissionError, OSError):
    DATA_DIR = Path(__file__).resolve().parent.parent / "data"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _secure_file_perms(DATA_DIR, 0o750)

SQLITE_DB_PATH = DATA_DIR / "teslamate_digest.db"
LEGACY_CONFIG_FILE = DATA_DIR / "config.json"
LEGACY_MAINTENANCE_FILE = DATA_DIR / "maintenance.json"


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(SQLITE_DB_PATH), timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn


def init_storage() -> None:
    """Initializes SQLite database tables and migrates existing JSON files if needed."""
    try:
        with get_db_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS maintenance_records (
                    car_id TEXT PRIMARY KEY,
                    last_tire_rotation_odometer REAL DEFAULT 0,
                    last_tire_rotation_date TEXT DEFAULT '',
                    active_tire_set TEXT DEFAULT 'all_season',
                    last_tire_swap_date TEXT DEFAULT '',
                    notes TEXT DEFAULT '',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS dispatch_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    schedule_id TEXT,
                    schedule_name TEXT,
                    frequency TEXT,
                    target_car_id INTEGER,
                    target_car_name TEXT,
                    recipient TEXT,
                    theme TEXT,
                    status TEXT NOT NULL,
                    details TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()

            # Check if migration needed for config
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM app_settings WHERE key = 'config' LIMIT 1;")
            if not cursor.fetchone() and LEGACY_CONFIG_FILE.exists():
                try:
                    with open(LEGACY_CONFIG_FILE, "r") as f:
                        raw_cfg = f.read().strip()
                    if raw_cfg:
                        json.loads(raw_cfg)  # validate
                        conn.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES ('config', ?);", (raw_cfg,))
                        conn.commit()
                        print("[Storage] Successfully migrated legacy config.json into SQLite.")
                except Exception as e:
                    print(f"[Storage] Warning: Failed migrating config.json: {e}")

            # Check if migration needed for maintenance
            cursor.execute("SELECT 1 FROM maintenance_records LIMIT 1;")
            if not cursor.fetchone() and LEGACY_MAINTENANCE_FILE.exists():
                try:
                    with open(LEGACY_MAINTENANCE_FILE, "r") as f:
                        m_data = json.load(f)
                    if isinstance(m_data, dict):
                        for cid_str, m_vals in m_data.items():
                            if isinstance(m_vals, dict):
                                conn.execute("""
                                    INSERT OR REPLACE INTO maintenance_records 
                                    (car_id, last_tire_rotation_odometer, last_tire_rotation_date, active_tire_set, last_tire_swap_date, notes)
                                    VALUES (?, ?, ?, ?, ?, ?);
                                """, (
                                    str(cid_str),
                                    float(m_vals.get("last_tire_rotation_odometer", 0) or 0),
                                    str(m_vals.get("last_tire_rotation_date", "") or ""),
                                    str(m_vals.get("active_tire_set", "all_season") or "all_season"),
                                    str(m_vals.get("last_tire_swap_date", "") or ""),
                                    str(m_vals.get("notes", "") or "")
                                ))
                        conn.commit()
                        print("[Storage] Successfully migrated legacy maintenance.json into SQLite.")
                except Exception as e:
                    print(f"[Storage] Warning: Failed migrating maintenance.json: {e}")
        
        # Enforce secure file permissions
        _secure_file_perms(SQLITE_DB_PATH, 0o600)
        _secure_file_perms(LEGACY_CONFIG_FILE, 0o600)
        _secure_file_perms(LEGACY_MAINTENANCE_FILE, 0o600)
    except Exception as e:
        print(f"[Storage] Error initializing SQLite database: {e}")


def load_config_data() -> Optional[Dict[str, Any]]:
    """Loads application configuration dictionary from SQLite."""
    init_storage()
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM app_settings WHERE key = 'config' LIMIT 1;")
            row = cursor.fetchone()
            if row and row["value"]:
                return json.loads(row["value"])
    except Exception as e:
        print(f"[Storage] Error loading config from SQLite: {e}")

    # Fallback to legacy file if DB read failed
    if LEGACY_CONFIG_FILE.exists():
        try:
            with open(LEGACY_CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return None


def save_config_data(data: Dict[str, Any]) -> None:
    """Saves application configuration dictionary to SQLite and keeps legacy file in sync."""
    init_storage()
    val_json = json.dumps(data, indent=2)
    try:
        with get_db_connection() as conn:
            conn.execute("INSERT OR REPLACE INTO app_settings (key, value, updated_at) VALUES ('config', ?, CURRENT_TIMESTAMP);", (val_json,))
            conn.commit()
        _secure_file_perms(SQLITE_DB_PATH, 0o600)
    except Exception as e:
        print(f"[Storage] Error saving config to SQLite: {e}")

    # Keep file backup in sync for external inspectability
    try:
        with open(LEGACY_CONFIG_FILE, "w") as f:
            f.write(val_json)
        _secure_file_perms(LEGACY_CONFIG_FILE, 0o600)
    except Exception as e:
        print(f"[Storage] Error writing backup config.json: {e}")


def load_maintenance_data() -> Dict[str, Any]:
    """Loads maintenance records from SQLite as a dictionary keyed by car_id."""
    init_storage()
    records: Dict[str, Any] = {}
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT car_id, last_tire_rotation_odometer, last_tire_rotation_date, 
                       active_tire_set, last_tire_swap_date, notes 
                FROM maintenance_records;
            """)
            for row in cursor.fetchall():
                records[str(row["car_id"])] = {
                    "last_tire_rotation_odometer": float(row["last_tire_rotation_odometer"] or 0),
                    "last_tire_rotation_date": str(row["last_tire_rotation_date"] or ""),
                    "active_tire_set": str(row["active_tire_set"] or "all_season"),
                    "last_tire_swap_date": str(row["last_tire_swap_date"] or ""),
                    "notes": str(row["notes"] or "")
                }
    except Exception as e:
        print(f"[Storage] Error loading maintenance from SQLite: {e}")

    # Fallback to legacy JSON if DB is empty but file exists
    if not records and LEGACY_MAINTENANCE_FILE.exists():
        try:
            with open(LEGACY_MAINTENANCE_FILE, "r") as f:
                records = json.load(f)
        except Exception:
            pass

    return records


def save_maintenance_data(data: Dict[str, Any]) -> None:
    """Saves entire maintenance dictionary into SQLite and keeps legacy file in sync."""
    init_storage()
    try:
        with get_db_connection() as conn:
            for cid_str, m_vals in data.items():
                if isinstance(m_vals, dict):
                    conn.execute("""
                        INSERT OR REPLACE INTO maintenance_records 
                        (car_id, last_tire_rotation_odometer, last_tire_rotation_date, active_tire_set, last_tire_swap_date, notes, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP);
                    """, (
                        str(cid_str),
                        float(m_vals.get("last_tire_rotation_odometer", 0) or 0),
                        str(m_vals.get("last_tire_rotation_date", "") or ""),
                        str(m_vals.get("active_tire_set", "all_season") or "all_season"),
                        str(m_vals.get("last_tire_swap_date", "") or ""),
                        str(m_vals.get("notes", "") or "")
                    ))
            conn.commit()
    except Exception as e:
        print(f"[Storage] Error saving maintenance to SQLite: {e}")

    # Keep file backup in sync
    try:
        with open(LEGACY_MAINTENANCE_FILE, "w") as f:
            json.dump(data, f, indent=2)
        _secure_file_perms(LEGACY_MAINTENANCE_FILE, 0o600)
    except Exception as e:
        print(f"[Storage] Error writing backup maintenance.json: {e}")


def reset_maintenance_rotation(car_id: str) -> None:
    """Clears/resets the tire rotation record for a specific vehicle."""
    init_storage()
    try:
        with get_db_connection() as conn:
            conn.execute("""
                UPDATE maintenance_records 
                SET last_tire_rotation_odometer = 0, last_tire_rotation_date = '', updated_at = CURRENT_TIMESTAMP
                WHERE car_id = ?;
            """, (str(car_id),))
            conn.commit()
    except Exception as e:
        print(f"[Storage] Error resetting maintenance rotation in SQLite: {e}")

    # Update legacy file
    current = load_maintenance_data()
    if str(car_id) in current:
        current[str(car_id)]["last_tire_rotation_odometer"] = 0
        current[str(car_id)]["last_tire_rotation_date"] = ""
        try:
            with open(LEGACY_MAINTENANCE_FILE, "w") as f:
                json.dump(current, f, indent=2)
            _secure_file_perms(LEGACY_MAINTENANCE_FILE, 0o600)
        except Exception:
            pass


def record_dispatch_history(
    status: str,
    details: str,
    timestamp: Optional[str] = None,
    schedule_id: Optional[str] = None,
    schedule_name: Optional[str] = None,
    frequency: Optional[str] = None,
    target_car_id: Optional[int] = None,
    target_car_name: Optional[str] = None,
    recipient: Optional[str] = None,
    theme: Optional[str] = None
) -> None:
    """Records an automated or manual schedule dispatch event in SQLite."""
    init_storage()
    ts = timestamp or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with get_db_connection() as conn:
            conn.execute("""
                INSERT INTO dispatch_history (
                    timestamp, schedule_id, schedule_name, frequency,
                    target_car_id, target_car_name, recipient, theme,
                    status, details
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                ts, schedule_id, schedule_name, frequency,
                target_car_id, target_car_name, recipient, theme,
                status, details
            ))
            # Also update latest dispatch snapshot in app_settings
            last_run_dict = {
                "timestamp": ts,
                "status": status,
                "details": details,
                "schedule_name": schedule_name or "Scheduled Digest",
                "target_car": target_car_name or (f"Car #{target_car_id}" if target_car_id else "Fleet"),
                "recipient": recipient or "",
                "theme": theme or ""
            }
            conn.execute("""
                INSERT OR REPLACE INTO app_settings (key, value, updated_at)
                VALUES ('last_dispatch', ?, CURRENT_TIMESTAMP);
            """, (json.dumps(last_run_dict),))
            conn.commit()
    except Exception as e:
        print(f"[Storage] Error recording dispatch history: {e}")


def get_last_dispatch() -> Optional[Dict[str, Any]]:
    """Retrieves the most recent dispatch event status, persisting across container restarts."""
    init_storage()
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM app_settings WHERE key = 'last_dispatch' LIMIT 1;")
            row = cursor.fetchone()
            if row and row["value"]:
                return json.loads(row["value"])

            # Fallback to latest entry in dispatch_history table
            cursor.execute("""
                SELECT timestamp, schedule_name, frequency, target_car_id, target_car_name, recipient, theme, status, details
                FROM dispatch_history
                ORDER BY id DESC LIMIT 1;
            """)
            d_row = cursor.fetchone()
            if d_row:
                return {
                    "timestamp": d_row["timestamp"],
                    "status": d_row["status"],
                    "details": d_row["details"],
                    "schedule_name": d_row["schedule_name"] or "Scheduled Digest",
                    "target_car": d_row["target_car_name"] or (f"Car #{d_row['target_car_id']}" if d_row["target_car_id"] else "Fleet"),
                    "recipient": d_row["recipient"] or "",
                    "theme": d_row["theme"] or ""
                }
    except Exception as e:
        print(f"[Storage] Error getting last dispatch: {e}")
    return None


def get_recent_dispatches(limit: int = 5) -> List[Dict[str, Any]]:
    """Retrieves a list of recent dispatch history events from SQLite."""
    init_storage()
    results = []
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, timestamp, schedule_name, frequency, target_car_id, target_car_name, recipient, theme, status, details
                FROM dispatch_history
                ORDER BY id DESC LIMIT ?;
            """, (limit,))
            for r in cursor.fetchall():
                results.append({
                    "id": r["id"],
                    "timestamp": r["timestamp"],
                    "schedule_name": r["schedule_name"] or "Manual Run",
                    "frequency": r["frequency"] or "",
                    "target_car": r["target_car_name"] or (f"Car #{r['target_car_id']}" if r["target_car_id"] else "Fleet"),
                    "recipient": r["recipient"] or "",
                    "theme": r["theme"] or "",
                    "status": r["status"],
                    "details": r["details"]
                })
    except Exception as e:
        print(f"[Storage] Error getting recent dispatches: {e}")
    return results
