# AgriTwin AI

**Know your land. Plan your crops. Protect your future.**

AgriTwin AI is a Django application for exploring crop rotations in Bangladesh. Create a farm profile, review regional NASA POWER climate data, compare three rotation strategies, and test how the comparisons change under different rainfall, temperature, and irrigation assumptions.

Real NASA POWER data is required for every climate analysis, rotation comparison, simulation baseline, and farmer report. The application does not substitute synthetic climate data when NASA is unavailable. Each analysis stores its NASA source URL, original response, reference period, and retrieval time.

The frontend uses Django HTML templates, CSS, and vanilla JavaScript. Django serves the pages, validates forms, stores farm profiles in SQLite, and runs all climate analysis and scoring in Python. There is no React, FastAPI, Node.js, or frontend build step in the Django application.

## Start locally

Install Python 3.10 or newer, then run these commands from the project directory.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/).

If PowerShell blocks environment activation, use the environment's Python directly:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py runserver
```

On Linux or macOS, replace the activation command with `source .venv/bin/activate`.

## What you can do

- Save, edit, and delete separate farm profiles with location, area, current crops, soil information, drainage, irrigation, budget, and farming priority.
- Choose any of Bangladesh's 64 districts, grouped under all 8 divisions with English/Bengali names, or enter farm coordinates; use the map when its external map resources are available.
- Review NASA monthly rainfall and temperature, dry-season rainfall, heat screening, relative root-zone wetness when available, source information, and data limitations.
- Download the original NASA POWER JSON response used by the analysis.
- Compare the farmer's current crop sequence with a legume rotation and a diversified rotation.
- Inspect component scores, farmer-priority weights, calendar checks, potential benefits, risks, and missing information.
- Run sensitivity tests for rainfall, temperature, irrigation access, and farming priority.
- Print a farmer report or save it as PDF through the browser; download the same analysis as JSON or CSV.
- Manage stored records through Django admin after creating a staff account.
- Ask questions in the Bangla/English farmer chatbot, keep private conversation history, and optionally include your farm's saved NASA summary.

Forms and analysis work through ordinary server requests. JavaScript enhances maps, charts, and controls; crop scoring stays on the server.

Bangla is the default language. The language button switches the full farmer-facing interface between Bangla and English, including forms, crop explanations, climate insights, scenario results, warnings, and reports. District names, chart labels, display numbers, and CSV reports follow the chosen language. The choice is retained in the browser session. User-entered names, numeric inputs, scientific calculations, machine-readable IDs, source URLs, and the original NASA response are preserved.

District presets provide approximate headquarters/city coordinates; update the coordinates for your actual field. A district does not determine your soil texture. The bundled district dataset and its source license are in `farms/data/`, so selecting a district works without a geocoding API.

Bangla translations are maintained in `locale/bn/LC_MESSAGES/django.po`, with a compiled `django.mo` included for normal setup. After editing translations, run `python manage.py compilemessages --locale bn --ignore .venv --ignore frontend`. That maintenance command requires GNU gettext; running the app with the included translations does not. Generated advice is translated at presentation time, so changing languages cannot change the saved NASA evidence or suitability scores.

The optional Leaflet map uses OpenStreetMap's canonical HTTPS tile endpoint. Tile images explicitly send an origin-only referrer to meet the [OpenStreetMap tile policy](https://operations.osmfoundation.org/policies/tiles/) while keeping Django's default policy on other resources. If tiles fail or time out, the form restores coordinate-entry guidance and preserves the entered values.

## First farm walkthrough

1. Select **Add farm** and enter a farm name and location, or choose **Explore NASA example farm** on the homepage to create a Rajshahi example in your browser session. An internet connection is required for its NASA data.
2. Keep soil pH blank if you do not have a measurement. Choose **Unknown** for other unknown properties.
3. Enter the crops in the current rotation and the farmer's constraints, then save. The app retrieves real NASA POWER climatology for the selected coordinates.
4. Open the climate dashboard. Review the NASA source, reference period, retrieval time, and original-response download.
5. Open the rotation explorer and review the calendar, component scores, and warnings for all three candidates.
6. Open the simulator, change an assumption, and submit to compare it with the saved baseline.
7. Open the report and print or download the result.

Farm profiles belong to the browser session that created them. Keep using the same browser and retain its session cookie to return to those profiles. This version does not provide farmer accounts, cross-device synchronization, or account recovery. Django admin is available to authorized staff separately.

Optionally run `python manage.py seed_demo` to prepare a Rajshahi example with real NASA POWER data for staff inspection. This command requires NASA connectivity; it is not an offline sample-data mode. The homepage example creates a separate farm in each browser session.

## Separate Django apps

| App | Responsibility |
| --- | --- |
| `core` | Homepage, project information, shared navigation, health check |
| `farms` | Farm models, validated forms, session ownership, saved analyses |
| `climate` | NASA POWER client, monthly climate summaries, source disclosure |
| `rotations` | Crop profiles, seasonal checks, transparent suitability scoring |
| `simulator` | Climate sensitivity scenarios and baseline comparisons |
| `reports` | Printable reports and JSON/CSV exports |
| `chatbot` | Local farmer conversations, reviewed agriculture help, crop/topic follow-ups and saved NASA context |

```text
agritwin-ai/
|-- manage.py
|-- requirements.txt
|-- agritwin/                 # Django settings, URLs, WSGI/ASGI
|-- core/
|-- farms/                    # Models and migrations
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

If a NASA request fails or returns unusable values, farm details remain saved. Without a valid NASA baseline, the climate, rotation, simulator, and report pages show an unavailable message with a retry action instead of generating results. If refreshing an existing valid NASA analysis fails, the saved NASA snapshot remains available with its original retrieval time. Legacy synthetic analyses are not reused. Refresh when connectivity returns.

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
```

The Django tests use a recorded real NASA response and mocked requests so test runs do not require external connectivity. They cover farm validation and session access, NASA response validation, unavailable-data handling, rotation comparisons, scenario calculations, and reports. The recorded fixture is test data and is not a substitute for fetching the selected farm in the application. Test results describe software behavior; they do not validate crop performance in the field.

## Administration

```powershell
python manage.py createsuperuser
```

Open [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/) and sign in using that account. Never put real staff passwords in source files.

## Configuration and deployment

The default setup is for local development. Copy [.env.example](.env.example) to `.env` to customize settings, or set the values in your shell or hosting platform. Existing environment variables take precedence. Keep private values out of version control.

Before hosting, use a private secret key, disable debug mode, set allowed hosts and trusted origins for the actual domain, serve static files, and use a production WSGI or ASGI server with HTTPS. Django's development server is intended for development. Run `python manage.py check --deploy` with the production configuration and follow the [official Django deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/).

No hosted deployment is included. The application is an independently developed prototype inspired by the supplied project brief; it does not imply NASA endorsement or certify eligibility for any competition.

## License

Source code is available under the [MIT License](LICENSE). External datasets, map tiles, and third-party libraries remain subject to their respective terms and attribution requirements.
