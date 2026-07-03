"""
Meeting Notes -> PM Artifacts
v1: paste messy notes, get a decision log, action items, and a draft status update.

This is the whole app. It does one thing: one LLM call, structured output, clean render.
Reliability/eval work comes in Phase 2 (see README).
"""

import json
import streamlit as st
import anthropic

from prompt import SYSTEM_PROMPT, build_user_prompt
from schema import normalize

# --- Model ---
# If you ever get a "model not found" error, this one line is the thing to change.
# Current model names: https://docs.claude.com/en/docs/about-claude/models
MODEL = "claude-sonnet-4-5"

# --- API key ---
# The key is read from Streamlit Secrets, NEVER hardcoded here.
# In Streamlit Cloud: app settings -> Secrets -> add:  ANTHROPIC_API_KEY = "sk-ant-..."
try:
    client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])
except Exception:
    st.error(
        "No API key found. Add ANTHROPIC_API_KEY in Streamlit Secrets "
        "(app settings -> Secrets). Do not put the key in the code."
    )
    st.stop()


def extract(notes: str) -> dict:
    """Send notes to the model, get back structured JSON."""
    resp = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_user_prompt(notes)}],
    )
    raw = resp.content[0].text.strip()

    # The model is told to return JSON only, but strip fences just in case.
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return normalize(json.loads(raw))


# --- UI ---
st.set_page_config(page_title="Meeting Notes -> Actions", page_icon="📝")
st.title("Meeting Notes → PM Artifacts")
st.caption(
    "Paste raw meeting notes or a transcript. Get a decision log, action items, "
    "and a draft status update. Use only synthetic / fake notes in the public demo."
)

notes = st.text_area("Meeting notes", height=260, placeholder="Paste messy notes here...")

if st.button("Generate", type="primary"):
    if not notes.strip():
        st.warning("Paste some notes first.")
        st.stop()

    with st.spinner("Reading notes..."):
        try:
            data = extract(notes)
        except json.JSONDecodeError:
            st.error("The model returned something that wasn't valid JSON. Try again.")
            st.stop()
        except Exception as e:
            st.error(f"Something went wrong: {e}")
            st.stop()

    # 1. Decisions
    st.subheader("Decision log")
    if data["decisions"]:
        for d in data["decisions"]:
            st.markdown(f"- {d}")
    else:
        st.markdown("_No clear decisions found._")

    # 2. Action items
    st.subheader("Action items")
    if data["action_items"]:
        st.table(
            [
                {
                    "Action": a["action"],
                    "Owner": a["owner"],
                    "Due": a["due"],
                }
                for a in data["action_items"]
            ]
        )
    else:
        st.markdown("_No action items found._")

    # 3. Open questions
    if data["open_questions"]:
        st.subheader("Open questions")
        for q in data["open_questions"]:
            st.markdown(f"- {q}")

    # 4. Draft status update
    st.subheader("Draft status update")
    st.text_area("Copy-ready", value=data["status_update"], height=180)
