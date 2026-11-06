#!/usr/bin/env node
/**
 * SinceAI submission checker.
 *
 * Deterministic, dependency-free check of a repository against the SinceAI
 * Hackathon submission requirements: README sections, tracked secrets and
 * binary or oversized files, licence, env example, links, git history, and the
 * SUBMISSION.md field sheet.
 *
 * Runs offline by default. `--public` also fetches the repository and demo
 * links and verifies they open while logged out. `--write` refreshes
 * SUBMISSION.md with the sinceai.app field sheet, pre-filled with everything
 * the repository can answer and a TODO line for everything only a human can.
 *
 * Usage: node scripts/sinceai_check.mjs [--public] [--write] [--json] [--repo <path>] [--max-links <n>]
 * Exit:  0 ready, 1 not ready, 2 error.
 */

import { spawnSync } from 'node:child_process'
import { existsSync, readFileSync, readdirSync, statSync, writeFileSync } from 'node:fs'
import { basename, extname, join, resolve } from 'node:path'

/** Event boundaries, SinceAI Hackathon 2026, Turku, 6 to 8 November 2026. */
const EVENT = {
  timeZone: 'Europe/Helsinki',
  summariesAt: '2026-11-05T15:00:00+02:00',
  eventStart: '2026-11-06T15:00:00+02:00',
  buildStartsAt: '2026-11-06T19:30:00+02:00',
  freezeAt: '2026-11-07T22:00:00+02:00',
  deadline: '2026-11-08T10:00:00+02:00',
}

/** How long before the deadline the submit phase starts. */
const SUBMIT_WINDOW_MS = 3 * 60 * 60 * 1000

/** The phase doctrine, one rule per phase. Keep in sync with AGENTS.md. */
const PHASES = {
  prep: {
    label: 'prep',
    rule: 'No challenge is chosen yet. Dry-run the deploy path now, agree the stack, and keep the event brief reproducible.',
  },
  shortlist: {
    label: 'shortlist',
    rule: 'The 15 challenge summaries are open. Read all of them with the team and agree on three you would genuinely accept.',
  },
  onboarding: {
    label: 'onboarding',
    rule: 'Check in in person, pick the challenge, and write down the evaluation criteria the company states at the briefing, not just the task.',
  },
  build: {
    label: 'build',
    rule: 'Build one demo-able path and cut every other feature. Commit something that runs before the night ends.',
  },
  freeze: {
    label: 'features frozen',
    rule: 'Features are frozen. README, demo video and submission text only. Fix nothing that is not needed to demo.',
  },
  submit: {
    label: 'submit',
    rule: 'Artifacts only. Save the submission entry first, then attach files and links. Be done by 09:30, not 09:59.',
  },
  judging: {
    label: 'voting and finals',
    rule: 'Vote from 10:00 to 12:00, 20 comparisons. If finalist: 4 minute pitch, then 6 minutes of jury questions.',
  },
}

const ARCHIVE_EXTENSIONS = new Set(['.zip', '.tar', '.tgz', '.gz', '.bz2', '.xz', '.7z', '.rar'])
const DOCUMENT_EXTENSIONS = new Set(['.pdf', '.pptx', '.ppt', '.docx', '.doc', '.xlsx', '.xls', '.key', '.pem', '.p12', '.jks', '.keystore'])
const MODEL_EXTENSIONS = new Set(['.pt', '.pth', '.onnx', '.gguf', '.safetensors', '.ckpt', '.bin', '.h5', '.pb'])
const MEDIA_EXTENSIONS = new Set(['.png', '.jpg', '.jpeg', '.gif', '.webp', '.mp4', '.webm', '.mov', '.mp3', '.wav', '.woff', '.woff2', '.ttf', '.otf', '.eot', '.ico', '.svg'])
const TEXT_EXTENSIONS = new Set([
  '.md', '.markdown', '.txt', '.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs', '.py', '.json', '.yaml', '.yml',
  '.toml', '.sh', '.bash', '.zsh', '.env', '.ini', '.cfg', '.conf', '.html', '.css', '.scss', '.rs', '.go',
  '.java', '.kt', '.swift', '.c', '.h', '.cpp', '.hpp', '.cs', '.rb', '.php', '.sql', '.graphql', '.prisma',
  '.vue', '.svelte', '.astro', '.dockerfile',
])

