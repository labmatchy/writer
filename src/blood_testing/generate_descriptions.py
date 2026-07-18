from __future__ import annotations

import argparse
import csv
import json
import os
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Union

import pandas as pd
from openai import OpenAI
from tqdm import tqdm

from blood_testing.prompts import COMBINED_PROMPT, SYSTEM_ROLE

DEFAULT_MODEL_NAME = "gemma4:latest"
DEFAULT_BASE_URL = "http://localhost:11434/v1"
DEFAULT_API_KEY = "ollama"

MAX_JSON_RETRIES = 2


def build_timestamped_output_path(output_path: Path) -> Path:
    """Return a new output path with a timestamp suffix so each run creates a fresh file."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return output_path.with_name(f"{output_path.stem}_{timestamp}{output_path.suffix}")


def build_client(base_url: str = DEFAULT_BASE_URL, api_key: str = DEFAULT_API_KEY) -> OpenAI:
    """Initialize the local OpenAI-compatible Ollama client."""
    return OpenAI(base_url=base_url, api_key=api_key)


def _strip_code_fences(text: str) -> str:
    """Remove ```json / ``` fences some local models add despite instructions."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 2)[1] if cleaned.count("```") >= 2 else cleaned
        cleaned = cleaned.replace("json", "", 1).strip() if cleaned.lower().startswith("json") else cleaned
    return cleaned.strip("`").strip()


def query_descriptions(
    test_name: str,
    model_name: str,
    client: OpenAI,
) -> Tuple[str, str]:
    """Ask the local LLM for both descriptions in a single call and parse the JSON result.

    Generating both fields together (instead of two separate calls) is what lets the model
    keep them consistent with each other, since it can see both requirements at once and
    self-checks for contradictions before returning.
    """
    prompt = COMBINED_PROMPT.format(TEST_NAME=test_name)

    last_error = ""
    for attempt in range(1, MAX_JSON_RETRIES + 2):
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": SYSTEM_ROLE},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.15,
            )
            raw = response.choices[0].message.content.strip()
            raw = _strip_code_fences(raw)
            parsed = json.loads(raw)

            short_desc = str(parsed.get("short_description", "")).strip()
            long_desc = str(parsed.get("clinical_overview", "")).strip()

            if short_desc and long_desc:
                return short_desc, long_desc

            last_error = f"Missing key(s) in JSON response: {parsed}"
        except json.JSONDecodeError as exc:
            last_error = f"Could not parse JSON (attempt {attempt}): {exc}\nRaw response: {raw}"
        except Exception as exc:  # noqa: BLE001 - surface any API/client error and retry
            last_error = f"Error querying local LLM (attempt {attempt}): {exc}"

    print(f"[WARN] Failed to get valid descriptions for '{test_name}': {last_error}")
    return "", ""


