# Features, grouped by how much we need them

P0 is the demo. P1 is the difference between a demo and a product. P2 is only if the gates pass early. P3 is out, and stays out.

## P0, the demo dies without these

| # | Feature | Why it is P0 | Owner | Gate |
| --- | --- | --- | --- | --- |
| 1 | Load a cloud and orbit it | there is no demo without the scan on screen | C | G0 |
| 2 | Asset records with position and inspection waypoint | the mission needs a place to go | A, D | G1 |
| 3 | Select an asset: highlight plus evidence card | this is the identity beat, and the proof the model is not a picture | C | G1 |
| 4 | Inspection request to asset, one click | this is the mission, not a viewer | D | G1 |
| 5 | Route from the door to the waypoint, with distance | the accessibility beat | B | G1 |
| 6 | Add a blocker, recompute, show the new route or a clear unreachable | the reveal, and the only beat that cannot be faked | B | G2 |
| 7 | Evidence panel with a citation: section, page, interval | the context beat, and the honest alternative to a chatbot | D | G2 |
| 8 | Runs with the network off | a plant demo that needs Wi-Fi is a liability | all | G3 |
| 9 | Data source label on screen | honesty about supplied, captured or generated geometry | C | G0 |
| 10 | Asset store persisted as a file the app reads | a demo restarted twice has to behave the same | D | G1 |

## P1, should have, and the value is large

| # | Feature | Value | Cost | Cut when |
| --- | --- | --- | --- | --- |
| 1 | Fly-to camera on selection | turns a click into a story beat | 2 h | G3 at 12:30 |
| 2 | Follow-the-route camera or walking marker | proves the route means something | 2 h | G2 at 12:30 |
| 3 | Three prepared destinations for the judge | live proof it generalises | 3 h | G3 at 12:30 |
| 4 | Semantics from geometry, scored against the reference truth | the "meaning" number, and a technical answer for a 3D judge | 4 h | G2 at 12:30 |
| 5 | Clearance in centimetres and an agent width parameter | the cart versus person story, robotics relevance for free | 2 h | never, it is a parameter |
| 6 | Photo capture mode as a second mode | shows the pipeline on real captures, not only on our own data | 3 h | G2 at 12:30 |
| 7 | Evaluation harness with the numbers printed | turns claims into results | 3 h | G4 at 16:00 |

## P2, only if the gates pass early

| # | Feature | Value | Cost |
| --- | --- | --- | --- |
| 1 | Person versus cart toggle with visibly different routes | a second spatial reveal | 1 h |
| 2 | CLIP zero-shot labels over proposals | richer meaning, weaker evidence than a tag | 3 h |
| 3 | Plan view or minimap beside the 3D view | orientation for a judge | 1 h |
| 4 | Walking time estimate at 1.2 m per second | a human number on the route | 0.5 h |
| 5 | Search by tag | small, useful, not demo critical | 1 h |
| 6 | Keyboard shortcuts for the six beats | keeps a live demo on the rails | 0.5 h |
| 7 | Screenshot export for the README | saves a manual step on Sunday | 1 h |

## P3, out, and stays out

Robot simulation, predictive maintenance, automatic pipe connectivity, whole plant understanding, multi-room twins, multi-floor navigation, VR or AR, LiDAR or photogrammetry capture, physics simulation, a login, a cloud service, an LLM on the answer path, a mobile app.

## The cut ladder

When time is short, this is the order things leave, and the hour that forces it. It matches the roadmap gates.

1. CLIP labels, first, because geometry and tags already carry meaning with better evidence.
2. The follow-the-route camera, keeping the waypoint highlight.
3. The judge-chosen destination, keeping the three scripted ones.
4. The photo capture mode, keeping the reference plant and noting it on screen.
5. Point density, down to 50k points at any stutter.
6. The fly-to animation, keeping a cut to the asset.

Never cut: the blocker reroute, the waypoint beside the machine, the citation, the offline run. Those four are the difference between answering the brief and answering a different one.

## Which judge each feature serves

| Judge line | Features that carry it |
| --- | --- |
| Works and answers the brief | P0 1 to 7, 9 |
| Technical quality and feasibility | P0 5, 6, P1 4, 5 |
| Understanding of the system | evidence panel, data source label, the code path from plate to asset |
| Responsible data handling | offline run, synthetic labels, no personal data, no cloud |
| Business value | the mission framing itself, the route and the blocked aisle |

A feature that serves none of these is not a feature, it is a distraction. That is why P3 exists.

## The submission surface, which is not a feature list

The vote card shows the name, the tagline, the first lines of the About text, the demo video playing inline, the optional pitch deck and the first five Built with chips. Voters can vote without watching the video to the end, so the tagline and the first two sentences do as much work as the demo. Judges read the full About text.

Treat these as P0 copy, not decoration: the tagline at 20:00 Friday, the first two sentences by Saturday midday, and the Built with order chosen deliberately because only the first five become chips.

## Rules

- No demo furniture in the product. A control exists because an operator needs it, not because a judge will click it. Timings, counts and provenance claims live in the pitch and the README.

- A P0 never gets cut. If a P0 is late, the demo changes shape around it, not without it.
- A P1 that misses its gate becomes P2 automatically. No negotiating at 03:00.
- A P2 can never displace a P1 without the lead naming the P1 it replaces.
- New ideas go to P2 or P3 first. A new idea may not enter P0 after G1.
