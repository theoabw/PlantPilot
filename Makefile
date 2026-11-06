PY := uv run

# The supplied capture, as delivered. `make scene` reads this file and filters
# it itself, so the counts it prints are the counts in the delivered file. A
# second capture is `make scene PLY=path/to/other.ply`.
PLY ?= data/supplied/Equipment Room.ply
PACK_XLSX ?= data/supplied/builder_pack.xlsx
SCENE ?= data/scene/scene.npz
OBJECTS ?= data/scene/objects.json
PREVIEW ?= data/scene/preview.png
OBJECTS_TOP ?= data/scene/objects_top.png
OBJECTS_VIEW ?= data/scene/objects_view.png

# The preview renderer draws native gaussian splats, which is slower than the
# point debug view and is what makes the room read as surfaces. This is the
# number of gaussians drawn for the preview PNGs, not what the artifact holds.
SPLAT_GAUSSIANS ?= 500000
PREVIEW_WIDTH ?= 1400
PREVIEW_HEIGHT ?= 900

# The second scene for the scene-agnostic check: the synthetic reference plant,
# written as a 3DGS PLY so the same stages run on it unchanged.
PLANT_PLY ?= data/plant/plant.ply
PLANT_SCENE ?= data/plant/scene.npz
PLANT_OBJECTS ?= data/plant/objects.json

.PHONY: demo web web-build corpus models register plates plant scan scene objects pack map diagnose pipeline generality proof route openapi test check clean

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
	  --mode splats --max-gaussians $(SPLAT_GAUSSIANS) --width $(PREVIEW_WIDTH) --height $(PREVIEW_HEIGHT)

## pack: convert the supplied builder workbook into data/scene/pack.json
pack:
	$(PY) python -m plantpilot.pack --xlsx "$(PACK_XLSX)" --out data/scene/pack.json

## map: assign builder-pack assets to distinct extracted objects
map: pack objects
	$(PY) python -m plantpilot.mapping --pack data/scene/pack.json --objects $(OBJECTS) --out data/scene/mapped.json

## diagnose: build an evidence-backed diagnosis for P-005
diagnose: pack
	$(PY) python -m plantpilot.diagnose --pack data/scene/pack.json --out data/scene/diagnosis.json

## pipeline: build the complete supplied-scene demo artifact set
pipeline: diagnose route

## generality: run the same stages on the reference plant, score the boxes
generality: plant
	$(PY) python scripts/make_plant_ply.py --ply $(PLANT_PLY)
	$(PY) python -m plantpilot.splat --ply $(PLANT_PLY) --out $(PLANT_SCENE)
	$(PY) python -m plantpilot.segment --scene $(PLANT_SCENE) --out $(PLANT_OBJECTS)
	$(PY) python scripts/plant_generality.py --objects $(PLANT_OBJECTS)

## demo: build the register, then serve the API and the built web page
demo: register
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
	$(PY) python scripts/make_route.py

## openapi: write the OpenAPI schema the API serves to docs/openapi.json
openapi:
	$(PY) python scripts/make_openapi.py

test:
	$(PY) pytest

check:
	node scripts/sinceai_check.mjs

clean:
	rm -rf app/web/dist data/index.db data/register.db
