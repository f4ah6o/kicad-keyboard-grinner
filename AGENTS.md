# Repository Guidelines

## Project Structure & Module Organization
`src/keyboard_grinner.py` houses the KiCad action plugin that arranges switch footprints along Grin-style curves. Shared helpers and constants live in this module; add new modules under `src/` only when functionality is reusable. Unit tests sit in `tests/`, mirroring the source nomenclature (`test_keyboard_grinner.py`). Reference material lives in the root alongside `README.md` and the `makefile`; keep large assets out of the repo.

## Build, Test, and Development Commands
Use `make lint` to run `uvx ruff check` and catch style regressions. Format the tree with `make fmt`, which delegates to `uvx black .`. Validate changes with `make test`, invoking `uvx pytest`. For ad-hoc runs, prefix commands with `uvx` so they execute inside the project’s virtual environment cache (e.g., `uvx pytest tests/test_keyboard_grinner.py::TestRot2d`).

## Coding Style & Naming Conventions
Write Python with 4-space indentation and prefer explicit imports. Keep functions small and pure when feasible; name helpers in `snake_case` and constants in `SCREAMING_SNAKE_CASE` (e.g., `UNIT_MM`). Follow Black’s default formatting and let Ruff surface lint fixes before committing. Pay attention to docstrings on public helpers that are used by the KiCad GUI layer, and include short comments when math-heavy sections would otherwise be opaque.

## Testing Guidelines
Pytest drives the suite. Add test modules under `tests/` with filenames matching the source (`test_<module>.py`) and descriptive test functions (`test_parse_unit_pair_with_times_separator`). Mock KiCad-specific APIs (`pcbnew`, `wx`) so tests stay hermetic; refer to the existing fixtures in `tests/conftest.py`. Aim to cover new branches in geometry and parsing routines, especially around unit conversions and Bezier calculations, and document any intentional gaps.

## Commit & Pull Request Guidelines
History currently uses concise, imperative commit subjects (e.g., `Initial commit`); continue that style and keep bodies focused on rationale when needed. Group related changes together, and prefer multiple small commits over one large sweep. Pull requests should include: a summary of behavior changes, test evidence (command output or screenshots of KiCad results when UI-visible), and references to issues or discussion threads. Highlight any KiCad configuration assumptions so reviewers can reproduce results locally.

## KiCad Environment Notes
The plugin depends on KiCad’s Python environment providing `pcbnew` and `wx`. When developing outside KiCad, rely on mocks (as the tests do) and avoid importing the module at top level in scripts that lack those bindings. Document any new environment variables or library paths in the README so other designers can load the action plugin without guesswork.
