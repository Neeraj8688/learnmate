# Deploying LearnMate: Vercel (frontend) + Render (backend)

Facts below marked "checked" come from the providers' official docs as read on 2026-10-21; anything marked
UNVERIFIED could not be confirmed and has a way to check after you deploy.

## 1. What the app stores (inspected in the code)

| Data | Where | Survives a restart on Render **free**? |
|---|---|---|
| Accounts, quizzes, attempts, revision plans | SQLite file (`SQLITE_PATH`) | **No** (checked: free disk is wiped on every redeploy, restart and idle spin-down) |
| Document chunks + embeddings | ChromaDB folder (`CHROMA_PERSIST_DIRECTORY`) | **No** |
| Raw uploaded PDFs | **Never saved.** Text is extracted in memory, chunked and indexed; the PDF itself is discarded. | n/a |
| Login-token secret | `JWT_SECRET` env var (required in production) | Yes (it is an env var, not a file) |
| Personal Gemini keys | **Nowhere on the server.** Browser tab (`sessionStorage`) -> request header -> memory only. Any key saved by an older version is wiped from SQLite at startup. | n/a |

## 2. Hosting reality check (read before choosing a plan)

* **Render free web service** (checked): 512 MB RAM, spins down after 15 minutes idle (first request afterwards
  takes about a minute), ephemeral disk, one instance, 750 free hours/month, no persistent disk.
* **Memory is the bigger risk.** The backend loads PyTorch + a sentence-embedding model + ChromaDB. That very likely
  needs more than 512 MB. I could not measure it in my sandbox (model download blocked). Measure it yourself:
  ```powershell
  docker compose up -d --build
  # upload a PDF in the UI and ask one question, then:
  docker stats --no-stream
  ```
  If the backend container is anywhere near 450 MB or above, the free plan will crash (out of memory).
