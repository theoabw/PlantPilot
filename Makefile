PY := uv run

.PHONY: demo web web-build corpus models register plates scan proof test check clean

## demo: build the register, then serve the API and the built web page
demo: register
	$(PY) uvicorn fieldplate.main:app --host 127.0.0.1 --port 8000 --app-dir app/server/src

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
	$(PY) -c "from fieldplate import register; from pathlib import Path; print(register.build(Path('data/register.db'), Path('fixtures/register/assets.csv')), 'assets indexed')"

## models: fetch the monocular depth model (27 MB) into data/models/
models:
	mkdir -p data/models
	curl -sL -o data/models/depth_anything_v2_small_q.onnx \
	  https://huggingface.co/onnx-community/depth-anything-v2-small/resolve/main/onnx/model_quantized.onnx

## scan: photo to point cloud, PHOTO=path/to.jpg
scan:
	$(PY) python scripts/scan.py "$(PHOTO)"

## plates: write a printable A4 sheet of synthetic nameplates into data/plates/
plates:
	$(PY) python scripts/make_plates.py

## proof: summarise the timed trials into proof/metrics.json
proof:
	$(PY) python scripts/proof.py

test:
	$(PY) pytest

check:
	node scripts/sinceai_check.mjs

clean:
	rm -rf app/web/dist data/index.db data/register.db
