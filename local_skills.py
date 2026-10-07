SKILLS_VERSION = "free-local-1"

LOCAL_SKILLS = {
    "frontend-design": {
        "description": "Distinctive, intentional visual design for interfaces.",
        "instructions": """Ground the design in the subject matter and audience.
Make deliberate choices for palette, typography, layout, interaction, and hierarchy rather than generic SaaS defaults.
Plan first: give a compact token system for color, type, layout, and design principles.
Keep typography readable, sentence-case, with line lengths under about 80 characters.
Use motion sparingly and purposefully; respect keyboard focus, accessibility, responsiveness, and reduced motion.
Use content and visual structure as information, not decoration. Critique the result against the brief before finalizing."""
    },
    "mcp-builder": {
        "description": "Build high-quality Model Context Protocol servers and tools.",
        "instructions": """Start with workflow and API research before implementation.
Design narrow, discoverable tools with clear names, descriptions, schemas, and actionable errors.
Use Pydantic or Zod for input validation, structured outputs where useful, async I/O, pagination, and explicit read/destructive/idempotent/open-world annotations.
Keep implementation modular, avoid duplicated code, and include syntax/build tests plus realistic read-only evaluations."""
    },
    "pdf": {
        "description": "Read, extract, transform, merge, split, and create PDF files.",
        "instructions": """For PDF reading and extraction, prefer pypdf for basic operations and pdfplumber for layout/tables; use PyMuPDF when appropriate.
For creation, use ReportLab or another suitable PDF library and verify page count, text placement, and rendering.
For scanned PDFs, inspect page images and use OCR only when necessary.
Never rely on Unicode subscript/superscript glyphs in ReportLab; use markup or supported fonts instead.
Preserve source fidelity when editing and keep outputs reproducible."""
    },
    "pptx": {
        "description": "Create, edit, validate, and inspect PowerPoint decks.",
        "instructions": """For new decks, use a deterministic presentation-generation workflow such as PptxGenJS; for edits, preserve the existing template/package structure.
Set slide dimensions explicitly before adding content.
Use valid six-digit hex colors without a leading # in PptxGenJS.
Avoid shared mutable option objects and validate the finished deck before delivery.
Use a visual review pass (thumbnails/rendering) to catch overflow, misalignment, and unreadable text."""
    },
    "skill-creator": {
        "description": "Create and refine reusable Agent Skills.",
        "instructions": """Define a precise skill name and trigger description, then write concise instructions that change behavior reliably.
Preserve an existing skill's name when updating it.
Build incrementally, run representative test cases, review results, and iterate.
Prefer concrete workflows, checklists, schemas, examples, and failure handling over vague prose.
Package the skill as a self-contained directory with exactly one top-level SKILL.md manifest."""
    },
    "web-artifacts-builder": {
        "description": "Build polished React/TypeScript web artifacts and bundle them for sharing.",
        "instructions": """Use React + TypeScript + Vite with Tailwind and shadcn-style components when appropriate.
Keep the project deterministic and componentized, use path aliases cleanly, and make the artifact responsive.
When a single-file deliverable is required, bundle the app and inline assets into one HTML document.
Verify the final artifact in a browser or equivalent rendering check before presenting it."""
    },
    "webapp-testing": {
        "description": "Test web apps with reliable Playwright workflows.",
        "instructions": """For dynamic apps, use reconnaissance before action: wait for networkidle, inspect the rendered DOM or take a screenshot, then choose stable descriptive selectors.
Use Playwright sync APIs for compact test scripts, close browsers cleanly, and add explicit waits for important UI state.
Prefer existing helper scripts as black boxes when available.
Test the user's real workflow, not just that the page loads."""
    },
    "xlsx": {
        "description": "Create, edit, analyze, and validate spreadsheet workbooks.",
        "instructions": """Use openpyxl for workbook formatting/formulas and pandas for bulk tabular operations.
Follow the user's exact sheet names, headers, and conventions.
Use formulas instead of hardcoded calculated results and document assumptions.
For formula workbooks, recalculate with LibreOffice and verify there are no formula errors.
Avoid unsupported modern spreadsheet functions when the target recalculation engine cannot evaluate them; preserve macros when required."""
    },
}

SKILL_NAMES = tuple(LOCAL_SKILLS.keys())
