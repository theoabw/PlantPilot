PY := uv run

# The port the demo serves on. Override it when 8000 is already taken, so a
# second build does not fail after it has built everything:
#   make demo PORT=8001
PORT ?= 8000

# Which supplied capture the demo uses. `equipment` is the complete capture the
# organiser re-uploaded after the first delivery was found truncated, and it is
# the default; `boiler` is the capture named in the brief as delivered. The
# choice sets every artifact path, so
#   make demo CAPTURE=boiler
# runs the named capture with no other overrides.
CAPTURE ?= equipment
ifeq ($(CAPTURE),equipment)
CAPTURE_DIR ?= data/equipment
CAPTURE_PLY ?= data/supplied/Equipment Room.ply
VIEWER_PLY ?= data/viewer/equipment.ply
else ifeq ($(CAPTURE),boiler)
CAPTURE_DIR ?= data/scene
CAPTURE_PLY ?= data/supplied/Industrial Boiler Room (1).ply
VIEWER_PLY ?= data/viewer/boiler.ply
else
$(error CAPTURE must be boiler or equipment, got '$(CAPTURE)')
endif

PLY ?= $(CAPTURE_PLY)
PACK_XLSX ?= data/supplied/builder_pack.xlsx
PACK ?= $(CAPTURE_DIR)/pack.json
SCENE ?= $(CAPTURE_DIR)/scene.npz
OBJECTS ?= $(CAPTURE_DIR)/objects.json
ASSETS ?= $(CAPTURE_DIR)/assets.json
ANCHORS ?= $(CAPTURE_DIR)/anchors.json
FILTERS ?= data/viewer/filters/$(notdir $(CAPTURE_DIR))
ANCHORS_FIXTURE ?= fixtures/scene/anchors_$(CAPTURE).json
INSTANCES_FIXTURE ?= fixtures/scene/instances_$(CAPTURE).json
MAPPED ?= $(CAPTURE_DIR)/mapped.json
ROUTE ?= $(CAPTURE_DIR)/route.json
DIAGNOSIS ?= $(CAPTURE_DIR)/diagnosis.json

# The browser viewer's copy of the capture: sane prefix only, core properties
# only. VIEWER_PLY is set by CAPTURE above.

.PHONY: demo web web-build scene objects audit anchors object-meshes object-splats filter-assets splat-asset pack map diagnose pipeline route test check clean assets

## scene: ingest the splat into data/scene/scene.npz
scene:
	$(PY) python -m plantpilot.splat --ply "$(PLY)" --out $(SCENE)

## objects: extract framed objects from the scene into data/scene/objects.json
objects:
	$(PY) python -m plantpilot.segment --scene $(SCENE) --out $(OBJECTS)
	$(PY) python -m plantpilot.classes --objects $(OBJECTS) --out $(OBJECTS) --instances $(INSTANCES_FIXTURE)

## audit: measure whether the framed objects are whole instances or fragments
audit: objects
	$(PY) python scripts/object_audit.py --objects $(OBJECTS) --anchors $(ANCHORS_FIXTURE) \
	  --scene $(SCENE) --out $(CAPTURE_DIR)/object_audit.json --markdown

## object-splats: one splat asset per reviewed anchor for the object atlas
object-splats: anchors
	$(PY) python scripts/make_object_splats.py --scene $(SCENE) --anchors $(ANCHORS) --out data/objects/splats

## object-meshes: reconstruct one mesh per reviewed anchor (needs open3d)
object-meshes: anchors
	$(PY) python scripts/make_object_meshes.py --scene $(SCENE) --anchors $(ANCHORS) --out data/objects/meshes

## anchors: build the reviewed demo layer from the committed fixture
anchors: scene
	@if [ -f "$(ANCHORS_FIXTURE)" ]; then \
	  $(PY) python scripts/make_anchors.py --scene $(SCENE) --fixture $(ANCHORS_FIXTURE) --out $(ANCHORS); \
	else \
	  echo "no reviewed anchors for $(CAPTURE), the viewer falls back to the proposal layer"; \
	fi

## filter-assets: bake the height, normals, edges and semantics PLYs for the viewer
filter-assets: scene objects assets
	$(PY) python scripts/make_filter_assets.py --scene $(SCENE) --objects $(OBJECTS) --assets $(ASSETS) --out $(FILTERS) --no-previews

## assets: merge the raw boxes into coherent, labelled equipment instances
assets: scene objects
	$(PY) python -m plantpilot.assets --scene $(SCENE) --objects $(OBJECTS) --out $(ASSETS)

## splat-asset: write the sanitised capture as a PLY for the browser viewer
splat-asset:
	$(PY) python scripts/make_splat_asset.py --ply "$(PLY)" --out $(VIEWER_PLY)

## pack: convert the supplied builder workbook into the capture's pack.json
pack:
	$(PY) python -m plantpilot.pack --xlsx "$(PACK_XLSX)" --out $(PACK)

## map: assign builder-pack assets to distinct extracted objects
map: pack objects
	$(PY) python -m plantpilot.mapping --pack $(PACK) --objects $(OBJECTS) --out $(MAPPED)

## diagnose: build an evidence-backed diagnosis for P-005
diagnose: pack
	$(PY) python -m plantpilot.diagnose --pack $(PACK) --out $(DIAGNOSIS)

## pipeline: build every artifact the room view needs for CAPTURE
pipeline: scene objects anchors assets map diagnose route splat-asset

## demo: build CAPTURE's artifacts and the web page, then serve both
demo: pipeline filter-assets web-build
	PLANTPILOT_SCENE=$(CAPTURE_DIR) PLANTPILOT_SPLAT=$(VIEWER_PLY) \
	  $(PY) uvicorn plantpilot.main:app --host 127.0.0.1 --port $(PORT) --app-dir app/server/src

## web: vite dev server on 5173, proxying /api to 8000
web:
	cd app/web && pnpm run dev

web-build:
	cd app/web && pnpm run build

## route: compute collision-free route to target asset with proximity samples
route: scene objects map
	$(PY) python scripts/make_route.py --scene $(SCENE) --objects $(OBJECTS) --mapped $(MAPPED) --output $(ROUTE)

test:
	$(PY) pytest

check:
	node scripts/sinceai_check.mjs

clean:
	rm -rf app/web/dist
