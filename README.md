# Blood Testing Lab Copy Generator

This project generates `short_description` and `clinical_overview` text for lab tests using a local Ollama-hosted LLM.

## What it does

- Reads a text file of test names (one per line)
- Calls a local Ollama model through the OpenAI-compatible API
- Writes the generated text to a CSV with `test_name`, `short_description`, and `clinical_overview`

## Project layout

- `run.sh` — one-command runner (checks environment, installs only what's missing, then generates)
- `src/blood_testing/generate_descriptions.py` — main generation logic
- `input/testnames.txt` — default input list of test names
- `output/` — generated CSV output
- `requirements.txt` — Python dependencies
- `pyproject.toml` — project metadata and CLI configuration

## Quick start

### Default run

From the repo root, just run:

```bash
./run.sh
```

With no arguments it uses:

| Flag | Default |
|------|---------|
| `--input` | `input/testnames.txt` |
| `--output` | `output/lab_test_descriptions.csv` |
| `--model` | `gemma4:latest` |

The script checks Python, the virtualenv, dependencies, and Ollama first, then generates a timestamped CSV under `output/` (for example `lab_test_descriptions_20260717_223000.csv`).

### Custom input and output

Pass your own paths when you need them:

```bash
./run.sh --input path/to/my_tests.txt --output output/my_results.csv
```

You can also change the model:

```bash
./run.sh --model gemma4:latest
```

Or combine all three:

```bash
./run.sh \
  --input path/to/my_tests.txt \
  --output output/my_results.csv \
  --model gemma4:latest
```

## Expected input

`input/testnames.txt` should look like:

```text
Test Name
CBC
CMP
TSH
A1C
```

## Output columns

The CSV will contain:

- `test_name`
- `short_description`
- `clinical_overview`

## Manual run (optional)

If you prefer to manage the environment yourself:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

python -m blood_testing \
  --input input/testnames.txt \
  --output output/lab_test_descriptions.csv
```

## Notes

- The default model is `gemma4:latest`
- The script uses the local HTTP endpoint at `http://localhost:11434/v1`
- Progress is reported with a tqdm progress bar
- Each run writes a timestamped CSV plus a matching `.metadata.txt` file
