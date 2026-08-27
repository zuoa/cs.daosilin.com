# CS Data Hub — Design System Master

> Global source of truth. The full rationale, IA, interaction rules and QA checklist live in [`docs/UI_UX_GUIDELINES.md`](../../docs/UI_UX_GUIDELINES.md).

## Direction

**Tactical Data Terminal** — a disciplined data interface derived from CS scoreboards, radar and post-match reports. Radar/crosshair is the single signature motif. Data surfaces stay quiet, legible and operational.

## Core tokens

| Role | Value |
|---|---|
| Ink 950 | `#0B111B` |
| Ink 900 | `#111A26` |
| Canvas | `#F2F5F6` |
| Surface | `#FFFFFF` |
| Line | `#DFE6E9` |
| Signal | `#15966B` |
| Signal Dark | `#0E7653` |
| Running | `#3976A8` |
| Warning | `#B77A24` |
| Danger | `#BF4747` |

- Body: Inter / SF Pro Text / PingFang SC / system UI.
- Display and metrics: DIN Alternate / Arial Narrow / SF Pro Display.
- IDs, dates, rankings and data: SFMono-Regular / Consolas / Menlo.
- Control radii: 7–9px. Panel radii: 11–16px. Brand containers: 18–26px.
- Spacing follows a 4px base: 8 / 12 / 16 / 20 / 24 / 32 / 48 / 64px.

## Non-negotiable rules

1. One clear primary action per view or task region.
2. Current tournament context is visible before roster, crawl or review actions.
3. Every asynchronous action exposes loading, disabled, success and error states.
4. Destructive-looking changes explain reversibility and never rely on color alone.
5. Form labels remain visible and are associated with their inputs.
6. Icon-only buttons have accessible names.
7. Desktop data tables scroll inside their own container on small screens.
8. Touch targets are at least 44px on mobile.
9. Focus-visible and reduced-motion behavior are mandatory.
10. No emoji icons, decorative gradients or arbitrary accent colors.
11. Creating or editing one entity uses a focused modal; ongoing operational workflows remain inline.

## Page overrides

If `pages/<page>.md` exists, it may override layout-specific rules only. Color, typography, accessibility and feedback rules remain global.
