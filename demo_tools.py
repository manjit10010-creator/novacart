"""
Demo tools: reset the business simulation back to Day 0 (CEO only).

Does NOT import Streamlit. The employees table and the Phase 1 CSV data
are not touched. Only simulation_* tables and saved AI briefings are reset.
A full backup of company.db is made first.
"""

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from sim_engine import DB_PATH, initialize_simulation

RESET_ROLE = "CEO"


def reset_simulation(role, db_path=None):
    """Back up the database, wipe simulation progress, rebuild at Day 0.

    Returns the path of the backup file.
    """
    if role != RESET_ROLE:
        raise PermissionError("Only the CEO can reset the simulation.")

    path = Path(db_path or DB_PATH)
    backup = path.with_name(
        f"{path.stem}_backup_before_reset_{datetime.now():%Y%m%d_%H%M%S}.db"
    )
    shutil.copy(path, backup)

    connection = sqlite3.connect(str(path), timeout=15)
    try:
        connection.execute("PRAGMA foreign_keys = OFF")
        names = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND (name LIKE 'simulation\\_%' ESCAPE '\\' OR name = 'ai_briefings')"
            )
        ]
        for name in names:
            connection.execute(f'DROP TABLE IF EXISTS "{name}"')
        connection.commit()
    finally:
        connection.close()

    initialize_simulation(db_path)
    return str(backup)