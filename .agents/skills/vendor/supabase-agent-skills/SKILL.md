---
name: supabase-agent-skills
description: Supabase official agent guidance for Database, Auth, SSR, RLS, migrations, security and debugging.
---

# Supabase Agent Skills

Source: https://github.com/supabase/agent-skills

Use this skill for ANY Manager 90 task involving Supabase. The source currently includes `supabase` and `supabase-postgres-best-practices` skills.

## Manager 90 rules
- Verify current Supabase behavior against current documentation/changelog before implementation.
- Verify database/auth changes with a real test query or equivalent verification.
- Never expose service-role/secret keys to browser code.
- Treat RLS and authorization as security boundaries; do not rely on authenticated role alone for ownership.
- Keep migrations and schema changes reproducible.
- When debugging Supabase errors, inspect current docs and relevant logs instead of repeatedly retrying the same guess.
