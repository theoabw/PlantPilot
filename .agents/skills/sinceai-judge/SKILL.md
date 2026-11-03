---
name: sinceai-judge
description: Score a SinceAI hackathon submission the way the company evaluators and the participant vote will, and return a ranked gap list with the cheapest fixes. Use before the Sunday deadline, when asked how the project would score or what to fix with the hours left, and for a pre-submission red team.
---

# Judge the submission before the judges do

Two gates decide the event, and they score different things.

1. The company evaluator picks the top three per challenge. It reads the repository, the submission text and the demo, and weighs five things from the judge guide: does it work and answer the challenge, real-world relevance and business value, technical quality and feasibility, how well the team understands and explains the system, and responsible handling of privacy, security and data.
2. The participant vote, Sunday 10:00 to 12:00 with 20 comparisons per builder, picks the five finalists. Those voters are about a thousand builders who are not domain experts. They see the submission text and the demo video, not the code, and one finalist per challenge is chosen this way.

A strong submission needs both: a product the company would buy, and a 20 second story a tired builder understands.

## Before you start

Read the repository as it is, not as it was meant to be: the README, `challenge.md`, the code entry points, and `SUBMISSION.md` when it exists. Run `node scripts/sinceai_check.mjs --json` for the mechanical facts. Do not edit anything during the passes; they are read-only.

Run each pass as its own subagent with the brief below, so the scores do not anchor each other, then aggregate them yourself. If you cannot dispatch subagents, run the passes in sequence and write down each score before reading the next pass.

## Pass 1: company evaluator

You are the engineer at the challenge company who has to justify a purchase. You have 20 minutes.

- Read the README, the submission text and the demo path. Open the code only where the README points.
- Score each of the five criteria 1 to 5, and cite evidence for every score: a file and line, a README section, or a demo step.
- Name the single cheapest change that would move the score most, and the one change you would not attempt with hours left.

Output: a table of criterion, score, evidence and cheapest fix, then the top three fixes ranked by expected gain per hour of work.

## Pass 2: non-expert builder

You are a builder with two hours and 20 comparisons. You see only `SUBMISSION.md` (or the README when there is no submission text) and a two minute demo video. You will not read the code.

- In 20 seconds, what do you think this does?
- What would make you vote for it over the entry next to it?
- What is confusing, unproven, or too abstract to remember?
- Would you guess it works, or that it is a mockup?

Output: your one-sentence summary, the vote decision (yes, no, maybe), and the three things that made you hesitate, each proven with a quote or a moment in the video.

## Pass 3: clean-clone reviewer

You are a judge with five minutes and an empty directory.

- Clone or copy the repository, follow the README exactly, and run the demo path. Record the first failure a judge would hit, with the exact command and the error.
- Check that the repository and the demo link open while logged out.
- Note anything that needs a secret the judges do not have.

Output: the first blocking failure, the time to the first working screen, and whether you reached the demo path at all.

## Pass 4, optional: red team

When the challenge touches personal or restricted data, add one pass: list every claim about data, privacy, security or accuracy and mark each as shown, asserted, or missing. Name the claim most likely to lose points and the one honest sentence that fixes it.

## The report

Return one page, not an essay.

- The three gate scores: company, vote, clean clone.
- A gap table: gate, gap, evidence, cheapest fix, hours, expected gain.
- The top three fixes for the time that is left, in order, each small enough to finish before the deadline.
- What to stop doing.
- One go/no-go line for the submission.

## Rules that keep this useful

- Cap each pass at 30 to 40 minutes. A judge pass that eats an afternoon costs more than it finds.
- Do not reward features the demo cannot show. For the voter, the demo is the product.
- After 07:00 Sunday, only submission text, video and link fixes count. Do not propose rewrites.
- Never score without evidence. "Looks good" is not a finding; name the file, the line, or the missing artifact.
- The criteria the company states at the Friday briefing, as recorded in `challenge.md`, override this skill.
