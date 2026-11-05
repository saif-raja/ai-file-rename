"""Render docs/assets/hero.svg from the mixed-folder fixture and its recorded naming response.

The table is the one ``cli._display_dry_run`` prints; the names come from
``tests/fixtures/mock-responses/holistic_naming_mixed.json``, the response recorded for
``tests/fixtures/sample-files/mixed-folder``, so the picture needs no API key and is
exactly as checkable as the fixture.

    uv run --frozen --extra dev python docs/assets/render_hero.py

PNG (1280x640, also the repository's social preview) via headless Chrome, from the repo root:

    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --disable-gpu \
      --hide-scrollbars --window-size=1280,640 --force-device-scale-factor=2 \
      --user-data-dir=/tmp/hero-chrome --screenshot="$PWD/docs/assets/hero.png" \
      "file://$PWD/docs/assets/hero.html"
"""
import json
from pathlib import Path

from rich.console import Console
from rich.table import Table

ASSETS = Path(__file__).resolve().parent
REPO = ASSETS.parent.parent
RESPONSE = REPO / "tests/fixtures/mock-responses/holistic_naming_mixed.json"

renames = json.loads(RESPONSE.read_text())["renames"]

console = Console(record=True, width=86, force_terminal=True, color_system="truecolor")
console.print("[bold]$ ai-rename rename tests/fixtures/sample-files/mixed-folder[/bold]")
console.print("[dim](impact summary and phase lines omitted)[/dim]")
table = Table(title="PROPOSED RENAMES")
table.add_column("#", justify="right", style="dim")
table.add_column("Current Name", style="red")
table.add_column("Proposed Name", style="green")
table.add_column("Notes", style="yellow")
for i, r in enumerate(renames, 1):
    table.add_row(str(i), r["current_name"], r["proposed_name"], "")
console.print(table)

(ASSETS / "hero.svg").write_text(console.export_svg(title="ai-rename"))
(ASSETS / "hero.html").write_text(
    "<!doctype html><html><head><meta charset='utf-8'><style>"
    "html,body{margin:0;width:1280px;height:640px;background:#0f1117;"
    "display:flex;align-items:center;justify-content:center}img{width:1180px;height:auto}"
    "</style></head><body><img src='hero.svg'></body></html>\n"
)
print("wrote hero.svg and hero.html under", ASSETS)
