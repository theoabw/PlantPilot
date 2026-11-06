PY := uv run

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
MAPPED ?= $(CAPTURE_DIR)/mapped.json
ROUTE ?= $(CAPTURE_DIR)/route.json
DIAGNOSIS ?= $(CAPTURE_DIR)/diagnosis.json
PREVIEW ?= $(CAPTURE_DIR)/preview.png
OBJECTS_TOP ?= $(CAPTURE_DIR)/objects_top.png
OBJECTS_VIEW ?= $(CAPTURE_DIR)/objects_view.png

# The preview renderer draws native gaussian splats, which is slower than the
# point debug view and is what makes the room read as surfaces. This is the
# number of gaussians drawn for the preview PNGs, not what the artifact holds.
SPLAT_GAUSSIANS ?= 500000
PREVIEW_WIDTH ?= 1400
PREVIEW_HEIGHT ?= 900

# The browser viewer's copy of the capture: sane prefix only, core properties
# only. VIEWER_PLY is set by CAPTURE above.

# The second scene for the scene-agnostic check: the synthetic reference plant,
# written as a 3DGS PLY so the same stages run on it unchanged.
PLANT_PLY ?= data/plant/plant.ply
PLANT_SCENE ?= data/plant/scene.npz
PLANT_OBJECTS ?= data/plant/objects.json

.PHONY: demo web web-build corpus models register plates plant scan scene objects splat-asset pack map diagnose pipeline generality proof route openapi test check clean assets

## scene: ingest the splat into data/scene/scene.npz, then render a preview
scene:
	$(PY) python -m plantpilot.splat --ply "$(PLY)" --out $(SCENE)
	$(PY) python -m plantpilot.render --scene $(SCENE) --out $(PREVIEW) --mode splats \
	  --max-gaussians $(SPLAT_GAUSSIANS) --width $(PREVIEW_WIDTH) --height $(PREVIEW_HEIGHT)

## objects: extract framed objects from the scene into data/scene/objects.json
objects:
	$(PY) python -m plantpilot.segment --scene $(SCENE) --out $(OBJECTS)
	$(PY) python -m plantpilot.render --scene $(SCENE) --objects $(OBJECTS) --view top --out $(OBJECTS_TOP)
	$(PY) python -m plantpilot.render --scene $(SCENE) --objects $(OBJECTS) --out $(OBJECTS_VIEW) \
	  --mode splats --max-gaussians $(SPLAT_GAUSSIANS) --width $(PREVIEW_WIDTH) --height $(PREVIEW_HEIGHT) --no-labels

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
pipeline: scene objects assets map diagnose route splat-asset

## generality: run the same stages on the reference plant, score the boxes
generality: plant
	$(PY) python scripts/make_plant_ply.py --ply $(PLANT_PLY)
	$(PY) python -m plantpilot.splat --ply $(PLANT_PLY) --out $(PLANT_SCENE)
	$(PY) python -m plantpilot.segment --scene $(PLANT_SCENE) --out $(PLANT_OBJECTS)
	$(PY) python scripts/plant_generality.py --objects $(PLANT_OBJECTS)

## demo: build CAPTURE's artifacts and the web page, then serve both
demo: pipeline web-build register
	PLANTPILOT_SCENE=$(CAPTURE_DIR) PLANTPILOT_SPLAT=$(VIEWER_PLY) \
	  $(PY) uvicorn plantpilot.main:app --host 127.0.0.1 --port 8000 --app-dir app/server/src

## web: vite dev server on 5173, proxying /api to 8000
web:
	cd app/web && pnpm run dev

web-build:
	cd app/web && pnpm run build

## corpus: fetch the two public PDFs into data/ and build the local index
corpus:
	$(PY) python scripts/make_corpus.py

## register: regenerate the synthetic CSV and the SQLite register
register:
	$(PY) python scripts/make_register.py
	$(PY) python -c "from plantpilot import register; from pathlib import Path; print(register.build(Path('data/register.db'), Path('fixtures/register/assets.csv')), 'assets indexed')"

## models: fetch the monocular depth model (27 MB) into data/models/
models:
	mkdir -p data/models
	curl -sL -o data/models/depth_anything_v2_small_q.onnx \
	  https://huggingface.co/onnx-community/depth-anything-v2-small/resolve/main/onnx/model_quantized.onnx

## plant: generate the synthetic reference plant, points plus ground truth
plant:
	$(PY) python scripts/make_plant.py

## scan: photo to point cloud, PHOTO=path/to.jpg
scan:
	$(PY) python scripts/scan.py "$(PHOTO)"

## plates: write a printable A4 sheet of synthetic nameplates into data/plates/
plates:
	$(PY) python scripts/make_plates.py

## proof: summarise the timed trials into proof/metrics.json
proof:
	$(PY) python scripts/proof.py

## route: compute collision-free route to target asset with proximity samples
route: scene objects map
	$(PY) python scripts/make_route.py --scene $(SCENE) --objects $(OBJECTS) --mapped $(MAPPED) --output $(ROUTE)

## openapi: write the OpenAPI schema the API serves to docs/openapi.json
openapi:
	$(PY) python scripts/make_openapi.py

test:
	$(PY) pytest

check:
	node scripts/sinceai_check.mjs

clean:
	rm -rf app/web/dist data/index.db data/register.db
