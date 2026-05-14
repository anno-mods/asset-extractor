# Development Guide

## Environment

```bash
uv sync                  # core deps
uv sync --dev            # + dev tools (nox, pyright, ruff)
uv sync --extra jupyter  # + Jupyter
```

## Code Quality

```bash
uv run nox               # all checks: format, lint, types, tests
uv run nox -s format_fix # format + autofix
uv run nox -s pyright    # type check only
uv run ruff format .
uv run ruff check . --fix
```

## Testing

```bash
test.cmd                 # all tests (also: uv run nox -s test, uv run pytest)
test.cmd -v              # verbose
test.cmd -m buff_ui      # markers: buff_ui | pool | mapping
test.cmd -k recruitment  # keyword filter
test.cmd -x              # stop on first failure
test.cmd --help
```

Test conventions live in `tests/AGENTS.md`.

## Running the Project

```bash
extract.cmd                                    # extract RDA files (after game updates)
uv run python main.py                          # generate asset browser only
uv run python main.py --version "1.0.1"        # browser + snapshot + version report
new_version.bat                                # full release: extract, generate, snapshot, archive, export
```

## Asset Versioning CLI

```bash
uv run python -m assetextractor.versioning snapshot "1.0.0" --description "Launch version"
uv run python -m assetextractor.versioning report   "1.0.0" "1.0.1" --output results/assetbrowser/
uv run python -m assetextractor.versioning diff     "1.0.0" "1.0.1"
uv run python -m assetextractor.versioning export   --output versions.csv
uv run python -m assetextractor.versioning history  --verbose
uv run python -m assetextractor.versioning [cmd] --help
```

## Configuration

`config.json` (see `config.template.json`):
- `game_path` — Anno installation directory
- `cache_path` — extracted files location
- `assetbrowser_dir` — HTML output directory

Paths may be relative (resolved from `config.json` location) or absolute.

## Release Workflow

`new_version.bat`:
1. Prompts for version number.
2. Runs `extract.cmd`.
3. Runs `main.py --version` (generates browser + snapshot + report; loads assets once).
4. Creates `assetbrowser-YYYY-MM-DD.7z` (LZMA2, 1GB dict, level 7) from `config.assetbrowser_dir`.
5. Exports items to Google Sheets (optional, needs `gsheet_credentials.json`).

Requirements: 7-Zip in PATH; Google Sheets credentials are optional.

`main.py --version` details:
- `create_snapshot()` accepts an optional `assets` argument to avoid double-loading.
- Version report is auto-generated when 2+ versions exist in the DB.
- `--prev-version` overrides the default (latest − 1) comparison base.

## Typed Asset Subclasses

Game-domain `Asset` subclasses live in `assetextractor/parsing/typed/`. Each subclass declares its XML template name(s) once (via `template_names=`) and is auto-registered; no other file needs updating. See `assetextractor/parsing/typed/README.md` for the full guide — including multi-template mapping, abstract base conventions, and `BaseAssetGUID` upgrade caveats.

## VS Code

`.vscode/launch.json` ships with:
- "Python Debugger: Main" — runs `main.py`
- "Run converter: Asset Browser"

## Dependencies

- Core: `lxml`, `Jinja2`, `Wand` (optional — only required if image conversion is needed)
- Dev: `nox`, `pyright`, `ruff`, `uv`
- Optional: Jupyter, analysis tools
