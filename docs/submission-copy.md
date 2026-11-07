# Submission copy

The vote card is read in about twenty seconds. This is the text that goes on it. Status: the facts below were corrected against the shipped app; the story rewrite is still due.

## Tagline, up to 80 characters for the name field, one line for the card

**Chosen:** A work order becomes a mission: find the machine, route to it, explain why.

Alternates, if the chosen one tests badly with the team:

- The scan is the easy part. This turns it into an inspection.
- Point at a plant. Get a route, a reason and a citation.

## First two sentences of About the project

These are what a scanning voter reads before anything else.

> A work order names a machine, not a place. PlantPilot turns a 3D capture of the plant into a mission: it identifies the equipment, plans a route to the position where a person can inspect it, and cites the document that explains why the visit is due.

## About the project, outline under 5,000 characters

1. **The problem** (300 chars): a work order names a machine; finding it and the reason for the visit is manual work, and a scan does not help on its own.
2. **What it does** (600): meaning, identity, accessibility, context, in one flow.
3. **How it works** (1,200): the capture is read once and the readable prefix is kept. The loader detects the up axis and the floor plane, removes the dominant planes, clusters what is left and fits an oriented 3D box to each cluster, with a class proposal refined against context and a confidence. On the complete capture that is 150 boxes from 272 clusters. The supplied builder workbook becomes a pack of 30 asset records, and a class-and-size prior proposes each record onto a distinct box behind two hard gates, so class alone cannot carry a wrongly sized object. Every record is marked proposed or unresolved, and no box receives two tags. The floor becomes an occupancy grid at 0.10 m with four obstacle layers: the boxes, the unobserved floor, near-vertical surfaces and overhead structure. The grid is inflated once for the robot radius. A* plans to a stand-off point beside the faulty target P-005. In the browser the robot follows the planned line, the nearby boxes light up with their mapped state, and on arrival the diagnosis card joins the pack's current state, telemetry, alarms, data-quality cases and documents for P-005, with evidence ids and a cited next check. No request leaves the machine.
4. **What we measured** (400): points, route distance and clearance, the detour, the response time, the test count. Only numbers produced by a command.
5. **What is simulated** (400): the capture is a real supplied scan, the metadata is not. The builder pack is Valmet's synthetic data, the mapping is a proposal rather than a confirmed identification, and the class labels are proposals from shape and context. No door-height scale check has run, so distances are the capture's own units treated as metres. The robot is a viewer marker, not a physics simulation. The diagnosis is retrieval and templates over the pack, not a model at runtime, so it cannot invent a cause.
6. **What we would do next** (300): real scans, an evidence panel over the company's own documents, robot clearance profiles, multi-floor routing.

## Built with, in the order it should be read

The first five become chips on the vote card, so the order is deliberate.

1. three.js
2. FastAPI
3. Python
4. React
5. OpenCV
6. TypeScript
7. Vite
8. Tailwind CSS
9. Spark
10. numpy
11. pydantic
12. pytest

## GenAI disclosure

- Tools used while building: AI coding agents for implementation, review and documentation; a synthesised voice for the demo video.
- Generative AI in the product: none on the answer path. The explanation is retrieval plus a template, so every sentence has a citation. An optional rewrite is cached and off the demo path.

## Form checklist

| Field | State |
| --- | --- |
| Project name | PlantPilot |
| Tagline | above, chosen line |
| About | outline above, fill the numbers from the app on Sunday |
| Built with | ordered list above |
| Repository | the repository link, hosted private; a source-code zip travels with the entry |
| Demo video | YouTube unlisted link, recorded Saturday night |
| Pitch deck | optional, one page, only if it earns its place |
| MLH questions | technology feedback, GenAI tools, GenAI in the product |
| IP terms | every member accepts in sinceai.app |