/** Credential shapes, described without ever printing the value. */
const SECRET_PATTERNS = [
  { id: 'private key block', pattern: /-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----/ },
  { id: 'OpenAI-style key', pattern: /\bsk-[A-Za-z0-9]{24,}\b/ },
  { id: 'AWS access key id', pattern: /\bAKIA[0-9A-Z]{16}\b/ },
  { id: 'GitHub token', pattern: /\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{24,}\b/ },
  { id: 'Google API key', pattern: /\bAIza[0-9A-Za-z_-]{30,}\b/ },
  { id: 'JWT', pattern: /\beyJ[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\./ },
  { id: 'credential assignment', pattern: /(?:api[_-]?key|apikey|secret|password|token)\s*[:=]\s*['"]([^'"\s]{16,})['"]/i, capture: 1, ignorePlaceholders: true },
]

/** Values that look like a credential slot rather than a credential. */
const PLACEHOLDER = /your|example|placeholder|xxx|changeme|change-me|dummy|sample|replace|todo|insert|insert_here|redacted|\.\.\./i

/** Requirements checked against the README. */
const README_CHECKS = [
  {
    id: 'readme.problem',
    title: 'README states the problem and who has it',
    patterns: [/problem|pain|why\b|who (?:is|has) (?:it|this) for|challenge|context/i],
    minBody: 40,
    fix: 'Add a "Problem" section: who has the pain, what it costs them, and why now.',
  },
  {
    id: 'readme.solution',
    title: 'README states what the solution does',
    patterns: [/solution|what it does|our approach|overview|features/i],
    minBody: 40,
    fix: 'Add a "Solution" section: what the product does, in the judge guide\'s words.',
  },
  {
    id: 'readme.setup',
    title: 'README has setup and run steps that work from a clean clone',
    patterns: [/setup|install|run(?:\s|s\b|ning)|getting started|quick ?start|usage/i],
    minBody: 20,
    bodyMatcher: /```|\b(?:npm|pnpm|yarn|pip3?|uv|poetry|docker|make|cargo|go run|python3?|node)\b/,
    fix: 'Add a "Setup" section with the exact commands, env vars and a sample .env.example.',
  },
  {
    id: 'readme.demo',
    title: 'README shows the demo path',
    patterns: [/demo|walkthrough|try it|screenshots?|gif|video/i],
    minBody: 20,
    fix: 'Add a "Demo" section: what to click, what to type, what to expect. A screenshot or GIF near the top helps.',
  },
  {
    id: 'readme.stack',
    title: 'README has a technology inventory',
    patterns: [/technolog|built with|stack|architecture|inventory|dependencies|tools used/i],
    minBody: 20,
    fix: 'Add a "Technology" section: AI tools and models, frameworks, datasets, services, and what is pre-existing.',
  },
  {
    id: 'readme.limits',
    title: 'README separates what is mocked from what is real',
    patterns: [/mocked|real\b|limitations?|future work|more time|what.s next/i],
    minBody: 20,
    fix: 'Add a "Limitations" section: what is mocked, what is real, and what you would do with more time.',
  },
]

/** Headings the generated field sheet must keep. */
const SUBMISSION_FIELDS = [
  { heading: 'Project name', pattern: /^##\s+Project name/im },
  { heading: 'About the project', pattern: /^##\s+About the project/im },
  { heading: 'Repository / demo link', pattern: /^##\s+Repository \/ demo link/im },
  { heading: 'Built with', pattern: /^##\s+Built with/im },
  { heading: 'GenAI tools used', pattern: /^##\s+GenAI tools used/im },
  { heading: 'Generative AI in the project', pattern: /^##\s+Generative AI in the project/im },
]

/** Run one git command in the repository, bounded and never through a shell. */
function git(repo, args, timeoutMs = 20_000) {
  const result = spawnSync('git', ['-C', repo, ...args], { encoding: 'utf8', timeout: timeoutMs, maxBuffer: 8 * 1024 * 1024 })
  if (result.error !== undefined || result.status !== 0) return { ok: false, out: '' }
  return { ok: true, out: result.stdout ?? '' }
}

function readText(path) {
  try {
    return readFileSync(path, 'utf8')
  } catch {
    return undefined
  }
}

function isTextPath(path) {
  const lower = path.toLowerCase()
  const ext = extname(lower)
  if (TEXT_EXTENSIONS.has(ext)) return true
  // Extensionless files are usually text: Dockerfile, Makefile, .env, .npmrc.
  if (ext === '') return true
  return /(^|\/)(dockerfile|makefile|procfile)$/.test(lower)
}

/** Human byte size, one decimal above a kilobyte. */
function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/** Split Markdown into heading sections. */
function splitSections(markdown) {
  const sections = []
  let title = ''
  let level = 0
  let body = ''
  const flush = () => {
    if (title !== '' || body.trim() !== '') sections.push({ title, body: body.trim(), level })
  }
  for (const line of markdown.split(/\r?\n/)) {
    const heading = /^(#{1,6})\s+(.*)$/.exec(line)
    if (heading === null) {
      body += `${line}\n`
      continue
    }
    flush()
    title = (heading[2] ?? '').trim()
    level = (heading[1] ?? '').length
    body = ''
  }
  flush()
  return sections
}

/** First section below the document title whose title matches any pattern. */
function findSection(sections, patterns) {
  for (const section of sections) {
    // A level 1 heading is the document title, not a content section: without
    // this, a project called "Demo Project" would satisfy the demo requirement.
    if (section.level < 2) continue
    if (patterns.some((pattern) => pattern.test(section.title))) return section
  }
  return undefined
}

/** Classify one tracked file by extension and size. */
function classifyTrackedFile(path, size) {
  const ext = extname(path).toLowerCase()
  if (ARCHIVE_EXTENSIONS.has(ext)) {
    return { severity: 'fail', reason: `${path} is an archive (${formatBytes(size)}); share code through the repository, not a ZIP` }
  }
  if (DOCUMENT_EXTENSIONS.has(ext)) {
    return { severity: 'fail', reason: `${path} is a document or key material (${formatBytes(size)}); deliverables and keys stay out of git` }
  }
  if (MODEL_EXTENSIONS.has(ext)) {
    return { severity: 'fail', reason: `${path} is a model or binary artifact (${formatBytes(size)}); keep weights out of git` }
  }
  if (size > 1_048_576) {
    return { severity: 'fail', reason: `${path} is ${formatBytes(size)}; tracked files stay well under 1 MB` }
  }
  if (MEDIA_EXTENSIONS.has(ext)) {
    if (size > 262_144) return { severity: 'warn', reason: `${path} is ${formatBytes(size)}; keep shipped assets small` }
    return undefined
  }
  if (size > 262_144) return { severity: 'warn', reason: `${path} is ${formatBytes(size)}; check whether it belongs in git` }
  return undefined
}

/** Scan one text body for a credential-shaped string. */
function detectSecret(content) {
  for (const candidate of SECRET_PATTERNS) {
    const pattern = new RegExp(candidate.pattern.source, candidate.pattern.flags.includes('g') ? candidate.pattern.flags : `${candidate.pattern.flags}g`)
    for (const match of content.matchAll(pattern)) {
      const value = candidate.capture === undefined ? match[0] : (match[candidate.capture] ?? '')
      if (candidate.ignorePlaceholders === true && PLACEHOLDER.test(value)) continue
      return candidate.id
    }
  }
  return undefined
}

/** Extract http(s) links from Markdown, dropping badge, local and placeholder hosts. */
function extractLinks(markdown) {
  const seen = new Set()
  for (const match of markdown.matchAll(/https?:\/\/[^\s<>"')\]]+/g)) {
    const url = match[0].replace(/[.,;:]+$/, '')
    if (/shields\.io|badgen\.net|badge|localhost|127\.0\.0\.1|example\.com|schema\.org|w3\.org|github\.com\/(?:features|pricing|about)/i.test(url)) continue
    seen.add(url)
  }
  return [...seen]
}

/** Classify a link as the code repository or a demo. */
function classifyLink(url) {
  if (/^https?:\/\/github\.com\/[^/]+\/[^/?#]+/i.test(url) && !/\/(?:issues|pull|actions|blob|tree|releases)\b/i.test(url)) return 'repo'
  return 'demo'
}

/** Normalize a git remote URL to a browser URL. */
function normalizeRemote(remote) {
  const value = remote.trim()
  const scp = /^git@([^:]+):(.+?)(?:\.git)?$/.exec(value)
  if (scp !== null) return `https://${scp[1]}/${scp[2]}`
  if (/^https?:\/\//.test(value)) return value.replace(/\.git$/, '')
  return undefined
}

/** Git facts, tolerating a repository without a HEAD. */
function gitFacts(repo) {
  const inside = git(repo, ['rev-parse', '--is-inside-work-tree'])
  if (!inside.ok || inside.out.trim() !== 'true') return { git: false, commits: 0, authors: 0, dirtyFiles: 0 }
  const branch = git(repo, ['rev-parse', '--abbrev-ref', 'HEAD']).out.trim() || undefined
  const commits = Number(git(repo, ['rev-list', '--count', 'HEAD']).out.trim() || '0')
  const emails = git(repo, ['log', '--format=%ae']).out.split('\n').filter((line) => line !== '')
  const authors = new Set(emails).size
  const lastCommit = git(repo, ['log', '-1', '--format=%cI']).out.trim() || undefined
  const rootSha = git(repo, ['rev-list', '--max-parents=0', 'HEAD']).out.split('\n')[0]?.trim() ?? ''
  const firstCommit = rootSha === '' ? undefined : (git(repo, ['show', '-s', '--format=%cI', rootSha]).out.trim() || undefined)
  const dirtyFiles = git(repo, ['status', '--porcelain']).out.split('\n').filter((line) => line.trim() !== '').length
  const remoteUrl = normalizeRemote(git(repo, ['remote', 'get-url', 'origin']).out)
  return { git: true, branch, commits, authors, firstCommit, lastCommit, dirtyFiles, remoteUrl }
}

/** Repository-relative tracked files, or a bounded walk when git is absent. */
function trackedFiles(repo, isGit) {
  if (isGit) {
    const listed = git(repo, ['ls-files', '-z'])
    if (listed.ok && listed.out !== '') return listed.out.split('\0').filter((path) => path !== '')
  }
  const files = []
  const stack = ['']
  while (stack.length > 0 && files.length < 4000) {
    const relativeDir = stack.pop() ?? ''
    let entries
    try {
      entries = readdirSync(join(repo, relativeDir))
    } catch {
      continue
    }
    for (const name of entries) {
      if (name === '.git' || name === 'node_modules' || name === '.venv' || name === 'venv') continue
      const relative = relativeDir === '' ? name : `${relativeDir}/${name}`
      let entry
      try {
        entry = statSync(join(repo, relative))
      } catch {
        continue
      }
      if (entry.isDirectory()) stack.push(relative)
      else if (entry.isFile()) files.push(relative)
      if (files.length >= 4000) break
    }
  }
  return files
}

/** Locate the repository README, case-insensitively. */
function findReadme(repo) {
  if (!existsSync(repo)) return undefined
  try {
    return readdirSync(repo).filter((name) => /^readme(?:\.md|\.markdown|\.txt)?$/i.test(name))[0]
  } catch {
    return undefined
  }
}

/** Which common stacks the repository contains, in a stable order. */
function detectStack(repo, tracked) {
  const stack = []
  const packagePath = join(repo, 'package.json')
  if (existsSync(packagePath)) {
    stack.push('Node')
    const text = readText(packagePath)
    if (text !== undefined) {
      try {
        const parsed = JSON.parse(text)
        const names = [...Object.keys(parsed.dependencies ?? {}), ...Object.keys(parsed.devDependencies ?? {})]
        for (const name of names.slice(0, 12)) stack.push(name)
      } catch {
        stack.push('package.json (unparseable)')
      }
    }
  }
  if (tracked.some((path) => path === 'requirements.txt' || path === 'pyproject.toml' || path === 'Pipfile')) stack.push('Python')
  if (tracked.includes('Dockerfile')) stack.push('Docker')
  if (tracked.includes('Cargo.toml')) stack.push('Rust')
  if (tracked.includes('go.mod')) stack.push('Go')
  if (tracked.some((path) => path === 'wrangler.toml' || path === 'wrangler.jsonc')) stack.push('Cloudflare Workers')
  if (tracked.some((path) => /^next\.config\./.test(path))) stack.push('Next.js')
  if (tracked.some((path) => /^vite\.config\./.test(path))) stack.push('Vite')
  return [...new Set(stack)]
}

function projectName(repo, readme, sections) {
  const packageText = readText(join(repo, 'package.json'))
  if (packageText !== undefined) {
    try {
      const parsed = JSON.parse(packageText)
      if (typeof parsed.name === 'string' && parsed.name.trim() !== '') return parsed.name.trim()
    } catch {
      // Fall through to the README title.
    }
  }
  const title = sections.find((section) => section.title !== '')?.title
  if (title !== undefined && readme !== undefined) return title
  return basename(repo)
}

function projectDescription(readme, sections) {
  if (readme === undefined) return undefined
  const prose = sections.map((section) => section.body).join('\n\n').replace(/```[\s\S]*?```/g, ' ')
  const paragraph = prose.split(/\n\s*\n/).map((part) => part.trim()).find((part) => part.length >= 30)
  if (paragraph === undefined) return undefined
  return paragraph.length > 300 ? `${paragraph.slice(0, 297).trimEnd()}...` : paragraph
}

/** Probe one URL, treating 404 as "not public or not there". */
async function probeUrl(url, timeoutMs) {
  try {
    const response = await fetch(url, {
      method: 'GET',
      redirect: 'follow',
      signal: AbortSignal.timeout(timeoutMs),
      headers: { 'user-agent': 'dsh-sinceai-check/0.1 (+https://sinceai.ai)' },
    })
    const status = response.status
    if (status === 404) return { ok: false, detail: `${url} -> 404 (not found, or not public while logged out)` }
    if (status >= 200 && status < 400) return { ok: true, detail: `${url} -> ${status}` }
    return { ok: false, detail: `${url} -> ${status}` }
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error)
    return { ok: false, detail: `${url} -> could not verify (${reason})` }
  }
}

/** Parse one ISO instant, failing loudly on a typo. */
function instant(name, value) {
  const parsed = Date.parse(value)
  if (Number.isNaN(parsed)) throw new Error(`${name} is not an ISO 8601 instant: ${JSON.stringify(value)}`)
  return parsed
}

/** The phase containing `now`, plus the instant it ends. */
function phaseAt(now) {
  const summariesAt = instant('summariesAt', EVENT.summariesAt)
  const eventStart = instant('eventStart', EVENT.eventStart)
  const buildStartsAt = instant('buildStartsAt', EVENT.buildStartsAt)
  const freezeAt = instant('freezeAt', EVENT.freezeAt)
  const deadline = instant('deadline', EVENT.deadline)
  if (now < summariesAt) return { phase: PHASES.prep, endsAt: summariesAt }
  if (now < eventStart) return { phase: PHASES.shortlist, endsAt: eventStart }
  if (now < buildStartsAt) return { phase: PHASES.onboarding, endsAt: buildStartsAt }
  if (now < freezeAt) return { phase: PHASES.build, endsAt: freezeAt }
  if (now < deadline - SUBMIT_WINDOW_MS) return { phase: PHASES.freeze, endsAt: deadline - SUBMIT_WINDOW_MS }
  if (now < deadline) return { phase: PHASES.submit, endsAt: deadline }
  return { phase: PHASES.judging }
}

/** Human distance between two instants. */
function formatDuration(ms) {
  const totalMinutes = Math.floor(Math.abs(ms) / 60_000)
  if (totalMinutes === 0) return 'under a minute'
  const days = Math.floor(totalMinutes / 1440)
  const hours = Math.floor((totalMinutes % 1440) / 60)
  const minutes = totalMinutes % 60
  const parts = []
  if (days > 0) parts.push(`${days}d`)
  if (days > 0 || hours > 0) parts.push(`${hours}h`)
  if (days === 0) parts.push(`${minutes}m`)
  else if (minutes > 0 && days < 2) parts.push(`${minutes}m`)
  return parts.join(' ')
}

/** One instant rendered in the event zone. */
function formatInstant(ms) {
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: EVENT.timeZone,
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
    timeZoneName: 'short',
  }).formatToParts(new Date(ms))
  const field = (type) => parts.find((part) => part.type === type)?.value ?? ''
  const zone = field('timeZoneName')
  const head = `${field('weekday')} ${field('day')} ${field('month')} ${field('hour')}:${field('minute')}`
  return zone === '' ? head : `${head} ${zone}`
}

