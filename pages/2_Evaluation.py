"""
Phase 2 (v2): adversarial reliability evaluation.

v1 scored 100% - because the cases were easy and the metric was loose (it only
checked whether the owner's NAME appeared in the source, not whether they were the
RIGHT owner). v2 fixes both:

1. Harder cases designed to induce hallucination: suggester-not-owner, negation
   ("X can't take this"), pronoun ambiguity, distractor names.
2. Tighter metric. Each case carries a `correct_owners` label - the set of owners a
   careful human would accept. An owner is now wrong if it's NOT in that set, even
   if the name appears in the text. This catches "confidently assigned the wrong
   person who was mentioned in passing."

The `correct_owners` labels are the human judgment you must own and defend.
Review every one. UNASSIGNED is always acceptable (the model declined to guess).
"""

import json
import streamlit as st
import anthropic

from prompt import SYSTEM_PROMPT, build_user_prompt
from schema import normalize

MODEL = "claude-sonnet-4-5"

# Each action's acceptable owners. Order matches how a human reads the actions.
# "UNASSIGNED" is auto-added as always-acceptable. REVIEW THESE.
TEST_SET = [
    {
        "id": "A01",  # suggester != owner
        "transcript": "Per Sarah's suggestion, the team will refresh the onboarding deck. Diego will book the review slot for Tuesday.",
        "correct_owners": [["team"], ["Diego"]],
        "note": "Sarah suggested; she is NOT the owner. Model often assigns Sarah.",
    },
    {
        "id": "A02",  # negation
        "transcript": "Tom said he can't take the migration this sprint. It still needs an owner. Meanwhile Nadia will update the risk log.",
        "correct_owners": [[], ["Nadia"]],
        "note": "Migration has no owner (Tom declined). Model may still assign Tom.",
    },
    {
        "id": "A03",  # pronoun ambiguity
        "transcript": "Priya and Lena reviewed the design. She will send the summary to stakeholders by Friday.",
        "correct_owners": [[]],
        "note": "'She' is ambiguous between two people. Correct = UNASSIGNED.",
    },
    {
        "id": "A04",  # distractor names, one real owner
        "transcript": "Great input from Carlos, Mei, and Raj in the workshop. Off the back of it, Mei will draft the process map by next week.",
        "correct_owners": [["Mei"]],
        "note": "Carlos and Raj are distractors. Only Mei owns something.",
    },
    {
        "id": "A05",  # role owner, legitimate
        "transcript": "We agreed marketing will own the launch campaign. Finance flagged budget concerns to revisit next month.",
        "correct_owners": [["marketing"]],
        "note": "'marketing' is a valid role owner. Finance 'flagged' - not an action owner.",
    },
    {
        "id": "A06",  # attributed quote, not ownership
        "transcript": "As Anil pointed out, the API docs are stale. Someone should refresh them before the partner demo.",
        "correct_owners": [[]],
        "note": "Anil pointed something out; he does not own the fix. Correct = UNASSIGNED.",
    },
    {
        "id": "A07",  # two actions, one owned one not
        "transcript": "Kavya will finalize the SLA doc by Thursday. The vendor comparison still needs doing - we'll figure out who later.",
        "correct_owners": [["Kavya"], []],
        "note": "SLA owned by Kavya; vendor comparison explicitly unassigned.",
    },
    {
        "id": "A08",  # name mentioned as absent
        "transcript": "Ravi is on leave next week. In his absence, the standup notes still need capturing. Sofia will chair the meeting.",
        "correct_owners": [[], ["Sofia"]],
        "note": "Ravi is absent - not an owner. Notes are unassigned. Sofia chairs.",
    },
    {
        "id": "A09",  # decision vs discussion + one owner
        "transcript": "We debated whether to sunset the legacy report. No decision yet. Leah will gather usage data to inform it.",
        "correct_owners": [["Leah"]],
        "note": "No decision reached (watch decision-precision). Leah owns the data pull.",
    },
    {
        "id": "A10",  # possessive misdirection
        "transcript": "The delay was mostly on Priyanka's team. To fix it, Arjun will set up a weekly sync starting Monday.",
        "correct_owners": [["Arjun"]],
        "note": "Priyanka is blamed, not assigned. Arjun owns the action.",
    },
    {
        "id": "A11",  # collective 'we', no individual
        "transcript": "We all agreed the intake form is too long. We'll trim it down before the next release.",
        "correct_owners": [[]],
        "note": "Collective 'we' with no named individual. Correct = UNASSIGNED.",
    },
    {
        "id": "A12",  # clean control (should be easy - sanity check)
        "transcript": "Meena will publish the roadmap Friday. Karan will notify the client afterwards.",
        "correct_owners": [["Meena"], ["Karan"]],
        "note": "Control case. Both clearly owned. Model should get this right.",
    },
]


