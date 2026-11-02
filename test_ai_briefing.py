"""
Test: AI CEO briefing (NOVA-AI-001).

Run from the project root:

    uv run python test_ai_briefing.py

SAFE: works on a temporary copy of company.db. It never calls a real AI;
it uses a fake "AI" function, so it is free and works offline.
"""

import json
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT))

import ai_briefing as ab  # noqa: E402

passed = failed = 0


def check(label, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
        print(f"  PASS  {label}")
    else:
        failed += 1
        print(f"  FAIL  {label}  {detail}")


def main():
    for name in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY",
                 "NOVACART_AI_PROVIDER", "NOVACART_AI_MODEL"):
        os.environ.pop(name, None)  # tests must never use a real key
    real_before = (PROJECT / "company.db").read_bytes()
    folder = Path(tempfile.mkdtemp())
    db = str(folder / "test.db")
    shutil.copy(PROJECT / "company.db", db)

    # A brand-new database is at Day 0. Make sure the copy has one real day.
    import sim_engine
    if not sim_engine.get_metrics_history(db):
        sim_engine.advance_day({"user_id": "USR-001", "role": "CEO"}, db_path=db)

    print("Facts")
    facts = ab.build_facts(db)
    check("facts have day, cash, latest day, stock",
          all(k in facts for k in ("day", "cash_balance", "latest_day", "stock")))
    c = sqlite3.connect(db)
    last = c.execute(
        "SELECT revenue, profit FROM simulation_daily_metrics ORDER BY day DESC LIMIT 1"
    ).fetchone()
    c.close()
    check("latest revenue matches database",
          abs(facts["latest_day"]["revenue"] - round(last[0], 2)) < 0.005)
    check("facts are JSON-serialisable", bool(json.dumps(facts)))

    print("\nFigure check")
    good = (f"Revenue was ${facts['latest_day']['revenue']:,.2f} "
            f"with {facts['latest_day']['orders']} orders.")
    check("real figures pass", ab.check_figures(good, facts) == [])
    check("rounded dollar figure passes",
          ab.check_figures(f"Revenue ${facts['latest_day']['revenue']:,.0f}.", facts) == [])
    bad = ab.check_figures("Revenue was $99,999.00 and margin 87.3%.", facts)
    check("invented figures are caught", "$99,999.00" in bad and "87.3%" in bad, str(bad))
    check("small words like '3 bullets' are ignored",
          ab.check_figures("Here are 3 points.", facts) == [])

    print("\nPermissions")
    for role in ("Marketing Manager", "Finance Manager", "Inventory Manager"):
        try:
            ab.generate_briefing(role, db_path=db)
            check(f"{role} blocked", False)
        except PermissionError:
            check(f"{role} blocked", True)

    print("\nNo API key -> rule-based briefing")
    result = ab.generate_briefing("CEO", db_path=db, force=True)
    check("source is rules", result["source"] == "rules")
    check("has headline and actions",
          "HEADLINE:" in result["text"] and "Recommended actions" in result["text"])
    check("rule-based text passes the figure check", result["figures_verified"],
          str(result["unverified"]))

    print("\nSaved briefings (no repeat AI calls)")
    calls = []

    def fake_ai(system, user):
        calls.append(1)
        data = json.loads(user.split("FACTS (JSON):\n", 1)[1])
        text = (f"HEADLINE: Day {data['day']} revenue was "
                f"${data['latest_day']['revenue']:,.2f}.\n\n"
                "What happened:\n- Sales continued.\n")
        return text, 900, 120

    first = ab.generate_briefing("CEO", db_path=db, llm=fake_ai, force=True)
    check("AI used when provided", first["source"] == "ai" and len(calls) == 1)
    check("tokens saved", first["input_tokens"] == 900 and first["output_tokens"] == 120)
    check("figures verified for honest AI text", first["figures_verified"])
    again = ab.generate_briefing("CEO", db_path=db, llm=fake_ai)
    check("second call reuses saved briefing",
          again["cached"] and len(calls) == 1)
    forced = ab.generate_briefing("CEO", db_path=db, llm=fake_ai, force=True)
    check("force=True writes a new one", len(calls) == 2 and not forced["cached"])

    print("\nHallucination is flagged, not hidden")

    def lying_ai(system, user):
        return "HEADLINE: Profit hit $1,234,567.00 today.", 10, 10

    liar = ab.generate_briefing("CEO", db_path=db, llm=lying_ai, force=True)
    check("invented number flagged",
          not liar["figures_verified"] and "$1,234,567.00" in liar["unverified"])

    print("\nAI failure -> graceful fallback")

    def broken_ai(system, user):
        raise RuntimeError("service down")

    fallback = ab.generate_briefing("CEO", db_path=db, llm=broken_ai, force=True)
    check("falls back to rules", fallback["source"] == "rules")
    check("error message kept", "service down" in (fallback["error"] or ""))

    print("\nChoosing the AI service")
    check("no keys -> None", ab.get_ai_config() is None and ab.get_api_key() is None)
    os.environ["ANTHROPIC_API_KEY"] = "a"
    check("only Anthropic key -> anthropic", ab.get_ai_config()["provider"] == "anthropic")
    os.environ["GEMINI_API_KEY"] = "g"
    cfg = ab.get_ai_config()
    check("both keys -> Gemini (free) first",
          cfg["provider"] == "gemini" and cfg["model"] == ab.GEMINI_DEFAULT_MODEL)
    os.environ["NOVACART_AI_PROVIDER"] = "anthropic"
    check("provider can be forced", ab.get_ai_config()["provider"] == "anthropic")
    os.environ["NOVACART_AI_PROVIDER"] = "gemini"
    os.environ["NOVACART_AI_MODEL"] = "my-model"
    check("model can be overridden", ab.get_ai_config()["model"] == "my-model")
    for name in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "NOVACART_AI_PROVIDER",
                 "NOVACART_AI_MODEL"):
        os.environ.pop(name, None)
    os.environ["GOOGLE_API_KEY"] = "g2"
    check("GOOGLE_API_KEY also works", ab.get_ai_config()["provider"] == "gemini")
    os.environ.pop("GOOGLE_API_KEY")

    print("\nGemini wiring (fake google.genai, no network)")
    import types as pytypes
    seen = {}

    class FakeModels:
        def generate_content(self, model, contents, config):
            seen.update(model=model, contents=contents, config=config)
            usage = pytypes.SimpleNamespace(prompt_token_count=321, candidates_token_count=45)
            return pytypes.SimpleNamespace(text=" HEADLINE: ok ", usage_metadata=usage)

    fake_genai = pytypes.ModuleType("google.genai")
    fake_genai.Client = lambda api_key: pytypes.SimpleNamespace(models=FakeModels())
    fake_types = pytypes.ModuleType("google.genai.types")
    fake_types.GenerateContentConfig = lambda **kw: kw
    fake_google = pytypes.ModuleType("google")
    fake_google.genai = fake_genai
    fake_genai.types = fake_types
    saved_modules = {k: sys.modules.get(k) for k in ("google", "google.genai", "google.genai.types")}
    sys.modules.update({"google": fake_google, "google.genai": fake_genai,
                        "google.genai.types": fake_types})
    try:
        out = ab.gemini_llm("k", "gemini-x")("SYS", "USER")
    finally:
        for k, v in saved_modules.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    check("text trimmed and tokens returned", out == ("HEADLINE: ok", 321, 45), str(out))
    check("system prompt and model passed on",
          seen["model"] == "gemini-x" and seen["contents"] == "USER"
          and seen["config"]["system_instruction"] == "SYS")

    print("\nMarkdown safety")
    md = ab.to_markdown("HEADLINE: Sales $100 and $200.\n\nWatch out:\n- x")
    check("dollar signs escaped", "\\$100" in md and "\\$200" in md)
    check("headline and section styled", md.startswith("### ") and "**Watch out**" in md)

    print("\nReal database untouched")
    check("company.db is byte-for-byte unchanged",
          (PROJECT / "company.db").read_bytes() == real_before)

    print(f"\nRESULT: {passed} passed, {failed} failed")
    shutil.rmtree(folder, ignore_errors=True)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()