/** The clock line printed above the report. */
function renderClock(now) {
  const { phase, endsAt } = phaseAt(now)
  const toDeadline = instant('deadline', EVENT.deadline) - now
  const remaining = toDeadline >= 0 ? `${formatDuration(toDeadline)} to submission` : `submission closed ${formatDuration(-toDeadline)} ago`
  const until = endsAt === undefined ? '' : `, until ${formatInstant(endsAt)}`
  return [
    `SinceAI clock: ${remaining} (${formatInstant(instant('deadline', EVENT.deadline))}). Phase: ${phase.label}${until}.`,
    `Rule for this phase: ${phase.rule}`,
  ].join('\n')
}

/** Run every check against one repository. */
async function checkRepo(repo, options = {}) {
  const items = []
  const gitInfo = gitFacts(repo)
  const files = trackedFiles(repo, gitInfo.git)
  const readmeName = findReadme(repo)
  const readmePath = readmeName === undefined ? undefined : join(repo, readmeName)
  const readme = readmePath === undefined ? undefined : readText(readmePath)
  const sections = readme === undefined ? [] : splitSections(readme)

  if (readme === undefined) {
    items.push({ id: 'readme.present', title: 'Repository README', severity: 'fail', detail: 'No README at the repository root.', fix: 'Write a README.md with the sections the judge guide asks for.' })
  } else {
    items.push({ id: 'readme.present', title: 'Repository README', severity: 'pass', detail: `Found ${readmeName} (${readme.length} characters).` })
  }
  if (readme !== undefined) {
    for (const check of README_CHECKS) {
      const section = findSection(sections, check.patterns)
      if (section !== undefined) {
        const body = section.body.trim()
        if (body.length < check.minBody) {
          items.push({ id: check.id, title: check.title, severity: 'warn', detail: `"${section.title}" is present but thin (${body.length} characters).`, fix: check.fix })
        } else if (check.bodyMatcher !== undefined && !check.bodyMatcher.test(body)) {
          items.push({ id: check.id, title: check.title, severity: 'warn', detail: `"${section.title}" has no command to run.`, fix: check.fix })
        } else {
          items.push({ id: check.id, title: check.title, severity: 'pass', detail: `Found under "${section.title}".` })
        }
      } else if (check.patterns.some((pattern) => pattern.test(readme))) {
        items.push({ id: check.id, title: check.title, severity: 'warn', detail: 'Mentioned in prose, but not as its own section.', fix: check.fix })
      } else {
        items.push({ id: check.id, title: check.title, severity: 'fail', detail: 'No matching section.', fix: check.fix })
      }
    }
  }

  const licenceName = files.find((path) => /^(?:licen[cs]e|copying)(?:\.[a-z]+)?$/i.test(basename(path)))
  const licenceInReadme = sections.some((section) => /licen[cs]e/i.test(section.title))
  const licence = licenceName === undefined ? undefined : basename(licenceName)
  if (licence !== undefined) {
    items.push({ id: 'licence.present', title: 'Licence', severity: 'pass', detail: `Found ${licence}.` })
  } else if (licenceInReadme) {
    items.push({ id: 'licence.present', title: 'Licence', severity: 'warn', detail: 'The README has a licence section but no LICENCE file.', fix: 'Add a LICENCE file at the root so the terms travel with the code.' })
  } else {
    items.push({ id: 'licence.present', title: 'Licence', severity: 'fail', detail: 'No licence file.', fix: 'Add a LICENCE file (MIT or whatever the challenge terms allow).' })
  }

  const badEnv = files.filter((path) => /(^|\/)\.env(?:\.[^/]+)?$/.test(path) && !/\.(?:example|sample|template)$/i.test(path))
  const envExample = files.some((path) => /(^|\/)\.env\.(?:example|sample|template)$/i.test(path))
  if (badEnv.length > 0) {
    items.push({ id: 'secrets.env', title: 'No tracked .env file', severity: 'fail', detail: `Tracked env files: ${badEnv.slice(0, 5).join(', ')}.`, fix: 'Remove them from the index (git rm --cached), add them to .gitignore, and rotate every key they held.' })
  } else {
    items.push({ id: 'secrets.env', title: 'No tracked .env file', severity: 'pass', detail: 'No env file is tracked.' })
  }
  const mentionsEnv = readme !== undefined && /\b(?:environment variable|env var|API[_ ]?key|secret|token)\b/i.test(readme)
  if (envExample) {
    items.push({ id: 'env.example', title: 'Sample .env.example', severity: 'pass', detail: 'Found an env example file.' })
  } else if (mentionsEnv) {
    items.push({ id: 'env.example', title: 'Sample .env.example', severity: 'warn', detail: 'The README mentions env vars or keys but no .env.example is tracked.', fix: 'Add .env.example with every variable name and a placeholder value.' })
  } else {
    items.push({ id: 'env.example', title: 'Sample .env.example', severity: 'pass', detail: 'No env vars referenced, so no sample file is needed.' })
  }
  const gitignore = readText(join(repo, '.gitignore'))
  if (gitignore !== undefined && !/(^|\n)\s*\.env\b/.test(gitignore)) {
    items.push({ id: 'env.gitignore', title: '.env is gitignored', severity: 'warn', detail: '.gitignore does not ignore .env.', fix: 'Add .env and .env.* to .gitignore, keeping !.env.example.' })
  }

  const secretHits = []
  let scannedBytes = 0
  let scannedFiles = 0
  for (const relative of files) {
    if (secretHits.length >= 8 || scannedBytes > 8 * 1024 * 1024 || scannedFiles > 800) break
    if (!isTextPath(relative)) continue
    const absolute = join(repo, relative)
    let size = 0
    try {
      size = statSync(absolute).size
    } catch {
      continue
    }
    if (size > 262_144) continue
    const text = readText(absolute)
    if (text === undefined) continue
    scannedBytes += size
    scannedFiles += 1
    const hit = detectSecret(text)
    if (hit !== undefined) secretHits.push(`${relative} (${hit})`)
  }
  if (secretHits.length > 0) {
    items.push({ id: 'secrets.content', title: 'No credentials in tracked files', severity: 'fail', detail: `Credential-shaped strings: ${secretHits.join('; ')}.`, fix: 'Remove the value, load it from the environment, and rotate the key. History keeps it, so rewrite the branch if it was pushed.' })
  } else {
    items.push({ id: 'secrets.content', title: 'No credentials in tracked files', severity: 'pass', detail: `Scanned ${scannedFiles} tracked text files.` })
  }

  const large = []
  for (const relative of files) {
    let size = 0
    try {
      size = statSync(join(repo, relative)).size
    } catch {
      continue
    }
    const finding = classifyTrackedFile(relative, size)
    if (finding === undefined) continue
    large.push({ id: 'binary', title: 'No binary or oversized tracked file', severity: finding.severity, detail: finding.reason, fix: 'Remove it from git and share the deliverable outside the repository, or shrink the asset.' })
  }
  if (large.length === 0) {
    items.push({ id: 'binary', title: 'No binary or oversized tracked file', severity: 'pass', detail: `Checked ${files.length} tracked files against the size rules.` })
  } else {
    items.push(...large.slice(0, 8))
  }

  const links = extractLinks(readme ?? '').map((url) => ({ url, kind: classifyLink(url) }))
  const repoUrl = gitInfo.remoteUrl ?? links.find((link) => link.kind === 'repo')?.url
  if (repoUrl !== undefined) {
    items.push({ id: 'links.repo', title: 'Repository link', severity: 'pass', detail: repoUrl })
  } else {
    items.push({ id: 'links.repo', title: 'Repository link', severity: 'fail', detail: 'No repository remote or GitHub link found.', fix: 'Push the repo and add its URL to the README.' })
  }
  const demoUrl = links.find((link) => link.kind === 'demo')?.url
  if (demoUrl !== undefined) {
    items.push({ id: 'links.demo', title: 'Demo link', severity: 'pass', detail: demoUrl })
  } else {
    items.push({ id: 'links.demo', title: 'Demo link', severity: 'warn', detail: 'No demo or deployment link found.', fix: 'Deploy the demo and add its URL, then check it opens while logged out.' })
  }

  if (options.public === true) {
    const probes = [repoUrl, demoUrl, ...links.filter((link) => link.kind === 'demo').map((link) => link.url)]
      .filter((url) => typeof url === 'string')
      .filter((url, index, all) => all.indexOf(url) === index)
      .slice(0, options.maxLinks ?? 5)
    if (probes.length === 0) {
      items.push({ id: 'links.public', title: 'Links open while logged out', severity: 'warn', detail: 'No links to probe.' })
    } else {
      const results = await Promise.all(probes.map((url) => probeUrl(url, options.timeoutMs ?? 8000)))
      const failures = results.filter((result) => !result.ok)
      items.push({
        id: 'links.public',
        title: 'Links open while logged out',
        severity: failures.length === 0 ? 'pass' : 'fail',
        detail: results.map((result) => result.detail).join('; '),
        fix: failures.length === 0 ? undefined : 'Make the repository public (or grant judge access), fix the demo URL, and check again from a private window.',
      })
    }
  }

  if (!gitInfo.git) {
    items.push({ id: 'history.git', title: 'Git history', severity: 'fail', detail: 'The directory is not a git repository.', fix: 'Initialise git, commit the work with meaningful messages, and push it.' })
  } else if (gitInfo.commits === 0) {
    items.push({ id: 'history.git', title: 'Git history', severity: 'fail', detail: 'No commits yet.', fix: 'Commit the work now and keep committing through the event.' })
  } else if (gitInfo.commits === 1) {
    items.push({ id: 'history.git', title: 'Git history', severity: 'warn', detail: 'Only one commit, so the event work is hard to separate from pre-existing work.', fix: 'Commit in small steps with meaningful messages.' })
  } else {
    const since = gitInfo.firstCommit === undefined ? '' : ` since ${gitInfo.firstCommit.slice(0, 10)}`
    items.push({ id: 'history.git', title: 'Git history', severity: 'pass', detail: `${gitInfo.commits} commits by ${gitInfo.authors} author(s)${since}.` })
  }
  if (gitInfo.dirtyFiles > 0) {
    items.push({ id: 'history.dirty', title: 'Working tree committed', severity: 'warn', detail: `${gitInfo.dirtyFiles} uncommitted change(s).`, fix: 'Commit or discard them before the submission check.' })
  } else if (gitInfo.git) {
    items.push({ id: 'history.dirty', title: 'Working tree committed', severity: 'pass', detail: 'Working tree clean.' })
  }

  const submissionText = readText(join(repo, 'SUBMISSION.md'))
  if (submissionText !== undefined) {
    const missing = SUBMISSION_FIELDS.filter((field) => !field.pattern.test(submissionText)).map((field) => field.heading)
    const todos = (submissionText.match(/^TODO:/gm) ?? []).length
    if (todos > 0 || missing.length > 0) {
      items.push({
        id: 'submission.ready',
        title: 'Submission field sheet is filled',
        severity: 'fail',
        detail: `${todos} TODO line(s) remain; missing headings: ${missing.length === 0 ? 'none' : missing.join(', ')}.`,
        fix: 'Answer every TODO in SUBMISSION.md, then run this check again.',
      })
    } else {
      items.push({ id: 'submission.ready', title: 'Submission field sheet is filled', severity: 'pass', detail: 'All fields present and no TODO lines remain.' })
    }
  }

  const counts = {
    pass: items.filter((item) => item.severity === 'pass').length,
    warn: items.filter((item) => item.severity === 'warn').length,
    fail: items.filter((item) => item.severity === 'fail').length,
  }
  const facts = {
    name: projectName(repo, readme, sections),
    description: projectDescription(readme, sections),
    stack: detectStack(repo, files),
    repoUrl,
    links,
    commits: gitInfo.commits,
    authors: gitInfo.authors,
    firstCommit: gitInfo.firstCommit,
    lastCommit: gitInfo.lastCommit,
    dirtyFiles: gitInfo.dirtyFiles,
    branch: gitInfo.branch,
    envExample,
    licence,
    readmePath: readmeName,
    git: gitInfo.git,
  }
  return { repo, items, facts, counts, ready: counts.fail === 0 }
}

