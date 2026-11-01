"""Prepare a private local Django signing key without displaying credentials."""
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.security import is_strong_secret_key


def configure_local_env(path):
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = existing.splitlines()
    indexes = []
    current = ""
    has_debug_setting = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, value = stripped.split("=", 1)
        if name.strip() == "DJANGO_DEBUG":
            has_debug_setting = True
        if name.strip() == "DJANGO_SECRET_KEY":
            indexes.append(index)
            current = value.strip().strip("\"'")
    needs_key = not is_strong_secret_key(current) or len(indexes) != 1
    if not needs_key and has_debug_setting:
        return False
    if needs_key:
        replacement = "DJANGO_SECRET_KEY=" + secrets.token_urlsafe(64)
        if indexes:
            lines[indexes[0]] = replacement
            lines = [line for index, line in enumerate(lines) if index not in indexes[1:]]
        else:
            if lines and lines[-1]:
                lines.append("")
            lines.extend(["# Private Django signing key. Never copy this into frontend code.", replacement])
    if not has_debug_setting:
        lines.extend(["# Local development only. Use DJANGO_DEBUG=False on a hosted server.", "DJANGO_DEBUG=True"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return True


if __name__ == "__main__":
    changed = configure_local_env(ROOT / ".env")
    print("Saved local server configuration in .env without displaying credentials." if changed else "Existing private server configuration retained.")
