import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const source = await readFile(new URL('../src/room/RoomLab.tsx', import.meta.url), 'utf8')

test('mission controls start hidden and can be opened from the header', () => {
  assert.match(source, /const \[missionOpen, setMissionOpen\] = useState\(false\)/)
  assert.match(source, /aria-expanded=\{missionOpen\}/)
  assert.match(source, /aria-controls="mission-panel"/)
  assert.match(source, /onClick=\{\(\) => setMissionOpen\(\(value\) => !value\)\}/)
  assert.match(source, /\{showMission && mission && missionOpen \? \(\s*<section id="mission-panel"/)
  assert.match(source, /onClick=\{startMission\}/)
  assert.match(source, /setArrivalDismissed\(false\)\s*setMissionOpen\(false\)\s*setTripToken/)
  assert.match(source, /onClick=\{sendToEquipment\}/)
})
