<!-- Hallmark · design-system: Tactical Signal · pre-emit critique: P5 H5 E4 S5 R5 V4 -->
# Design — CS Data Hub

A locked design system for this app. Every page reads this file before visual changes are made. Extend this system when the product grows; do not invent a different theme per route.

## Genre

Modern-minimal with a technical, utilitarian voice. The visual idea is “Tactical Data Terminal”: scoreboard discipline, post-match analysis, and one restrained radar/crosshair signature—never a simulated game HUD.

## Macrostructure family

- Marketing/public index: **Marquee Hero**. The opening statement owns the first fold; orientation and live archive data begin below it.
- Data application: **Workbench**. Season comparison and admin operations expose the working interface directly, with compact annotations and fewer containment layers.
- Player dossier: **Stat-Led**. A real PWR Rating is the lead figure and the rest of the page qualifies it.
- Authentication: **Split Studio**. Product purpose on one side, focused credentials on the other.

## Navigation and footer

- Public navigation: N9 Edge-aligned minimal.
- Admin navigation: N3 Side-rail; it collapses to a compact top rail below the content breakpoint.
- Public index footer: Ft5 Statement. Data pages use a restrained Ft2 inline close.
- The login view has no footer; the back link is its only secondary navigation.

## Theme

- `--color-paper`: `oklch(96.5% 0.009 178)`
- `--color-paper-2`: `oklch(98.2% 0.006 178)`
- `--color-ink`: `oklch(17% 0.027 244)`
- `--color-ink-2`: `oklch(23% 0.029 242)`
- `--color-rule`: `oklch(88.5% 0.014 188)`
- `--color-accent`: `oklch(59% 0.132 163)`
- `--color-focus`: `oklch(49% 0.15 163)`

Signal green is the only brand accent and stays below roughly 5% of any viewport. Blue, amber, and red are semantic status colours only. Canvas and ink carry a subtle blue-green tint.

Uploaded player portraits unlock one contained exception: the player showcase and its downloadable poster use a charcoal and competition-red palette inspired by broadcast player cards. The red does not escape that component, change control states, or recolour the surrounding dossier page. PWR Rating remains the lead figure.

## Typography

- Display: DIN Alternate / Arial Narrow / SF Pro Display, weight 700–800, roman.
- Body: Inter / SF Pro Text / PingFang SC, weight 400.
- Outlier: SFMono-Regular / Menlo, used for IDs, dates, rankings, and operational labels.
- Display tracking: `-0.035em`; display headings use `overflow-wrap: anywhere`.
- Type-scale anchor: `--text-display: clamp(3.6rem, 10vw, 7rem)`.

## Spacing

Four-point named scale in `tokens.css`. Production CSS uses semantic tokens rather than improvising new gaps.

## Motion

- Easings: `--ease-out`, `--ease-in`, `--ease-in-out` from `tokens.css`.
- Product pages load composed; only controls, modals, loading indicators, and radar/status feedback move.
- Reduced motion removes spatial movement and limits state transitions to 150 ms.

## Microinteractions stance

- Silent success when the result is visible; toasts are reserved for failures or hidden effects.
- Hover is paired with focus; hover treatment is enabled only for fine pointers.
- Buttons press inward by one pixel; focus rings appear immediately.
- Stateful controls cover default, hover, focus, active, disabled, loading, error, and success.

## CTA voice

- Primary: dark ink fill, compact rectangular radius, specific action verb, one line.
- Secondary: paper surface with a rule border; no celebratory colour fill.

## Per-page allowances

- Home may use the existing CSS-built radar as Tier-A enrichment below the marquee fold.
- Season and player pages may use real data visualisation only.
- Admin pages use no enrichment; function carries the page.
- Login may use the crosshair grid as a restrained background signature.

## What pages MUST share

- Wordmark, crosshair mark, signal-green placement, type roles, focus treatment, control height, and status vocabulary.
- One primary action per task region.
- Stacked section headings without decorative eyebrow labels.
- Page-level horizontal overflow is clipped; only explicit table and day rails may scroll.

## What pages MAY differ on

- Macrostructure inside the declared family.
- Data density and table/card collapse strategy.
- Radar enrichment on public pages only.

## Exports

