"""The request and response shapes the API serves, as Pydantic models.

The models exist so `app.openapi()` describes fields instead of an untyped
object. `make openapi` writes that schema to `docs/openapi.json`, and
`app/server/tests/test_openapi.py` fails when the committed file drifts from
the app, so the published contract is the served one.

The register, the plant spec and the service table are generated tables: a
column can appear without this file changing. Every model therefore allows
extra keys, and only the keys the front end reads are required. `main.py` holds
the routes and their models together.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ApiModel(BaseModel):
    """Base model: a generated table can grow a column without a 500 here."""

    model_config = ConfigDict(extra="allow")


class Gate(ApiModel):
    """The photo gate: whether the frame is good enough to read a plate from."""

    ok: bool
    character_px: float
    blur: float
    message: str


class PlateFields(ApiModel):
    """The fields recovered from the nameplate, written the way the plate writes them."""

    type: str | None = None
    dn: str | None = None
    pn: str | None = None
    body: str | None = None
    serial: str | None = None


class Plate(ApiModel):
    """A read nameplate: its fields, their confidence and the family they imply."""

    fields: PlateFields
    confidence: dict[str, float]
    family: str | None = None


class Section(ApiModel):
    """One manual section: where it is, and the one or two lines quoted from it."""

    id: str
    title: str
    page: int
    quote: str
    anchor: str


class ServiceAction(ApiModel):
    """The next maintenance action for a part, as the service table states it."""

    family: str | None = None
    part: str
    action: str
    interval: str
    source: str


class RegisterAsset(ApiModel):
    """One row of the CMMS-shaped asset register."""

    tag: str
    line: str | None = None
    family: str | None = None
    type: str | None = None
    dn: str | None = None
    pn: str | None = None
    body: str | None = None
    serial: str | None = None
    install_date: str | None = None
    last_service: str | None = None
    criticality: str | None = None
    spare_group: str | None = None
    overdue: bool = False


class Neighbour(ApiModel):
    """Another asset on the same line, for the maintenance graph."""

    tag: str
    label: str | None = None
    overdue: bool = False


class PlantAsset(ApiModel):
    """An asset in the plant spec, in metres, with its inspection waypoint."""

    id: str
    kind: str
    tag: str
    pos: tuple[float, float, float]
    size: tuple[float, float, float]
    waypoint: tuple[float, float]
    interval: str
    last_service: str
    criticality: str
    shape: str | None = None
    type: str | None = None
    dn: str | None = None
    pn: str | None = None
    symptom: str | None = None


class Area(ApiModel):
    """The floor the route is planned on, in metres, y is up."""

    x0: float
    x1: float
    z0: float
    z1: float
    height: float


class Door(ApiModel):
    """The door at one end of the floor: the default place a route starts."""

    x0: float
    x1: float
    z: float


class Aisle(ApiModel):
    """A walkable aisle, as the two ends of its centre line and its width."""

    id: str
    points: list[tuple[float, float]]
    width: float


class Blocker(ApiModel):
    """A fixed obstruction the route planner turns into blocked cells."""

    id: str
    label: str
    pos: tuple[float, float, float]
    size: tuple[float, float, float]


class WorkOrder(ApiModel):
    """The inspection the register implies: last service plus the interval."""

    interval: str
    last_service: str
    due: str
    due_in_days: int
    symptom: str


class HealthResponse(ApiModel):
    """What the process can see: the two indexes it reads and its version."""

    ok: bool
    corpus_sections: int
    assets: int
    version: str


class ScanResponse(ApiModel):
    """Everything one scan yields: the plate, the asset, the cited sections, the action."""

    gate: Gate
    plate: Plate | None
    asset: RegisterAsset | None
    sections: list[Section]
    action: ServiceAction | None


class AssetGraphResponse(ApiModel):
    """One register asset with its line neighbours and the spares it shares."""

    asset: RegisterAsset | None
    neighbours: list[Neighbour]
    shared_spares: list[str]


class SectionResponse(ApiModel):
    section: Section | None


class PlantResponse(ApiModel):
    """The plant spec the mission view draws and plans routes on."""

    name: str
    note: str
    source: str
    area: Area
    door: Door
    start: tuple[float, float]
    assets: list[PlantAsset]
    aisles: list[Aisle]
    blockers: list[Blocker]


class CloudMetaResponse(ApiModel):
    """How to read the binary cloud: how many points, and in what layout."""

    available: bool
    count: int
    layout: str | None = None
    source: str


class ExplainResponse(ApiModel):
    """A work order and its cited reason, or why there is no asset to explain."""

    asset: PlantAsset | None = None
    reason: str | None = None
    request: WorkOrder | None = None
    sections: list[Section]
    action: ServiceAction | None = None


class RouteResponse(ApiModel):
    """A route and its cost, or the reason there is no route. A failure has no distance."""

    reachable: bool
    path: list[tuple[float, float]]
    reason: str | None = None
    distance_m: float | None = None
    clearance_m: float | None = None
    astar_ms: float | None = None
    cells: int | None = None
    start: tuple[float, float] | None = None
    goal: tuple[float, float] | None = None
    agent_radius_m: float | None = None


class ExplainRequest(ApiModel):
    """Ask for an inspection by asset id. `to` is the older name for the same thing."""

    asset_id: str | None = None
    to: str | None = None
    symptom: str | None = None


class RouteRequest(ApiModel):
    """Ask for a route to an asset id or a goal point, with optional blocked rectangles."""

    to: str | None = None
    goal: tuple[float, float] | None = None
    start: tuple[float, float] | None = None
    blockers: list[tuple[float, float, float, float]] | None = None
    agent_radius_m: float | None = None