/** One line per check, grouped by severity. */
function renderReport(result) {
  const { facts, counts } = result
  const lines = ['# SinceAI submission check', '']
  const gitLine = facts.git
    ? `git on ${facts.branch ?? 'detached HEAD'}, ${facts.commits} commit(s), ${facts.authors} author(s), ${facts.dirtyFiles} uncommitted change(s)`
    : 'not a git repository'
  lines.push(`- Repo: \`${result.repo}\` (${gitLine})`)
  if (facts.readmePath !== undefined) lines.push(`- README: ${facts.readmePath}`)
  if (facts.stack.length > 0) lines.push(`- Stack: ${facts.stack.join(', ')}`)
  if (facts.repoUrl !== undefined) lines.push(`- Repo link: ${facts.repoUrl}`)
  lines.push(`- Verdict: **${result.ready ? 'READY' : 'NOT READY'}**, ${counts.fail} failure(s), ${counts.warn} warning(s), ${counts.pass} pass(es).`)
  const bySeverity = (severity) => result.items.filter((item) => item.severity === severity)
  for (const [severity, heading] of [['fail', 'Failures'], ['warn', 'Warnings'], ['pass', 'Passed']]) {
    const group = bySeverity(severity)
    if (group.length === 0) continue
    lines.push('', `## ${heading}`)
    for (const item of group) {
      lines.push(`- \`${item.id}\` ${item.title}: ${item.detail}`)
      if (severity !== 'pass' && item.fix !== undefined) lines.push(`  Fix: ${item.fix}`)
    }
  }
  lines.push('', 'Run the check again with `--public` to probe the links, and `--write` to refresh the submission field sheet.')
  return lines.join('\n')
}