* **Paid options** (Render pricing page, checked): `0.5c-512mb` $7/mo (same RAM as free), `1c-2g` $25/mo (2 GB). Persistent
  disks are a paid feature (Render's pricing page did not say which instance types support them; confirm in the dashboard).

Your realistic choices:

| Option | Works? | Cost | Change needed |
|---|---|---|---|
| A. Free plan as a **demo** | Only if measured RAM fits; data resets constantly; ~1 min cold start | $0 | None. Keep `EPHEMERAL_STORAGE_NOTICE=true` so visitors see a notice |
| B. Paid instance (e.g. `1c-2g`) + persistent disk | Yes, simplest durable setup | paid | Uncomment the `disk:` block and the two path env vars in `render.yaml`; set `EPHEMERAL_STORAGE_NOTICE=false`. Single instance only |
| C. Postgres + hosted vector DB | Durable and scalable | varies | **Not done.** Needs a rewrite of `db.py` and `vectorstore.py`. Ask if you want it |

## 3. Deploy the backend on Render

1. Push the project to a **private** GitHub repo (see section 6 first).
2. Render dashboard -> **New -> Blueprint** -> pick the repo. It reads `render.yaml` (service `learnmate-api`, Docker,
   Dockerfile `./backend/Dockerfile`, context `./backend`, health check `/health`).
   Manual alternative: **New -> Web Service -> Docker**, Dockerfile path `./backend/Dockerfile`, Docker context `./backend`.
3. When prompted, set the secrets (they exist only in Render, never in Git):
   * `GEMINI_API_KEY` = your shared demo key (create at https://aistudio.google.com/apikey)
   * `CORS_ORIGINS` = your exact Vercel origin, e.g. `https://learnmate-yourname.vercel.app` (no trailing slash).
     You will know the real value after step 4; you can leave a placeholder now and edit it later.
   `JWT_SECRET` is generated automatically. The app listens on Render's `PORT` (default 10000) on `0.0.0.0` (checked).
4. After the first deploy copy the service URL, e.g. `https://learnmate-api.onrender.com`.
5. Open `https://YOUR-BACKEND/health` in a browser and check (these two settings are UNVERIFIED for Render because its
   docs do not describe the proxy headers):
   * `"https_detected": true`. If it says false, personal keys will be rejected with `https_required`. Fix: this means Render
     is not sending `X-Forwarded-Proto`; set `REQUIRE_HTTPS_FOR_KEYS=false` (Render already forces HTTPS at its edge).
   * `"client_ip"` should be **your** public IP. If it shows a private/Render address, per-IP login throttling would treat
     every visitor as one person; try `TRUSTED_PROXY_HOPS=2`, or `TRUST_PROXY_HEADERS=false` and raise `RATE_AUTH_PER_MIN`.

## 4. Deploy the frontend on Vercel

1. Vercel -> **Add New -> Project** -> import the same repo.
2. **Root Directory: `frontend`**. Framework preset: Vite. Build command `npm run build`, output `dist`
   (also set in `frontend/vercel.json`, which adds the single-page-app rewrite).
3. **Environment variable** (Production, and Preview if you use previews): `VITE_API_BASE_URL` = your Render URL
   (public URL only, no trailing slash needed). It is baked in at build time, so **redeploy after changing it**.
4. Deploy, copy the Vercel URL, then set `CORS_ORIGINS` on Render to exactly that origin and let Render redeploy.
   Preview deployments get different URLs; add them to `CORS_ORIGINS` (comma separated) only if you need them.
   The app refuses to start in production with `*` or non-`https://` origins.

If `VITE_API_BASE_URL` is missing or still points at localhost, the site shows a red configuration banner instead of
silently calling localhost.

## 5. Post-deploy test checklist
1. Register, upload a small PDF, ask a question: answer renders Markdown, citations `[1]` link to a Sources list showing
   file name and page, with no internal IDs.
2. Browser DevTools -> Network: every request goes to your Render URL, none to `localhost`.
3. Ask something unrelated to your notes: "not in your notes", and no Gemini call is made.
4. **Test the quota path without spending real quota:** temporarily set `DAILY_LLM_CALLS_PER_USER=1` on Render, ask two
   questions: the second shows the "Demo allowance used" dialog. Connect a (test) personal key; your question is retried.
   Restore the value afterwards.
5. Free plan only: wait 15+ minutes; the first request shows "Waking server..." and your account/notes are gone (expected).

## 6. Secrets and repository hygiene
* `.env` is in `.gitignore`, `.dockerignore` and excluded from the release ZIP. Only `.env.example` (placeholders) ships.
* Before every push or ZIP: `python scripts/scan_secrets.py` (and `python scripts/scan_secrets.py learnmate_fixed.zip`).
  It is a heuristic, not a guarantee.
* First push (PowerShell): `git init; git add .; git status` and confirm no `.env`, `data/`, `*.db`, `.venv`, `node_modules`
  appear; then `git commit -m "Initial commit"`.
* **If a real key was ever committed, pasted in chat, or put in a `VITE_` variable: rotate it now** (create a new key in
  Google AI Studio, delete the old one) and update `GEMINI_API_KEY` on Render. Removing it from Git history alone is not enough.
  The upload I received contained only placeholder values, but I cannot see your Git history.
* Keeping the shared key only on the backend stops it being copied out of the web page (Google's docs say keys in client-side
  code can be extracted). It does **not** make it unabusable: the per-user and site-wide daily limits, request-length limit,
  upload limit, rate limits and the pause-on-confirmed-quota behaviour are what protect your quota. Tune them to your real
  Gemini limits (AI Studio shows them; Google's docs say quotas are per project, reset at midnight Pacific).
* A visitor's personal key lives in their browser tab and travels in a request header over HTTPS. A malicious script on the
  page (XSS) could read it, which is why raw HTML in model output is disabled and the page loads no third-party scripts.

## 7. Rollback
Render: Deploys -> pick a previous deploy -> Rollback. Vercel: Deployments -> Promote a previous deployment.
