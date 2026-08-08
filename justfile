set shell := ["bash", "-eu", "-o", "pipefail", "-c"]
set dotenv-load := false

skills_dir := "skills"
py_targets := "."
md_targets := "."

list-skills:
  @find {{skills_dir}} -mindepth 1 -maxdepth 1 -type d -print

# Refresh the review-suite contract copies bundled into each review skill and
# each caller that consumes a review-code-change result, so every skill stays
# self-contained when installed outside this repository.
sync-contracts:
  @for skill in review-code-change review-correctness review-code-simplicity review-solution-simplicity review-fix-loop; do \
    dest="{{skills_dir}}/$skill/references/review-suite"; \
    mkdir -p "$dest"; \
    cp review-suite/CONTRACT.md "$dest/CONTRACT.md"; \
    cp review-suite/contracts/review-packet.schema.json "$dest/review-packet.schema.json"; \
    cp review-suite/contracts/review-result.schema.json "$dest/review-result.schema.json"; \
    cp review-suite/scripts/validate.py "$dest/validate.py"; \
    echo "Synced $dest"; \
  done
  @for skill in implement-ticket babysit-pr carve-changesets; do \
    dest="{{skills_dir}}/$skill/references/review-suite"; \
    mkdir -p "$dest"; \
    cp review-suite/consumption-disciplines.md "$dest/consumption-disciplines.md"; \
    echo "Synced $dest/consumption-disciplines.md"; \
  done
  @for skill in review-fix-loop; do \
    scripts_dest="{{skills_dir}}/$skill/scripts"; \
    tests_dest="$scripts_dest/tests"; \
    mkdir -p "$tests_dest"; \
    cp review-suite/scripts/review_gate.py "$scripts_dest/review_gate.py"; \
    cp review-suite/scripts/tests/test_review_gate.py "$tests_dest/test_review_gate.py"; \
    echo "Synced $scripts_dest/review_gate.py and $tests_dest/test_review_gate.py"; \
  done
  @for skill in implement-epic carve-changesets babysit-pr; do \
    scripts_dest="{{skills_dir}}/$skill/scripts"; \
    mkdir -p "$scripts_dest"; \
    cp ledger/core.py "$scripts_dest/ledger_core.py"; \
    echo "Synced $scripts_dest/ledger_core.py"; \
  done

# Compare the separately installed skill copies under ~/.agents/skills against
# this repository's working tree. `sync-contracts` above only refreshes the
# copies bundled *inside* this repository; an installed snapshot is a distinct
# distribution that keeps running stale prose and stale contracts until it is
# re-installed. Deliberately excluded from `lint` and `check`: the installed
# path is machine-specific and absent in continuous integration.
#
# Exit 0 in sync, 1 an installed copy drifted, 2 the operator's environment is
# wrong: no such root, nothing there to compare, or this repository's own
# skills tree could not be read.
# Override the location with --skills-root or $AGENTS_SKILLS_DIR; only the
# built-in default may be absent, since naming a root asserts that it exists.
check-installed *args:
  python3 scripts/check_installed_skills.py {{args}}

test: test-plugins
  @found=0; \
  for tests in {{skills_dir}}/*/scripts/tests; do \
    if [ -d "$tests" ]; then \
      found=1; \
      echo "Running tests in $tests"; \
      python3 -m unittest discover -s "$tests" -p 'test_*.py'; \
    fi; \
  done; \
  if [ "$found" -eq 0 ]; then \
    echo "No skill tests found under {{skills_dir}}/*/scripts/tests"; \
  fi; \
  for tests in review-suite/scripts/tests triggering/tests; do \
    if [ -d "$tests" ]; then \
      echo "Running tests in $tests"; \
      python3 -m unittest discover -s "$tests" -p 'test_*.py'; \
    fi; \
  done

test-review-suite:
  python3 -m unittest discover -s review-suite/scripts/tests -p 'test_*.py'

# Validate the replay corpus: schemas, cross-field expectation semantics,
# reviewer/private separation, provenance shape, outcome-revealing names, and
# the complete executor payload. Never launches a model.
audit-review-corpus:
  python3 review-suite/scripts/evals/audit_corpus.py

