# Meeting Notes → PM Artifacts

Paste messy meeting notes or a raw transcript. Get back three clean artifacts a program manager actually needs: a **decision log**, an **action-item table** (owner + due date), and a **draft status update**.

**[Live demo](ADD_YOUR_STREAMLIT_URL_HERE)**

---

## Why I built this

Turning a messy meeting into owned actions and a clean status update is one of the most repetitive parts of program management. It's also a good test case for a real question I wanted to answer for myself: *where do LLMs actually break when you put them inside a real workflow, and how do you make them trustworthy enough to use?*

The generation part is easy — any model can draft a status update. The interesting part is reliability. Early on, the model would confidently assign action items to people who were never named in the notes, and occasionally record a "decision" that was only a topic of discussion. In a PM context, a confidently wrong owner is worse than no owner.

So the design treats model output as untrusted by default: the prompt is constrained to only extract what's present, unnamed owners are forced to `UNASSIGNED` rather than guessed, and a normalization layer guarantees the app never breaks on a malformed response. The next phase (below) measures the failure rate directly.

The takeaway I care about: **using an LLM in a workflow is an accuracy-and-guardrails problem, not a prompting problem.**

## What it does (v1)

- One constrained LLM call → structured JSON (decisions, action items, open questions, status update)
- Owners default to `UNASSIGNED` and dates to `None` when not stated — no guessing
- Defensive normalization so malformed output never crashes the UI
- Thin Streamlit UI, deployable to a public URL

## How it works

```
notes → prompt.py (constrained extraction prompt)
      → Claude API (single call, JSON out)
      → schema.py (normalize / harden the output)
      → app.py (render 3 artifacts)
```

Files:
- `app.py` — Streamlit UI + the API call
- `prompt.py` — the extraction prompt (the actual product logic)
- `schema.py` — output hardening
- `requirements.txt`, `.gitignore`

## Roadmap

- **v1 (done)** — working extraction, structured output, public demo
- **Phase 2 — measured reliability** — a small labeled set of synthetic transcripts with known-correct answers, run against the model to measure extraction accuracy and catch hallucinated owners/decisions; add a human-in-the-loop verification step for low-confidence items
- **Phase 3 (optional)** — push action items into a real task tracker via MCP

## Run it yourself

1. `pip install -r requirements.txt`
2. Add your Anthropic API key to `.streamlit/secrets.toml`:
   ```toml
   ANTHROPIC_API_KEY = "sk-ant-..."
   ```
3. `streamlit run app.py`

> Note: the public demo uses only synthetic meeting notes. No real or confidential data.

## Troubleshooting

- **"model not found"** → update `MODEL` in `app.py`; current names are at https://docs.claude.com/en/docs/about-claude/models
- **"No API key found"** → the key must be in Streamlit Secrets (app settings → Secrets), not in the code
