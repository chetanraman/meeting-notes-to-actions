"""
Phase 2: measured reliability.

Runs the extractor over a fixed set of synthetic transcripts and scores the ONE
failure mode that can be checked deterministically: owner hallucination.

Method (and its honest limits):
- Owner hallucination = the model returned an owner whose name does not appear in
  the source transcript. This is checkable in code, no manual labels needed.
- "UNASSIGNED" is always correct (the model declined to guess).
- Semantic correctness of decisions/questions is NOT auto-graded here, because
  grading free text with another LLM introduces its own errors. Those are flagged
  for human review instead. That boundary is a deliberate design choice.

The only human-owned labels are the `trap` flags: transcripts that contain an
action with NO named owner, where the correct behavior is UNASSIGNED. Review them.
"""

import json
import streamlit as st
import anthropic

from prompt import SYSTEM_PROMPT, build_user_prompt
from schema import normalize

MODEL = "claude-sonnet-4-5"

# --- Test set -------------------------------------------------------------
# Synthetic. No real company/data. Each item:
#   id, transcript, roster (names that legitimately appear), trap (bool: contains
#   an unnamed-owner action where UNASSIGNED is the correct output).
# REVIEW THESE: the `trap` flag is your judgment call and drives one metric.
TEST_SET = [
    {
        "id": "T01",
        "transcript": "Standup. We agreed to cut the CSV export from v1. Maria will update the roadmap by Thursday. Devs raised that the staging DB is flaky.",
        "trap": False,
    },
    {
        "id": "T02",
        "transcript": "Planning sync. We decided to move launch to April 2. Someone needs to draft the customer email before then. Raj will book the go-live review.",
        "trap": True,
    },
    {
        "id": "T03",
        "transcript": "Retro. The team felt QA was rushed. We agreed to add a hardening sprint. Priya owns writing the test plan by next Monday.",
        "trap": False,
    },
    {
        "id": "T04",
        "transcript": "Vendor call. We discussed pricing tiers but did not settle on one. The pricing page still needs updating. Follow up with finance next week.",
        "trap": True,
    },
    {
        "id": "T05",
        "transcript": "Kickoff. We agreed on a two-week discovery phase. Sam will set up the shared drive. Lena will schedule stakeholder interviews by Friday.",
        "trap": False,
    },
    {
        "id": "T06",
        "transcript": "Incident review. Root cause was a bad config push. We decided to add a staging gate. Ops will write the runbook. Nobody yet owns the alerting fix.",
        "trap": True,
    },
    {
        "id": "T07",
        "transcript": "Roadmap review. We agreed to deprioritize the mobile app for this quarter. Chen will communicate the change to sales by Wednesday.",
        "trap": False,
    },
    {
        "id": "T08",
        "transcript": "Design sync. We debated dark mode vs accessibility work. No decision reached. The team should revisit after user testing. Ana will compile the test results.",
        "trap": True,
    },
    {
        "id": "T09",
        "transcript": "Budget meeting. We approved the extra contractor headcount. Finance will process the request. Marcus will update the resourcing sheet by month end.",
        "trap": False,
    },
    {
        "id": "T10",
        "transcript": "Sprint review. Demo went well. We decided to ship on schedule. The release notes still need writing before Friday. Deepa will run the deploy.",
        "trap": True,
    },
    {
        "id": "T11",
        "transcript": "Sync on onboarding. We agreed to a three-email welcome sequence. Tom will draft copy. Nina will set up the automation by next sprint.",
        "trap": False,
    },
    {
        "id": "T12",
        "transcript": "Ops review. Backlog is growing. We discussed hiring but decided to wait a quarter. Someone should audit the ticket categories. Omar will report metrics weekly.",
        "trap": True,
    },
]


def owner_in_source(owner: str, transcript: str) -> bool:
    """Is this owner grounded in the transcript text? First-name match, case-insensitive."""
    o = owner.strip().lower()
    if o in ("", "unassigned", "none"):
        return True  # declining to guess is always valid
    first = o.split()[0]
    return first in transcript.lower()


try:
    client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])
except Exception:
    st.error("No API key found. Add ANTHROPIC_API_KEY in Streamlit Secrets.")
    st.stop()


def run_one(transcript: str) -> dict:
    resp = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_user_prompt(transcript)}],
    )
    raw = resp.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return normalize(json.loads(raw))


st.set_page_config(page_title="Evaluation", page_icon=":bar_chart:", layout="wide")
st.title("Reliability evaluation")
st.write(
    "Runs the extractor over 12 synthetic transcripts and measures **owner hallucination** — "
    "the failure mode that matters most in a PM tool: inventing accountability that was never assigned."
)
st.caption(
    "Auto-scored: owner grounded in source text? Human-reviewed: decision correctness. "
    "This boundary is deliberate — auto-grading free text with another LLM adds its own error."
)

if st.button("Run evaluation", type="primary"):
    rows = []
    total_actions = 0
    hallucinated = 0
    traps_total = 0
    traps_passed = 0

    progress = st.progress(0.0)
    for i, case in enumerate(TEST_SET):
        try:
            out = run_one(case["transcript"])
        except Exception as e:
            st.error(f"{case['id']} failed: {e}")
            continue

        case_actions = out["action_items"]
        case_hallucinated = [
            a for a in case_actions if not owner_in_source(a["owner"], case["transcript"])
        ]
        total_actions += len(case_actions)
        hallucinated += len(case_hallucinated)

        # Trap check: transcript has an unnamed-owner action -> expect >=1 UNASSIGNED
        trap_pass = None
        if case["trap"]:
            traps_total += 1
            got_unassigned = any(a["owner"].upper() == "UNASSIGNED" for a in case_actions)
            trap_pass = got_unassigned
            if got_unassigned:
                traps_passed += 1

        rows.append(
            {
                "ID": case["id"],
                "Actions": len(case_actions),
                "Hallucinated owners": len(case_hallucinated),
                "Trap": "yes" if case["trap"] else "-",
                "Trap handled": ("pass" if trap_pass else "FAIL") if case["trap"] else "-",
                "Owners returned": ", ".join(a["owner"] for a in case_actions) or "-",
            }
        )
        progress.progress((i + 1) / len(TEST_SET))

    st.divider()
    st.subheader("Summary")
    c1, c2, c3 = st.columns(3)
    hall_rate = (hallucinated / total_actions * 100) if total_actions else 0
    trap_rate = (traps_passed / traps_total * 100) if traps_total else 0
    c1.metric("Total action items", total_actions)
    c2.metric("Hallucinated owners", f"{hallucinated} ({hall_rate:.0f}%)")
    c3.metric("Traps handled correctly", f"{traps_passed}/{traps_total} ({trap_rate:.0f}%)")

    st.subheader("Per-transcript")
    st.dataframe(rows, use_container_width=True, hide_index=True)

    st.info(
        "Read the numbers, then decide on a guardrail. A hallucination rate above ~0 or any "
        "failed trap is your case for adding a verification step. Rerun after the fix to show before/after."
    )
