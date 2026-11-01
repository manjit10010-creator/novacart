"""
Streamlit panel for the AI CEO briefing (CEO only).
All logic lives in ai_briefing.py; this file only draws the page.
"""

import os

import streamlit as st

from ai_briefing import (
    generate_briefing,
    get_api_key,
    get_saved_briefing,
    to_markdown,
)


def _load_key_from_streamlit_secrets():
    """Use .streamlit/secrets.toml (or Streamlit Cloud secrets) if present."""
    for name in ("GEMINI_API_KEY", "ANTHROPIC_API_KEY"):
        try:
            key = st.secrets.get(name)
        except Exception:
            key = None  # no secrets file: that is fine
        if key:
            os.environ.setdefault(name, key)


def render_ai_briefing(user):
    """Draw the briefing panel. Does nothing for roles other than CEO."""
    if user.get("role") != "CEO":
        return

    _load_key_from_streamlit_secrets()
    has_key = get_api_key() is not None

    st.divider()
    st.subheader("AI CEO Briefing")
    st.caption(
        "A short written summary of today's numbers. The figures come from the "
        "database; the AI only writes the wording, and every number is checked "
        "afterwards."
        + ("" if has_key else
           " No AI key is set, so a rule-based briefing is used (free).")
    )

    saved = get_saved_briefing()
    label = "Regenerate briefing" if saved else "Generate today's briefing"

    if st.button(label, key="ai_briefing_button"):
        try:
            with st.spinner("Writing briefing..."):
                saved = generate_briefing(user["role"], force=True)
        except PermissionError as error:
            st.error(str(error))
            return
        except Exception as error:
            st.error(f"Could not create the briefing: {error}")
            return

    if not saved:
        return

    st.markdown(to_markdown(saved["text"]))

    if saved["source"] == "ai":
        used = f"AI ({saved['model']})"
        tokens = ""
        if saved["input_tokens"] is not None and saved["output_tokens"] is not None:
            tokens = (f" · {saved['input_tokens']:,} tokens in, "
                      f"{saved['output_tokens']:,} out")
    else:
        used = "Rule-based (no AI used)"
        tokens = ""

    if saved["figures_verified"]:
        check_note = "all figures checked against the database"
    else:
        check_note = (
            "could not verify: " + ", ".join(saved["unverified"]) + " - treat with care"
        )

    st.caption(f"Day {saved['day']} · {used}{tokens} · {check_note}")

    if saved["error"]:
        st.warning(saved["error"])