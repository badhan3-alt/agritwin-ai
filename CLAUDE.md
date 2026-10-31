# Frontend engineering

Read `DESIGN.md` before modifying UI. This is a Django templates, CSS, and vanilla JavaScript application. Keep calculations on the server and forms functional without JavaScript.

- Use the exact tokens, type scale, spacing, radii, and shadows in `DESIGN.md`.
- Preserve Bangla and English translations; retain English branding and standard technical names, user-entered values, and NASA evidence.
- Avoid generic gradient headlines, emoji feature tiles, and unnecessary animation. Use the existing SVG icon library.
- Review component layout, typography, and backgrounds. Use installed audit/polish skills when available; never claim a command ran if it was unavailable.
- Keep targets at least 24px, or 44px on touch devices; preserve zoom and visible keyboard focus.
- Pending actions retain their labels and show accessible progress with a CSS spinner. Restore controls after failed requests and browser Back.
- Check validation, empty, unavailable, and loading states. Mobile inputs use at least 16px type.
- After changes, inspect the live local pages with Playwright when available. Check phone and desktop screenshots for overflow, overlapping controls, and clipped text. Record any verification limitations.
- Run `python manage.py test`, `node --test tests/map.test.cjs`, and JavaScript syntax checks for affected files.

Use the official references linked in `DESIGN.md`. Do not invent audit scores, install a different frontend stack, or replace this application's brand with an unrelated company's identity.
