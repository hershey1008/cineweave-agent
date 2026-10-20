"""Create a portable local configuration without overwriting existing secrets."""
import argparse
from pathlib import Path
import secrets


def configure(root: Path, env_file: Path):
    if env_file.exists():
        raise FileExistsError(f"{env_file.name} already exists; edit it explicitly instead of overwriting it")
    values = {
        "DB_PASSWORD": secrets.token_hex(16),
        "SECRET_KEY": secrets.token_hex(32),
        "FUNREC_RAW_DATA_PATH": "./artifacts/data",
        "FUNREC_MODELS_PATH": "./artifacts/processed/web_project/deployed_models",
        "FUNREC_PROCESSED_DATA_PATH": "./artifacts/processed",
    }
    template = (root / ".env.example").read_text(encoding="utf-8")
    lines = [line.split("=", 1)[0] + "=" + values[line.split("=", 1)[0]]
             if "=" in line and line.split("=", 1)[0] in values else line
             for line in template.splitlines()]
    for name in ("artifacts/data", "artifacts/processed/web_project/deployed_models",
                 "artifacts/model_cache", "artifacts/semantic_index"):
        (root / name).mkdir(parents=True, exist_ok=True)
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Created {env_file.name}; independent secrets generated (values hidden).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    args = parser.parse_args()
    configure(Path(__file__).resolve().parents[1], args.env_file)