def owner_ok(owner: str, acceptable: list) -> bool:
    """Tightened check: owner must be UNASSIGNED, or match an accepted owner
    for that action (case-insensitive first-token match). Being merely present
    in the transcript is NOT enough anymore."""
    o = owner.strip().lower()
    if o in ("", "unassigned", "none"):
        return True
    o_first = o.split()[0]
    for acc in acceptable:
        if o_first == acc.strip().lower().split()[0]:
            return True
    return False


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


st.set_page_config(page_title="Evaluation v2", page_icon=":bar_chart:", layout="wide")
st.title("Adversarial reliability evaluation (v2)")
st.write(
    "v1 scored 100% because the test was easy and the metric only checked whether the "
    "owner's **name appeared** in the source. v2 uses harder cases and a **tighter metric**: "
    "an owner is wrong if it's not an accepted owner for that action - even if the name is present."
)
st.caption("This is the point where real failures show up. Each miss is material for the guardrail.")

if st.button("Run adversarial evaluation", type="primary"):
    rows = []
    total_actions = 0
    wrong_owner = 0

    progress = st.progress(0.0)
    for i, case in enumerate(TEST_SET):
        try:
            out = run_one(case["transcript"])
        except Exception as e:
            st.error(f"{case['id']} failed: {e}")
            continue

        actions = out["action_items"]
        # Map each returned action's owner against the union of acceptable owners
        # for this transcript (positional matching is unreliable, so we accept if the
        # owner is valid for ANY action in the case; wrong = present nowhere in accepted set).
        accepted_union = [name for group in case["correct_owners"] for name in group]
        case_wrong = [a for a in actions if not owner_ok(a["owner"], accepted_union)]

        total_actions += len(actions)
        wrong_owner += len(case_wrong)

        rows.append({
            "ID": case["id"],
            "Actions": len(actions),
            "Wrong owner": len(case_wrong),
            "Owners returned": ", ".join(a["owner"] for a in actions) or "-",
            "Accepted": ", ".join(accepted_union) or "(all UNASSIGNED)",
            "Trap tested": case["note"],
        })
        progress.progress((i + 1) / len(TEST_SET))

    st.divider()
    st.subheader("Summary")
    rate = (wrong_owner / total_actions * 100) if total_actions else 0
    c1, c2 = st.columns(2)
    c1.metric("Total action items", total_actions)
    c2.metric("Wrong owners", f"{wrong_owner} ({rate:.0f}%)")

    if wrong_owner == 0:
        st.warning(
            "Still 0? Either the model is genuinely strong on ownership grounding (possible with "
            "current models), or the cases still aren't hard enough. Read the 'Owners returned' "
            "column against 'Accepted' by hand before you trust a clean score."
        )
    else:
        st.success(
            "Real failures found. These are your guardrail case. Note WHICH categories broke "
            "(suggester, negation, pronoun) - that's the interview detail."
        )

    st.subheader("Per-transcript")
    st.dataframe(rows, use_container_width=True, hide_index=True)
