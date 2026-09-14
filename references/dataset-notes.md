# High-frequency dataset notes

Use this reference for a small set of recurring, error-prone dataset decisions.
It is not an Earth Engine dataset directory and does not replace the current
official Earth Engine Data Catalog.

These notes are defaults, not permission to change the research specification.
If the user names another official dataset, use the user's dataset. If a band,
scale factor, offset, QA definition, processing version, or availability detail
is uncertain, check the current official Earth Engine catalog or upstream
product documentation before writing or running the final calculation. Never
guess from memory or from a variable name.

## Sentinel-2 Surface Reflectance Harmonized

Default collection when this product is intended:
`COPERNICUS/S2_SR_HARMONIZED`.

Common spectral bands:

| Band | Meaning | Native pixel size |
| --- | --- | ---: |
| `B2` | Blue | 10 m |
| `B3` | Green | 10 m |
| `B4` | Red | 10 m |
| `B8` | Near infrared | 10 m |
| `B11` | SWIR 1 | 20 m |
| `B12` | SWIR 2 | 20 m |

The catalog represents these reflectance bands with a scale of `0.0001`.
Confirm whether the current computation is intentionally using scaled
reflectance or stored integer values and keep that choice consistent.

Common indices:

- `NDVI = (B8 - B4) / (B8 + B4)`
- `STI = B11 / B12`

For ratios, retain the source masks and handle a zero or invalid denominator
without turning NoData into observations. Do not use `unmask(0)` merely to
make an index spatially complete.

`B2`, `B3`, `B4`, and `B8` are natively 10 m; `B11` and `B12` are
natively 20 m. Mixed-resolution calculations and exports must state the
analysis scale and any reprojection or resampling method. Do not assume that
requesting a 10 m export creates new 10 m information from a 20 m SWIR band.
Use nearest-neighbor semantics for categorical masks unless the method requires
otherwise; choose continuous-band resampling deliberately and record it.

The harmonized collection adjusts newer processing-baseline values to match
older scenes. Do not replace it with `COPERNICUS/S2_SR` or a Level-1C
collection without user agreement. Cloud metadata is not a pixel mask, and
`QA60` availability/construction changed over time; verify the current
official cloud-mask guidance before adopting a QA workflow.

## VIIRS nighttime land-surface temperature

Collection: `NASA/VIIRS/002/VNP21A1N`.

This is a daily nighttime land-surface-temperature and emissivity product on a
1 km grid. The current Earth Engine catalog identifies `LST_1KM` in Kelvin
and provides a `QC` bitmask for production status, cloud state, calibration,
and LST accuracy. The catalog presentation can change, and upstream product
files may describe stored values differently, so every temperature workflow
must:

1. inspect the exact band's current official scale and offset, including whether
   Earth Engine already exposes physical units;
2. state the relationship among stored DN, Kelvin, and Celsius;
3. never infer temperature units solely from a band or Python variable name;
4. record the verified conversion expression in the final research method.

Use this general conversion order only after verifying the catalog metadata:

```text
Kelvin = DN * scale + offset
Celsius = Kelvin - 273.15
```

If Earth Engine already exposes `LST_1KM` as Kelvin with no additional scale
or offset, do not invent another multiplication. Apply a documented `QC`
selection and report how masked, cloudy, unreliable, or missing pixels were
handled.

## Landsat Collection 2 Level 2

Select the mission, tier, and Level-2 collection explicitly. Do not assume
that the same `SR_B*` number represents the same spectral region for every
Landsat sensor:

| Meaning | Landsat 4/5 TM and Landsat 7 ETM+ | Landsat 8/9 OLI |
| --- | --- | --- |
| Blue | `SR_B1` | `SR_B2` |
| Green | `SR_B2` | `SR_B3` |
| Red | `SR_B3` | `SR_B4` |
| Near infrared | `SR_B4` | `SR_B5` |
| SWIR 1 | `SR_B5` | `SR_B6` |
| SWIR 2 | `SR_B7` | `SR_B7` |

For Collection 2 Level 2 surface-reflectance bands, the current catalog uses
`reflectance = DN * 0.0000275 - 0.2`. Verify this on the exact collection page
before final computation, especially when code may mix collections or
processing levels. Do not reuse Collection 1 scaling.

Surface-temperature bands also differ: commonly `ST_B6` for Landsat 4/5/7
and `ST_B10` for Landsat 8/9. Verify the exact band, scale, offset, units, and
`PROCESSING_LEVEL`; an ST band can be present but fully masked in an
SR-only scene. Decode `QA_PIXEL` and `QA_RADSAT` using the chosen
mission/product documentation rather than copying an unverified bit mask.

When combining missions, map bands by physical meaning, not by matching band
numbers, and record any cross-sensor harmonization, resampling, or temporal
limitations.

## MODIS vegetation indices

When `MODIS/061/MOD13Q1` is requested, treat NDVI/EVI, QA, compositing
interval, sinusoidal projection, and scale factor as separate methodological
choices. Apply the current catalog's scale and QA definitions before
interpreting values. Do not mix daily, 8-day, 16-day, monthly, or annual
products as though their timestamps and observation support were equivalent.

## User Assets and other official datasets

- A user-specified official dataset always takes priority over the defaults in
  this file; do not substitute one of these collections for convenience.
- For a user Asset, inspect its type, bands/schema, time property, geometry,
  projection, scale, masks/NoData, and relevant metadata before applying a
  catalog rule from another product.
- If official documentation and observed metadata appear inconsistent, stop,
  show the discrepancy, and resolve it before the full calculation.

## Official catalog pages

- Sentinel-2 SR Harmonized:
  https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S2_SR_HARMONIZED
- VIIRS VNP21A1N:
  https://developers.google.com/earth-engine/datasets/catalog/NASA_VIIRS_002_VNP21A1N
- Landsat Collection 2 migration:
  https://developers.google.com/earth-engine/landsat_c1_to_c2
- Landsat collections:
  https://developers.google.com/earth-engine/datasets/catalog/landsat
- MOD13Q1 V6.1:
  https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MOD13Q1
