# M02 Public-Data Ingestion and Audit

Status: **Complete for the primary GSW curve; optional FRED live retrieval requires a user secret**

## Objective

Create a reproducible, versioned, and auditable data pipeline for the public market inputs used by the phase-one Treasury portfolio. M02 validates data availability and integrity only. It does not construct an interpolated valuation curve or calculate portfolio risk.

## Primary source

The primary source is the Federal Reserve Board's Gürkaynak-Sack-Wright nominal Treasury yield-curve CSV:

```text
https://www.federalreserve.gov/data/yield-curve-tables/feds200628.csv
```

The source is a staff research product rather than an official statistical release. It may be delayed, revised, or changed methodologically. The repository therefore preserves each downloaded payload, retrieval timestamp, response metadata, byte count, and SHA-256 digest.

The pipeline selects only `SVENY01` through `SVENY30`. These fields are continuously compounded zero-coupon yields reported in percentage points. The normalized model field divides the source value by 100 and stores a decimal annual rate.

Par yields (`SVENPYXX`), forward rates (`SVENFXX` and `SVEN1FXX`), and Svensson parameters are not substituted for the zero-yield fields.

## Optional FRED sources

The repository includes a FRED API adapter for:

- `DFF`: cash and funding proxy
- `DGS3MO`: short-end yield proxy

FRED values are stored separately from the GSW curve and are not treated as identical to an instantaneous short rate. Live FRED retrieval requires `FRED_API_KEY` through Colab Secrets. The key is passed only to the HTTPS request and is excluded from raw metadata, logs, configuration, and Git.

## Pipeline outputs

Each run creates ignored local artifacts under `data/`:

```text
data/
├── raw/
│   ├── gsw/<timestamped hash-addressed CSV and metadata>
│   └── fred/<timestamped hash-addressed JSON and metadata>
├── processed/<normalized long-form gzip CSV>
└── audit/<JSON audit report>
```

Raw bytes are never overwritten by normalized or interpolated values. Data artifacts are excluded from Git because they are reproducible and may become large.

## Audit rules

The primary GSW audit checks:

- Presence of `SVENY` fields
- Valid observation dates
- Unique date-tenor keys
- Decimal conversion from source percentage points
- Required 3Y, 7Y, and 15Y coverage from 2005 onward
- Availability of required tenors on the latest curve date
- Yield range diagnostic of -5% to 25%
- Source staleness relative to a 14-calendar-day threshold
- Explicit preservation of missing values

The source contains dates on which the entire curve is missing, primarily holidays. These dates remain in the normalized data and are counted as `empty_curve_date_count`; they are not misclassified as a missing-tenor defect. If one required tenor is missing on a date where another curve tenor exists, the audit still reports a warning.

## Live validation snapshot

The pipeline was validated against the official file retrieved on 2026-09-22 UTC.

| Check | Result |
|---|---:|
| Raw SHA-256 | `73761455d39b3cccbbf4b520b1dda81c142f7fcda77b774e9e3f3eea917e3862` |
| Analysis start | 2005-01-01 |
| Latest observation | 2026-09-11 |
| Effective curve dates | 5,428 |
| Empty full-curve dates | 232 |
| Duplicate date-tenor rows | 0 |
| Invalid yield-range observations | 0 |
| 3Y observed coverage | 100% |
| 7Y observed coverage | 100% |
| 15Y observed coverage | 100% |
| Audit status | PASS |

This snapshot demonstrates that the pipeline worked for one identified source vintage. It does not guarantee that future source schemas or values will remain unchanged; each run repeats the same audit.

## Acceptance evidence

- Eleven standard-library unit tests pass.
- The official full GSW file downloads and receives a SHA-256 digest.
- The current source preamble and delayed `Date` header are parsed correctly.
- Missing observations remain explicit.
- Required-tenor coverage is calculated only on dates with an observed curve.
- Raw, processed, and audit artifacts are separated.
- FRED parsing and secret-exclusion behavior are covered by tests.
- No downloaded data, API keys, or generated outputs are committed.

## Completion boundary

M02 establishes reliable market-data inputs. Curve interpolation, discount-factor construction, zero-coupon pricing, DV01, and valuation invariants belong to M03.
