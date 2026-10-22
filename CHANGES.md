# What changed in this version

## 1. Chat rendering and citations
* `frontend/src/markdown.jsx` (new): react-markdown + remark-gfm (tables) + remark-math + rehype-katex + KaTeX CSS.
  Raw HTML is disabled. `\(..\)` / `\[..\]` and one-line `$$..$$` are normalised to proper inline/display math. Loaded
  lazily (separate ~130 kB gzip chunk) so the first page stays small.
* `backend/app/services/answer.py` (new): the model now sees sources as numbered `[1] (file, page N)`, never chunk IDs.
  Replies are post-processed: stray chunk IDs become `[n]` or are removed, and citations to nonexistent sources are removed.
* `frontend/src/components.jsx` `Sources`: shows `1 · file.pdf · page 10` plus the excerpt; chunk IDs are no longer displayed
  anywhere. `[n]` in the answer is a clickable superscript that opens the matching source.
* Quiz questions and result explanations also render Markdown/math.

## 2. Shared Gemini key and personal-key fallback
* `GEMINI_API_KEY` / `GEMINI_MODEL` are the new backend-only settings (`LLM_*` still works as a fallback alias).
* `backend/app/llm/base.py`, `gemini.py` (rewritten): separate errors for confirmed quota, temporary rate limit, invalid key,
  HTTP 503 (one automatic retry), network failure, empty/blocked answer. Messages never contain keys or raw provider text.
* `backend/app/deps.py` (`LLMGate`): demo budgets and request limits for the shared key; confirmed quota exhaustion pauses the
  shared key (`ratelimit.py` `SharedQuota`); failed calls refund the demo allowance; personal-key failures never fall back
  to the shared key.
* `backend/app/errors.py` (new): errors are JSON `{"detail": "<message>", "code": "<stable code>"}`.
  Codes: `shared_quota_exhausted`, `demo_limit_reached` (these two open the key dialog), `personal_quota_exhausted`,
  `invalid_api_key`, `provider_unavailable`, `provider_network_error`, `provider_rate_limited`, `server_ai_misconfigured`,
  `question_too_long`, `https_required`.
* Personal keys: browser tab session -> `X-LLM-Key` header -> request memory. **Removed**: saving keys encrypted in SQLite
  (`PUT/DELETE /me/llm-key`, `/me/llm-key/test`, `ENCRYPTION_KEY`, the `cryptography` dependency). Existing saved keys are wiped
  at startup. In production keys are accepted only over HTTPS.
* Frontend: `KeyModal.jsx` (dialog only for the two exhaustion codes, retries your last question after connecting),
  `ConnectAI.jsx`, `Chat.jsx`, `Account.jsx`, status pill in `App.jsx`. Other errors are shown inline with Try again.
* Limits (all env-configurable): demo and personal question length, daily calls per user and site-wide, request rate,
  upload size, documents per user.

## 3. Deployment preparation
* `render.yaml` (new), `frontend/vercel.json` (new), `frontend/.env.example` (new), `DEPLOY.md` (rewritten).
* `backend/Dockerfile`: listens on `${PORT:-8000}`. Frontend uses `VITE_API_BASE_URL` (old `VITE_API_URL` still read); production
  builds show a config banner instead of calling localhost.
* `backend/app/config.py`: `ENVIRONMENT=production` refuses to start without a 32+ char `JWT_SECRET` or with `*`/non-https CORS
  origins. CORS is the exact configured origin(s) and exposes `Retry-After`.
* Client IP for rate limiting now uses the Nth-from-right `X-Forwarded-For` entry (`TRUSTED_PROXY_HOPS`) instead of the
  spoofable left side. `/health` reports `https_detected`, `client_ip`, `ephemeral_storage` for post-deploy checks.
* UI notices for free hosting: "Waking server..." and a demo-storage warning (`EPHEMERAL_STORAGE_NOTICE`).

## 4. Repository safety
`.gitignore`, `backend/.dockerignore` tightened; `.env.example` placeholders only; `scripts/scan_secrets.py` (new);
the release ZIP excludes `.env`, databases, vector data, logs, `node_modules`, virtual environments.

## API changes to know about
* Error bodies gained `code` (`detail` unchanged and still a string).
* `GET /me`: removed `has_own_key`, `provider`, `model`, `key_hint`.
* `POST /chat` / `/agent` answers: `sources[].ref` added; `agent` AI errors are now coded HTTP errors, not a `budget_exceeded` result.
* Removed endpoints listed above. Added `POST /llm/check`. Header `X-LLM-Provider` is accepted only as `gemini`.
* OpenAI/OpenRouter/Groq personal-key adapters were removed (unverified code; Gemini is the supported provider).

## Files modified
Backend: `app/config.py, db.py, deps.py, main.py, ratelimit.py, schemas.py, security.py`, `app/llm/{__init__,base,gemini}.py`,
`app/routers/{agent,auth,chat,health}.py`, `app/services/{quiz,tools}.py`, `requirements.txt`, `Dockerfile`, `.dockerignore`;
new `app/errors.py`, `app/services/answer.py`, `tests/test_gemini_and_limits.py`; removed `app/llm/openai_compat.py`;
tests updated: `test_auth_security.py`, `test_day2.py`.
Frontend: `src/{App.jsx,api.js,components.jsx,styles.css}`, `src/pages/{Account,Chat,ConnectAI,Quiz,Results}.jsx`, `package.json`,
`Dockerfile`; new `src/markdown.jsx`, `src/pages/KeyModal.jsx`, `vercel.json`, `.env.example`.
Root: `.env.example, .gitignore, docker-compose.yml, docker-compose.prod.yml, README.md, DEPLOY.md, VERIFICATION_STATUS.md`;
new `render.yaml, CHANGES.md, scripts/scan_secrets.py`.
