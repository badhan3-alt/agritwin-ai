# AgriTwin AI

**Know your land. Plan your crops. Protect your future.**

AgriTwin AI is a Django application for managing farms and exploring crop rotations in Bangladesh. Save a farm profile and boundary, plan field work, record finances and observations, review weather forecasts and NASA POWER climate data, and compare three crop rotation strategies.

Real NASA POWER data is required for climate analysis, rotation comparisons, simulation baselines, the HTML analysis report, and JSON/CSV analysis exports. The application does not substitute synthetic climate data when NASA is unavailable. Each analysis stores its NASA source URL, original response, reference period, and retrieval time. Farm records and downloadable PDF reports also work without a NASA connection; a PDF clearly identifies missing climate analysis.

The frontend uses Django HTML templates, CSS, and vanilla JavaScript. Django serves the pages, validates forms, stores farm profiles in SQLite, and runs all climate analysis and scoring in Python. There is no React, FastAPI, Node.js, or frontend build step in the Django application.

## Start locally

Install Python 3.10 or newer, then run these commands from the project directory.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python scripts/setup_env.py
python manage.py migrate
python manage.py runserver
```

Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/).

For an existing checkout, reinstall `requirements.txt`, run `python scripts/setup_env.py`, then run `python manage.py migrate` before starting the updated app. Local setup creates a private signing key in the ignored `.env` file without displaying it; an existing strong key is retained. The additional dependencies provide image validation (Pillow), WGS84 boundary measurements (GeographicLib), and PDF generation with Bangla shaping (ReportLab and HarfBuzz). No frontend build or external API key is needed for these features.

If PowerShell blocks environment activation, use the environment's Python directly:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe scripts/setup_env.py
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py runserver
```

On Linux or macOS, replace the activation command with `source .venv/bin/activate`.

## What you can do

- Save, edit, and delete separate farm profiles with location, area, current crops, soil information, drainage, irrigation, budget, and farming priority.
- Create an account, sign in, and change your password. Farms created as a guest in the current browser are linked to your account at registration or sign-in.
- Draw a field boundary on the map, or enter its GeoJSON coordinates, and save an estimated area and perimeter.
- Plan planting, irrigation, fertilizer application, and harvesting with dated tasks, completion states, and reminders inside the app.
- Record actual expenses and sales in BDT and see total income, expenses, and recorded net profit or loss.
- Keep a dated farm diary with notes, observations, and private photos.
- Store soil pH and N-P-K test results and compare the latest measurements with earlier results.
- See Open-Meteo current model conditions and a seven-day weather forecast, separately from NASA historical climate averages.
- Choose any of Bangladesh's 64 districts, grouped under all 8 divisions with English/Bengali names, or enter farm coordinates; use the map when its external map resources are available.
- Review NASA monthly rainfall and temperature, dry-season rainfall, heat screening, relative root-zone wetness when available, source information, and data limitations.
- Download the original NASA POWER JSON response used by the analysis.
- Compare the farmer's current crop sequence with a legume rotation and a diversified rotation.
- Inspect component scores, farmer-priority weights, calendar checks, potential benefits, risks, and missing information.
- Run sensitivity tests for rainfall, temperature, irrigation access, and farming priority.
- Download a PDF containing the farm profile, boundary schematic, saved analysis, calendar, finances, diary text, and soil test history. Print the HTML analysis report or download its NASA-backed analysis as JSON or CSV.
- Manage stored records through Django admin after creating a staff account.
- Ask questions in the Bangla/English farmer chatbot, keep private conversation history, and optionally include your farm's saved NASA summary.

Forms and analysis work through ordinary server requests. JavaScript enhances maps, charts, and controls; crop scoring stays on the server.

Bangla is the default language. The language button switches the full farmer-facing interface between Bangla and English, including forms, crop explanations, climate insights, scenario results, warnings, and reports. District names, chart labels, display numbers, and CSV reports follow the chosen language. The choice is retained in the browser session. User-entered names, numeric inputs, scientific calculations, machine-readable IDs, source URLs, and the original NASA response are preserved.

