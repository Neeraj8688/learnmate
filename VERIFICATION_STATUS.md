# Verification status (what has actually been run)

Environment for all runs below: Linux sandbox, Python 3.13, Node 22, Chromium via Playwright, no Docker daemon,
no access to Hugging Face or Google. Gemini was **mocked**; no real key was used and no real quota was spent.

| Item | Status | Evidence |
|---|---|---|
| Backend tests | Verified | `python -m pytest -q` -> 81 passed (49 earlier tests updated + 32 new) |
| New tests mutation-checked (refund, personal-quota isolation, HTTPS rule) | Verified | each deliberate bug made the right test fail |
| Gemini failure handling: daily quota, per-minute 429, ambiguous 429 escalation, 503 retry, network, invalid key, shared-key rejected, blocked answer, bad model | Verified (mocked HTTP) | tests/test_gemini_and_limits.py |
| Shared key never in API responses/logs; personal key never in responses, logs or SQLite | Verified | tests + server-log grep after browser run |
| No silent fallback from personal key to shared key | Verified | tests + browser run |
| Demo limits: question length, daily per-user/global, request rate, upload size | Verified | tests |
| Auth, tenant isolation (docs, vectors, quizzes, attempts, tasks) | Verified | existing + updated tests |
| Production config checks, exact-origin CORS, HTTPS-only personal keys | Verified | tests + live server run on `PORT=10000` |
| Dockerfile start command on host-provided PORT | Verified (same command via uvicorn shim) | `curl /health` on port 10000 |
| Real Chromium run against the real backend (36 checks): Markdown (headings, bold/italic, lists, table, blockquote, code), inline+display KaTeX, no chunk IDs, readable sources, citation click, unsupported question, 503 retry, per-minute 429, network error, quota dialog, invalid key, personal-key retry of the same question with chat preserved, no shared key after switching, personal quota inline, quiz/results/weak topics/plan, disconnect | Verified (Gemini mocked) | Playwright, 0 page errors |
| Production frontend build: no `localhost:8000` in bundle; missing `VITE_API_BASE_URL` shows a banner and makes no localhost requests | Verified | build + Playwright |
| `docker compose config` for both compose files; `render.yaml` parses and its env passes production startup checks | Verified (syntax/config only) | commands run |
| Secret scan of the source tree and ZIP | Verified | `scripts/scan_secrets.py` |
| `docker compose up --build` (images build, containers start) | **Not verified** | no Docker daemon here: run the PowerShell commands in README.md |
| Real Gemini API: model name, real 429/503/invalid-key response bodies | **Not verified** | Google documents 429 `RESOURCE_EXHAUSTED` and 503 `UNAVAILABLE` but not the 429 body fields; the quota-vs-rate-limit split is a best-effort parse plus a 3-strike rule. Test with a real key |
| Real embedding model, retrieval quality, `MIN_RELEVANCE` | **Not verified** | Hugging Face unreachable here |
| Render deploy: RAM fit on 512 MB, proxy headers (`https_detected`, `client_ip`), disk behaviour | **Not verified** | needs a real deploy; see DEPLOY.md section 3 step 5 |
| Vercel deploy | **Not verified** | needs a real deploy |
| Email verification, password reset, CAPTCHA, monitoring | Not built | |
