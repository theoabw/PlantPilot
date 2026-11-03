# SinceAI Hackathon 2026, team workspace

This repo is the team's workspace for SinceAI Hackathon 2026 in Turku, 6 to 8 November 2026. It holds the event notes now and becomes the submission repository when the challenge is chosen. The organiser's platform (`sinceai.app`) and email always win over these notes. `README.md` is the event brief, and `challenge.md` is the challenge card.

These instructions apply only inside this repository. They load when a dsh session starts with this directory as its working directory, and they change nothing outside it.

## The numbers that matter

| | |
| --- | --- |
| Submission closes | Sunday 8 November 2026, 10:00 EET, fixed |
| Submission platform | `sinceai.app`, not Devpost |
| Challenge | exactly one per team, chosen Friday 15:00 to 17:30, final |
| Team | up to 5 people, roster locks when the lead marks the team ready |
| Finalists | picked by the participant vote Sunday 10:00 to 12:00, not by the companies |
| Prizes | top three per challenge Sunday 13:30, finals Sunday 14:00 |

## Where we are in the event

`node scripts/sinceai_check.mjs` prints the live line. The doctrine:

| Phase | From (EET) | Rule for the phase |
| --- | --- | --- |
| prep | now | No challenge is chosen yet. Dry-run the deploy path, agree the stack, keep the event brief reproducible. Do not pre-build a company challenge: the summaries are not public before Thursday 15:00. |
| shortlist | Thu 5 Nov 15:00 | Read all 15 summaries on sinceai.app and agree on three the team would genuinely accept. Write them into `challenge.md`. |
| onboarding | Fri 6 Nov 15:00 | Check in in person, pick the challenge, and at the briefing write down the evaluation criteria the company states, not just the task. |
| build | Fri 6 Nov 19:30 | Build one demo-able path and cut every other feature. Commit something that runs before the night ends. |
| freeze | Sat 7 Nov 22:00 | Features frozen. README, demo video and submission text only. |
| submit | Sun 8 Nov 07:00 | Artifacts only. Save the entry first, then attach files and links. Be done by 09:30. |
| judging | Sun 8 Nov 10:00 | Vote 10:00 to 12:00. If finalist: 4 minute pitch, then 6 minutes of questions. |

When a phase rule and an explicit request conflict, do what the user asks and say what it costs.

## Standing rules for anything written here

- Never commit secrets. `.env` is ignored, keep `.env.example` current, and if a key lands in the repo, rotate it: history keeps it.
- Restricted challenge data (the FORCIT NDA, anything under `restricted/` or `challenge-material/`) never enters the repo, the video, or the deck. The challenge rules are in the event brief.
- No archives, PDFs, decks, model weights or media in git. The checker enforces the size rules.
- The repository and the demo must open while logged out. A private repo is acceptable only if the organisers can open it.
- Commit in small steps with meaningful messages, so the judges can separate event work from pre-existing work.
- No em dashes and no en dashes in anything written into this repo. Use a comma, parentheses, a colon, or a plain hyphen.
- The submission README is the one judges read. When the challenge is chosen, move the event notes to `docs/event-brief.md` and write the project README at the root, following "What the repo README must contain" in the event brief.

## The submission check

`scripts/sinceai_check.mjs` is deterministic, dependency-free, and offline by default. It writes nothing unless asked. Run it with Node 24.

| Flag | Effect |
| --- | --- |
| `--public` | fetch the repo and demo links and verify they open while logged out |
| `--write` | write `SUBMISSION.md` from the current facts, or `SUBMISSION.generated.md` when a hand-edited one exists |
| `--json` | print the result object for another pass to consume |
| `--repo <path>` | check another directory; defaults to the working directory |

Exit code 0 means ready, 1 means failures remain, 2 means the check itself failed. A failure is a repository defect; a warning is a judgement call. The check cannot fill the sinceai.app form, record the video, or verify that every member accepted the IP terms. Those are human steps.

## The Sunday routine

When asked to submit, prepare the submission, or check the entry, run this in order. Timebox it: the entry should be saved by 09:30.

1. Run `node scripts/sinceai_check.mjs --public --write` and read the whole report.
2. Fix every failure that is a repository defect, then re-run until only TODO lines remain.
3. Answer every TODO in `SUBMISSION.md` from the real repository and this conversation. Keep "About the project" under 5,000 characters. Never invent a number, a URL or a claim.
4. Open the repo and demo links while logged out and report their status. Use the browser tools when they are available.
5. Write the demo video shot list from the product's real flows: 6 shots, under 2 minutes.
6. Report one go/no-go line: `READY at HH:MM` or `NOT READY: <blocking items>`.

Before 09:30, if the product does not demo, fix the demo path, not the README. After 09:30, submitting is the only action.

## Two project skills

- `sinceai-judge`: the three scoring passes (company evaluator, non-expert voter, clean-clone reviewer) and a ranked gap list. Load it when asked how the project would score, or before submission.
- `sinceai-pitch`: the 4 minute finals pitch, the 6 minute Q&A traps, and the 20 second comprehension test for the participant vote.

## Working with the team

- One challenge, one demo path, one README. In a parallel wave, say which files you will touch so two agents never write the same one.
- Keep the repo runnable from a clean clone at all times. A half-merged feature that breaks setup is worse than a missing feature.
- The product is the pitch: a working prototype beats a deck. The README, the video and the submission text are what the vote sees.
