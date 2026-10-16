# Production audit of all directional CASCO comparisons — 2026-10-16

Branch: `fix/audit-all-pair-comparisons`  
Baseline deployment: `insurance-comparator-eta.vercel.app`  
Dataset: 11 insurers × 10 accepted parameters = 110 accepted insurer-field answers.

## Scope

- Opened all 110 directional comparison routes for the 55 unique insurer pairs (both company orders); pages returned HTTP 200. One route was retried through the production deployment alias.
- Reviewed displayed advantage cards, client scripts, all ten table outcomes per page, and how the published outcomes relate to the accepted field text and deterministic comparison rules.
- This is a comparison-logic audit against the accepted dataset, not a re-extraction of all 110 PDF answers.

## Confirmed defects in the published baseline

1. **GAP was treated as equivalent merely because both insurers had a GAP product/option.** The UI consequently called RESO and Alfa conditions comparable and could rank a 25% cap against a different GAP variant whose limit was expressed as a vehicle-value uplift. These are not demonstrably comparable variants or calculation bases. The shared-feature client script also repeated GAP as a generic positive feature in many unrelated pairs.
2. **Coverage level was mistaken for equality of contract terms.** The same broad level (included/optional) does not prove equal conditions, exclusions, triggers, or requirements. This affected GAP and could produce overconfident “comparable conditions” wording for self-ignition, terrorism, drones, and evacuation.
3. **Total-loss equality ignored the boundary operator.** VSK describes a threshold that is exceeded (>75% of actual value), while Rosgosstrakh describes a threshold reached at or above 75% (≥75% of actual value). Same percentage and basis do not make these conditions identical.
4. **The comparison table header was misleading.** It said “Advantage [first insurer]” even when a row correctly reported an advantage for the competitor.

## Corrections in this branch

- If both accepted GAP answers establish the same broad availability level, do not call them equal or compare their limits unless the variants and calculation bases are demonstrated to be comparable. Preserve the special accepted rule: if one checked official rule set has no direct GAP condition and the other explicitly offers GAP, show the availability advantage without claiming an explicit exclusion or the non-existence of a separate product.
- For other coverage parameters, same availability level alone no longer means equivalent terms. Only identical accepted conditions or two explicit exclusions are treated as equal; otherwise the result is incomparable unless a specific comparable limit or level difference proves a distinction.
- For evacuation, do not infer equality from a shared broad availability level when route, scope, or limits are not demonstrated to match.
- Total-loss comparison now checks both calculation basis and whether the threshold is strict or inclusive; “exceeds 75%” is not equal to “75% or more.”
- Rename the fourth table column to “Result of comparison,” because it can legitimately describe either company’s advantage.
- Add regression tests for GAP variant mismatch, total-loss threshold boundaries, coverage-level false equality, and the published page label.

## Interpretation of the audit

The first insurer remains the sales focus, but the comparison table must still report competitor advantages honestly. “Unknown in the checked official rules” is not an explicit exclusion; a separate optional product is not automatically part of the base policy; and identical headline percentages or broad availability labels are not enough to establish equivalent contract conditions.