# Validate connector-outcome curation records and promotion decisions: intake
# schema, disposition vocabulary, duplicate/unresolved handling, provenance and
# retention fields, reviewer/private separation, the mechanical disclosure
# guardrail, and promotion-decision evidence and target rules. Never scrapes
# GitHub, never mutates a review thread, and never launches a model.
audit-review-curation:
  python3 review-suite/scripts/evals/audit_curation.py

# Result-blind replay evaluation through an explicit real-runtime executor.
# Deliberately excluded from `test`, `lint`, and `check`: this is the only
# review-suite command that may spend money.
#
# Extra arguments are forwarded to the runner, because a stratum is not
# reachable without them: `--corpus` defaults to the protocol-proof corpus and
# `--runs` to 1, so a frozen per-stratum configuration cannot be executed by
# naming an executor alone. The exact per-stratum invocations are recorded in
# review-suite/evals/baseline/v1/frozen-configuration.json.
eval-review-suite executor *args:
  python3 review-suite/scripts/evals/runner.py --executor "{{executor}}" {{args}}

# Re-grade already-captured raw attempts with the current grader, spending no
# new money: no executor process is launched. Use after a grader change to
# correct a stratum's report from its retained `--artifact-dir` and
# `--attempts-out` without repeating the model calls that produced them.
regrade-review-suite *args:
  python3 review-suite/scripts/evals/regrade.py {{args}}

test-plugins:
  python3 -m unittest discover -s scripts/tests -p 'test_*.py'

test-babysit-pr:
  python3 -m unittest discover -s {{skills_dir}}/babysit-pr/scripts/tests -p 'test_*.py'

test-ready-ticket:
  python3 -m unittest discover -s {{skills_dir}}/ready-ticket/scripts/tests -p 'test_*.py'

test-implement-ticket:
  python3 -m unittest discover -s {{skills_dir}}/implement-ticket/scripts/tests -p 'test_*.py'

eval-implement-ticket:
  python3 {{skills_dir}}/implement-ticket/scripts/evals/run_forward.py

# Run only implement-epic packets from the shared result-blind corpus.
eval-implement-epic:
  python3 {{skills_dir}}/implement-ticket/scripts/evals/run_forward.py \
    --target-skill implement-epic
# Real-runtime forward evaluation; requires the `claude` CLI on PATH.
eval-implement-ticket-claude:
  python3 {{skills_dir}}/implement-ticket/scripts/evals/run_forward.py \
    --executor "python3 {{skills_dir}}/implement-ticket/scripts/evals/claude_executor.py"

# Run a skill's evaluations and record the summary as committed evidence under
# skills/<skill>/evals/results/, per the eval-evidence norm in AGENTS.md.
# Prefers the real-model forward-eval executor where the skill has one and
# falls back to the deterministic tier with the gap recorded where it does not.
# Deliberately excluded from `test`, `lint`, and `check`: the real-model tier
# spends money, and the norm records evidence rather than gating CI.
#
# `{{args}}` is substituted textually before bash sees it, as in the other
# executor recipes here, so an argument containing shell metacharacters needs
# its own inner quotes: --note "'text with (parens)'".
eval-record skill *args:
  python3 scripts/record_eval_run.py "{{skill}}" {{args}}

test-implement-epic:
  python3 -m unittest discover -s {{skills_dir}}/implement-epic/scripts/tests -p 'test_*.py'

test-carve-changesets:
  python3 -m unittest discover -s {{skills_dir}}/carve-changesets/scripts/tests -p 'test_*.py'

test-review-fix-loop:
  python3 -m unittest discover -s {{skills_dir}}/review-fix-loop/scripts/tests -p 'test_*.py'

# Result-blind, deterministic replay of the review-fix-loop cross-cutting
# corpus: drives the real local_commit/update_pr engine against disposable
# Git repositories with scripted reviewer/decide/apply_fix fixtures (no
# subprocess boundary, no model call, no network). Also exercised under
# `just test` via scripts/tests/test_evals.py; this target is the standalone
# entry point for ad hoc runs and per-scenario `--output-dir` reports.
eval-review-fix-loop:
  python3 {{skills_dir}}/review-fix-loop/scripts/evals/runner.py

