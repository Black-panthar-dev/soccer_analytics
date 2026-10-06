# Sogility GO Athlete Report Generator

This offline tool combines A-CHAMPS assessment results, the master player roster,
and juggling scores to generate individualized Sogility GO athlete assessment
reports. Each eligible athlete receives a Page 1 radar summary, a Page 2
performance table, and a combined two-page PDF.

## Requirements

- Python 3.11 or newer
- Dependencies listed in `requirements.txt`

Install dependencies from the project folder:

```text
python -m pip install -r requirements.txt
```

## Input files and folders

- A-CHAMPS hardware CSV: `data/hardware/`
- Master Player Roster CSV: `data/roster/`
- Juggling Scores CSV: `data/juggling/`
- Report templates: `templates/`
- Sogility and club logos: `logos/`

The expected input filenames are configured in `config/config.json`. Keep an
unchanged backup of every source file; the generator never needs the original
CSVs to be edited.

## 1. Generating reports

### Windows

Double-click `run_generate_reports.bat`, or run it from Command Prompt.

### macOS

The first time only, allow the launcher to run:

```text
chmod +x run_generate_reports.command
```

Then double-click `run_generate_reports.command` or run it from Terminal.

Both launchers regenerate the analytical data and final reports from the
currently configured source files. To rerun after replacing an input file,
place the new CSV in the appropriate input folder using the configured filename
and run the launcher again.

## Generated reports

Final files are written to:

- Page 1 PNGs: `output/final/png/page1/`
- Page 2 PNGs: `output/final/png/page2/`
- Combined PDFs: `output/final/pdf/`

Run records are written to:

- `output/final/report_manifest.csv`
- `output/final/batch_summary.csv`
- `output/final/failed_reports.csv`
- `output/final/generation_log.txt`

Additional validation CSVs are written under `output/`, while detailed audit
artifacts used by the calculation pipeline are written under `output/debug/`.

## Missing and unmatched records

Missing measurements are displayed as `N/A` in the performance table and as
gaps in the radar chart; they are never converted to zero. Records without an
authoritative roster match or age group are excluded from report generation and
remain visible in validation and matching outputs. Matching is conservative:
ambiguous or unresolved identities are not fuzzy-matched automatically.

## Configuration and overrides

`config/config.json` controls input filenames, relative paths, metric settings,
template placement, and logo defaults. Paths are relative to the project folder
so the package can be moved between supported computers. This local file is
excluded from version control because it can contain client-specific settings.
For a new checkout, copy `config/config.example.json` to `config/config.json`
and update it for the local input files.

Confirmed client corrections can be recorded under
`client_overrides.roster_age_groups` without changing the source roster. Each
entry uses a normalized athlete name, the confirmed age group, and a reason.
Keep client-specific corrections in the local configuration file.

The `team_logos` object can map teams to logo files stored in `logos/`, and
`logo_defaults.team_logo` provides a fallback. The current STLDA Page 1 template
already contains its header logos, so `page1_club_logo_overlay` is disabled to
prevent duplication. It can be enabled for a future template that needs a
dynamic club logo.

## Verification

Inspect the three source types without modifying them:

```text
python -m src.inspection
```

Run the automated tests:

```text
python -m pytest -q
```

## Troubleshooting

- If Python is not found, install Python 3.11 or newer and reopen the terminal.
- If a module is missing, rerun `python -m pip install -r requirements.txt` from
  the project folder.
- If an input file is reported missing, confirm its filename matches
  `config/config.json` and that it is in the correct `data/` subfolder.
- If an athlete is not generated, review `output/validation_details.csv`,
  `output/final/failed_reports.csv`, and `output/final/generation_log.txt`.
- If a report has `N/A` values, check the source assessment data. Missing values
  are intentionally preserved and are not calculation failures.
- A rerun safely rewrites the manifest and same-named report files. Remove or
  archive an old `output/final/` folder first if a completely clean delivery set
  is required.

Production reports are delivered separately under `output/final/`; they are not
embedded in the code/tool ZIP.

## 2. Dry run

Email delivery is a separate, deliberate operation. Generating reports never
sends email. Review the complete recipient plan first:

```text
python -m src.email_send_cli --dry-run
```

**DO NOT run `--live-send` until the recipient dry-run has been reviewed.** A
shared parent address receives one message containing all reports assigned to
that address.

## 3. Test email

Follow `CLIENT_SETUP_GOOGLE_EMAIL.md`, set a controlled `test_recipient` in
`config/email_settings.json`, and run:

```text
python -m src.email_send_cli --test-send
```

This sends exactly one test message only to that configured address. The Google
account authorized in the browser is the sender; the tool never stores the
account's normal password.

## 4. Live email delivery

Live delivery requires all three safeguards: `live_send_enabled` set to `true`,
the explicit command below, and the exact dynamic confirmation phrase displayed
by the CLI:

```text
python -m src.email_send_cli --dry-run
python -m src.email_send_cli --live-send
```

Successful deliveries are logged and protected against accidental duplicates.
Failed deliveries remain retryable; force resend is a separate explicit option.
Google credentials and tokens remain local and private. Workspace administrator
approval may be required. See `PHASE2_EMAIL_HOW_TO_USE.md` for operator details.

## Historical comparisons

The data model supports multiple dated assessments. When history exists, reports
compare the latest assessment with the immediately previous assessment and add a
third page. Current production data contains only one genuine assessment date,
so current production reports remain two pages; comparison pages begin when a
second dated assessment dataset is supplied.
