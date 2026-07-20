import os
from pathlib import Path

import pandas as pd
from supabase import create_client

ENV_PATH = Path(__file__).resolve().parents[1] / ".env.local"


def load_env_file(path: Path) -> None:
    """Load KEY=VALUE pairs from a .env file into os.environ (no overwrite)."""
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        os.environ.setdefault(key, value)


load_env_file(ENV_PATH)

supabase_url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
service_role_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

if not supabase_url or not service_role_key:
    raise SystemExit(
        f"Missing NEXT_PUBLIC_SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in {ENV_PATH}"
    )

# Use the service role key from .env.local (API access), not the Postgres password.
client = create_client(supabase_url, service_role_key)
print(f"Connected to Supabase API at {supabase_url}")

df = pd.read_csv(
    "/Users/qazi/Documents/gitRepos/ollama/blood-testing/input/dataTobeUpdated.csv"
)

print(f"Updating descriptions for {len(df)} tests...")

updated = 0
missing = 0
failed = 0

for _, row in df.iterrows():
    test_name = str(row["test_name"]).strip()
    short_desc = str(row["short_description"]).strip()
    long_desc = str(row["clinical_overview"]).strip()

    try:
        test_res = (
            client.table("tests")
            .update({"short_description": short_desc})
            .eq("name", test_name)
            .execute()
        )

        if not test_res.data:
            missing += 1
            print(f"[MISS] No tests row for: {test_name}")
            continue

        test_id = test_res.data[0]["id"]
        client.table("test_details").update({"clinical_note": long_desc}).eq(
            "test_id", test_id
        ).execute()
        updated += 1
        print(f"[OK] {test_name}")
    except Exception as exc:  # noqa: BLE001 - continue on per-row failures
        failed += 1
        print(f"[FAIL] {test_name}: {exc}")

print(
    f"Done. updated={updated} missing={missing} failed={failed} total={len(df)}"
)
