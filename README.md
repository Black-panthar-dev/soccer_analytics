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

## How to run

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

The tool is local and offline. It does not include Phase 2 history, comparison,
web, or email-delivery features.