/** Today's date in the event zone, as YYYY-MM-DD. */
function todayInEventZone() {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: EVENT.timeZone, year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date())
  const field = (type) => parts.find((part) => part.type === type)?.value ?? ''
  return `${field('year')}-${field('month')}-${field('day')}`
}

/** Render the sinceai.app field sheet from the repository facts. */
function renderSubmission(result) {
  const { facts } = result
  const stack = facts.stack.length > 0 ? facts.stack.join(', ') : 'TODO: list the technologies'
  const demoLinks = facts.links.filter((link) => link.kind === 'demo').map((link) => link.url).join('\n') || 'TODO: demo URL'
  return `# SinceAI submission sheet

Generated by \`scripts/sinceai_check.mjs\` from \`${facts.name}\` on ${todayInEventZone()}. Paste each answer into the matching field on sinceai.app.

The form caps "About the project" at 5,000 characters. Submission closes Sunday 8 November 2026 at 10:00 EET. Save the entry before attaching files, and check every link from a private window.

## Project name

${facts.name}

## Submission URL

${facts.repoUrl ?? 'TODO: the public URL where judges view the project'}

## About the project (max 5,000 characters)

TODO: the problem in one paragraph: who has it and what it costs them.
TODO: the solution in one paragraph: what the product does and what the demo shows.
TODO: the evidence: one number, before/after, or concrete scenario that shows it works.
TODO: data and privacy: what data it touches, where it goes, and how it is handled.

## Repository / demo link

${facts.repoUrl ?? 'TODO: repository URL'}
${demoLinks}

## Built with

${stack}

## Technology feedback

TODO: one paragraph on the technology used over the weekend: what worked, what did not, what we would use again.

## GenAI tools used

TODO: tick these on the form: dsh (DeepSeek Harness), plus every model and API the repo actually calls.

## Generative AI in the project

TODO: did the project implement a GenAI model or API, how, and why. Write N/A only if it did not.

## Challenge IP terms

Every member ticks this in sinceai.app personally. The team cannot submit until all of them have.

## Challenge

Filled by the organisers from the Friday selection. Do not edit.

## Optional

- YouTube video URL: TODO: the 2 minute demo video
- Pitch deck: TODO: PDF or PPTX, only if it helps
- Public summary, for a confidential challenge: TODO or N/A

## Demo video shot list (about 2 minutes)

1. Title card: project name, challenge company, one-line problem (5 s).
2. The problem in one real scene, with the person or data it affects (15 s).
3. The product doing the core job end to end, no cuts (40 s).
4. The moment that proves it works: the output, the number, the before/after (20 s).
5. Responsible handling: where the data goes, what is mocked (15 s).
6. Close: what is real today and what comes next (10 s).
`
}

