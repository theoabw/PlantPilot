---
title: "Valmet challenge SinceAI 2026: PlantPilot"
sub_title: "Pathfinding through obstacles determined from 3DGS-data"
author: PlantPilot
---
<!-- font_size: 2 -->
<!-- incremental_lists: true -->
## Valmet 3DGS Boiler Room solution overview

This solution includes three parts:

1. Data pipeline for generating assets
2. An assets server
3. A demo client application

```mermaid +render
flowchart LR
  subgraph Three.js client
    UI[Web app]
  end
  UI --> API
  API[FastAPI BE] --> AssetDB[(Pipeline outputted assets)]
```

<!-- end_slide -->
<!-- font_size: 2 -->
<!-- incremental_lists: true -->
### The data pipeline

The data pipeline processes the 3d gaussian splatting data and the excel builder pack spreadsheet to
produce derived data like cleaned scene data, object anchors, object-to-asset mapping, etc.

The data pipeline can be ran locally and utilizes standard tools to perform the cleanup and derivations


```mermaid +render
flowchart LR
  subgraph Pipeline
    Scene[Scene cleanup]
    Object[Obj. extraction]
    Anchors[Obj. anchors]
    Assets[Builder pack to assets]
    Mapping[Asset to scene mapping]
    Diagnose[Diagnostics aggregation]
    Routing[Mapping of obstacles]
    SceneAsset[Minified scene asset]
  end
  Scene-->Object
  Scene-->sceneOut[scene.ply]
  Object-->Anchors
  Object-->objsOut[objects.json]
  Anchors-->Assets
  Anchors-->anchorsOut[anchors.json]
  Assets-->Mapping
  Assets-->assetsOut[assets.json]
  Mapping-->Diagnose
  Mapping-->mappingOut[mapping.json]
  Diagnose-->Routing
  Diagnose-->diagnoseOut[diagnostics.json]
  Routing-->SceneAsset
  SceneAsset-->sceneassetOut[scene-asset.npz]
```
<!-- end_slide -->
<!-- font_size: 2 -->
<!-- incremental_lists: true -->
### The pipeline consists of the following steps

1. Scene preparation
  - Determines directions, units, axes
  - artifact: scene.npz, used for later steps (Scene)
2. Object extraction
  - Voxelize the scene in order to create bounding boxes for objects
  - artifacts: objects.json
3. Incorporation of object anchors
  - Use optionally manually reviewed object anchors to map out objects more accurately
4. Compile assets from builder pack excel file
  - Turn excel into csv and use this for further processing
<!-- end_slide -->
<!-- font_size: 2 -->
<!-- incremental_lists: true -->
### The pipeline consists of the following steps

5. Map builder pack assets to segmented objects
  - Make a best-effort mapping between builder pack assets and objects detected during step 2/3
6. Diagnose
  - Aggregate data from the builder pack sheets and produce a textual diagnosis for all objects
7. Route computing: compute collission-free pathing to targets using rules for proximity to objects
  - Uses scene geometry, mapped assets, and other objects
  - Produces a list of rectangles along the floor, indicating geometry that cannot be traversed
8. Stripped Scene asset creation
  - Strip the input .ply data to make a smaller file that can be provided to the three.js client app
<!-- end_slide -->
<!-- font_size: 2 -->

### FastAPI Server
<!-- incremental_lists: true -->

The server consumes the outputs of the data pipeline:

- scene. assets.json, anchors.json, mapped.json, route.json, diagnosis.json

These files hold the data needed to populate the three.js demo scene

- Data is served from asset files as either application/json or octet-stream
- The server can run locally or be hosted somewhere else

<!-- end_slide -->
<!-- font_size: 2 -->
<!-- incremental_lists: true -->

### Three.js demo client

![PlantPilot Scene Screenshot](data/plantpilot-screenshot.png)
<!-- end_slide -->
<!-- font_size: 2 -->
<!-- incremental_lists: true -->

The demo consists of two parts:

1. The main scene

- The scene is fetched as a minified .ply file from the FastAPI backend, it is then rendered.
- Based on the selected layer, the relevant assets are pulled from the backend and layered ontop of the scene.

2. UI

The UI is made with React and it hosts the controls of the demo and the aggregated diagnostics data for each identified object from the builders pack

<!-- end_slide -->
