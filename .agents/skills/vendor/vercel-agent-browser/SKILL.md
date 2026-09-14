---
name: vercel-agent-browser
description: Browser automation guidance from Vercel Labs agent-browser for Manager 90 visual QA and web interaction workflows.
---

# Vercel agent-browser

Source: https://github.com/vercel-labs/agent-browser

Use this skill when browser automation, screenshots, DOM inspection, clicking, typing, scrolling, or end-to-end UI verification is required.

## Manager 90 use
- Prefer browser-based verification over assumptions about visual quality when a browser automation runtime is available.
- Inspect the rendered page, not only source code.
- Capture screenshots at desktop and mobile breakpoints.
- Verify navigation, forms, states, responsive behavior, and console/runtime failures.
- Do not claim a visual check was completed unless an actual browser/screenshot result was obtained.

## Important limitation
This repository is a browser automation CLI, not itself a ChatGPT browser connector. Installing this project in Manager 90 does not automatically grant the ChatGPT session browser control.
