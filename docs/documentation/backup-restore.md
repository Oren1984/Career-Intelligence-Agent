# Backup and restore

All application data (jobs, scores, knowledge-base chunks, tracker, profile overlay, preferences) lives in the PostgreSQL volume `pgdata`. Back it up to the `backups/` folder in the project. That folder is outside the Docker volume and is ignored by Git. Your credentials (`config/users.yaml`), `.env` and documents (`knowledge_base/`) are plain files, so back them up with your normal file backup.

The commands below were verified with Docker Compose, including a full delete-and-restore round trip. Use your own `POSTGRES_USER` / `POSTGRES_DB` values if you changed them. In Git Bash on Windows, run `export MSYS_NO_PATHCONV=1` first so `/tmp/...` paths are passed through unchanged. PowerShell and Linux/macOS shells need nothing extra.

## Back up

```bash
docker compose exec -T db pg_dump -U career_owner -d career -Fc -f /tmp/career.dump
docker compose cp db:/tmp/career.dump backups/career-2026-10-18.dump
```

`-Fc` is PostgreSQL's compressed custom format. The dump includes the row-level-security policies and the application role's grants.

## Restore

Restoring replaces the current data. Stop the app first so nothing writes during the restore:

```bash
docker compose stop app
docker compose cp backups/career-2026-10-18.dump db:/tmp/restore.dump
docker compose exec -T db pg_restore -U career_owner -d career --clean --if-exists /tmp/restore.dump
docker compose start app
```

To restore onto a brand-new volume, run `docker compose up -d db migrate` first. That creates the database and the application role. Then run the restore commands above.

## Optional: nightly backup

Nothing is scheduled automatically. If you want a nightly dump, add one of the following yourself.

**Linux / macOS (cron)** — `crontab -e`, then:

```cron
30 2 * * * cd /path/to/Career-Intelligence-Agent && docker compose exec -T db pg_dump -U career_owner -d career -Fc -f /tmp/career.dump && docker compose cp db:/tmp/career.dump backups/career-$(date +\%F).dump
```

**Windows (Task Scheduler)** — create `backup.ps1` in the project folder:

```powershell
Set-Location $PSScriptRoot
docker compose exec -T db pg_dump -U career_owner -d career -Fc -f /tmp/career.dump
docker compose cp db:/tmp/career.dump "backups/career-$(Get-Date -Format yyyy-MM-dd).dump"
```

and register it once:

```powershell
schtasks /Create /TN "CareerAgentBackup" /SC DAILY /ST 02:30 /TR "pwsh -File C:\path\to\Career-Intelligence-Agent\backup.ps1"
```

Delete old dumps from time to time, and copy the `backups/` folder to another disk if you want protection against disk failure.

## What not to do

- `docker compose down -v` **deletes** the `pgdata` volume and all data. Use plain `docker compose down` to stop the stack.
- Do not commit dumps. `backups/` and `*.dump` are ignored by Git and excluded from the Docker build context.
