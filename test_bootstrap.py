"""
Test: first-start data builder (NOVA-DEMO-001).

Run from the project root:

    uv run python test_bootstrap.py

SAFE: works only in temporary folders. Builds a small copy of the project
and runs the real setup_demo.py there (takes about 10 seconds).
"""

import shutil
import sys
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT))

import bootstrap  # noqa: E402

passed = failed = 0


def check(label, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
        print(f"  PASS  {label}")
    else:
        failed += 1
        print(f"  FAIL  {label}  {detail}")


def copy_code(dst):
    dst.mkdir()
    for path in PROJECT.glob("*.py"):
        shutil.copy(path, dst / path.name)
    shutil.copytree(PROJECT / "views", dst / "views",
                    ignore=shutil.ignore_patterns("__pycache__"))


def main():
    folder = Path(tempfile.mkdtemp())

    print("Status checks")
    empty = folder / "empty"
    empty.mkdir()
    check("empty folder -> empty", bootstrap.data_status(empty)[0] == "empty")
    (empty / "orders.csv").write_text("x")
    status, missing = bootstrap.data_status(empty)
    check("one file -> partial", status == "partial" and "company.db" in missing)

    print("\nPartial data is never touched")
    result = bootstrap.build_if_empty(empty)
    check("reports partial", result == "partial")
    check("file unchanged", (empty / "orders.csv").read_text() == "x"
          and not (empty / "company.db").exists())

    print("\nBuilds everything on a fresh copy")
    fresh = folder / "fresh"
    copy_code(fresh)
    check("fresh copy has no data", bootstrap.data_status(fresh)[0] == "empty")
    result = bootstrap.build_if_empty(fresh)
    check("reports built", result == "built", result)
    check("all required files exist", bootstrap.data_status(fresh)[0] == "ready")

    print("\nSecond start does nothing")
    stamp = (fresh / "company.db").stat().st_mtime
    check("reports ready", bootstrap.build_if_empty(fresh) == "ready")
    check("database not rewritten", (fresh / "company.db").stat().st_mtime == stamp)

    print(f"\nRESULT: {passed} passed, {failed} failed")
    shutil.rmtree(folder, ignore_errors=True)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()