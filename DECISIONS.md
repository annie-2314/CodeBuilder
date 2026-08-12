# DECISIONS.md — Why these choices?

Engineering decisions for **CodeBuilder** (multi-agent coding assistant).

This file documents the main technical choices, why they were made, and the trade-offs considered — so reviewers can see *intent*, not only *implementation*.

---

## Choice 1: LangGraph multi-agent pipeline (Planner → Architect → Coder)

### What we chose
A **LangGraph** state machine with three specialized agents, where the **Coder** node loops until all implementation tasks are complete.

### Why
- Matches a real engineering workflow: plan → design tasks → implement files.
- Clear separation of responsibilities improves prompt quality and debuggability.
- Conditional edges make the coder loop explicit (`DONE` vs continue), which fits multi-file generation.
- Aligns with the reference [Coder Buddy](https://github.com/codebasics/coder-buddy) architecture while remaining easy to extend.

### Trade-offs considered
| Option | Pros | Cons |
| --- | --- | --- |
| **Single LLM call that dumps all files** | Simpler, cheaper | Weak structure; poor multi-file consistency |
| **CrewAI roles** | Nice abstractions | Heavier dependency surface; less explicit control flow for this graph |
| **LangGraph (chosen)** | Explicit graph, good tooling, fits ReAct coder | More boilerplate; recursion limits need tuning |

---

## Choice 2: Groq Cloud LLMs (GPT-OSS / Qwen) instead of paid OpenAI-only APIs

### What we chose
Run agents on **Groq** with selectable models:

- `openai/gpt-oss-120b` (default)
- `qwen/qwen3.6-27b`
- `openai/gpt-oss-20b` (faster / cheaper)

All model IDs and keys come from **environment variables** (no hard-coded secrets).

### Why
- Fast inference for multi-step agent loops (planner + architect + N coder turns).
- Free / low-cost access for demos and student projects.
- Model dropdown makes experiments easy without code changes.
- Original Kimi K2 / Qwen3-32B IDs were unavailable on the active Groq account, so we migrated to currently listed models.

### Trade-offs considered
| Option | Pros | Cons |
| --- | --- | --- |
| **OpenAI GPT-4.x / Claude** | Often stronger coding quality | Cost; key gatekeeping for demos |
| **Local Ollama** | Free offline | Slower; weaker tool-calling on smaller models |
| **Groq (chosen)** | Speed + cost + easy API | Model catalog can change; rate limits on free tier |

---

## Choice 3: FastAPI + React (and Streamlit) for user experience

### What we chose
- **FastAPI** as the shared backend for generation jobs, file serving, live preview, and ZIP download.
- **React (Vite)** as the primary interactive UI.
- **Streamlit** as a fast Python-native alternative UI.
- **CLI** for scripting / debugging.

### Why
- Assignment called for a way to **download or run locally**; live preview + ZIP covers both.
- React gives a polished “product” demo (status stream, tabs, iframe preview).
- Streamlit keeps a one-command Python path for demos/teaching.
- Isolated folders `generated_projects/<slug>_<timestamp>_<id>/` prevent run collisions and keep downloads clean.

### Trade-offs considered
| Option | Pros | Cons |
| --- | --- | --- |
| **CLI only** | Minimal surface | Hard to demo live testing/download |
| **Streamlit only** | Fast to build | Weaker SPA UX; preview depends on API for iframe |
| **React only** | Best UX | Needs Node + API always running |
| **React + Streamlit + FastAPI (chosen)** | Covers demos, teaching, and product feel | More moving parts to run/document |

---

## Summary

| Decision | Primary reason |
| --- | --- |
| LangGraph agents | Explicit multi-agent coding workflow |
| Groq models | Speed + affordable demos; env-based config |
| FastAPI + React (+ Streamlit) | Live preview, zip download, and flexible demos |

If product priorities change (e.g. strongest code quality over cost), the first swap would be the **default LLM provider/model**; the graph and UI can stay the same.