District presets provide approximate headquarters/city coordinates; update the coordinates for your actual field. A district does not determine your soil texture. The bundled district dataset and its source license are in `farms/data/`, so selecting a district works without a geocoding API.

Bangla translations are maintained in `locale/bn/LC_MESSAGES/django.po`, with a compiled `django.mo` included for normal setup. After editing translations, run `python manage.py compilemessages --locale bn --ignore .venv --ignore frontend`. That maintenance command requires GNU gettext; running the app with the included translations does not. Generated advice is translated at presentation time, so changing languages cannot change the saved NASA evidence or suitability scores.

Farm cards display an interactive OpenStreetMap centered on each saved farm location, with a coordinate marker, zoom controls, and a durable offline fallback. Card maps use the bundled Leaflet 1.9.4 library; its license is included in `static/vendor/leaflet/LICENSE`. These card maps identify locations; the separate boundary editor stores the shape you draw. Neither is a satellite photograph or land survey.

The optional Leaflet map uses OpenStreetMap's canonical HTTPS tile endpoint. Tile images explicitly send an origin-only referrer to meet the [OpenStreetMap tile policy](https://operations.osmfoundation.org/policies/tiles/) while keeping Django's default policy on other resources. If tiles fail or time out, the form restores coordinate-entry guidance and preserves the entered values.

## First farm walkthrough

1. Create an account for access across devices, or continue as a guest. Select **Add farm** and enter a farm name and location, or choose **Explore NASA example farm** on the homepage to create a Rajshahi example in your workspace. An internet connection is required for its NASA data.
2. Keep soil pH blank if you do not have a measurement. Choose **Unknown** for other unknown properties.
3. Enter the crops in the current rotation and the farmer's constraints, then save. The app retrieves real NASA POWER climatology for the selected coordinates.
4. Open the climate dashboard. Review the NASA source, reference period, retrieval time, and original-response download.
5. Open the rotation explorer and review the calendar, component scores, and warnings for all three candidates.
6. Open the simulator, change an assumption, and submit to compare it with the saved baseline.
7. Use the boundary, crop calendar, expenses and income, farm diary, soil test, and weather links for the same farm.
8. Choose **Download PDF** to export the saved farm records, or open the analysis report for NASA-backed HTML, JSON, and CSV output.

Accounts use Django's username/password authentication and password validation. Registering or signing in claims only unowned guest farms belonging to the browser's current session. After sign-in, the same account can access its farms from another device that connects to the same running server and database. Separate local installations do not synchronize databases, and this repository does not include a hosted deployment. Account settings allow password changes; email password recovery and SMTP delivery are not configured. Django admin remains available to authorized staff separately.

Guest farms remain private to their browser session. Keep its session cookie until you link them to an account; losing the cookie does not make them available to another browser.

Optionally run `python manage.py seed_demo` to prepare a Rajshahi example with real NASA POWER data for staff inspection. This command requires NASA connectivity; it is not an offline sample-data mode. The homepage example creates or reuses an example in the signed-in account's workspace or the current guest browser session.

## Farm management records

**Boundaries:** The map editor accepts one closed polygon without holes. Manual GeoJSON uses longitude first and latitude second, within the Bangladesh planning envelope. The server validates the ring and calculates its geodesic area and perimeter on WGS84. An optional checkbox copies the estimated acreage to the farm profile; deleting the boundary does not change that saved acreage. The estimate and north-up PDF schematic are planning aids, not surveyed ownership boundaries.

**Crop calendar:** Tasks have an activity, planned date, optional crop/field, notes, completion state, and a reminder lead time of 0–30 days. Overdue, due-today, and approaching reminders appear in the calendar when you visit it. No email, SMS, push notifications, or background reminder service is configured.

**Expenses and income:** Enter positive BDT amounts as expenses or income. The ledger totals all saved dates using decimal arithmetic; net is income minus expenses. This is a record of entered transactions, separate from the rotation engine's qualitative economic score, and does not predict profit.

**Farm diary:** Notes and photos stay attached to the selected farm. JPEG/PNG uploads must be at most 5 MB and 20 megapixels; accepted images are re-encoded as PNG. Photo requests check farm ownership, and the app does not expose a public media route. Files live under local `MEDIA_ROOT` (`media/` by default). Back up this directory together with the database. Replacing/removing a photo or deleting its diary entry or farm removes the corresponding stored file after the database change commits.