eval-carve-changesets:
  python3 {{skills_dir}}/carve-changesets/scripts/evals/runner.py --integration-self-test
  python3 {{skills_dir}}/carve-changesets/scripts/evals/runner.py

# Forward-evaluate through any fresh-process stdin/stdout JSON adapter.
eval-carve-changesets-executor executor:
  python3 {{skills_dir}}/carve-changesets/scripts/evals/runner.py --executor "{{executor}}"

# Run the triggering-and-composition corpus: which skill does a prompt route
# to? The default executor is a deterministic stand-in that exercises the
# harness without a model; pass --executor to grade a real router.
eval-triggering *args:
  python3 triggering/runner.py {{args}}

validate-skills: lint-skills

validate-plugins:
  python3 scripts/validate_plugins.py

fmt-py:
  @if command -v ruff >/dev/null 2>&1; then \
    ruff check --select I,RUF022 --fix {{py_targets}}; \
    ruff format {{py_targets}}; \
  else \
    echo "ruff not found on PATH; skipping Python formatting"; \
  fi

fmt-md:
  @if command -v mdformat >/dev/null 2>&1; then \
    md_files="$(find {{md_targets}} -type f -name '*.md' \
      -not -path '*/.venv/*' \
      -not -path '*/.git/*' \
      -not -path '*/.tools/*')"; \
    if [ -n "$md_files" ]; then \
      mdformat --wrap 80 $md_files; \
    fi; \
  else \
    echo "mdformat not found on PATH; skipping Markdown formatting"; \
  fi

lint-py:
  @if command -v ruff >/dev/null 2>&1; then \
    ruff check {{py_targets}}; \
  else \
    echo "ruff not found on PATH; skipping Python lint"; \
  fi

lint-md:
  @if command -v mdformat >/dev/null 2>&1; then \
    md_files="$(find {{md_targets}} -type f -name '*.md' \
      -not -path '*/.venv/*' \
      -not -path '*/.git/*' \
      -not -path '*/.tools/*')"; \
    if [ -n "$md_files" ]; then \
      mdformat --check --wrap 80 $md_files; \
    fi; \
  else \
    echo "mdformat not found on PATH; skipping Markdown lint"; \
  fi

lint-skills:
  @set -euo pipefail; \
  AGENTSKILLS_DIR=".tools/agentskills"; \
  SKILLS_REF_BIN=""; \
  install_skills_ref() { \
    echo "Installing skills-ref: recreating .venv and cloning agentskills from GitHub (network required)..."; \
    rm -rf .venv; \
    python -m venv .venv; \
    mkdir -p .tools; \
    rm -rf "$AGENTSKILLS_DIR"; \
    git clone https://github.com/agentskills/agentskills.git "$AGENTSKILLS_DIR"; \
    .venv/bin/pip install --upgrade pip; \
    .venv/bin/pip install -e "$AGENTSKILLS_DIR/skills-ref"; \
    SKILLS_REF_BIN=".venv/bin/skills-ref"; \
  }; \
  if command -v skills-ref >/dev/null 2>&1; then \
    SKILLS_REF_BIN="$(command -v skills-ref)"; \
    if ! "$SKILLS_REF_BIN" --help >/dev/null 2>&1; then \
      SKILLS_REF_BIN=""; \
    fi; \
  fi; \
  if [ -z "$SKILLS_REF_BIN" ] && [ -x .venv/bin/skills-ref ]; then \
    SKILLS_REF_BIN=".venv/bin/skills-ref"; \
    if ! "$SKILLS_REF_BIN" --help >/dev/null 2>&1; then \
      SKILLS_REF_BIN=""; \
    fi; \
  fi; \
  if [ -z "$SKILLS_REF_BIN" ]; then \
    install_skills_ref; \
  fi; \
  "$SKILLS_REF_BIN" --help >/dev/null; \
  for skill in {{skills_dir}}/*; do \
    if [ -d "$skill" ]; then \
      echo "Validating $skill"; \
      "$SKILLS_REF_BIN" validate "$skill"; \
    fi; \
  done

lint: lint-py lint-md lint-skills validate-plugins

format: fmt-py fmt-md

check: test lint
