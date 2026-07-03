"""
Defensive shaping of the model's output.

Even with a good prompt, an LLM will occasionally drop a field or return a string
where you expected a list. This function guarantees the app always gets the shape
it expects, so the UI never crashes. This is a small but real example of the
"treat model output as untrusted" mindset that Phase 2 builds on.
"""


def normalize(data: dict) -> dict:
    if not isinstance(data, dict):
        data = {}

    decisions = data.get("decisions") or []
    if isinstance(decisions, str):
        decisions = [decisions]

    raw_items = data.get("action_items") or []
    action_items = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        action_items.append(
            {
                "action": str(item.get("action", "")).strip() or "(no description)",
                "owner": str(item.get("owner", "UNASSIGNED")).strip() or "UNASSIGNED",
                "due": str(item.get("due", "None")).strip() or "None",
            }
        )

    open_questions = data.get("open_questions") or []
    if isinstance(open_questions, str):
        open_questions = [open_questions]

    status_update = str(data.get("status_update", "")).strip()

    return {
        "decisions": [str(d).strip() for d in decisions if str(d).strip()],
        "action_items": action_items,
        "open_questions": [str(q).strip() for q in open_questions if str(q).strip()],
        "status_update": status_update,
    }
