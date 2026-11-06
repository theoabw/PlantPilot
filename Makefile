PY := uv run

# The supplied capture, as delivered. `make scene` reads this file and filters
# it itself, so the counts it prints are the counts in the delivered file. A
# second capture is `make scene PLY=path/to/other.ply`.
PLY ?= data/supplied/Industrial Boiler Room (1).ply
SCENE ?= data/scene/scene.npz
OBJECTS ?= data/scene/objects.json

.PHONY: demo web web-build corpus models register plates plant scan scene objects proof route test check clean

## scene: ingest the splat into data/scene/scene.npz, then render a preview
scene:
	$(PY) python -m plantpilot.splat --ply "$(PLY)" --out $(SCENE)
	$(PY) python -m plantpilot.render --scene $(SCENE) --out data/scene/preview.png

## objects: extract framed objects from the scene into data/scene/objects.json
objects:
	$(PY) python -m plantpilot.segment --scene $(SCENE) --out $(OBJECTS)
	$(PY) python -m plantpilot.render --scene $(SCENE) --objects $(OBJECTS) --view top --out data/scene/objects_top.png
	$(PY) python -m plantpilot.render --scene $(SCENE) --objects $(OBJECTS) --out data/scene/objects_view.png

## demo: build the register, then serve the API and the built web page
demo: register
	$(PY) uvicorn plantpilot.main:app --host 127.0.0.1 --port 8000 --app-dir app/server/src

## web: vite dev server on 5173, proxying /api to 8000
web:
	cd app/web && npm run dev

web-build:
	cd app/web && npm run build

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
route:
	$(PY) python scripts/make_route.py

test:
	$(PY) pytest

check:
	node scripts/sinceai_check.mjs

clean:
	rm -rf app/web/dist data/index.db data/register.db
