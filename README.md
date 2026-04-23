# Foli Data Collector

Python collector for Turku Foli SIRI and alerts data. It stores normalized vehicle
observations, service alerts, collector state, and dated GTFS zip archive metadata in
Turso/libSQL or a local SQLite-compatible file database.

## What It Collects

- SIRI Vehicle Monitoring from `http://data.foli.fi/siri/vm` every 30 seconds.
- Alerts and cancellations from `http://data.foli.fi/alerts` every 5 minutes.
- A dated GTFS zip snapshot from `http://data.foli.fi/gtfs/gtfs.zip` weekly.

Weather data is intentionally not collected in v1.

## Data Attribution and API Use

This project uses Turku region public transport's transit and timetable data from the
Föli open data API.

Data source: Turku region public transport's transit and timetable data, administered by
Turku region public transport. Data is downloaded from <http://data.foli.fi/> and licensed
under [Creative Commons Attribution 4.0 International (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/).

Any published datasets, analysis outputs, dashboards, notebooks, or derived files based on
this collector's Föli API data should retain this attribution.

Föli's API docs also state that the open interface can be used without registration, but
clients should use the service appropriately, avoid unnecessary load, support gzip handling,
and use an identifying `User-Agent` where possible. The default 30-second SIRI VM polling
interval is intentionally conservative.

References:

- [Föli open data API documentation](https://data.foli.fi/doc/index-en)
- [Föli API policies and recommendations](https://data.foli.fi/doc/linjaukset-en)
- [Föli open data page](https://www.foli.fi/en/looking-for-these/about-f%C3%B6li/open-data)

## Local Setup

Copy `.env.example` to `.env` and edit the database and User-Agent values.

This project uses [`uv`](https://docs.astral.sh/uv/) for dependency management.
`uv sync` creates and updates the local `.venv`; activating it is optional.

For local development without Turso, this works:

```env
TURSO_DATABASE_URL=file:data/foli.db
TURSO_AUTH_TOKEN=
```

For Turso, set:

```env
TURSO_DATABASE_URL=libsql://your-db.turso.io
TURSO_AUTH_TOKEN=your-token
```

Windows PowerShell:

```powershell
uv sync
uv run foli-harvester init-db
uv run foli-harvester collect
```

WSL or Linux:

```bash
uv sync
uv run foli-harvester init-db
uv run foli-harvester collect
```

## Commands

```bash
uv run foli-harvester init-db
uv run foli-harvester collect
uv run foli-harvester fetch-gtfs-once
uv run foli-harvester healthcheck
```

`collect` automatically creates the schema on startup, but `init-db` is useful for
checking credentials before running the long-lived process.

## Blackout Recovery

The collector records persistent source state in `collector_state` and uses a renewable
database lease in `collector_lock`. If the laptop shuts down, WSL stops, the process dies,
or a Docker container restarts, the next collector process resumes from the saved state.

Missed SIRI VM and alert observations are not backfilled because Foli exposes current
snapshots, not a historical stream. The next successful poll records
`gap_seconds_since_previous_success` so analysis can identify blackout windows.

Only one active collector should write at a time. If a second process starts while a live
lease exists, it exits with a clear error. If the previous process died and the lease
expired, the new process takes over.

## Runtime Supervision

### Windows Task Scheduler

After syncing the uv environment:

```powershell
uv sync
.\scripts\register-windows-task.ps1
```

The task starts at logon and restarts the collector after failures. The task runs:

```powershell
.\.venv\Scripts\foli-harvester.exe collect
```

### WSL

Use Linux `systemd --user` inside WSL if systemd is enabled. Otherwise create a Windows
scheduled task that launches WSL:

```powershell
wsl.exe --cd /home/<user>/omat/foli-data-collector -- .venv/bin/foli-harvester collect
```

### Linux systemd

Edit `scripts/foli-harvester.service` so `WorkingDirectory` and `ExecStart` match your
repo path, then install it as a user service:

```bash
mkdir -p ~/.config/systemd/user
cp scripts/foli-harvester.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now foli-harvester.service
systemctl --user status foli-harvester.service
```

### Docker Alternative

Docker is optional. It uses the same application code, `.env`, and persistent `./data`
directory:

```bash
docker compose up -d
docker compose logs -f
```

The compose service uses `restart: unless-stopped` and the image healthcheck runs:

```bash
foli-harvester healthcheck
```

## Build Windows EXE Locally

The project can be packaged as a simple portable Windows folder.

Sync a Windows uv environment with the build dependencies:

```powershell
uv sync --python 3.14 --group build
```

Build the portable EXE folder:

```powershell
.\scripts\build-windows-exe.ps1
```

The output is:

```text
dist\foli-harvester\
```

That folder contains `foli-harvester.exe`, `.env.example`, and simple command wrappers:

```powershell
.\dist\foli-harvester\foli-harvester.exe --help
.\dist\foli-harvester\init-db.cmd
.\dist\foli-harvester\collect.cmd
.\dist\foli-harvester\healthcheck.cmd
.\dist\foli-harvester\fetch-gtfs-once.cmd
```

Before running the EXE with private configuration, copy the example file inside the output
folder:

```powershell
Copy-Item .\dist\foli-harvester\.env.example .\dist\foli-harvester\.env
```

Then edit `dist\foli-harvester\.env`. Keep the default `file:data/foli.db` value for local
SQLite storage, or add your own Turso URL and token. The EXE looks for `.env` beside
`foli-harvester.exe` before falling back to the current working directory.

Private credential policy:

- `.env` is ignored by Git and is not copied into the portable EXE folder.
- Turso keys are never baked into the EXE.
- Anyone receiving the EXE must use their own `.env` or the default local SQLite database.

## GTFS Archive Strategy

GTFS files are stored under `data/gtfs/` with UTC download-date filenames such as:

```text
gtfs_2026-04-22.zip
gtfs_2026-04-22_2.zip
```

The database records the exact filename, sha256, ETag, and server `Last-Modified` header
when available. Use `last_modified` as the best schedule-version signal. The
`download_service_date` is only the collector download date, not necessarily the effective
start date of the GTFS schedule.

## Development

```bash
uv sync --group dev
uv run python -m unittest discover -s tests
uv run pytest
uv run ruff check .
```

Optional live API smoke tests should be run manually so CI does not depend on Foli uptime.

## License

This project's source code is licensed under the [MIT License](LICENSE).

Föli API data collected by this project is separate from the code license and is licensed
by its data provider under CC BY 4.0, with attribution requirements described above.
