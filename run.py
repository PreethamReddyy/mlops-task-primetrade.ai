#!/usr/bin/env python3
"""
run.py — Minimal MLOps-style batch job.

Pipeline:
  1. Load + validate YAML config (seed, window, version)
  2. Load + validate OHLCV CSV data (requires a 'close' column)
  3. Compute rolling mean on 'close' using the configured window
  4. Generate a binary signal: 1 if close > rolling_mean else 0
  5. Write structured metrics to a JSON file (success or error schema)
  6. Log every step to a log file (and stdout) for observability

Usage:
  python run.py --input data.csv --config config.yaml --output metrics.json --log-file run.log
"""

import argparse
import json
import logging
import os
import sys
import time

import numpy as np
import pandas as pd
import yaml

REQUIRED_CONFIG_FIELDS = ("seed", "window", "version")


def parse_args():
    parser = argparse.ArgumentParser(description="Minimal MLOps batch job.")
    parser.add_argument("--input", required=True, help="Path to input OHLCV CSV file")
    parser.add_argument("--config", required=True, help="Path to YAML config file")
    parser.add_argument("--output", required=True, help="Path to write metrics JSON")
    parser.add_argument("--log-file", required=True, help="Path to write log file")
    return parser.parse_args()


def setup_logging(log_file_path):
    """Configure logging to write to both the log file and stdout."""
    logger = logging.getLogger("mlops_task")
    logger.setLevel(logging.DEBUG)
    logger.handlers = []  # avoid duplicate handlers if re-run in same process

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(log_file_path, mode="w")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    return logger


def write_metrics(output_path, payload, logger):
    """Write metrics JSON to disk. Called for both success and error cases."""
    with open(output_path, "w") as f:
        json.dump(payload, f, indent=2)
    logger.info(f"Metrics written to {output_path}: {payload}")


def load_config(config_path, logger):
    """Load and validate the YAML config file."""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r") as f:
        try:
            config = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in config file: {e}")

    if not isinstance(config, dict):
        raise ValueError("Invalid config structure: expected a YAML mapping (key: value)")

    missing = [field for field in REQUIRED_CONFIG_FIELDS if field not in config]
    if missing:
        raise ValueError(f"Config missing required field(s): {missing}")

    if not isinstance(config["seed"], int):
        raise ValueError("Config field 'seed' must be an integer")
    if not isinstance(config["window"], int) or config["window"] <= 0:
        raise ValueError("Config field 'window' must be a positive integer")
    if not isinstance(config["version"], str):
        raise ValueError("Config field 'version' must be a string")

    logger.info(
        f"Config loaded + validated: seed={config['seed']}, "
        f"window={config['window']}, version={config['version']}"
    )
    return config


def load_dataset(input_path, logger):
    """Load and validate the OHLCV CSV file."""
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")

    if os.path.getsize(input_path) == 0:
        raise ValueError(f"Input file is empty: {input_path}")

    try:
        df = pd.read_csv(input_path, quotechar='|')
        df.columns = df.columns.str.replace('"', '').str.strip()
    except pd.errors.EmptyDataError:
        raise ValueError(f"Input file has no parseable data: {input_path}")
    except pd.errors.ParserError as e:
        raise ValueError(f"Invalid CSV format: {e}")
    if df.empty:
        raise ValueError("Input file contains no rows")

    if "close" not in df.columns:
        raise ValueError("Required column 'close' not found in input data")

    if df["close"].isna().all():
        raise ValueError("Column 'close' contains no valid (non-null) values")

    logger.info(f"Rows loaded: {len(df)} from {input_path}")
    return df


def compute_signal(df, window, logger):
    """
    Compute rolling mean on 'close' and derive a binary signal.

    The first (window - 1) rows will have NaN rolling means (pandas default,
    min_periods=window). For those rows, close > rolling_mean evaluates to
    False, so signal = 0. This is a deliberate, consistent choice: rather
    than fabricating an early signal from partial windows, we treat the
    warm-up period as "no signal" (0).
    """
    logger.info(f"Computing rolling mean with window={window}")
    df["rolling_mean"] = df["close"].rolling(window=window).mean()

    logger.info("Generating binary signal (1 if close > rolling_mean else 0)")
    df["signal"] = np.where(df["close"] > df["rolling_mean"], 1, 0)

    return df


def main():
    args = parse_args()
    logger = setup_logging(args.log_file)

    start_time = time.perf_counter()
    logger.info("Job started")

    try:
        config = load_config(args.config, logger)
        np.random.seed(config["seed"])
        logger.info(f"Random seed set to {config['seed']}")

        df = load_dataset(args.input, logger)
        df = compute_signal(df, config["window"], logger)

        rows_processed = int(len(df))
        signal_rate = float(df["signal"].mean())
        latency_ms = int((time.perf_counter() - start_time) * 1000)

        logger.info(
            f"Metrics summary: rows_processed={rows_processed}, "
            f"signal_rate={signal_rate:.4f}, latency_ms={latency_ms}"
        )

        metrics = {
            "version": config["version"],
            "rows_processed": rows_processed,
            "metric": "signal_rate",
            "value": round(signal_rate, 4),
            "latency_ms": latency_ms,
            "seed": config["seed"],
            "status": "success",
        }
        write_metrics(args.output, metrics, logger)
        logger.info("Job ended: status=success")
        sys.exit(0)

    except Exception as e:
        logger.exception(f"Job failed: {e}")
        error_payload = {
            "version": "v1",
            "status": "error",
            "error_message": str(e),
        }
        try:
            write_metrics(args.output, error_payload, logger)
        except Exception as write_err:
            logger.exception(f"Failed to write error metrics file: {write_err}")
        logger.info("Job ended: status=error")
        sys.exit(1)


if __name__ == "__main__":
    main()
