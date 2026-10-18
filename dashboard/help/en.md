# Help Center (English)

Each article starts with "## Title" followed by a topic marker used by contextual Help buttons.

## What's new in V2.0
<!-- topic: whats-new -->
- **PostgreSQL + pgvector** replace the local SQLite file. All data lives in one local database.
- **Semantic search** over your documents with a local multilingual model (English and Hebrew). Keyword (TF-IDF) search remains as an automatic fallback.
- **Sign-in**: a private owner account plus a separate **demo** account with synthetic data. The two never see each other's data.
- **New pages**: Dashboard (job-search KPIs and charts), Application Tracker (with Excel import/export) and this Help Center.
- **English and Hebrew** interface with right-to-left layout.
- **Nothing runs on its own**: jobs are collected and scored only when you click the buttons in *Job pipeline*.
- The n8n automation integration was removed; collection, scoring and the optional built-in scheduler work without it.

## Getting started and signing in
<!-- topic: getting-started -->
1. Start the stack: `docker compose up -d --build` (see the README for the one-time `.env` setup).
2. Create your login once: `docker compose run --rm tools scripts/create_user.py <username> --workspace personal`. You will be asked for the password twice; it is never shown or stored in plain text.
3. Open http://localhost:8508 and sign in.
4. Optional: `docker compose run --rm tools scripts/seed_demo.py` creates the **demo** login and its sample data.

Your session ends when you click **Log out**, after the inactivity timeout (default 60 minutes, `SESSION_TIMEOUT_MINUTES`), or when you reload the page — the app keeps no login cookie. After several wrong passwords the username is locked for a few minutes.

## Switching language
<!-- topic: language -->
Use the **Language** selector in the sidebar (or on the sign-in screen). The interface switches between English and Hebrew; Hebrew uses a right-to-left layout while code, links and numbers stay left-to-right.

Your choice is saved for your account and restored at your next sign-in. Only the interface is translated: job postings, your documents, your tracker notes and the text produced by the scoring engines (explanations, gaps, action items) are shown as they are.

## Execution modes
<!-- topic: modes -->
The **Execution mode** in the sidebar controls *Analyze External Job*:

- **Hybrid (RAG + Agent)** — career scoring plus supporting evidence from your knowledge base (default).
- **Agent Only** — career scoring only; the knowledge base is not used.
- **RAG Only** — knowledge-base evidence only; no scoring. "Should I apply?" and "Which project?" need scoring, so they ask you to switch mode.

## Collecting and scoring jobs
<!-- topic: jobs -->
Open **Job pipeline** on the Decision Console or Classic Jobs page:

- **Fetch jobs** from the selected source (mock demo data, RSS feeds or Israeli sources). Duplicates are skipped.
- **Score (classic)** — keyword + semantic match score for jobs without a score.
- **Career score** — the multi-factor decision engine (fit score, recommendation label, gaps, action items).
- **Reset job data** deletes this workspace's jobs and scores, then fetches and scores again. It needs a confirmation tick and never touches the tracker, documents or profile.

Nothing is fetched or scored automatically when the application starts.

## Application tracker and Excel
<!-- topic: tracker -->
The **Application Tracker** mirrors the *Job_Search_Tracker.xlsx* workbook: submission date, company, role, track, source, location and work model, salary range, status, notes and closure reason. "Days since submission" is calculated automatically.

- Edit cells directly in the table, add rows at the bottom and delete rows with the row checkbox, then click **Save changes**. Status, track and source are chosen from fixed lists.
- **Import from Excel** accepts the original Hebrew workbook (or an English export). Before anything is saved you see a summary: rows to add, duplicates (same date, company and role), blank rows, rows without company/role, invalid dates and values that do not match the lists. Unknown values and extra columns are kept, never silently dropped.
- **Export to Excel** downloads a workbook with the same sheets, dropdowns and formulas as the original, in the current interface language.

## Dashboard
<!-- topic: dashboard -->
The Dashboard summarises your applications. Filters (date range, track, source) apply to every number and chart on the page.

- **Total submitted** — applications with a submission date.
- **Active processes** — status Submitted, Under review, Initial call, Professional interview or Home assignment.
- **Interviews scheduled** — status Initial call or Professional interview.
- **Home assignments & offers** — status Home assignment or Offer / advanced.

These are the same definitions as the workbook's dashboard sheet. The **pipeline funnel** counts, for each stage, the applications whose *current* status is at that stage or later (rejected and closed applications count only as submitted, because the tracker does not record how far they got). **Needs follow-up** lists active applications with no update for 14 days or more.

## Semantic search and the TF-IDF fallback
<!-- topic: search -->
Documents in your knowledge base are split into chunks and embedded locally with *intfloat/multilingual-e5-small* (384 dimensions, supports English and Hebrew; long chunks are truncated at 512 tokens). Search uses PostgreSQL pgvector cosine similarity.

If the model cannot load, or vector search fails, the app switches to keyword (TF-IDF) search automatically and the Knowledge Base page says so. TF-IDF matches exact words only, so cross-language questions (Hebrew question, English document) work only with semantic search.

Click **Sync knowledge base** after adding, editing or deleting documents: unchanged files are skipped, edited files are replaced and deleted files are removed, so results never contain stale text.

## Personal and demo separation
<!-- topic: workspaces -->
Each login belongs to one **workspace**: your account uses *personal*, the demo account uses *demo*. Both live in the same PostgreSQL database, but every row carries its workspace and the database itself (row-level security) only returns rows of the signed-in workspace — for jobs, scores, documents, tracker rows, profile and preferences. The workspace is taken from your login, never from the browser. The demo account uses synthetic documents and profile files shipped in `demo/`.

## Privacy and local storage
<!-- topic: privacy -->
Everything runs on your machine: PostgreSQL in Docker (data in the `pgdata` volume), the embedding model inside the image, and your documents in `knowledge_base/` (mounted read-only). No API key or cloud service is needed for the core features. Login passwords are stored only as bcrypt hashes in `config/users.yaml`, which is excluded from Git and from the Docker image.

## Backup and restore
<!-- topic: backup -->
Back up the database to a folder outside the Docker volume:

`docker compose exec -T db pg_dump -U career_owner -d career -Fc > backups/career-$(date +%F).dump`

Restore into a running stack (replaces existing objects):

`docker compose exec -T db pg_restore -U career_owner -d career --clean --if-exists < backups/career-YYYY-MM-DD.dump`

Keep backups out of Git (the `backups/` folder is ignored). See *docs/documentation/backup-restore.md* for an optional nightly schedule.

## Troubleshooting and FAQ
<!-- topic: faq -->
**"No login is configured yet."** Create one with `scripts/create_user.py` (see *Getting started*).

**I was signed out.** The session expired after inactivity, or the page was reloaded. Sign in again.

**"Too many failed attempts."** Wait a few minutes; the lock clears automatically.

**Semantic search is unavailable.** Check the error shown on the Knowledge Base page. In Docker the model is part of the image; outside Docker run `python scripts/download_model.py` once.

**The Decision Console is empty.** Open *Job pipeline*, fetch jobs, then run *Career score*.

**The import says some values do not match.** They are kept in the row's extra data and exported back unchanged; pick a value from the list to make them count in the dashboard.

**Where is my data?** In the `pgdata` Docker volume. Removing the volume deletes it, so keep backups.