### tokens.css

`tokens.css` at the project root is the canonical source. It contains the complete colour, typography, spacing, type, motion, rule, radius, shadow, and z-index tokens.

### Tailwind v4 `@theme`

```css
@theme {
  --color-paper: oklch(96.5% 0.009 178);
  --color-paper-2: oklch(98.2% 0.006 178);
  --color-paper-3: oklch(93.5% 0.012 178);
  --color-ink: oklch(17% 0.027 244);
  --color-ink-2: oklch(23% 0.029 242);
  --color-rule: oklch(88.5% 0.014 188);
  --color-accent: oklch(59% 0.132 163);
  --color-focus: oklch(49% 0.15 163);
  --font-display: "DIN Alternate", "Arial Narrow", "SF Pro Display", sans-serif;
  --font-body: Inter, "SF Pro Text", "PingFang SC", sans-serif;
  --font-outlier: "SFMono-Regular", Menlo, monospace;
  --spacing-xs: 0.75rem;
  --spacing-sm: 1rem;
  --spacing-md: 1.5rem;
  --spacing-lg: 2rem;
  --spacing-xl: 3rem;
  --text-md: 1rem;
  --text-lg: 1.25rem;
  --text-xl: 1.563rem;
  --text-2xl: 1.953rem;
  --ease-out: cubic-bezier(0.16, 1, 0.3, 1);
  --radius-card: 12px;
  --radius-input: 8px;
}
```

### DTCG `tokens.json`

```json
{
  "$schema": "https://design-tokens.github.io/community-group/format/",
  "color": {
    "paper": { "$value": "oklch(96.5% 0.009 178)", "$type": "color" },
    "paper-2": { "$value": "oklch(98.2% 0.006 178)", "$type": "color" },
    "ink": { "$value": "oklch(17% 0.027 244)", "$type": "color" },
    "ink-2": { "$value": "oklch(23% 0.029 242)", "$type": "color" },
    "rule": { "$value": "oklch(88.5% 0.014 188)", "$type": "color" },
    "accent": { "$value": "oklch(59% 0.132 163)", "$type": "color" },
    "focus": { "$value": "oklch(49% 0.15 163)", "$type": "color" }
  },
  "font": {
    "display": { "$value": "DIN Alternate, Arial Narrow, SF Pro Display, sans-serif", "$type": "fontFamily" },
    "body": { "$value": "Inter, SF Pro Text, PingFang SC, sans-serif", "$type": "fontFamily" },
    "outlier": { "$value": "SFMono-Regular, Menlo, monospace", "$type": "fontFamily" }
  },
  "space": {
    "xs": { "$value": "0.75rem", "$type": "dimension" },
    "sm": { "$value": "1rem", "$type": "dimension" },
    "md": { "$value": "1.5rem", "$type": "dimension" },
    "lg": { "$value": "2rem", "$type": "dimension" },
    "xl": { "$value": "3rem", "$type": "dimension" },
    "2xl": { "$value": "4rem", "$type": "dimension" }
  },
  "duration": {
    "micro": { "$value": "120ms", "$type": "duration" },
    "short": { "$value": "220ms", "$type": "duration" },
    "long": { "$value": "420ms", "$type": "duration" }
  }
}
```

### shadcn/ui CSS variables

```css
:root {
  --background: 96.5% 0.009 178;
  --foreground: 17% 0.027 244;
  --card: 98.2% 0.006 178;
  --card-foreground: 17% 0.027 244;
  --popover: 98.2% 0.006 178;
  --popover-foreground: 17% 0.027 244;
  --primary: 59% 0.132 163;
  --primary-foreground: 98.2% 0.008 178;
  --secondary: 93.5% 0.012 178;
  --secondary-foreground: 23% 0.029 242;
  --muted: 88.5% 0.014 188;
  --muted-foreground: 53% 0.025 235;
  --accent: 59% 0.132 163;
  --accent-foreground: 98.2% 0.008 178;
  --destructive: 54% 0.17 25;
  --destructive-foreground: 98.2% 0.008 178;
  --border: 88.5% 0.014 188;
  --input: 88.5% 0.014 188;
  --ring: 49% 0.15 163;
  --radius: 12px;
}
```
