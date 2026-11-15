"""Print the CHANGELOG.md section of one version (for the GitHub release body)."""
import re
import sys

ver = sys.argv[1].lstrip("v")
text = open("CHANGELOG.md", encoding="utf-8").read()
m = re.search(rf"^## {re.escape(ver)}\b.*?$(.*?)(?=^## |\Z)", text, re.M | re.S)
print((m.group(1) if m else "").strip() or f"Keyglot {ver}")
