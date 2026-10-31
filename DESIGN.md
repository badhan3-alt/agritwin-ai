# AgriTwin interface system

Read this file before changing UI. Audience: Bangladeshi farmers using Bangla or English on phones and desktops. The primary journey is save a field, understand its NASA baseline, compare rotations, and explore a scenario.

## Direction

A field notebook with the clarity of a planning workspace. Preserve the forest-green identity and agricultural artwork where used. The homepage hero uses the credited historical USGS Landsat image in `static/images/bangladesh-landsat.jpg`; retain its source and capture date. Use typography, deliberate alignment, and whitespace for hierarchy. Avoid decorative gradients, emoji tiles, and unnecessary animation.

## Tokens

- Forest: `#173d32`; deep forest: `#133229`; supporting green: `#557447`.
- Canvas: `#f7f8f1`; surface: `#ffffff`; quiet surface: `#f0f2e7`.
- Text: `#223d32`; secondary text: `#526451`; border: `#d9e1d2`.
- Accent: `#d6eaa2`; warning: `#815719`; error: `#a3372c`.
- Spacing: 4, 8, 12, 16, 24, 32, 40, 48, 64px.
- Radius: controls 10px, panels 18px, hero 24px.
- Shadow: `0 8px 24px #173d3208`; avoid stacking shadows.
- English: DM Sans body, DM Serif Display headings, system fallbacks.
- Bangla: Noto Sans Bengali body, Noto Serif Bengali headings, Nirmala UI fallbacks.
- Body 15px / 1.75; secondary 13px minimum; mobile inputs 16px.
- Heading scale: 24, 32, 40, 48px; fluid sizing. Bangla headings need 1.5 line height and zero letter spacing.

## Interaction

Use semantic links and buttons, visible keyboard focus, and labelled inputs. Interactive targets are at least 24px and at least 44px on touch devices. Preserve browser zoom. Pending submissions retain their labels and show a spinner; prevent duplicate saves and restore controls after browser Back. Link validation summaries to fields and focus the summary after server validation. Announce status changes accessibly.

Boldness 5/10; motion 2/10; density 4/10. Limit motion to short focus/hover feedback and progress indicators. Honor reduced motion. Keep table scrolling inside its container, and never clip page content to hide layout bugs. Use one column for phone forms and no sticky controls that cover content.

## Verification

Check home, farm list, new/edit form, climate, rotations, simulator, report, and chat in both languages. Inspect desktop and phone widths, keyboard navigation, validation, pending actions, long field names, and empty/unavailable states. Run Django and map checks. Record browser screenshot verification honestly; do not claim an external audit score or invoke unavailable slash commands.

References: [Impeccable](https://github.com/pbakaus/impeccable), [Taste Skill](https://github.com/leonxlnx/taste-skill), [Vercel guidelines](https://github.com/vercel-labs/web-interface-guidelines), [DESIGN.md collection](https://github.com/voltagent/awesome-design-md).
