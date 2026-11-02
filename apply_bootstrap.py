"""
Make app.py build the demo data on first start (needed for hosting).

Run ONCE from the project root:

    python apply_bootstrap.py

Needs bootstrap.py and setup_demo.py in the same folder.
Checks both edit points first; if either is wrong NOTHING is written.
Backs up app.py as app.py.bak_boot. Safe to re-run.
"""

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = ROOT / "app.py"

for needed in ("bootstrap.py", "setup_demo.py"):
    if not (ROOT / needed).exists():
        print(f"STOPPED: {needed} is missing. Create it first.")
        sys.exit(1)

text = APP.read_text(encoding="utf-8")

if "build_if_empty" in text:
    print("Bootstrap already added. Nothing to do.")
    sys.exit(0)

IMPORT_OLD = "from audit import log_event\n"
IMPORT_NEW = "from audit import log_event\nfrom bootstrap import build_if_empty\n"

CALL_OLD = "user = require_login()  # shows the login screen and stops until signed in\n"
CALL_NEW = '''

@st.cache_resource(show_spinner="First start: building the demo data (about 10 seconds)...")
def prepare_data():
    return build_if_empty()


_data_status = prepare_data()
if _data_status == "partial":
    st.error(
        "Some data files are missing. Run `uv run python setup_demo.py --force` "
        "to rebuild everything (old files are moved to a backup folder)."
    )
    st.stop()
if _data_status == "failed":
    st.error("The demo data could not be built. Check the app logs.")
    st.stop()

''' + CALL_OLD

problems = []
for name, old in (("import line", IMPORT_OLD), ("login line", CALL_OLD)):
    found = text.count(old)
    if found != 1:
        problems.append(f"  - {name}: found {found} times, expected exactly 1")

if problems:
    print("STOPPED: app.py does not look as expected.")
    print("\n".join(problems))
    print("Nothing was changed.")
    sys.exit(1)

new_text = text.replace(IMPORT_OLD, IMPORT_NEW, 1).replace(CALL_OLD, CALL_NEW, 1)

shutil.copy(APP, str(APP) + ".bak_boot")
APP.write_text(new_text, encoding="utf-8")
print("Done. Backup: app.py.bak_boot")