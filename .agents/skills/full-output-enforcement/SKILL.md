---
name: full-output-enforcement
description: Ensures complete, production-ready code when the user explicitly requests a whole file or exhaustive implementation.
---

# Full Output Enforcement

- Never replace required code with `...`, TODOs, pseudo-code or “rest unchanged”.
- When the task requires a full file, provide the complete file.
- Preserve unrelated existing behavior while making the requested change.
- If output must be split because of length, split at safe file boundaries and clearly identify each complete part.
- Do not claim code is complete when required sections are omitted.
