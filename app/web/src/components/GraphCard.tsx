import type { GraphResponse, Neighbour, ScanState } from '../types'
import Card from './Card'

// 25 nodes maximum including the asset itself.
const MAX_NEIGHBOURS = 24
const VIEW_WIDTH = 560
const VIEW_HEIGHT = 380
const CENTER_X = VIEW_WIDTH / 2
const CENTER_Y = 175

type GraphNode = Neighbour & {
  overdue: boolean
  x: number
  y: number
  labelX: number
  labelY: number
  anchor: 'start' | 'middle' | 'end'
}

function layoutNodes(neighbours: Neighbour[]): GraphNode[] {
  // Overdue neighbours first, so the red node is easy to find in a demo.
  const ordered = [...neighbours].sort(
    (a, b) => Number(Boolean(b.overdue)) - Number(Boolean(a.overdue)),
  )
  const shown = ordered.slice(0, MAX_NEIGHBOURS)
  const count = shown.length

  const radiusX = count <= 4 ? 165 : count <= 8 ? 185 : 200
  const radiusY = count <= 4 ? 100 : count <= 8 ? 112 : 122

  return shown.map((neighbour, index) => {
    const angle = -Math.PI / 2 + (index * 2 * Math.PI) / Math.max(count, 1)
    const cos = Math.cos(angle)
    const sin = Math.sin(angle)
    const x = CENTER_X + cos * radiusX
    const y = CENTER_Y + sin * radiusY
    const labelX = CENTER_X + cos * (radiusX + 56)
    const labelY = CENTER_Y + sin * (radiusY + 36) + 6
    const anchor: GraphNode['anchor'] =
      Math.abs(cos) < 0.3 ? 'middle' : cos > 0 ? 'start' : 'end'

    return {
      tag: neighbour.tag,
      label: neighbour.label,
      overdue: Boolean(neighbour.overdue),
      x,
      y,
      labelX,
      labelY,
      anchor,
    }
  })
}

type GraphCardProps = {
  graph: GraphResponse | null
  loading: boolean
  error: string | null
  assetTag: string | null
  state: ScanState
  className?: string
}

export default function GraphCard({
  graph,
  loading,
  error,
  assetTag,
  state,
  className = '',
}: GraphCardProps) {
  const nodes = graph ? layoutNodes(graph.neighbours) : []
  const hiddenNeighbours = graph ? Math.max(0, graph.neighbours.length - nodes.length) : 0
  const tag = graph?.asset.tag ?? assetTag

  return (
    <Card
      title="Line neighbours"
      className={className}
      badge={
        nodes.length > 0 ? (
          <span className="text-base font-bold text-slate-700">
            {nodes.length} neighbour{nodes.length === 1 ? '' : 's'}
          </span>
        ) : undefined
      }
    >
      {loading ? (
        <p className="flex items-center gap-3 text-base font-semibold text-slate-800">
          <span
            aria-hidden="true"
            className="h-5 w-5 animate-spin rounded-full border-[3px] border-slate-700 border-t-transparent"
          />
          loading line neighbours...
        </p>
      ) : null}

      {error ? <p className="text-base font-bold text-red-800">{error}</p> : null}

      {!loading && !error && state === 'idle' ? (
        <p className="text-base font-medium text-slate-700">
          No graph yet. It appears when a scan matches an asset.
        </p>
      ) : null}

      {!loading && !error && state === 'error' ? (
        <p className="text-base font-semibold text-slate-800">
          The last scan did not return an asset tag, so there is no graph.
        </p>
      ) : null}

      {!loading && !error && state === 'done' && !tag ? (
        <p className="text-base font-semibold text-slate-800">
          No asset tag, so there are no line neighbours to draw.
        </p>
      ) : null}

      {!loading && !error && state === 'done' && tag && !graph ? (
        <p className="text-base font-semibold text-slate-800">The line graph did not load.</p>
      ) : null}

      {!loading && !error && graph && tag ? (
        <>
          <svg
            viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`}
            className="h-auto w-full"
            role="img"
            aria-label={`asset ${tag} and ${nodes.length} line neighbours`}
          >
            <g stroke="#64748b" strokeWidth="2.5">
              {nodes.map((node) => (
                <line
                  key={`edge-${node.tag}`}
                  x1={CENTER_X}
                  y1={CENTER_Y}
                  x2={node.x}
                  y2={node.y}
                />
              ))}
            </g>

            <circle
              cx={CENTER_X}
              cy={CENTER_Y}
              r="34"
              fill="#0f172a"
              stroke="#0f172a"
              strokeWidth="3"
            />
            <text
              x={CENTER_X}
              y={CENTER_Y + 7}
              textAnchor="middle"
              fontSize="18"
              fontWeight="700"
              fill="#ffffff"
            >
              {tag}
            </text>

            {nodes.map((node) => (
              <g key={`node-${node.tag}`}>
                <circle
                  cx={node.x}
                  cy={node.y}
                  r={node.overdue ? 13 : 12}
                  fill={node.overdue ? '#b91c1c' : '#475569'}
                  stroke={node.overdue ? '#7f1d1d' : '#0f172a'}
                  strokeWidth="3"
                />
                <text
                  x={node.labelX}
                  y={node.labelY}
                  textAnchor={node.anchor}
                  fontSize="16"
                  fontWeight="700"
                  fill={node.overdue ? '#991b1b' : '#0f172a'}
                >
                  {node.tag}
                </text>
                {node.overdue ? (
                  <text
                    x={node.labelX}
                    y={node.labelY + 22}
                    textAnchor={node.anchor}
                    fontSize="16"
                    fontWeight="700"
                    fill="#b91c1c"
                  >
                    overdue
                  </text>
                ) : node.label ? (
                  <text
                    x={node.labelX}
                    y={node.labelY + 22}
                    textAnchor={node.anchor}
                    fontSize="16"
                    fontWeight="600"
                    fill="#334155"
                  >
                    {node.label}
                  </text>
                ) : null}
              </g>
            ))}
          </svg>

          <div className="mt-2 flex flex-wrap items-baseline gap-x-6 gap-y-1 text-base font-semibold text-slate-800">
            <span className="inline-flex items-center gap-2">
              <span
                aria-hidden="true"
                className="h-4 w-4 rounded-full border-2 border-red-800 bg-red-700"
              />
              overdue
            </span>
            <span className="inline-flex items-center gap-2">
              <span
                aria-hidden="true"
                className="h-4 w-4 rounded-full border-2 border-slate-900 bg-slate-600"
              />
              in service
            </span>
          </div>

          {hiddenNeighbours > 0 ? (
            <p className="mt-2 text-base font-semibold text-slate-700">
              showing {nodes.length} of {graph.neighbours.length} neighbours
            </p>
          ) : null}

          {graph.shared_spares && graph.shared_spares.length > 0 ? (
            <div className="mt-3">
              <div className="text-base font-bold text-slate-900">shared spares</div>
              <ul className="mt-1 flex flex-wrap gap-2">
                {graph.shared_spares.map((spare) => (
                  <li
                    key={spare}
                    className="rounded-md border-2 border-slate-300 bg-slate-50 px-2 py-0.5 text-base font-semibold text-slate-800"
                  >
                    {spare}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </>
      ) : null}
    </Card>
  )
}
