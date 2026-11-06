# Demo video: shooting script

Screen capture of the running app, plus one terminal cut: 2 minutes 44 seconds, six beats, English voiceover. The room is the complete supplied capture, Equipment Room; the target is P-005. The brief's named boiler room capture is damaged, and beat 1 says so. Every number comes from the app or a make target.

## Beat 1. Capture and framing (0:00 to 0:38, 38 s)

Scores criterion 1, 30 percent.

**On screen.** Room view, panel open, slow orbit. Hold the badge "1,676,481 gaussians · 150 framed objects" and the Capture card: 150 objects, up axis -y, largest share 1.2 percent. Click a duct frame, then a machine frame; hold each card with class, points, confidence and size. Close the panel, orbit over the frames, reopen.

**Voiceover.** "This room was captured with a 3D Gaussian splat: 1,676,481 gaussians. The pipeline finds the floor, reads the up axis, and cuts the room into objects. Every frame is a 3D box around one object: its centre, its size, and a geometric class proposal. On this complete capture we frame 150 objects. The brief names the boiler room capture, and that file is damaged: it declares 1,506,136 gaussians and fills only the first 502,483. The same code frames 130 there."

**Counts if.** The room and boxes are rendered, not a placeholder; the badge reads 150; two selected frames show class, size and confidence; the panel names the capture.

## Beat 2. Mapping (0:38 to 1:08, 30 s)

Scores criterion 1, 30 percent; feeds criterion 3.

**On screen.** Scroll Builder assets: "30/30 proposed", "13 of 30 proposed need attention, 3 attention required", the red "P-005 FOULING" row with OBJ-068. Click the row, zoom, scroll to the mapping record.

**Voiceover.** "The pack designates one faulty target: P-005, fouling, health 44. Our mapping proposes it onto OBJ-068. All thirty package records are proposed onto thirty different objects, each with a method and a match score. The word is proposed: this is a class and size prior over geometry, not a confirmed identification, and the card says so."

**Counts if.** P-005, FOULING, OBJ-068 legible; method and match score on the record; the words "a proposal, not a confirmed identification" on screen; "30/30 proposed" visible.

## Beat 3. Route (1:08 to 1:36, 28 s)

Scores criterion 2, 25 percent.

**On screen.** Click Overview. The amber path lies on the floor with a ring at each end; the Route card is bottom right. Hold until "6.1 m" and "0.32 m clear" read.

**Voiceover.** "Obstacles come from the extracted boxes, filtered to the robot's body height of 0.55. The grid is inflated once for a 0.20 agent radius and a 0.02 safety margin. A star search plans a route of 6.14, clearing the nearest object surface by 0.32. The viewer labels those numbers as metres; the door-height scale check has not been done."

**Counts if.** The whole path and both rings are visible; the Route card shows a distance and "0.32 m clear"; the robot marker is at the start.

## Beat 4. Walk (1:36 to 2:00, 24 s)

Scores criterion 2, 25 percent; feeds criterion 5.

**On screen.** The Nearby assets chips at the start. Click "Send robot to P-005"; the camera follows. Record at 60 fps, retime only the walk to half speed. Mid route, click Panel to show tags with state words. Cover three nearby sets, then arrival.

**Voiceover.** "The robot marker follows the planned line at 1.15 units per second. Everything close by lights up: the frame brightens, and its tag appears in the nearby list in its state colour. The set changes as it moves. Healthy is green, watch is amber, degraded is orange, attention required is red. P-005 comes into range before the robot stops."

**Counts if.** At three points the nearby tag set differs; two state colours appear; the "m to go" counter falls; tags are legible at half size.

## Beat 5. Arrival and diagnosis (2:00 to 2:30, 30 s)

Scores criterion 3, 20 percent.

**On screen.** On arrival the Diagnosis on arrival card appears in the panel. One slow scroll: FOULING, "health 44", evidence counts 19 and 9, "Next safe check: inspect hydraulic path", the citation line.

**Voiceover.** "On arrival the card appears. Condition attention required, health 44, issue fouling, high urgency. Two findings, each showing how many evidence references it carries, from telemetry rows, alarm events and data quality cases. The next safe check is to inspect the hydraulic path. The card is grounded in the pack's process pump document, and the evidence ids point back to rows in the supplied pack."

**Counts if.** The card shows FOULING, health 44, an evidence count, the next check and the citation; the robot reads "arrived".

## Beat 6. Architecture (2:30 to 2:44, 14 s)

Scores criterion 4, 15 percent.

**On screen.** Terminal: `uv run pytest -q`, last lines; then `ls data/scene`, listing objects.json, mapped.json, route.json, diagnosis.json. End card: PlantPilot, offline, repository URL.

**Voiceover.** "One offline Python pipeline writes the scene, object, mapping, route and diagnosis artifacts; the tests run without a network; the repository is the submission."

**Counts if.** The pytest summary reads passed; the four artifact files are listed; the end card shows the repository URL.

## Shot list

1. Room settled, panel open; orbit; badge and Capture card.
2. Duct frame card; machine frame card.
3. Close panel; orbit the frames; reopen.
4. Builder assets; 30/30, attention line, P-005 row.
5. Click P-005; zoom; scroll to the mapping record; hold the proposal line.
6. Overview; path, rings, Route card.
7. Robot ready; nearby chips.
8. Chips; Send robot; record 60 fps.
9. Half-speed walk; three nearby sets; open Panel mid-walk.
10. Arrival; let the card appear; hold "arrived".
11. Diagnosis card; one slow scroll.
12. Terminal: pytest tail; `ls data/scene`.
13. End card.

## Setup checklist

- Build: `make scene objects map route diagnose splat-asset`, `make web-build`, `make demo`. Open `http://127.0.0.1:8000`; the room view is first.
- 1920 by 1080, 100 percent, one tab, bookmarks and notifications off. Record 60 fps, export 30.
- Terminal: `export PS1='plantpilot $ '` so no local path shows.
- Dry run once; confirm the Route card reads 6.1 m and 0.32 m clear. Run `make test`; if it fails, fix it or cut the shot.
- Do not open: the Scene lab, Plant mission or Plate scan views. Do not show: the editor, chat, server logs, other tabs, or any number the app is not printing. No captions over numbers.
