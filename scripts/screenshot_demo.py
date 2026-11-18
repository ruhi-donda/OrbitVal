#!/usr/bin/env python3
"""
Screenshot the running demo for slide 7: "Brownout in sun" preset, light
theme toggle on, 1600x900 viewport at 2x scale (3200x1800 PNG).

Start the demo first:  streamlit run orbitval/ml/app/demo.py
Needs Playwright with an installed Google Chrome, not part of the extras:
    pip install playwright==1.49.1
Usage: python scripts/screenshot_demo.py [OUT]
       (default OUT: results/slides/demo_brownout_light.png)
"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
out = sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "results" / "slides" / "demo_brownout_light.png")
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    page = b.new_page(viewport={"width": 1600, "height": 900}, device_scale_factor=2,
                      color_scheme="light")
    page.goto("http://localhost:8501/", wait_until="networkidle")
    page.get_by_text("Brownout in sun").wait_for(timeout=60000)
    page.get_by_text("Light theme (for projectors)").click()
    page.wait_for_timeout(6000)
    page.get_by_text("Brownout in sun").click()
    page.wait_for_timeout(8000)
    page.screenshot(path=out)
    b.close()
print(out)