def process_text_catalog(
    input_text_path: Union[str, os.PathLike[str]],
    output_text_path: Union[str, os.PathLike[str]],
    model_name: str = DEFAULT_MODEL_NAME,
) -> None:
    """Generate short and long descriptions from a text file of test names.

    The workflow starts from a clean output state: the report file is created up front with the
    expected header, then each test is processed, and the result row is written immediately to disk.
    """
    input_path = Path(input_text_path)
    output_path = Path(output_text_path)
    output_path = build_timestamped_output_path(output_path)

    if not input_path.exists():
        raise FileNotFoundError(f"Could not find input file '{input_path}'")

    with input_path.open("r", encoding="utf-8") as handle:
        raw_lines = [line.strip() for line in handle if line.strip()]

    test_names = []
    for line in raw_lines:
        normalized = line.lower()
        if normalized in {"test name", "test_name"}:
            continue
        test_names.append(line)

    if not test_names:
        raise ValueError(f"No test names were found in '{input_path}'")

    total_tests = len(test_names)
    client = build_client()
    start_time = datetime.now()
    start_ts = start_time.isoformat()
    print(f"Starting local generation for {total_tests} tests using {model_name}...")
    print(f"Run started at: {start_ts}")
    print(f"Loop size: {total_tests} tests")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    metadata_path = output_path.with_suffix(output_path.suffix + ".metadata.txt")

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["test_name", "short_description", "clinical_overview"])
        handle.flush()
        os.fsync(handle.fileno())

        for index, test_name in enumerate(
            tqdm(test_names, desc="Generating Descriptions", total=total_tests),
            start=1,
        ):
            print(f"[START] {index}/{total_tests}: {test_name}")

            try:
                short_desc, long_desc = query_descriptions(test_name, model_name, client)
                writer.writerow([test_name, short_desc, long_desc])
                handle.flush()
                os.fsync(handle.fileno())
                print(f"[OK] Finished: {test_name}")
            except Exception:  # noqa: BLE001 - continue on per-record failures
                print(f"[FAIL] {test_name}")
                traceback.print_exc()
                continue

    end_time = datetime.now()
    duration_seconds = round(time.time() - start_time.timestamp(), 2)
    end_ts = end_time.isoformat()

    with metadata_path.open("w", encoding="utf-8") as meta_handle:
        meta_handle.write(f"started_at={start_ts}\n")
        meta_handle.write(f"ended_at={end_ts}\n")
        meta_handle.write(f"duration_seconds={duration_seconds}\n")
        meta_handle.write(f"test_count={total_tests}\n")

    print(f"Run ended at: {end_ts}")
    print(f"Total elapsed time: {duration_seconds} seconds")
    print(f"\nProcessing complete! Output saved successfully to: {output_path}")
    print(f"Run metadata saved to: {metadata_path}")


def process_catalog(
    input_excel_path: Union[str, os.PathLike[str]],
    output_excel_path: Union[str, os.PathLike[str]],
    model_name: str = DEFAULT_MODEL_NAME,
    batch_save_every: int = 50,
) -> None:
    """Generate descriptions for each test in an Excel catalog file."""
    input_path = Path(input_excel_path)
    output_path = Path(output_excel_path)
    output_path = build_timestamped_output_path(output_path)

    if not input_path.exists():
        raise FileNotFoundError(f"Could not find input file '{input_path}'")

    df = pd.read_excel(input_path)
    df.columns = [str(col).strip() for col in df.columns]

    target_column = "test_name"
    if target_column not in df.columns:
        available = ", ".join(df.columns)
        raise ValueError(
            f"Could not find '{target_column}' column in your Excel. Available columns: {available}"
        )

    client = build_client()

    short_descriptions: List[str] = []
    long_descriptions: List[str] = []

    print(f"Starting local generation for {len(df)} tests using {model_name}...")

    for index, row in tqdm(df.iterrows(), total=len(df), desc="Generating Descriptions"):
        test_name = str(row[target_column]).strip()
        short_desc, long_desc = query_descriptions(test_name, model_name, client)

        short_descriptions.append(short_desc)
        long_descriptions.append(long_desc)

        if batch_save_every and index > 0 and index % batch_save_every == 0:
            temp_df = df.iloc[: index + 1].copy()
            temp_df["short_description"] = short_descriptions
            temp_df["clinical_overview"] = long_descriptions
            temp_df.to_excel(output_path, index=False)

    df["short_description"] = short_descriptions
    df["clinical_overview"] = long_descriptions
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(output_path, index=False)
    print(f"\nProcessing complete! Output saved successfully to: {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate short and long clinical descriptions for lab test catalogs using Ollama."
    )
    parser.add_argument("--input", required=True, help="Path to the input Excel file")
    parser.add_argument("--output", required=True, help="Path to the output Excel file")
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL_NAME,
        help=f"Ollama model name to use (default: {DEFAULT_MODEL_NAME})",
    )
    parser.add_argument(
        "--batch-save-every",
        type=int,
        default=50,
        help="Autosave every N rows to protect progress (default: 50)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    input_path = Path(args.input)
    if input_path.suffix.lower() == ".txt":
        process_text_catalog(
            input_text_path=args.input,
            output_text_path=args.output,
            model_name=args.model,
        )
        return

    process_catalog(
        input_excel_path=args.input,
        output_excel_path=args.output,
        model_name=args.model,
        batch_save_every=args.batch_save_every,
    )


if __name__ == "__main__":
    main()