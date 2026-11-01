"""
NOVA-AI-001: add the AI CEO briefing to the Business Simulation page.

Run ONCE from the project root (the folder containing sim_engine.py):

    python apply_ai_briefing.py

Before running, these two files must already be in place:
    ai_briefing.py
    views/ai_briefing_view.py

What it does:
  1. Checks both edit points exist exactly once. If not, NOTHING is
     written and your files stay untouched.
  2. Backs up views/game_view.py as game_view.py.bak_ai
  3. Adds the import and shows the briefing panel (CEO only) just above
     the "Simulation Controls" section.
Re-running is safe: it detects that the panel is already added.
"""

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VIEW = ROOT / "views" / "game_view.py"

for needed in (ROOT / "ai_briefing.py", ROOT / "views" / "ai_briefing_view.py"):
    if not needed.exists():
        print(f"STOPPED: {needed.relative_to(ROOT)} is missing. Create it first.")
        sys.exit(1)

text = VIEW.read_text(encoding="utf-8")

if "render_ai_briefing" in text:
    print("AI briefing already added. Nothing to do.")
    sys.exit(0)

IMPORT_OLD = "import plotly.express as px\n"
IMPORT_NEW = (
    "import plotly.express as px\n"
    "\n"
    "from views.ai_briefing_view import render_ai_briefing\n"
)

CALL_OLD = (
    "    # -------------------------------------------------\n"
    "    # CEO SIMULATION CONTROL\n"
)
CALL_NEW = (
    "    # -------------------------------------------------\n"
    "    # AI CEO BRIEFING (CEO only)\n"
    "    # -------------------------------------------------\n"
    "\n"
    "    render_ai_briefing(user)\n"
    "\n"
    "    # -------------------------------------------------\n"
    "    # CEO SIMULATION CONTROL\n"
)

problems = []
for name, old in (("import line", IMPORT_OLD), ("insert point", CALL_OLD)):
    found = text.count(old)
    if found != 1:
        problems.append(f"  - {name}: found {found} times, expected exactly 1")

if problems:
    print("STOPPED: views/game_view.py does not look as expected.")
    print("\n".join(problems))
    print("Nothing was changed.")
    sys.exit(1)

new_text = text.replace(IMPORT_OLD, IMPORT_NEW, 1).replace(CALL_OLD, CALL_NEW, 1)

shutil.copy(VIEW, str(VIEW) + ".bak_ai")
VIEW.write_text(new_text, encoding="utf-8")
print("Done. Backup: views/game_view.py.bak_ai")
print("Next: uv run python test_ai_briefing.py")