# AGENTS.md

Conventions for anyone changing this repository, whether that is a person or an
AI agent. It is deliberately short: these are the rules a reviewer would send a
change back for. `README.md` describes the product, `docs/workflow.md` covers
seats and the event clock, and the `Makefile` holds the commands.

## Before anything else

- `main` is the only long-lived branch, and it stays runnable from a clean clone.
- Read the file you are about to change, and the test that covers it.
- One change per branch. If the diff needs the word "also" twice, split it.

## Commits

Commits follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <subject>

<body>

<footer>
```

- **Type**: `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `build`, `ci`,
  `chore`, `style` or `revert`. `style` is formatting only and never changes
  behaviour. `chore` is the housekeeping that fits nowhere else.
- **Scope**, when the change is confined to one area: `server`, `web`, `nav`,
  `ocr`, `corpus`, `register`, `capture`, `pipeline`, `fixtures`, `proof`,
  `scripts`, `docs`, `deps` or `ci`. A change that spans several areas gets no
  scope, or the one a reviewer would say out loud.
- **Subject**: imperative, lowercase after the colon, no trailing period, the
  whole line 72 characters or fewer. "Add route clearance to the API", not
  "Added" and not "Adding".
- **Body**: why, not what. The diff already says what changed. Wrap at 72
  characters and say what a reader now sees differently, and what breaks if the
  commit is reverted.
- **Footer**: `Refs: #12`, `Closes: #12`, or
  `BREAKING CHANGE: <what changed and who must act>`. A breaking change also
  takes `!` after the type, as in `refactor!(nav): move the grid into metres`.

History written before this file uses plain imperative subjects. Leave it alone.
Rewriting old commits into the new format costs a force push and buys the reader
nothing.

One logical change per commit, and a bug fix that is squash merged keeps the
explanation in its message: what was wrong, why, and how the test catches it.

## Branches and pull requests

- Branch from an up-to-date `main` as `<type>/<short-topic>`, for example
  `fix/route-clearance` or `docs/agents`.
- The PR title is a Conventional Commit subject, because this repository squash
  merges: the PR title becomes the commit on `main`. A vague title is a vague
  permanent log entry.
- The description answers four questions: what changed, why it matters, how it
  was verified, and what is still risky or not covered.
- Keep the diff reviewable. A dependency bump, a formatting pass and a behaviour
  change are three PRs, in that order.
- Do not merge with a failing check. If a check fails for a reason outside the
  change, say which and why in the description instead of silencing it.
- Rebase a stale or conflicting branch on `main`, then push with
  `git push --force-with-lease`, never a bare `--force`. Rebase because the
  branch is stale, not to tidy history.
- Do not amend a commit that is already pushed, and do not rewrite a branch
  someone has already reviewed without saying so in the same message.

## Before you push

- `make test` for the Python suite, `make web-build` for the front end, and
  `make check` for the submission rules. CI runs the same three from a clean
  clone, so a green local run is the cheap version of the same answer.
- `git status` holds only what you mean to commit. `git diff --cached --numstat`
  prints a `-` in place of a line count for a binary file, which is the cheapest
  way to catch one before it ships.
- A commit that adds a dependency, an environment variable or a network call says
  so in the PR, and updates `uv.lock` or `app/web/package-lock.json` in the same
  commit as the change that needs it.
- New behaviour gets a test, and a bug fix gets a test that fails without the
  fix. Tests are offline and deterministic: no network, no dependence on the
  clock, no sleeping.
- Deleting a feature or a file deletes its docs, its fixture and its test in the
  same PR. Dead references are a defect even when the code runs.

## Python

- Python 3.12 or newer (`pyproject.toml`); CI runs 3.13 with `uv sync --locked`.
- Type hints on public functions, `from __future__ import annotations` at the top
  of each module.
- The standard library first. A package the code imports belongs in
  `pyproject.toml` or `app/web/package.json`, not only in a lock file. A new
  dependency needs a sentence in the PR saying what it replaces or makes possible.
- One module, one job, with a docstring whose first line says what the module is
  for.
- Raise with context. Do not catch an exception you cannot handle, and never let
  a `try` block hide a failed import, a missing file or a bad configuration value.
- Tests live in `app/server/tests/` and run through `uv run pytest`. CI installs
  poppler and Tesseract, so a test that needs them runs there and skips locally
  rather than failing.

## Front end

- TypeScript strict, with `noUnusedLocals` and `noUnusedParameters` on: the build
  fails on dead code, which is the intended behaviour.
- `npm run build` is `tsc --noEmit` then `vite build`, and both pass before a push.
  `npm run typecheck` is the fast half.
- Components live in `app/web/src/components/`, one component per file, named for
  what it shows.
- Nothing on the network at demo time. A new request needs a local fallback,
  because the product is shown offline.
- `app/web/dist` is generated and stays out of git. `make web-build` writes it.

## Data, secrets and files

- Never commit a secret. `.env` is ignored, `.env.example` is tracked and stays
  current. If a key reaches the repository, rotate it: deleting the line does not
  remove it from history.
- No archives, PDFs, decks, model weights, database dumps or screenshots in git.
  `data/` is generated and ignored; `fixtures/` is committed and holds small text
  only, well under 256 KB.
- A tracked file stays under 1 MB. `scripts/sinceai_check.mjs` fails above it and
  warns above 256 KB.
- Generated and vendored paths are read-only: `data/`, `app/web/dist`, `.venv/`,
  `node_modules/` and `.agents/`. Regenerate them with `make` instead of editing
  them by hand.
- Numbers that appear in the README, the video script or the submission copy come
  from the generated artifacts in `data/<capture>/` or from a `make` target's
  output. A claim with no number behind it does not ship.
- The Valmet documents are copyright Valmet. The repository ships section ids,
  titles, pages and short quotes only, never the PDFs themselves.

## Writing

- No em dashes and no en dashes. Use a comma, parentheses, a colon or a plain
  hyphen.
- Every file, path and document you name must exist in this repository. A reader
  cannot open a file that only exists on someone's laptop.
- Say what changed and why it matters to the reader, not how the change was
  produced.
- The README is the judge-facing description of the product, and it stays honest
  about what is real, what is synthetic and what was not attempted.

## Working next to other people and agents

- One writer per file. In a parallel session, say which files you will touch
  before you start, because two writers silently overwrite each other.
- Do not run `git reset --hard`, `git clean -fd`, `git checkout -- .`, a force
  push or a branch delete on work you did not create. Ask instead.
- Do not commit someone else's uncommitted work, and do not stage with
  `git add -A` when the tree holds anything you did not write.
- If the work is bigger than the request, or the request conflicts with a rule
  here, raise it before opening the PR, not in a review comment after.

## Where things live

| Path | Contents |
| --- | --- |
| `app/server/src/plantpilot/` | the demo path: splat, segment, pack, assets, mapping, nav, diagnose, main |
| `app/server/tests/` | pytest suite, offline |
| `app/web/` | React, Vite and three.js viewer |
| `scripts/` | the demo builds (splat asset, route, anchors, object splats, meshes, filter channels) and the submission check |
| `fixtures/` | committed and small: the reviewed scene anchors |
| `docs/` | plan, roadmap, features, acceptance, video script, submission copy |
| `.github/workflows/ci.yml` | the checks a pull request must pass |

## When in doubt

Run `node scripts/sinceai_check.mjs` and read the whole report. Exit 0 means the
submission rules hold. A failure is a repository defect and a warning is a
judgement call you have to make and say out loud.
