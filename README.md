# WanderAI

A React and FastAPI travel planner using a LangGraph agent and Groq. It supports conversation follow-ups, curated notes for 21 Indian destinations, general packing lists and static per-person INR budget estimates. Estimates exclude transport to the destination, taxes and seasonal changes. No live prices, weather, hours, booking or availability data is provided.

## Requirements

Python 3.10+ and Node.js 20.19+ or 22.12+ (npm included). Tested locally with Python 3.13 and Node 24. Vercel uses Python 3.13 via `.python-version`. The Groq API key stays on the Python server.

## Setup

1. Install Python dependencies: `python -m pip install -r requirements.txt`
2. Copy `backend/.env.example` to `backend/.env` and put your real `GROQ_API_KEY` there. Alternatively, set `GROQ_API_KEY` in the server environment. `GROQ_MODEL` defaults to `openai/gpt-oss-120b`; choose a different tool-calling model if your Groq project permits it.
3. Run `python start.py`. The launcher runs `npm ci` from the repository root on first run, builds the frontend, starts FastAPI on port 8000, and opens http://localhost:8000. Use `python start.py --rebuild` after frontend changes.
4. For Vite hot reload run `python start.py --dev`. Vite serves http://localhost:5173 and proxies `/api` to FastAPI on port 8000. Run `python start.py --no-browser` to keep the browser closed.

The optional legacy Streamlit interface uses the same Groq agent. Install `streamlit` separately, then run `streamlit run Agent_app.py`.

## API

- `GET /api/health` → `{"status":"ok","provider_configured":true|false}`. This does not call Groq.
- `POST /api/chat` with `{"message":"Plan three days in Jaipur", "session_id":null, "history":[]}` → `{"session_id":"UUID", "reply":"..."}`. Reuse the returned ID for follow-ups. On Vercel, send prior visible turns in `history` as alternating user and assistant objects, for example `[{"role":"user","content":"Plan Jaipur"},{"role":"assistant","content":"Here is a plan"}]`; the React app does this automatically.
- `POST /api/clear` with `{"session_id":"UUID"}` → `{"session_id":"UUID", "cleared":true}`.

Messages must be 1–4000 characters after trimming. Local sessions are held in process memory and vanish on restart. Calls within one local session are serialized; different sessions are isolated. Vercel functions use a stateless path because instances can change between requests: the browser sends up to ten complete visible exchanges for context. Only user and assistant text travels to the browser; tool calls, tool results and Groq credentials remain server-side. Clearing removes the browser's history. API documentation is at `/docs` locally.

## Deploy on Vercel

1. Push this repository to GitHub. Import it into Vercel with **Root Directory** set to the repository root (leave it blank or `.`), not `frontend/` or `backend/`.
2. In the Vercel project settings, add `GROQ_API_KEY` as a server environment variable for **Production** and **Preview**. Set `GROQ_MODEL` only if you need a different accessible tool-calling model; the default is `openai/gpt-oss-120b`. Do not create a `VITE_GROQ_API_KEY` variable or commit `backend/.env`.
3. Deploy. Vercel installs packages using the repository root `package-lock.json`; `vercel.json` runs `npm run build` to create `frontend/dist` and configures `api/index.py` as the Python function. Vercel installs the root `requirements.txt` for that function. Check `/api/health`, then send a chat message and a follow-up from the deployed page. If the project was previously imported with `frontend` as its Root Directory, change it to the repository root in **Settings → Build and Deployment → Root Directory** and redeploy.

The project has no external session database. Vercel follow-ups rely on the browser's session history (up to ten exchanges), so history is local to that browser tab and is cleared when a new conversation starts. If you later need account-wide or long-term history, add a persistent store. Deployment itself is not performed by this repository's local checks.

## Verification

`python -m unittest discover -s tests -v`

`npm ci && npm run lint && npm run build`

The tests use a fake tool-capable LLM and make no paid Groq calls.
The same tests, lint check and frontend build run in GitHub Actions on each push and pull request without a Groq key.
