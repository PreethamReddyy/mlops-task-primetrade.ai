# MLOps Task 0 — Batch Signal Job

A minimal, reproducible MLOps-style batch job that reads OHLCV price data,
computes a rolling-mean-based binary trading signal, and emits structured
metrics + logs. Built to run identically on a local machine and inside Docker.

## What it does

1. Loads and validates a YAML config (`seed`, `window`, `version`)
2. Loads and validates an OHLCV CSV file (requires a `close` column)
3. Computes a rolling mean on `close` over `window` periods
4. Generates a binary signal per row: `1` if `close > rolling_mean`, else `0`
5. Writes `metrics.json` (success or error schema — always written, either way)
6. Writes a detailed `run.log` covering every pipeline step

## Files

| File | Purpose |
|---|---|
| `run.py` | Main batch job |
| `config.yaml` | Config (`seed`, `window`, `version`) |
| `data.csv` | Input OHLCV data |
| `requirements.txt` | Python dependencies |
| `Dockerfile` | Container build definition |
| `metrics.json` | Sample output from a successful run |
| `run.log` | Sample log from a successful run |

## Local run

```bash
pip install -r requirements.txt

python run.py \
  --input data.csv \
  --config config.yaml \
  --output metrics.json \
  --log-file run.log
```

Exit code is `0` on success, non-zero on any failure (missing file, bad CSV,
missing `close` column, invalid config, etc.). `metrics.json` is written in
both cases.

## Docker

Build:

```bash
docker build -t mlops-task .
```

Run:

```bash
docker run --rm mlops-task
```

This runs the job inside the container using the bundled `data.csv` and
`config.yaml`, writes `metrics.json` and `run.log` inside the container, and
prints the final `metrics.json` contents to stdout. No paths are hardcoded —
everything is passed via CLI args and resolved relative to the working
directory (`/app` inside the container).

## Example `metrics.json` (success)

```json
{
  "version": "v1",
  "rows_processed": 10000,
  "metric": "signal_rate",
  "value": 0.4973,
  "latency_ms": 25,
  "seed": 42,
  "status": "success"
}
```

## Example `metrics.json` (error)

```json
{
  "version": "v1",
  "status": "error",
  "error_message": "Required column 'close' not found in input data"
}
```

## Notes on dependency versions

`requirements.txt` uses minimum-version constraints (`>=`) rather than exact
pins. This keeps the build portable across the Python version used inside
Docker (3.9, per the suggested base image) and whatever Python version a
developer has locally — exact pins can force pip to build a package from
source (and fail) if the local Python version is newer than the pinned
package version supports.

## Design notes

- **Determinism:** `numpy.random.seed(seed)` is set from config immediately
  after config validation. The signal logic itself is a deterministic
  function of the input data (no randomness involved), so repeated runs on
  the same `data.csv` produce identical `rows_processed` and `signal_rate`.
- **Warm-up rows:** The first `window - 1` rows have an undefined
  (`NaN`) rolling mean. Since `close > NaN` evaluates to `False` in pandas,
  these rows are consistently assigned `signal = 0` rather than being
  dropped or backfilled — this keeps `rows_processed` equal to the full
  row count while keeping the rule simple and consistent.
- **Error handling:** Config loading, dataset loading, and CSV validation are
  each wrapped with specific, descriptive exceptions (missing file, empty
  file, malformed CSV, missing column, invalid config structure). All
  exceptions bubble up to a single top-level handler in `main()` that logs
  the failure, writes the error-schema `metrics.json`, and exits non-zero —
  so the metrics file is *always* written, regardless of where a failure
  occurs.
