# Contributing to Canali

Thank you for your interest in contributing to Canali! Code, data checks, bug reports and ideas are all welcome.

The best place to start is an [open question](docs/open-questions.md). If you
are unsure where to begin, or want to check an idea before working on it,
[open an issue](https://github.com/whitehml/canali/issues).

How each module works and how to run it is in its own README; the [root README](README.md) maps them all. The rest of
this guide covers what's expected of a contribution. The short version:

> Use whatever tools help you. Explain to me why yourself, send changes in pieces a person can read, and leave nothing
> behind that the repository does not need.

## Why these rules?

I review every pull request myself, and I ask contributors to be respectful of the effort that review takes. Each review
weighs whether the problem is real, whether the approach is right, whether the work is on task and in scope for Canali,
and whether its claims are backed by evidence.

A polished pull request used to be a sign that its author understood the problem. It no longer is, now that tools
produce tidy code, tests and descriptions quickly. The rules below ask for two things instead:

1. **Visible thought and effort.** A contribution should show that someone understood the problem, not only that code
   was produced.
2. **Design for human review.** A contribution should arrive in pieces a person can read, understand and judge, one at
   a time.

## What does a pull request look like?

### Size

- **A small change is a single pull request.**
    - It changes about 800 lines at most. `uv.lock` and generated files do not count.
    - It merges into `dev`.
- **A larger feature gets a branch of its own.**
    - Branch `feature/<name>` off `dev`.
    - Send the feature in chunks, each its own pull request of about 800 lines at most, merged into the feature branch
      and reviewed alone.
    - When the feature branch is complete it is rebased onto `dev`.
    - I recommend opening an issue first, saying why the feature is needed and how you plan to split it.

### Description

You can format the PR description however you want so long as you include:
- The *Why*, what is the problem or need being solved, in your own words. You must write it yourself, without an LLM.
- The *What* in a brief summary of the change.

### Commits

Make commits however you want, but before a PR merges, reorder and squash its commits into atomic chunks, and force-push. Pull requests are rebased onto `dev`.

### Licensing

**By opening a pull request, you agree to license your contribution under the [MIT License](LICENSE).**

### Plans

**LLM plans stay local by default.** Keep them in `plans/`, which git ignores. To collaborate on one for a particular feature branch, commit it with `git add -f` on
the pull request's branch, then drop those commits when you reorder before merging, so the plan never reaches `dev`.

## What about LLMs?

It's fine to use LLMs without attribution for any part of a contribution except the initial "Why". You are responsible for your LLM and for not polluting the repository context. **A pull request must not contain anything the repository does not need**, such as:

- comments that narrate the change or state the obvious
- leftovers: debug output, scratch scripts, notebooks, sample outputs, unused helpers, commented-out code
- experiments that were never formalized into `analysis`
- speculative code: abstractions, options, fallbacks or error handling for cases that do not exist yet
- tests or documentation that restate the code, are repeated in a centralized location, or otherwise easily rot

## What if a pull request misses the mark?

**I may close a pull request that breaks these rules**, with a pointer to this guide and no further explanation. It is
not a verdict on you or the idea: fix it and reopen it if you wish.

## How do I get set up?

You need [uv](https://docs.astral.sh/uv/) and Python 3.12.

```
uv sync --all-packages      # create .venv, install every module and the dev group
uv run pre-commit install   # write .git/hooks/pre-commit
```

The first commit after installing builds the hook environments. That repeats only when `.pre-commit-config.yaml`
changes.

Local settings and FTC Events credentials go in `warehouse/.env`, which git ignores. Register for credentials at
[FTC Events](https://ftc-events.firstinspires.org/services/API/register).

```
WAREHOUSE_FTC_EVENTS_USERNAME=...
WAREHOUSE_FTC_EVENTS_TOKEN=...
```

The command line tools, and the `db` tests run against real data, need the local database started, migrated and
loaded. The [warehouse quick start](warehouse/README.md#quick-start) sets it up.

## What runs before and after I push?

- **Before you push**, the pre-commit hooks run on every commit: ruff with `--fix`, the ruff formatter, mypy and file
  hygiene checks, and `warehouse rules check` when a rule pack changes. They do not run the tests, so run those
  yourself.
- **After you push**, CI runs the hooks and `pytest` on every pull request and every push to `dev`, and `pytest -m db`
  in a separate job against Postgres.

To run any of them by hand:

```
uv run ruff check .         # lint
uv run ruff format .        # format in place
uv run mypy                 # types, strict
uv run pytest               # tests that need no database
uv run pytest -m db         # tests that need a database
```

### How are tests tagged?

Untagged tests run everywhere. `pytest` deselects `credentialed`, `scheduled` and `db` by default, and
`--strict-markers` rejects any tag not declared at the root.

| Tag | Meaning |
| --- | --- |
| `credentialed` | needs network access or credentials; not run in CI |
| `scheduled` | regular checks for data accuracy/calibrations; run by hand with `uv run pytest -m scheduled`, never by the hooks or CI |
| `db` | needs a live Postgres |

A `db` test runs against `WAREHOUSE_DATABASE_URL` when it is set, and otherwise starts a local Postgres under
`var/pgdata-test`. Each run migrates a scratch database of its own and removes stale ones.

## How is the workspace organized?

The repository is a single uv workspace. The root `pyproject.toml` holds the shared ruff, mypy and pytest configuration
and is not itself a package. Each module carries its own dependencies and scripts.

**A new module is named in the root `pyproject.toml`** in each of these places:

- the `dev` dependency group
- `[tool.uv.sources]`
- the workspace `members`
- ruff's `src`
- isort's `known-first-party`
- mypy's `mypy_path` and `files`

**Every module inherits the root ruff configuration**, per-file ignores included.

```toml
# Root pyproject.toml
[tool.ruff.lint.per-file-ignores]
"pridge/src/pridge/{design,estimator}.py" = ["N803", "N806"]
```

A module that needs its own `[tool.ruff]` writes `extend = "../pyproject.toml"` in it. Without `extend`, the module's
table replaces the root configuration rather than adding to it.

**Every mypy override is declared at the root**, whichever module it applies to.

```toml
# Root pyproject.toml
[[tool.mypy.overrides]]
module = ["pgserver.*"]
ignore_missing_imports = true
```

## Style

- **Python**
    - Docstrings follow [Google style](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings).
    - Inline comments only where the code works around a language feature or is genuinely counter-intuitive.
    - Names are not abbreviated.
    - Imports are absolute; lint bans relative imports to a parent package.
    - Private members start with an underscore. `__all__` appears only in an `__init__.py`, to re-export a name for
      mypy strict.
    - Lines are at most 120 characters.
    - The target version is Python 3.12.
- **Documentation**
    - A reference to what is, not why: like your favorite TTRPG index, a manual to get in and out of quickly.
    - Methodology documents may cover why, naming the A/B tests and experiments behind a decision, but still lead
      with what.
    - Markdown may use GitHub alerts (`> [!NOTE]`, `[!TIP]`, `[!IMPORTANT]`, `[!WARNING]`, `[!CAUTION]`) and
      footnotes. In VS Code, [Markdown Preview GitHub Styling][github-styles] renders alerts and
      [Markdown Footnotes][footnotes] renders footnotes.

[github-styles]: https://marketplace.visualstudio.com/items?itemName=bierner.markdown-preview-github-styles
[footnotes]: https://marketplace.visualstudio.com/items?itemName=bierner.markdown-footnotes
