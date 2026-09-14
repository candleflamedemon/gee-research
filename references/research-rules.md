# Research reliability rules

Read this file before executing or validating an actual remote-sensing computation. Apply its checks in proportion to the scientific importance, failure risk, and cost of the run. A metadata probe needs fewer checks than a publication result or export, and a metric that is meaningless for the output type should be omitted rather than calculated mechanically.

## Truthfulness and observation integrity

- Preserve the distinction between observed values, valid physical zeros, masked pixels, and NoData.
- Never make a program appear successful by filling missing remote-sensing values with random numbers, zero, or a fixed constant and then treating those fills as observations.
- Never treat NoData or masked pixels as valid pixels. A documented fill value may be used as an output-format encoding only when the user requests it or the format requires it; keep it distinguishable from observations and exclude it from scientific statistics unless the method explicitly defines otherwise.
- Treat user-specified dataset or Asset IDs and time ranges as locked constraints. Do not widen the period, use another year, or substitute another sensor or product without the user's permission.
- Never alter genuine computed values merely to make a map, chart, statistic, classification, or coverage result look better.
- Use synthetic or mock values only for an explicitly requested simulation or test fixture, label them as synthetic, and never report them as measured Earth observations.

## Scientific specification

Resolve the parts that materially affect interpretation:

- research variable and operational definition;
- ROI/AOI source, geometry validity, and boundary convention;
- observation dates versus compositing or reporting periods;
- product processing level, collection/version, bands, units, scale factors, and QA flags;
- masking, mosaicking, temporal aggregation, reducer, spatial scale, projection, and resampling;
- expected output type, destination, precision, and acceptance criteria.

When an alternative dataset or time range could solve a problem, explain the scientific tradeoff and wait for the user's agreement before switching.

## ImageCollection checks

Before calling `median`, `mean`, `mosaic`, `qualityMosaic`, `first`, or `toBands`, inspect the effective collection when practical. At minimum, confirm:

- the effective start and end dates;
- the spatial bounds or intersection with the requested ROI;
- image count after all filters;
- band names required by the next operation.

If the filtered count is zero, stop that computation and report the empty collection instead of allowing `first()` or a reducer to produce an image with no bands. When band schemas may differ between scenes, checking only the first image is not sufficient; inspect representative schemas or band availability as needed. Keep these probes bounded so the check does not become more expensive than the calculation it protects.

## Spatial coverage

When the user requires the ROI to be covered, work inside the specified dataset and time range. Prefer, as scientifically appropriate:

- collecting multiple scenes that intersect the ROI;
- a deliberately ordered mosaic when scene priority matters;
- a median composite when its temporal meaning is acceptable;
- relaxing an allowed cloud-percentage filter when the user did not lock that threshold, while disclosing the changed threshold and its quality tradeoff.

Do not fill coverage gaps with full-year imagery, another year, another satellite, or a constant `unmask` value without user authorization. If valid-pixel gaps remain, calculate and report the uncovered area or ratio—and a gap mask or geometry when useful—instead of fabricating coverage.

## Result checks

For important outputs, compute the checks that are meaningful for the data type and decision:

- minimum, maximum, and mean;
- relevant percentiles;
- valid-pixel ratio and masked-pixel ratio;
- spatial coverage of the requested ROI.

For categorical products, prefer class counts, class areas, confusion metrics, or other category-aware checks over a meaningless mean. Warn the user about implausible ranges, unexpected all-zero or all-masked outputs, extreme missingness, insufficient coverage, or other anomalies. Report unavailable or intentionally skipped checks and why; an API call completing successfully is not by itself scientific validation.

## Evidence-first execution

Before a large computation, use a bounded probe to establish that authentication works, the dataset or Asset is accessible, filters return observations, required bands and properties exist, and units, scaling, QA definitions, projection, and scale fit the method. Prefer server-side summaries and bring only small metadata, aggregates, samples, or diagnostic values to the client. Preserve the smallest failing request while debugging.

## Reproducibility record

After actual execution, return or save the applicable reproducibility fields:

- Dataset or Asset ID and collection version;
- date range and filters;
- ROI/AOI source or reproducible geometry description;
- image count and bands;
- QA/mask and scaling rules;
- scale, projection/CRS or transform, and resampling;
- algorithm, reducers, compositing, classification, or other material method choices;
- code path and execution timestamp;
- output path or destination;
- export Task ID and observed task state.

Record only fields that exist for the run; a non-export analysis has no Task ID. Never record credential contents.

## Exports and destructive operations

Creating an `ee.batch.Export` object is preparation; calling `task.start()` submits work. Start only when the user explicitly requested submission and the effective destination, name, region, bands or columns, resolution or transform, CRS, and relevant limits have been checked. Report the Task ID and initial state; `READY` or `RUNNING` does not mean the output is complete.

Obtain explicit user permission immediately before any of these actions:

- deleting an Asset;
- overwriting an existing research result;
- deleting tasks in bulk;
- cancelling tasks at large scale;
- modifying historical research data;
- deleting code or original research files.

Before acting, resolve and show the exact target or target count, explain the impact, and prefer a reversible alternative when practical. Permission for one target or operation does not authorize a broader batch. Also obtain explicit authorization before changing sharing permissions.

## Iteration and stopping

Classify failures before changing code: environment/package, authentication, Cloud Project/API registration, permissions, missing Asset, empty filters, band/property mismatch, invalid geometry, scale/projection, quota, memory/pixel limits, timeout, or destination configuration. Change one permitted cause at a time and rerun the bounded reproducer; do not repair failures by changing locked scientific constraints or fabricating values.

Stop and request input when progress requires a user-owned Cloud Project, interactive authentication, new permissions, an unknown Asset or destination, a scientifically consequential choice, or a costly full-scale execution. Include the exact failing stage and sanitized error.
