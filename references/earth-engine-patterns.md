# Earth Engine Python patterns

Use this reference when implementing, optimizing, exporting, or diagnosing Earth Engine Python work.

## Select a Project and initialize with the existing identity

Follow [project-selection.md](project-selection.md); do not embed one personal
Project in skill code. The shared helper applies explicit argument, current
workspace config, then the Earth Engine default:

```python
import ee
from _gee_common import initialize_ee

selection = initialize_ee(ee, project=user_project_or_none)
```

Do not automatically invoke `ee.Authenticate()`. `ee.Initialize()` can reuse Earth Engine credentials or Application Default Credentials already available to the operating system. If initialization fails, report the sanitized error and let the user complete any interactive sign-in.

## Keep work server-side

Earth Engine objects describe server computations. Filter collections early by date, bounds, and metadata; select required bands; map server-side functions; then request only bounded summaries. Avoid converting large collections, rasters, or feature sets with `getInfo()`.

Use a progression such as metadata -> small AOI/date probe -> diagnostic aggregate -> intended run -> export. During diagnosis, use a deliberately bounded AOI, date interval, image limit, and `maxPixels` appropriate to the probe.

## Masks, values, and quality

- A masked pixel is not the same as numeric zero. Measure valid support when zero has scientific meaning.
- Apply documented scale and offset before interpreting physical values unless the chosen product already exposes scaled values.
- Preserve QA bands until the mask has been validated. Record the exact bits, scores, or thresholds used.
- For temporal composites, verify observation counts or valid coverage; a visually complete median can conceal sparse support.

## Projection and scale

Many reductions and exports depend on the requested scale/CRS rather than a single intrinsic image projection. Inspect a representative band's projection, choose a scale justified by the product and question, and specify resampling or aggregation intentionally. Use nearest-neighbor semantics for categorical classes unless the method explicitly requires another approach.

For pixel-aligned exports, prefer an explicit CRS and transform from the intended grid. `scale` is convenient but does not guarantee alignment to another raster. Do not provide mutually exclusive export grid parameters together.

## Error diagnosis

- **Import failure:** the selected interpreter lacks `earthengine-api`; identify the interpreter before proposing installation.
- **Initialization/authentication:** check the Cloud Project argument and whether credentials exist without opening the credential file. Interactive authentication belongs to the user.
- **Permission or missing Asset:** distinguish not-found from access-denied; print the requested Asset ID and active project, never credentials.
- **Empty collection:** inspect each filter independently, especially date exclusivity, AOI intersection, and metadata property names.
- **Band/property mismatch:** probe the first image after all filters; collections can change schema across sensors or processing eras.
- **Too many pixels/memory/timeout:** reduce the diagnostic region/time/bands, aggregate earlier, avoid unnecessary reprojection, and use exports for intended large outputs.
- **Export failure:** inspect region validity, grid parameters, `maxPixels`, destination permissions/quota, filename/Asset ID, and task error message.

## Export and task lifecycle

For image/table exports to Asset or Drive, use the matching `create_*_task` builder from `gee_export_helpers.py`. Supply `region`, grid/resolution, CRS, limits, destination, format, and naming from the current research specification; the helper intentionally does not invent fixed scientific values. Asset builders perform a read-only conflict check, block ambiguous targets by default, force `overwrite=False`, and never delete an Asset.

The builders return an unsubmitted `PreparedExport`. Pass it to `start_prepared_task` with `submit=True` only after explicit user authorization for that exact export:

```python
from gee_export_helpers import create_image_to_drive_task, start_prepared_task

prepared = create_image_to_drive_task(
    result_image,
    description="study_result",
    folder="GEE_exports",
    file_name_prefix="study_result_2024",
    region=roi,
    scale=analysis_scale,
    crs=analysis_crs,
    max_pixels=checked_max_pixels,
)
result = start_prepared_task(prepared, submit=True)
```

Task states commonly include `UNSUBMITTED`, `READY`, `RUNNING`, `COMPLETED`, `FAILED`, and `CANCELLED`. The start helper reads status once and never waits for the long-running export to finish. Report task ID, description, destination, initial state, and any error. Never equate task creation or `READY` with successful output delivery.