**Soil tests:** Store the test date, laboratory/source, pH, measured nitrogen, phosphorus, potassium, and sampling notes. Nutrients use mg/kg (equivalent to ppm by soil mass). Leave unmeasured values blank; zero is a recorded measurement. Each change compares the latest two available values for that measurement, with dates shown. Compare equivalent laboratory methods, sample depths, and units. Soil history does not automatically overwrite the farm profile or recalculate crop scores; edit the profile's pH yourself when appropriate.

**Weather:** The weather page retrieves current model conditions and seven daily forecasts from Open-Meteo in Asia/Dhaka time. It shows model temperature, humidity, precipitation, wind, conditions, and daily rain probability, with source and retrieval time. Successful responses are cached for up to 15 minutes; failed or incomplete requests show an unavailable state. Internet access and the provider's service availability are required. The integration uses the public endpoint without an API key; review Open-Meteo's current terms and usage limits before hosting. Forecasts never replace or update the stored NASA baseline.

**PDF reports:** The server generates an attachment using ReportLab and bundled Noto fonts with Bangla shaping. It reads saved records and validated NASA evidence only, and makes no NASA, weather, map-tile, or other network requests during export. The boundary is rendered as a north-up schematic without a basemap. Diary notes and photo captions are included; photo image files remain in the private diary. If no valid NASA analysis is saved, the PDF still exports the profile and records and explains that climate values and crop scores are unavailable. JSON/CSV exports and the HTML analysis report retain their NASA requirement.

## Separate Django apps

| App | Responsibility |
| --- | --- |
| `core` | Homepage, project information, shared navigation, health check |
| `accounts` | Registration, sign-in/out, password changes, guest farm claims |
| `farms` | Farm models, validated forms, account/guest ownership, saved analyses |
| `boundaries` | Validated GeoJSON polygons, WGS84 area/perimeter, map editor and exports |
| `notebook` | Crop calendar, BDT ledger, private diary photos, soil test history |
| `weather` | Open-Meteo current model conditions, seven-day forecasts, response validation/cache |
| `climate` | NASA POWER client, monthly climate summaries, source disclosure |
| `rotations` | Crop profiles, seasonal checks, transparent suitability scoring |
| `simulator` | Climate sensitivity scenarios and baseline comparisons |
| `reports` | Printable analysis report, saved-record PDF reports, and JSON/CSV analysis exports |
| `chatbot` | Local farmer conversations, reviewed agriculture help, crop/topic follow-ups and saved NASA context |

```text
agritwin-ai/
|-- manage.py
|-- requirements.txt
|-- agritwin/                 # Django settings, URLs, WSGI/ASGI
|-- core/
|-- accounts/
|-- farms/                    # Models and migrations
|-- boundaries/
|-- notebook/
|-- weather/
|-- climate/
|-- rotations/
|   `-- data/crop_profiles.json
|-- simulator/
|-- reports/
|-- chatbot/
|-- templates/                # HTML pages and shared components
|-- static/                   # CSS, JavaScript, and visual assets
|-- tests/
`-- docs/
```

## Data and scoring

Verify the real NASA connection directly from the terminal:

```powershell
python manage.py verify_nasa
```

This calls the same NASA client as the application and prints the request URL, data period, monthly record count, and climate totals. It reports an error if NASA is unavailable.

NASA POWER climatology supplies regional monthly climate patterns. It is historical climatology, not today's weather, a seasonal forecast, or a field sensor. The application preserves the source metadata and original JSON response with each analysis so the input evidence can be inspected and downloaded.

If a NASA request fails or returns unusable values, farm details remain saved. Without a valid NASA baseline, the climate, rotation, simulator, and HTML analysis report pages show an unavailable message with a retry action instead of generating results; JSON/CSV analysis exports are also unavailable. Boundaries, management records, and saved-record PDF downloads remain usable. If refreshing an existing valid NASA analysis fails, the saved NASA snapshot remains available with its original retrieval time. Legacy synthetic analyses are not reused. Refresh when connectivity returns.

