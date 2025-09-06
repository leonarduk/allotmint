import shutil
from pathlib import Path

ENV_EXAMPLE = Path(__file__).resolve().parents[1] / ".env.example"
ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
REQUIRED_KEYS = ["ALPHA_VANTAGE_KEY", "JWT_SECRET"]


def prompt_values():
    values = {}
    for key in REQUIRED_KEYS:
        values[key] = input(f"Enter value for {key}: ").strip()
    return values


def update_env_file(env_path: Path, values: dict) -> None:
    lines = env_path.read_text().splitlines()
    for key, value in values.items():
        prefix = f"{key}="
        for i, line in enumerate(lines):
            if line.startswith(prefix):
                lines[i] = f"{prefix}{value}"
                break
        else:
            lines.append(f"{prefix}{value}")
    env_path.write_text("\n".join(lines) + "\n")


def main() -> None:
    if not ENV_EXAMPLE.exists():
        raise FileNotFoundError(".env.example not found")

    if ENV_FILE.exists():
        overwrite = input(".env already exists. Overwrite? [y/N]: ").lower()
        if overwrite != "y":
            print("Aborting without changes.")
            return
    shutil.copy(ENV_EXAMPLE, ENV_FILE)
    print("Copied .env.example to .env")
    values = prompt_values()
    update_env_file(ENV_FILE, values)
    print("Updated .env with provided values.")


if __name__ == "__main__":
    main()
