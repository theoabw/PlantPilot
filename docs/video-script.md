# Demo video: shooting script

Screen capture of the running app, plus one terminal cut: 2 minutes 44 seconds, six beats, English voiceover. The room is the supplied boiler room capture; the target is P-005. Every number comes from the app or a make target.

## Brand in the edit

Open on [`brand/title-1920x1080-dark.png`](brand/title-1920x1080-dark.png) and keep [`brand/logo-bug-600x192-dark.png`](brand/logo-bug-600x192-dark.png) in a corner the header and panels do not use. Count the title card in the two-minute limit.

## Read this before the first take

The app moved on after this script was written, so these do not match it. Fix them in the edit, not at the shoot:

- The route, the target ring and the robot are only drawn while the robot is moving (`showRoute={driving}` in `RoomLab.tsx`). Beat 3 cannot be shot at idle, so it starts on the click in beat 4.
- The mission card starts closed; open it with Mission in the header before using Send robot.
- There is no gaussian badge and no object-count badge in the header. The header reads `PlantPilot`, the capture name, the synthetic-scenario badge and the live dot. The gaussian count, the raw object count, the reviewed count, the route and the clearance are in the developer drawer, which Settings opens.
- There is no `Panel` control; the panel is open or closed, and beat 4 says so.
- The diagnosis lists up to four evidence references per finding, not an evidence count. 19 and 9 are the number of evidence ids behind each finding in `diagnosis.json`, not numbers on screen.
- The organiser's guide asks for a video under two minutes. This cut is 2:44, so about 45 seconds has to come out when the beats are assembled.

## Beat 1. Capture and framing (0:00 to 0:38, 38 s)

Scores criterion 1, 30 percent.

**On screen.** Room view, panel open, slow orbit. Hold the header (`PlantPilot`, the capture name, the synthetic-scenario badge) and the developer drawer: 1,676,481 gaussians and 150 raw objects. Click a duct frame, then a machine frame; hold each card with class, points, confidence and size. Close the panel, orbit over the frames, reopen.

**Voiceover.** "This room was captured with a 3D Gaussian splat: 1,676,481 gaussians. The pipeline finds the floor, reads the up axis, and cuts the room into objects. Every frame is a 3D box around one object: its centre, its size, and a class proposal from shape and context. On this boiler room capture we frame 150 objects."

**Counts if.** The room and boxes are rendered, not a placeholder; the drawer reads 150 raw objects; two selected frames show class, size and confidence; the header names the capture.

## Beat 2. Mapping (0:38 to 1:08, 30 s)

Scores criterion 1, 30 percent; feeds criterion 3.

**On screen.** Open Equipment and switch to the attention filter: the panel reads `Synthetic pack records 30/30 procedurally mapped`, with the red "P-005 FOULING" row on OBJ-037. Click the row, zoom, scroll to the mapping record.

**Voiceover.** "The pack designates one faulty target: P-005, fouling, health 44. Our mapping proposes it onto OBJ-037. All thirty package records are proposed onto thirty different objects, each with a method and a match score. The word is proposed: this is a class and size prior over geometry, not a confirmed identification, and the card says so."

**Counts if.** P-005, FOULING, OBJ-037 legible; method and match score on the record; the on-screen note that the mapping is a proposal; `30/30 mapped` visible.

## Beat 3. Route (1:08 to 1:36, 28 s)

Scores criterion 2, 25 percent.

**On screen.** The default target is close to the inward start, so its route is brief. To show a longer trip, select another equipment item and use Send robot here. The route and target ring are visible while the robot moves.

**Voiceover.** "Obstacles come from the extracted boxes, from the floor the capture never saw, from near-vertical surfaces that run the room's height, and from overhead structure. The grid is inflated once for a 0.20 agent radius and a 0.02 safety margin. A star search plans the route and reports its clearance. The viewer labels those numbers as metres; the door-height scale check has not been done."

**Counts if.** The path and the target ring are visible and the route distance and clearance are shown.

## Beat 4. Walk (1:36 to 2:00, 24 s)

Scores criterion 2, 25 percent; feeds criterion 5.

**On screen.** Nearby highlighted assets at the start. The robot is already sent in beat 3, so this shot continues the walk and the camera follows. Record at 60 fps, retime only the walk to half speed. Cover three nearby sets, then arrival.

**Voiceover.** "The robot follows the planned line at 0.5 metres per second. Nearby assets light up as it moves, and the distance remaining falls. P-005 comes into range before the robot stops."

**Counts if.** At three points the nearby highlighted set differs and the distance readout falls.

## Beat 5. Arrival and diagnosis (2:00 to 2:30, 30 s)

Scores criterion 3, 20 percent.

**On screen.** On arrival the diagnosis card appears in the panel. One slow scroll: FOULING, "health 44", up to four evidence references per finding, "Next check: inspect hydraulic path", the citation line.

**Voiceover.** "On arrival the card appears. Condition attention required, health 44, issue fouling, high urgency. Two findings, each listing the evidence references behind it: telemetry rows, alarm events and data quality cases. The next check is to inspect the hydraulic path. The card is grounded in the pack's process pump document, and the evidence ids point back to rows in the supplied pack."

**Counts if.** The card shows FOULING, health 44, an evidence reference, the next check and the citation.

## Beat 6. Architecture (2:30 to 2:44, 14 s)

Scores criterion 4, 15 percent.

**On screen.** Terminal: `uv run pytest -q`, last lines; then `ls data/equipment`, listing objects.json, mapped.json, route.json, diagnosis.json. End card: PlantPilot, offline, repository URL.

**Voiceover.** "One offline Python pipeline writes the scene, object, mapping, route and diagnosis artifacts; the tests run without a network; the repository is the submission."

**Counts if.** The pytest summary reads passed; the four artifact files are listed; the end card shows the repository URL.

## Shot list

1. Room settled, panel open; orbit; the developer drawer with the counts.
2. Duct frame card; machine frame card.
3. Close panel; orbit the frames; reopen.
4. Equipment attention filter; 30/30 mapped, P-005 row.
5. Click P-005; zoom; scroll to the mapping record; hold the proposal line.
6. Select P-005 and send the robot; show the path and target ring.
7. Nearby highlights at the start; trip progress visible.
8. Walk; record 60 fps.
9. Half-speed walk; three nearby sets.
10. Arrival; let the card appear; hold "arrived".
11. Diagnosis card; one slow scroll.
12. Terminal: pytest tail; `ls data/equipment`.
13. End card.

## Setup checklist

- Build: `make demo` builds the artifacts, the filter assets, the web page and the server, then serves at `http://127.0.0.1:8000`. Open that; the room view is first.
- 1920 by 1080, 100 percent, one tab, bookmarks and notifications off. Record 60 fps, export 30.
- Terminal: `export PS1='plantpilot $ '` so no local path shows.
- Dry run once; select a target far enough away to show the route and proximity changes. Run `make test`; if it fails, fix it or cut the shot.
- Do not open: developer tools unless a shot calls for them. Do not show: the editor, chat, server logs, other tabs, or any number the app is not printing. No captions over numbers.
