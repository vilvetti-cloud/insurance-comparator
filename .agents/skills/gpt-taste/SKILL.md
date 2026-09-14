---
name: gpt-taste
description: Primary premium frontend design direction for this project. Use for deliberate layouts, strong typography, spacing, responsive composition, interaction and motion. Avoid generic AI/SaaS patterns.
---

# GPT Taste — Project Design Standard

Use this as the default visual direction for significant UI work.

## Core principles
- Do not default to generic centered SaaS layouts, repetitive left-text/right-image sections, or arbitrary card grids.
- Choose a deliberate composition based on the page purpose and existing product context.
- Use strong typographic hierarchy and generous macro-spacing.
- Keep headings readable: avoid narrow containers that create awkward multi-line walls of text.
- Prefer a small number of intentional components over collections of nearly identical cards.
- Every interactive element must have clear text, contrast, hover/focus/active states and usable hit areas.
- Motion should communicate hierarchy or feedback; never add animation only for decoration.
- Keep horizontal overflow under control when using transforms or motion.

## Typography
- Avoid Inter/Roboto/Arial/Open Sans when a suitable project font already exists or a deliberate alternative can be introduced safely.
- Do not change the project's typography stack without checking its existing design system and dependencies.
- Avoid excessive uppercase micro-labels and meaningless labels such as “SECTION 01”.

## Layout
- Vary composition intentionally between sections while preserving a coherent visual language.
- Use asymmetric layouts, editorial rhythm, controlled bento grids, large media or strong whitespace when appropriate.
- Never leave accidental dead space in a grid.
- On mobile, preserve hierarchy rather than simply shrinking desktop layouts.

## Motion
- Prefer CSS transitions for small interactions.
- Use GSAP or another existing motion system only when it is already available or the task justifies adding it.
- Favor scroll reveals, subtle transforms, image scale and coordinated transitions over gratuitous animation.

## Pre-flight
Before implementation, state internally: page purpose, primary action, layout direction, typography hierarchy, responsive strategy and interaction states. Then implement using the existing stack.