/** Write the field sheet without clobbering a hand-edited one. */
function writeSubmissionSheet(result) {
  const target = join(result.repo, 'SUBMISSION.md')
  const path = existsSync(target) ? join(result.repo, 'SUBMISSION.generated.md') : target
  writeFileSync(path, renderSubmission(result), 'utf8')
  return path
}

/** Print usage. */
function usage() {
  return [
    'Usage: node scripts/sinceai_check.mjs [options]',
    '',
    'Options:',
    '  --public          probe repository and demo links over the network',
    '  --write           write SUBMISSION.md (or SUBMISSION.generated.md if one exists)',
    '  --json            print the JSON result instead of the Markdown report',
    '  --repo <path>     repository root; defaults to the current directory',
    '  --max-links <n>   most links to probe with --public (default 5)',
    '  --help            print this message',
    '',
    'Exit codes: 0 ready, 1 not ready, 2 error.',
  ].join('\n')
}

/** Parse CLI arguments. */
function parseArgs(argv) {
  const options = { public: false, write: false, json: false, repo: undefined, maxLinks: 5, help: false }
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index]
    if (arg === '--public') options.public = true
    else if (arg === '--write') options.write = true
    else if (arg === '--json') options.json = true
    else if (arg === '--help' || arg === '-h') options.help = true
    else if (arg === '--repo') {
      const value = argv[index + 1]
      if (value === undefined) throw new Error('--repo needs a path')
      options.repo = value
      index += 1
    } else if (arg.startsWith('--repo=')) options.repo = arg.slice('--repo='.length)
    else if (arg === '--max-links') {
      const value = Number(argv[index + 1])
      if (!Number.isInteger(value) || value < 0) throw new Error('--max-links needs a non-negative integer')
      options.maxLinks = value
      index += 1
    } else if (arg.startsWith('--max-links=')) {
      const value = Number(arg.slice('--max-links='.length))
      if (!Number.isInteger(value) || value < 0) throw new Error('--max-links needs a non-negative integer')
      options.maxLinks = value
    } else {
      throw new Error(`unknown argument ${JSON.stringify(arg)}`)
    }
  }
  return options
}

/** CLI entry point. */
async function main() {
  const options = parseArgs(process.argv.slice(2))
  if (options.help) {
    console.log(usage())
    return
  }
  const repo = resolve(options.repo ?? process.cwd())
  if (!existsSync(repo) || !statSync(repo).isDirectory()) {
    console.error(`sinceai_check: ${JSON.stringify(repo)} is not a directory`)
    process.exitCode = 2
    return
  }
  const result = await checkRepo(repo, options)
  if (options.write) {
    const written = writeSubmissionSheet(result)
    if (!options.json) console.log(`Submission field sheet written to ${written}.\n`)
  }
  if (options.json) {
    console.log(JSON.stringify(result, null, 2))
  } else {
    console.log(renderClock(Date.now()))
    console.log('')
    console.log(renderReport(result))
  }
  process.exitCode = result.ready ? 0 : 1
}

main().catch((error) => {
  console.error(`sinceai_check: ${error instanceof Error ? error.message : String(error)}`)
  process.exitCode = 2
})
