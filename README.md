# Blood Testing Lab Copy Generator

This project generates `short_description` and `clinical_overview` text for lab tests using a local Ollama-hosted LLM.

## What it does

- Reads an Excel catalog file
- Uses `test_name` as the input label
- Calls a local Ollama model through the OpenAI-compatible API
- Writes the generated text back into the workbook as new columns

## Project layout

- `src/blood_testing/generate_descriptions.py` — main generation logic
- `requirements.txt` — Python dependencies
- `pyproject.toml` — optional project metadata and CLI configuration

## Quick start

1. Create and activate a virtual environment:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Install and run Ollama locally:

   ```bash
   brew install ollama
   ollama pull gemma4:12b
   ollama serve
   ```

4. Put your input workbook next to the repo root, for example:

   ```bash
   tests_catalog.xlsx
   ```

5. Run the generator:

   ```bash
   python -m blood_testing.generate_descriptions \
     --input tests_catalog.xlsx \
     --output tests_catalog_completed.xlsx
   ```

## Expected Excel input

Your workbook should contain a column named `test_name`.

The script will add these output columns:

- `short_description`
- `clinical_overview`

## Notes

- The default model is `gemma4:12b`
- The script uses the local HTTP endpoint at `http://localhost:11434/v1`
- Progress is reported with a tqdm progress bar
