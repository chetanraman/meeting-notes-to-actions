"""
Meeting Notes -> PM Artifacts
v1 (polished): paste messy notes, get a decision log, action items, and a draft status update.

Logic is unchanged from v1. This pass only improves layout and adds a sample-notes
button so the demo reads as intentional. Reliability/eval work is Phase 2 (see README).
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

SAMPLE_NOTES = """Team synced on the launch. We agreed to ship the beta on March 10.
We decided to drop the analytics dashboard from v1 to hit the date.
Priya will write the release notes by Friday.
Someone needs to update the pricing page before launch.
Still unsure whether we support SSO at launch - needs a decision from security."""

# --- API key ---
# Read from Streamlit Secrets, NEVER hardcoded.
try:
    client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])
except Exception:
    st.error(
        "No API key found. Add ANTHROPIC_API_KEY in Streamlit Secrets "
        "(app settings -> Secrets). Do not put the key in the code."
    )
    st.stop()


def extract(notes: str) -> dict:
    resp = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_user_prompt(notes)}],
    )
    raw = resp.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return normalize(json.loads(raw))


# --- Page setup ---
st.set_page_config(page_title="Meeting Notes -> Actions", page_icon=":memo:", layout="centered")

# --- Sidebar: the "why" ---
with st.sidebar:
    st.header("About")
    st.write(
        "Turns messy meeting notes into three artifacts a program manager needs: "
        "a decision log, an action-item table, and a draft status update."
    )
    st.write(
        "**The point isn't generation - it's reliability.** Unnamed owners are marked "
        "`UNASSIGNED` rather than guessed, so the tool never invents accountability."
    )
    st.caption("Demo uses synthetic notes only. No real or confidential data.")

# --- Header ---
st.title("Meeting Notes -> PM Artifacts")
st.write("Paste raw notes or a transcript. Get a clean decision log, owned action items, and a status update.")

# --- Input ---
if "notes" not in st.session_state:
    st.session_state.notes = ""

col1, col2 = st.columns([1, 4])
with col1:
    if st.button("Load sample"):
        st.session_state.notes = SAMPLE_NOTES

notes = st.text_area(
    "Meeting notes",
    value=st.session_state.notes,
    height=240,
    placeholder="Paste messy notes here, or click 'Load sample'...",
)

go = st.button("Generate", type="primary")

# --- Run ---
if go:
    if not notes.strip():
        st.warning("Paste some notes first, or click 'Load sample'.")
        st.stop()

    with st.spinner("Reading notes..."):
        try:
            data = extract(notes)
        except json.JSONDecodeError:
            st.error("The model returned invalid JSON. Try again.")
            st.stop()
        except Exception as e:
            st.error(f"Something went wrong: {e}")
            st.stop()

    st.divider()

    left, right = st.columns(2)

    with left:
        st.subheader("Decisions")
        if data["decisions"]:
            for d in data["decisions"]:
                st.markdown(f"- {d}")
        else:
            st.caption("None found.")

    with right:
        st.subheader("Open questions")
        if data["open_questions"]:
            for q in data["open_questions"]:
                st.markdown(f"- {q}")
        else:
            st.caption("None found.")

    st.subheader("Action items")
    if data["action_items"]:
        st.dataframe(
            [
                {"Action": a["action"], "Owner": a["owner"], "Due": a["due"]}
                for a in data["action_items"]
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.caption("None found.")

    st.subheader("Draft status update")
    st.text_area("Copy-ready", value=data["status_update"], height=170, label_visibility="collapsed")
