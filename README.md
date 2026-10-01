# WanderAI

A React and FastAPI travel planner using a LangGraph agent and Groq. It supports worldwide destinations, conversation follow-ups, general packing lists, Open-Meteo weather forecasts, and dated Frankfurter currency conversions. Place names are resolved on the server; ambiguous names require a country or region. Itineraries remain useful without optional dates or budgets. Trip costs are illustrative only when based on amounts you provide or a cited source; the app does not offer live attraction prices, hours, bookings, transport schedules, visa rules or availability.

## Requirements

Python 3.10+ and Node.js 20.19+ or 22.12+ (npm included). Tested locally with Python 3.13 and Node 24. Vercel uses Python 3.13 via `.python-version`. The Groq API key stays on the Python server.

## Setup

1. Install Python dependencies: `python -m pip install -r requirements.txt`
2. Copy `backend/.env.example` to `backend/.env` and put your real `GROQ_API_KEY` there. Alternatively, set `GROQ_API_KEY` in the server environment. `GROQ_MODEL` defaults to `openai/gpt-oss-120b`. `GROQ_FALLBACK_MODEL` defaults to `openai/gpt-oss-20b`; set it to an empty string to disable fallback. Both support tool calling. Open-Meteo's non-commercial API and Frankfurter need no key. Never put a Groq key in a `VITE_` variable or commit an `.env` file.
3. Run `python start.py`. The launcher runs `npm ci` from the repository root on first run, builds the frontend, starts FastAPI on port 8000, and opens http://localhost:8000. Use `python start.py --rebuild` after frontend changes.
4. For Vite hot reload run `python start.py --dev`. Vite serves http://localhost:5173 and proxies `/api` to FastAPI on port 8000. Run `python start.py --no-browser` to keep the browser closed.

The optional legacy Streamlit interface uses the same Groq agent. Install `streamlit` separately, then run `streamlit run Agent_app.py`.

## API

- `GET /api/health` → `{"status":"ok","provider_configured":true|false}`. This does not call Groq.
- `POST /api/chat` with `{"message":"Plan three days in Lisbon, Portugal", "session_id":null, "history":[]}` → `{"session_id":"UUID", "reply":"..."}`. Reuse the returned ID for follow-ups. On Vercel, send prior visible turns in `history` as alternating user and assistant objects, for example `[{"role":"user","content":"Plan Lisbon, Portugal"},{"role":"assistant","content":"Here is a plan"}]`; the React app does this automatically.
- `POST /api/clear` with `{"session_id":"UUID"}` → `{"session_id":"UUID", "cleared":true}`.

Messages must be 1–4000 characters after trimming. Local sessions are held in process memory and vanish on restart. Calls within one local session are serialized; different sessions are isolated. Vercel functions use a stateless path because instances can change between requests: the browser sends up to ten complete visible exchanges for context. Only user and assistant text travels to the browser; tool calls, tool results and Groq credentials remain server-side. Clearing removes the browser's history. API documentation is at `/docs` locally.

Each trip request can require several Groq calls when the agent uses tools. If the primary model returns HTTP 429, the server tries the fallback model and pauses primary calls for the provider's `Retry-After` period. Both models still use the same Groq account, so an exhausted account-wide limit cannot be bypassed in code. If both are limited, the API returns 429 with the provider's retry time when available; the chat UI preserves the failed message and enables Retry after that wait. A provider timeout returns 504. Other planner failures return a generic 502 without internal details.

The agent is limited to travel and trip planning. Clearly unrelated questions receive a short travel-only redirect without a Groq call; travel requests and brief follow-ups about an earlier trip continue through the planner. Named destinations use Open-Meteo geocoding. If a name like "Paris" matches different places, ask for "Paris, France" or "Paris, Texas". Unresolved names never receive guessed coordinates. Destination timezones and usual currencies come from the resolved location and territory currency metadata.

Weather requests use Open-Meteo's global forecast API. The app fetches model-based current conditions and daily forecasts in the destination's local timezone, with temperature in °C, precipitation in mm, source and UTC retrieval time. The API's forecast limit is 16 days; dates beyond it get no invented day-by-day forecast. For distant trips, any seasonal guidance is clearly labeled general guidance. Weather lookup failures do not prevent an itinerary. Open-Meteo's [free API terms](https://open-meteo.com/en/terms) permit non-commercial use subject to limits and attribution; a commercial service needs a suitable paid arrangement.

Currency conversion uses [Frankfurter](https://frankfurter.dev/) daily institutional rates. The displayed `as-of` date is the provider's observation date; Frankfurter does not publish a time of day for each rate. The app also returns its UTC retrieval time. Rates are cached for six hours per server instance, and an expired fallback is explicitly labeled cached if the provider fails. There is no made-up fallback rate. Converted amounts are separate from estimated local costs, and card or exchange fees can change the actual amount paid.

## Deploy on Vercel

1. Push this repository to GitHub. Import it into Vercel with **Root Directory** set to the repository root (leave it blank or `.`), and set the project **Framework Preset** to **Services** in Build and Deployment settings. The top-level `vercel.json` defines two services: `app` (FastAPI, root `.`) and `frontend` (Vite, root `frontend`).
2. In the Vercel project settings, add `GROQ_API_KEY` as a server environment variable for **Production** and **Preview**. `GROQ_MODEL` and `GROQ_FALLBACK_MODEL` are optional server settings. Keep the fallback different from the primary. Do not create a `VITE_GROQ_API_KEY` variable or commit `backend/.env`.
3. Deploy a new commit. Vercel installs the Vite service from `frontend/package-lock.json`, builds it into `frontend/dist`, and loads the FastAPI service from `api.index:app` using the root `requirements.txt`. Public `/api/*` requests go to `app`; all other paths go to `frontend`. Both services are public. There are no service bindings because the Vite output is static and its browser requests use the public same-origin `/api` route; no server-side service calls exist. Check `/api/health`, then send a chat message and a follow-up from the deployed page. If the project was previously imported with `frontend` as its Root Directory, change it to the repository root in **Settings → Build and Deployment → Root Directory**. For local service-mode testing, run `vercel dev -L` from the repository root; `python start.py` and `python start.py --dev` remain available for local development.

The project has no external session database. Vercel follow-ups rely on the browser's session history (up to ten exchanges), so history is local to that browser tab and is cleared when a new conversation starts. If you later need account-wide or long-term history, add a persistent store.

## Verification

`python -m unittest discover -s tests -v`

`npm ci --prefix frontend && npm run lint --prefix frontend && npm run test --prefix frontend && npm run build --prefix frontend`

To check the itinerary layout in a browser, install Playwright's Chromium once with `npx playwright install chromium`, then run `npm run test:browser --prefix frontend`. On Windows, you can instead set `WANDERAI_BROWSER_PATH` to an installed Edge or Chrome executable. The browser test covers the five-day Bhopal table and a seven-day international table at desktop and mobile widths.

The tests use a fake tool-capable LLM and make no paid Groq calls.
The Python and renderer tests, lint check and frontend build run in GitHub Actions on each push and pull request without a Groq key. Run the browser layout test locally with Chromium or Edge.
