from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import yaml
from phoenix.client import Client

BASE_DIR = Path(__file__).parent


def load_registry() -> dict:
    return yaml.safe_load((BASE_DIR / "datasets.yaml").read_text(encoding="utf-8"))


def load_frame(dataset_name: str) -> tuple[dict, pd.DataFrame]:
    registry = load_registry()["datasets"]
    if dataset_name not in registry:
        raise KeyError(f"Unknown dataset: {dataset_name}")
    config = registry[dataset_name]
    csv_path = BASE_DIR / config["csv_path"]
    frame = pd.read_csv(csv_path)
    required = set(config["input_keys"] + config["output_keys"])
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Dataset missing required columns: {sorted(missing)}")
    return config, frame


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-name", default="veteran-access-eval-0")
    parser.add_argument("--phoenix-name")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    config, frame = load_frame(args.dataset_name)
    if args.dry_run:
        print(f"Validated {args.dataset_name}: {len(frame)} rows")
        return

    client = Client()
    client.datasets.create_dataset(
        name=args.phoenix_name or args.dataset_name,
        dataframe=frame,
        input_keys=config["input_keys"],
        output_keys=config["output_keys"],
        description=config["description"],
    )
    print(f"Uploaded {args.dataset_name}: {len(frame)} rows")


if __name__ == "__main__":
    main()
