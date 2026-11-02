"""
Add the CEO-only "Demo tools" (Reset simulation) panel to the
Business Simulation page.

Run ONCE from the project root, after apply_ai_briefing.py:

    python apply_demo_tools.py

Needs demo_tools.py and views/demo_tools_view.py to exist.
Checks both edit points first; if either is wrong NOTHING is written.
Backs up views/game_view.py as game_view.py.bak_demo. Safe to re-run.
"""

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VIEW = ROOT / "views" / "game_view.py"

for needed in (ROOT / "demo_tools.py", ROOT / "views" / "demo_tools_view.py"):
    if not needed.exists():
        print(f"STOPPED: {needed.relative_to(ROOT)} is missing. Create it first.")
        sys.exit(1)

text = VIEW.read_text(encoding="utf-8")

if "render_demo_tools" in text:
    print("Demo tools already added. Nothing to do.")
    sys.exit(0)

IMPORT_OLD = "from views.ai_briefing_view import render_ai_briefing\n"
IMPORT_NEW = IMPORT_OLD + "from views.demo_tools_view import render_demo_tools\n"
CALL_OLD = "    render_ai_briefing(user)\n"
CALL_NEW = CALL_OLD + "    render_demo_tools(user)\n"

problems = []
for name, old in (("import line", IMPORT_OLD), ("call line", CALL_OLD)):
    found = text.count(old)
    if found != 1:
        problems.append(f"  - {name}: found {found} times, expected exactly 1")

if problems:
    print("STOPPED: views/game_view.py does not look as expected.")
    print("(Did you run apply_ai_briefing.py first?)")
    print("\n".join(problems))
    print("Nothing was changed.")
    sys.exit(1)

new_text = text.replace(IMPORT_OLD, IMPORT_NEW, 1).replace(CALL_OLD, CALL_NEW, 1)

shutil.copy(VIEW, str(VIEW) + ".bak_demo")
VIEW.write_text(new_text, encoding="utf-8")
print("Done. Backup: views/game_view.py.bak_demo")