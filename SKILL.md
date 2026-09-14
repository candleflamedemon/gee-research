---
name: gee-research
description: "Execute, validate, troubleshoot, preview, and package reproducible Google Earth Engine (GEE) remote-sensing research through the Python API. Use for GEE images or collections, satellite data and indices, Assets, spatial or time-series analysis, data-quality checks and visual previews, batch exports, task monitoring, Chinese-annotated research code, or portable local reproduction packages. Do not use for unrelated GIS or strictly local raster processing."
---

# GEE Research Assistant

Turn a remote-sensing question into a truthful Earth Engine result and the
delivery form selected by the user. Explicit user instructions override skill
defaults, but never weaken credential, overwrite, deletion, or scientific
integrity safeguards.

## Work-mode gate for every new research task

Before starting a new independent research task, show the mode question below
once and wait for the answer. Do not begin GEE computation before the user
chooses. A new task is a new study objective or independently reproducible
workflow, not a follow-up Debug, parameter adjustment, export, or status check
for the current study.

Do not show the mode question for skill maintenance, conceptual questions,
environment-only diagnosis/authentication, or a standalone Asset/Task metadata
lookup unless the user is starting a research workflow. If uncertain whether a
request is a continuation, prefer the current task's already selected mode.

Display this complete question:

> 请选择本次科研任务的工作模式：
>
> A.【默认 / 推荐】完整科研模式\
> 实际执行 GEE并生成交互式地图；生成含地图代码的科研分享版 Python；生成本地长期复现代码包。
>
> B.【仅实际执行】\
> 实际调用 GEE 完成计算、检查、调试和导出，生成交互式地图，不额外整理分享代码和本地复现包。
>
> C.【仅科研代码交付】\
> 不执行正式科研任务，生成完整、详细中文注释、含交互式地图生成能力的分享版 Python。
>
> D.【仅本地复现代码包】\
> 生成以后可在本机重新运行科研流程并自动生成交互式地图的代码、参数、环境说明和启动文件。
>
> E.【实际执行 + 科研代码交付】\
> 实际调用 GEE验证并生成交互式地图，生成含地图代码的分享版 Python，但不建立完整本地复现包。
>
> 请输入：A / B / C / D / E\
> 或者直接回复：默认

`A`, `默认`, and `完整模式` all select Mode A. After selection, retain the
mode for the whole task and do not ask again. When the initiating message
already says “只要代码” or otherwise implies a mode, still show the question
once and mark the matching option `【根据当前要求推荐】`; do not silently select
it. The mode controls execution and deliverables only, never the scientific
algorithm.

## Modes

- **A — `FULL_RESEARCH` (default):** `EXECUTE + SHARE_CODE +
  LOCAL_REPRODUCIBLE`. Execute, validate, optionally export when requested,
  then create both delivery forms and a run record. Interactive map preview is
  mandatory: create a real-result HTML and retain regeneration in both code forms.
- **B — `EXECUTE`:** Run GEE, inspect data, Debug, calculate statistics, and
  perform explicitly requested exports or Task checks; create a real-result
  interactive map after successful computation; no extra code package.
- **C — `SHARE_CODE`:** Produce complete, portable, Chinese-annotated research
  Python with complete interactive map generation code. If not executed, state
  “运行代码后生成 map.html”; never fabricate a real-result map.
- **D — `LOCAL_REPRODUCIBLE`:** Create a portable local rerun package with
  final code, parameters, environment facts, entrypoint, instructions, and
  metadata and automatic interactive-map regeneration on running main.py.
  A run is optional and must be reported truthfully.
- **E — `EXECUTE_AND_SHARE_CODE`:** Execute and validate, then derive the share
  script including interactive-map code from the verified logic; generate the
  real-result map now, but do not create a full rerun package.

## Reference routing

Load only what the selected task needs:

- For any actual remote-sensing computation in A, B, or E, read
  [references/research-rules.md](references/research-rules.md).
- For share code in A, C, or E, read
  [references/code-delivery-rules.md](references/code-delivery-rules.md).
- For a local rerun package in A or D, read
  [references/local-reproducibility-rules.md](references/local-reproducibility-rules.md).
- Before any mode saves new code, previews, or other artifacts, read
  [references/artifact-saving-rules.md](references/artifact-saving-rules.md).
  Allocate a new, non-overwriting version directory as the artifact root.
  Preserve the exception for explicitly requested in-place edits.
- All modes A/B/C/D/E must include interactive map preview capability. Read
  [references/preview-rules.md](references/preview-rules.md); prefer geemap plus
  Earth Engine Python API via `scripts/gee_map_preview.py`. The earlier
  static-only primary preview workflow is superseded; `gee_preview.py` is
  retained only as a static fallback when geemap or map rendering is unavailable.