SMAP, GPM, and Landsat retrievals are not implemented in this version. A POWER relative soil-wetness indicator, when available, is not SMAP volumetric soil moisture and is not converted into a fabricated measurement. Satellite and reanalysis products do not provide farm-specific pH or N-P-K tests.

The engine combines four relative component scores:

```text
Suitability = water_weight × water_score
            + climate_weight × climate_score
            + soil_weight × soil_score
            + economic_weight × economic_score
```

Farmer priorities adjust the weights. The economic component is a qualitative planning heuristic, not a prediction of prices, profit, or yield. Crop water-demand values and calendar windows are prototype assumptions, not measured irrigation requirements or a local agronomist's prescription. Calendar checks identify possible scheduling conflicts; variety choice and actual planting dates still require local confirmation.

A score of 85 is a comparison score, **not an 85% chance of success**. The simulator applies user-defined perturbations to a shared baseline; its outputs are sensitivity tests rather than climate forecasts. The crop knowledge base and farm setup currently target Bangladesh. Farm forms reject coordinates outside the prototype's Bangladesh planning envelope, which is a coarse bounding area rather than a verified national boundary.

See [the architecture](docs/architecture.md) and [data sources and limitations](docs/nasa_sources.md) for details.

## Farmer chatbot

The **Farmer assistant** navigation link and **Ask a question** button open `/chatbot/`. The local chatbot uses the project's agriculture library and conversation rules to answer in Bangla or English, recognize common Banglish questions, and understand crop or topic follow-ups. It runs inside Django without an API key, paid credits, model downloads, or external AI services.

Run `python manage.py check_chatbot` to check the local assistant. Existing OpenAI settings are ignored. The chatbot makes no network requests, can explain an explicitly shared saved NASA analysis, and links to reviewed references for further reading. It has a bounded farming knowledge base and cannot provide live weather, current prices, or unrestricted general-knowledge answers. Other app features still need internet for new NASA data and maps. Chat privacy, examples, limits, and setup are described in [the chatbot guide](docs/chatbot.md).

## Tests and checks

```powershell
python manage.py check
python manage.py test
node --test tests/map.test.cjs
```

The Django tests use a recorded real NASA response and mocked requests so test runs do not require external connectivity. They cover account and guest access, ownership isolation, farm and boundary validation, calendar reminders, decimal finance totals, private photo handling, soil comparisons, bilingual pages, weather parsing and failures, NASA provenance, rotation comparisons, scenarios, and report exports. The recorded fixture is test data and is not a substitute for fetching the selected farm in the application. Test results describe software behavior; they do not validate crop performance in the field. The map test requires Node.js only for developer checks; Node.js is not needed to serve the app.

## Administration

```powershell
python manage.py createsuperuser
```

Open [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/) and sign in using that account. Never put real staff passwords in source files.

## Configuration and deployment

Run `python scripts/setup_env.py` for local development. It prepares a private `DJANGO_SECRET_KEY` and explicitly enables local debug mode when no debug choice is configured. Without an explicit choice, debug mode defaults to off. Startup rejects missing or weak signing keys and privileged credentials under browser-public prefixes such as `VITE_` or `NEXT_PUBLIC_`. Use [.env.example](.env.example) as a configuration reference, or set values in your shell or hosting platform. Existing environment variables take precedence. Keep private values out of version control.

Authentication and farm ownership checks run on the Django server. SQLite has no PostgreSQL-style RLS policy configured, and there is no Supabase client or service-role/admin API key in this application. See [security and secret handling](docs/security.md) for access controls, hosting boundaries, and credential rotation.

Before hosting, use a private secret key, disable debug mode, set allowed hosts and trusted origins for the actual domain, serve static files, and use a production WSGI or ASGI server with HTTPS. Django's development server is intended for development. Run `python manage.py check --deploy` with the production configuration and follow the [official Django deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/).

No hosted deployment is included. The application is an independently developed prototype inspired by the supplied project brief; it does not imply NASA endorsement or certify eligibility for any competition.

## License

Source code is available under the [MIT License](LICENSE). External datasets, map tiles, and third-party libraries remain subject to their respective terms and attribution requirements.
