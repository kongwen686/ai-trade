# UI Rule Skill: Blue White Trading Operations Console

## 1. Product Definition

This project is an enterprise SaaS-style trading operations console for a personal quantitative trading system. The primary user is the system owner who monitors market data, signals, backtests, account status, risk controls, and runtime configuration on desktop web screens.

The UI should behave like a production admin workspace: fixed navigation, compact information density, visible tables, clear module boundaries, fast scanning, and operational controls that can be used repeatedly.

## 2. Visual Direction

- Overall style: bright blue-white enterprise dashboard, close to a project management collaboration backend.
- Background: very light blue-gray canvas, with soft edge glow and no dark cyberpunk treatment.
- Surface: white cards, subtle blue borders, low shadow, 10-14px radius.
- Primary color: saturated SaaS blue for active navigation, primary buttons, selected tabs, progress bars, and important values.
- Accent colors: green for success/growth, amber for warning/pending, red for danger/error, purple/cyan only as small chart or tag accents.
- Typography: system sans-serif, strong dark titles, compact gray metadata, clear numeric hierarchy.

## 3. Layout System

- Use a fixed left sidebar on desktop with logo, grouped navigation, active item highlight, and a status block at the bottom.
- Use a sticky top utility bar with horizontal workspace tabs, action buttons, language switch, alerts, and user/session chip.
- Main workspace uses a constrained content width and modular 12-column grid behavior.
- Page hero should be compact like a project overview header, not a marketing hero. It should expose page identity and KPI cards without dominating the viewport.
- Dense pages should prioritize filters, tables, charts, and right-side detail panels over decorative copy.
- Mobile/tablet should collapse sidebar into horizontal groups and keep controls scrollable.

## 4. Component Rules

- Sidebar: white surface, 1px right border, blue active row, colored icon dot, compact 36-40px nav rows.
- Top tabs: white header, blue underline/filled active state, subtle search/action feel.
- Cards: white, #e6edf7 border, soft shadow, 16-20px padding, consistent 18-24px gaps.
- KPI cards: small colored icon badge, gray label, large dark number, small delta/status text.
- Tables: sticky pale header, 12-14px cell padding, clear separation between header and body, hover background, status chips.
- Buttons: blue filled primary, white secondary with blue border, destructive red outline/text only.
- Tags/chips: pale blue/green/yellow/red backgrounds with compact 11-12px text.
- Forms: white inputs, #d8e2f0 borders, blue focus ring, aligned labels.
- Charts/progress: blue primary bars, green success bars, amber warning bars, no neon.

## 5. Content Rules

- Use concise Chinese operational copy.
- Keep trading domain vocabulary visible: signal, scan, risk, account, position, execution, backtest, strategy, on-chain, basis.
- Avoid lorem ipsum and generic placeholder blocks.
- Numeric values should be tabular and right-aligned in tables.
- Empty states should explain the next operational action.

## 6. Boundary Rules

- Do not use dark backgrounds, neon gradients, glassmorphism, or cyberpunk styling.
- Do not turn dashboard pages into poster/landing pages.
- Do not add oversized decorative illustrations to data-heavy pages.
- Do not let cards overlap or use equal visual weight for every module.
- Do not hide tables behind card-only layouts when the user needs comparison.
- Do not use excessive purple or one-note monochrome palettes.

## 7. Generation Prompt

Create a desktop SaaS admin dashboard for a personal quantitative trading operations system.

Theme: trading signal monitoring, strategy research, automated paper/live execution, and runtime configuration for a single advanced user.
Palette: bright blue-white enterprise SaaS; #f4f7fc background, white cards, #1769ff primary blue, green success, amber warning, red danger, subtle blue borders.
Structure: fixed left sidebar, sticky top utility bar, compact project-style hero, KPI cards, filter bar, dense tables, charts, and right-side detail panels where useful.
Details: include signal tables, strategy cards, risk rules, trading status, account logs, settings forms, status chips, blue active navigation, compact buttons, and realistic Chinese trading labels.
Data realism: use plausible symbols, prices, volumes, dates, statuses, risk messages, and account events.
Boundaries: no dark cyberpunk theme, no abstract poster, no decorative 3D hero, no lorem ipsum, no overlapping modules.
Quality bar: must look like a production admin workspace with readable dense data and consistent spacing.

## 8. QA Checklist

- The page uses a bright blue-white admin palette.
- Sidebar active state is blue and clearly visible.
- Top utility bar stays compact and sticky.
- Cards and tables have consistent spacing and no overlap.
- Table header and body have clear visual separation.
- Primary actions are blue; danger actions are red and restrained.
- Status chips use semantic pale backgrounds.
- Mobile layout remains usable without text collisions.