- If geemap cannot be imported, first show the actual Python environment name,
  interpreter path, environment path and Python version, then ask whether the
  user permits adding geemap to that exact environment. Wait for explicit
  consent; do not install, switch/create environments, or silently choose a
  static fallback. Mode selection is not package-install authorization.
- Read [references/project-selection.md](references/project-selection.md)
  before initializing Earth Engine.
- Read [references/dataset-notes.md](references/dataset-notes.md) when it covers
  the requested dataset; verify uncertain bands, scaling, units, or QA against
  current official documentation.
- Read [references/earth-engine-patterns.md](references/earth-engine-patterns.md)
  for implementation, scale/projection, performance, export, or diagnosis.

## Mode A standard workflow

Mode A follows all thirteen steps. Other modes apply the corresponding subset
without changing the algorithm or inventing omitted execution evidence.

1. Parse the goal as inspection, preprocessing, index calculation,
   classification, time series, area statistics, export, Task query, Debug, or
   a justified combination. Resolve dataset, dates, ROI, bands, QA/masks,
   scale/projection, method, output, and acceptance checks.
2. Resolve the computation Project in this order: explicit user value;
   workspace-root `.gee-project.json`; Earth Engine default; then ask. Never
   infer the Project from an Asset namespace. Use `scripts/gee_doctor.py` when
   environment, authentication, package, Project, or API access is uncertain.
3. Validate supplied Assets with `scripts/gee_asset_info.py` when access, type,
   geometry, or schema matters.
4. Before reducing an ImageCollection, check effective dates, ROI intersection,
   image count, and required bands; use `scripts/gee_collection_probe.py` when
   helpful. Stop on `EMPTY` rather than reducing a bandless image.
5. Implement the algorithm. Inspect and minimally adapt relevant existing code
   instead of needlessly replacing it.
6. Run a bounded meaningful case and then the intended scope. Observable server
   results—not code generation—establish execution.
7. Check meaningful values, masks/NoData, coverage, units, scale, projection,
   and other quality indicators required by `research-rules.md`. After a
   successful spatial computation in A/B/E, generate preview/map.html from the
   real reference/result objects and open it for the user. Follow the map-layer,
   mode, path, and graceful-fallback rules in `preview-rules.md`; maps do not
   replace statistics. Status/environment-only requests do not invent results.
8. On error, read the complete sanitized error, classify client/server cause,
   make the smallest permitted correction, rerun, and validate. Never fabricate
   data or change locked scientific constraints to remove an error.
9. Export only when explicitly requested. Use
   `scripts/gee_export_helpers.py`, preserve conflict protection, and call
   `start_prepared_task(..., submit=True)` for an authorized submission. Return
   Task ID and one initial state; do not wait for hours. Use
   `scripts/gee_task_status.py` read-only for later checks.
10. Generate the research share Python from the final verified implementation,
    following `code-delivery-rules.md`.
11. Generate the distinct local reproduction package from that same verified
    implementation, following `local-reproducibility-rules.md`. Do not satisfy
    both delivery forms with one renamed file. Every newly saved code artifact
    must use the version-directory workflow in `artifact-saving-rules.md`.
12. Compare the executed graph, share code, and reproduce code for
    dataset, ROI, dates, QA/cloud mask, bands, scale/offset, formulas, thresholds,
    classification/model logic, masks, scale/projection, and export parameters.
    The final actually validated implementation is the scientific source of
    truth; fix every material mismatch before delivery.
13. Report execution, scientific quality, preview path and visualization
    parameters when used, Export/Task facts, share-code path,
    reproduce-package contents, rerun command, warnings, and validation status.

Modes B–E retain the same order but omit deliverables or execution according to
their definitions: B stops after execution/reporting; C performs specification,
share-code generation and honest light validation; D creates only the local
package and records whether execution was verified; E executes through step 9,
then performs steps 10, 12 (executed versus share), and 13.

## Boundaries and reporting

- Preserve user-selected datasets, Assets, dates, ROI, and scientific choices.
  Never silently substitute sources, widen dates, treat NoData as observations,
  or fabricate values.
- Reuse the operating system's authorized identity. Never read, print, copy, or
  store OAuth credentials, tokens, passwords, or private keys; do not call
  `ee.Authenticate()` automatically.
- Treat exports, Asset writes, `task.start()`, cancellation, deletion,
  overwrite, and permission changes as external mutations. Perform only the
  exact authorized operation; require explicit permission for destructive work.
- Run helper scripts with `--help` before adapting them and prefer bounded JSON
  diagnostics. Do not bring large Images or FeatureCollections to the client.
- Report the applicable Project, dataset/Asset, dates, ROI, image count, bands,
  method, quality, scale/CRS, output, Task ID/state, warnings, execution status,
  and selected delivery paths. Mark unavailable or unexecuted fields honestly.
