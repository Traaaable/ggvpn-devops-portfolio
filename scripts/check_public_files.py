"""Reject production state/credentials without printing file contents."""
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
errors = []
patterns = {
    "private key": re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"),
    "GitHub token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,})\b"),
    "Telegram token": re.compile(r"\b[0-9]{8,12}:[A-Za-z0-9_-]{30,}\b"),
    "production domain": re.compile(r"\bggvpn\.xyz\b"),
    "internal admin route": re.compile(r"/[A-Za-z0-9]{20,}/admin\b"),
}
for path in root.rglob("*"):
    relative = path.relative_to(root)
    if set(relative.parts) & {".git", ".venv", "__pycache__", "dist"}:
        continue
    if path.is_symlink():
        errors.append((str(relative), "symlink"))
        continue
    if not path.is_file():
        continue
    if path.name.startswith(".env") and path.name != ".env.example":
        errors.append((str(relative), "environment file"))
    if any(path.name.endswith(suffix) for suffix in (".db", ".sqlite", ".pem", ".key", ".tfstate", ".tfvars")):
        errors.append((str(relative), "runtime/credential filename"))
    text = path.read_text(errors="replace")
    for label, pattern in patterns.items():
        if pattern.search(text):
            errors.append((str(relative), label))
for path, reason in errors:
    print(f"FAIL {path}: {reason}")
print(f"Public-file checks: {len(errors)} finding(s). Pattern checks are not a full secret audit.")
sys.exit(bool(errors))
