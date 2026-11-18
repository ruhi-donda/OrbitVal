#!/usr/bin/env python3
"""
Build results/slides/14_Ruhi_Donda.pptx: the 3-slide, 3-minute version of
the CS462 deck (no demo).

Content is condensed from docs/slide-outline.md. Every number comes from
docs/ml-project-log.md, the README results section, or the held-out JSON
files in results/heldout/heldout/. The ~60-second script for each slide is
in its speaker notes. Text is at least 18 pt; fonts are measured with macOS
Arial to warn about text that won't fit its box.

Needs python-pptx, not part of the project's extras:
    pip install python-pptx==1.0.2
Usage: python scripts/build_short_deck.py
"""

from pathlib import Path

from PIL import Image, ImageFont
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "results" / "slides"
OUT = FIG / "14_Ruhi_Donda.pptx"

INK = RGBColor(0x0B, 0x0B, 0x0B)
INK2 = RGBColor(0x52, 0x51, 0x4E)
ACCENT = RGBColor(0x2A, 0x78, 0xD6)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
FONT = "Arial"
W, H = 13.333, 7.5
M = 0.5
MIN_PT = 18

_fonts = {}
fit_report = []


def font(size, bold=False):
    if (size, bold) not in _fonts:
        name = "Arial Bold.ttf" if bold else "Arial.ttf"
        _fonts[(size, bold)] = ImageFont.truetype(f"/System/Library/Fonts/Supplemental/{name}", size * 10)
    return _fonts[(size, bold)]


def lines_needed(text, size, bold, width_in):
    f, max_w, n = font(size, bold), width_in * 720, 0
    for para in text.split("\n"):
        n += 1
        cur = ""
        for word in para.split(" "):
            trial = (cur + " " + word).strip()
            if f.getlength(trial) <= max_w:
                cur = trial
            else:
                n += 1
                cur = word
    return n


def style_run(run, size, bold=False, color=INK):
    assert size >= MIN_PT, size
    run.font.name = FONT
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color


def bullet(p, on):
    pPr = p._p.get_or_add_pPr()
    if on:
        pPr.set("marL", str(Emu(Inches(0.28))))
        pPr.set("indent", str(-Emu(Inches(0.28))))
        pPr.append(pPr.makeelement(qn("a:buChar"), {"char": "•"}))
    else:
        pPr.append(pPr.makeelement(qn("a:buNone"), {}))


def text_box(slide, x, y, w, h, items, size=18, space_after=6, align=PP_ALIGN.LEFT, name=""):
    """items: str or dict(text, bullet, bold, color, size). Rich runs: dict(runs=[(text, bold, color)])."""
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.TOP
    tf.margin_left = tf.margin_right = Inches(0.08)
    tf.margin_top = tf.margin_bottom = Inches(0.04)
    used = 0.08
    for i, it in enumerate(items):
        it = {"text": it} if isinstance(it, str) else it
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        s = it.get("size", size)
        bullet(p, it.get("bullet", False))
        p.alignment = align
        sa = it.get("space_after", space_after)
        p.space_after = Pt(sa)
        runs = it.get("runs") or [(it["text"], it.get("bold", False), it.get("color", INK))]
        for txt, bold, col in runs:
            r = p.add_run()
            r.text = txt
            style_run(r, s, bold, col)
        full = "".join(t for t, _, _ in runs)
        width = w - 0.16 - (0.28 if it.get("bullet") else 0)
        used += lines_needed(full, s, any(b for _, b, _ in runs), width) * s * 1.2 / 72 + sa / 72
    used -= sa / 72
    fit_report.append((name or "".join(t for t, _, _ in (items[0].get("runs") if isinstance(items[0], dict) and items[0].get("runs") else [(items[0] if isinstance(items[0], str) else items[0]["text"], 0, 0)]))[:50], used, h))
    return tb


def title(slide, text, size=30):
    t = slide.shapes.title
    t.left, t.top, t.width, t.height = Inches(M), Inches(0.2), Inches(W - 2 * M), Inches(0.75)
    tf = t.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    tf.text = text
    tf.paragraphs[0].alignment = PP_ALIGN.LEFT
    style_run(tf.paragraphs[0].runs[0], size, bold=True)
    fit_report.append(("TITLE " + text, lines_needed(text, size, True, W - 2 * M - 0.2) * size * 1.2 / 72, 0.75))
    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(M + 0.08), Inches(0.98), Inches(1.0), Inches(0.06))
    bar.fill.solid()
    bar.fill.fore_color.rgb = ACCENT
    bar.line.fill.background()


def picture(slide, path, x, y, w):
    img = Image.open(path)
    h = w * img.height / img.width
    slide.shapes.add_picture(str(path), Inches(x), Inches(y), Inches(w), Inches(h))
    return h


def heading(slide, x, y, w, text):
    text_box(slide, x, y, w, 0.46, [{"text": text, "bold": True, "size": 20, "color": ACCENT}], name="h " + text)


prs = Presentation()
prs.slide_width, prs.slide_height = Inches(W), Inches(H)
LAYOUT = prs.slide_layouts[5]       # Title Only
TWIN_NOTE = "*LSTM: 1 of these catches also fires on the fault-free twin mission."

# ------------------------------------------------------------------ Slide 1
s = prs.slides.add_slide(LAYOUT)
title(s, "Can a detector catch this fault?", size=30)
text_box(s, M, 1.05, W - 2 * M, 0.42, [
    {"text": "Validating spacecraft fault detection with OrbitVal · Ruhi Donda · CS462 · Nov 20, 2026", "color": INK2},
], name="s1 sub")
text_box(s, M, 1.42, W - 2 * M, 0.45, [
    {"runs": [("Problem: ", True, INK),
              ("faults are rare and mostly unlabeled; operators need early alarms, not constant false ones.", False, INK)]},
], name="s1 problem")

# forecast-then-flag flow
steps = ["Past window", "Forecaster", "Error", "Smoothing + rolling z-score", "Alarm line", "Alarm"]
widths = [1.55, 1.55, 1.15, 3.0, 1.45, 1.15]
gap = 0.36
x = (W - sum(widths) - gap * 5) / 2
y, hbox = 1.95, 0.75
for i, (label, bw) in enumerate(zip(steps, widths)):
    box = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(bw), Inches(hbox))
    box.line.color.rgb = ACCENT
    box.line.width = Pt(2)
    box.fill.solid()
    box.fill.fore_color.rgb = ACCENT if label == "Forecaster" else WHITE
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Inches(0.06)
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    tf.text = label
    tf.paragraphs[0].alignment = PP_ALIGN.CENTER
    style_run(tf.paragraphs[0].runs[0], 18, bold=True, color=WHITE if label == "Forecaster" else INK)
    fit_report.append(("box " + label, lines_needed(label, 18, True, bw - 0.12) * 18 * 1.2 / 72, hbox))
    x += bw
    if i < len(steps) - 1:
        arr = s.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, Inches(x + 0.05), Inches(y + hbox / 2 - 0.13),
                                 Inches(gap - 0.1), Inches(0.26))
        arr.fill.solid()
        arr.fill.fore_color.rgb = INK2
        arr.line.fill.background()
        x += gap
text_box(s, M, 2.78, W - 2 * M, 0.75, [
    "Every detector only forecasts the next reading; the scoring after it is shared, so detectors differ only in the "
    "forecaster. Alarm line set on clean data: at most 2 false alarms per 10,000 steps.",
], name="s1 flow note")

# three detectors
cw = (W - 2 * M - 0.3) / 3
cols = [("Persistence", "next = current; no learning (the baseline)"),
        ("LSTM", "1 layer, hidden size 32, 64-step window; 4,513 parameters"),
        ("GRU", "1 layer, hidden size 32, 64-step window; 3,393 parameters")]
for i, (name, desc) in enumerate(cols):
    cx = M + i * (cw + 0.15)
    box = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(cx), Inches(3.6), Inches(cw), Inches(1.05))
    box.fill.background()
    box.line.color.rgb = ACCENT if i else INK2
    box.line.width = Pt(1.5)
    text_box(s, cx + 0.04, 3.61, cw - 0.08, 1.02,
             [{"runs": [(name + ": ", True, INK), (desc, False, INK)]}], name="col " + name)

text_box(s, M, 4.68, W - 2 * M, 1.0, [
    {"runs": [("Deep learning techniques: ", True, ACCENT),
              ("recurrent networks (LSTM, GRU), gating, backpropagation through time, gradient clipping, Adam, "
               "MSE loss (= Gaussian likelihood), early stopping, 3 random seeds, trained on normal data only.", False, INK)]},
], name="s1 techniques")

half = (W - 2 * M - 0.3) / 2
text_box(s, M, 5.75, half, 1.6, [
    {"runs": [("NASA SMAP/MSL (real): ", True, INK),
              ("spacecraft telemetry with expert-labeled anomalies. Built while viewing only 30% of channels (dev); "
               "final numbers on the other 70%, held out (SMAP 37 channels, MSL 19).", False, INK)]},
], name="s1 data L")
text_box(s, M + half + 0.3, 5.75, half, 1.6, [
    {"runs": [("OrbitVal (simulated): ", True, INK),
              ("real orbit propagation drives sun and shadow, solar power, battery and temperature. 5 fault types. "
               "Final numbers on 2 orbits never seen in training.", False, INK)]},
], name="s1 data R")
s.notes_slide.notes_text_frame.text = (
    "Satellites stream telemetry all day. Faults are rare and mostly unlabeled, and operators want early alarms, "
    "but every false alarm teaches them to ignore the system. So the question is: which faults can a deep learning "
    "detector actually catch, and how would you know? Every detector here does the same thing. It forecasts the next "
    "reading from the last 64, and if the error is unusually large compared with the recent past, it raises an alarm. "
    "The scoring is shared, so the only difference is the forecaster: persistence, which just repeats the last value, "
    "against a small LSTM and GRU, trained with backpropagation through time, Adam, gradient clipping and early "
    "stopping, on normal data only, three seeds each. Every alarm line is set on clean data to allow two false alarms "
    "per ten thousand steps. I test on real NASA SMAP and MSL telemetry and on simulated OrbitVal missions, and the "
    "final numbers come from held-out channels and held-out orbits."
)

# ------------------------------------------------------------------ Slide 2
s = prs.slides.add_slide(LAYOUT)
title(s, "Result: trained models catch much smaller sudden faults", size=30)
text_box(s, M, 1.1, W - 2 * M, 0.55, [
    {"runs": [("Held-out brownout at 0.1: ", True, INK),
              ("persistence 0/20 · LSTM 59/60* · GRU 60/60", True, ACCENT)], "size": 22},
], name="s2 headline")
pic_w = 7.9
pic_h = picture(s, FIG / "heldout_detectability.png", M, 1.72, pic_w)
assert 1.72 + pic_h <= 6.22, pic_h
rx = M + pic_w + 0.2
text_box(s, rx, 1.8, W - M - rx, 4.4, [
    {"text": "Missions where the fault was caught: persistence out of 20, models out of 60 (3 seeds × 20).",
     "color": INK2},
    {"text": "Sensor noise at 0.1: persistence 0/20, LSTM 54/60, GRU 60/60.", "bullet": True},
    {"text": "Persistence needs severity 0.2 to catch most brownouts (17/20).", "bullet": True},
    {"text": "Eclipse stress at 0.1: a small edge (LSTM 13/60, GRU 12/60, persistence 0/20).", "bullet": True},
], space_after=10, name="s2 side")
text_box(s, M, 6.25, W - 2 * M, 0.7, [
    {"runs": [("Real NASA data, held-out channels. ", True, INK),
              ("SMAP, 49 events: persistence 30; LSTM 31, 34, 28; GRU 30, 32, 35 (per seed), within seed spread. "
               "MSL, 25 events: persistence 4; LSTM 7, 6, 6; GRU 7, 6, 6.", False, INK)]},
], name="s2 nasa")
text_box(s, M, 6.95, W - 2 * M, 0.45, [{"text": TWIN_NOTE, "color": INK2}], name="s2 note")
s.notes_slide.notes_text_frame.text = (
    "This is the main result, on two orbits the models never trained on. Each cell counts the missions where the "
    "fault was caught: out of 20 for persistence, out of 60 for the models over three seeds. Look at brownout at "
    "severity 0.1: persistence catches none, the LSTM 59 of 60, the GRU all 60. Sensor noise is the same story: "
    "0, 54 and 60. Persistence needs severity 0.2 to catch most brownouts. So on sudden simulated faults, learning "
    "a forecast clearly pays off. On real NASA data the picture is far more modest. On SMAP the models land between "
    "28 and 35 of 49 events, against 30 for persistence, which is within the spread between seeds. On MSL every "
    "model run beats persistence, but only by two or three of 25 events. The models forecast better, but that "
    "doesn't reliably turn into catching more real faults."
)

# ------------------------------------------------------------------ Slide 3
s = prs.slides.add_slide(LAYOUT)
title(s, "A shared blind spot, and what it means", size=30)
colw = (W - 2 * M - 0.4) / 2
heading(s, M, 1.15, colw, "Blind spot (held-out orbits)")
text_box(s, M, 1.6, colw, 3.14, [
    {"text": "Frozen solar sensor: persistence 0/20, LSTM 6/60*, GRU 20/60, all at eclipse crossings. "
             "In steady sun the forecast error drops, so nothing fires.", "bullet": True},
    {"text": "Slow drift at severity 1.0: persistence 0/20, LSTM 12/60, GRU 4/60.", "bullet": True},
    {"text": "Also alarming on unusually low error (two-sided): 0 catches attributable to the low side; "
             "cost SMAP 1–9 events per run.", "bullet": True},
], space_after=10, name="s3 L")
rx = M + colw + 0.4
heading(s, rx, 1.15, colw, "Alarm lines don't transfer predictably")
text_box(s, rx, 1.62, colw, 3.05, [
    "False alarms per 10k steps on clean missions, dev orbits → held-out orbits (budget 2):",
    {"text": "Persistence 2.23 → 4.46", "bullet": True},
    {"text": "LSTM 2.83 → 4.76", "bullet": True},
    {"text": "GRU 3.57 → 2.83", "bullet": True},
    "Persistence and LSTM got noisier on new orbits; GRU got quieter.",
], space_after=8, name="s3 R")

band = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(M), Inches(4.75), Inches(W - 2 * M), Inches(1.65))
band.fill.background()
band.line.color.rgb = ACCENT
band.line.width = Pt(2)
text_box(s, M + 0.1, 4.8, W - 2 * M - 0.2, 1.55, [
    {"text": "OrbitVal: before a satellite's fault detection flies, it tells the team which faults the detector "
             "misses and how late it catches the rest.", "bold": True, "color": ACCENT, "size": 22},
    {"text": "This is the first version of that validation feature in OrbitVal, an open-source (MIT) CubeSat "
             "stress-testing tool.", "size": 18},
], space_after=6, name="s3 orbitval")
text_box(s, M, 6.5, W - 2 * M, 0.95, [
    {"text": TWIN_NOTE, "color": INK2, "space_after": 2},
    {"text": "Code and slides drafted with Claude Code under a staged plan I reviewed; details in the repo log.",
     "color": INK2},
], name="s3 foot")
s.notes_slide.notes_text_frame.text = (
    "Some faults no detector here can see. A frozen solar sensor is caught only when the freeze crosses an eclipse. "
    "In steady sun a frozen reading is easy to predict, so the error drops and nothing fires: to this score, a "
    "frozen sensor looks like an eclipse. Slow drift is mostly missed too, 12 of 60 for the LSTM and 4 for the GRU "
    "at full severity. I also tried alarming on unusually low error. It caught nothing attributable to the low side "
    "and cost SMAP up to nine events per run, so it stays a measured negative result. Second, alarm lines don't "
    "transfer predictably: set on familiar orbits, false alarms rose for persistence and the LSTM on new orbits, and "
    "fell for the GRU. That is why this matters for OrbitVal: before a satellite's fault detection flies, the team "
    "can see which faults it misses and how late it catches the rest."
)

prs.save(OUT)
bad = [(n, u, h) for n, u, h in fit_report if u > h]
for n, u, h in bad:
    print(f"OVERFLOW {u:.2f}in > {h:.2f}in: {n}")
print(f"saved {OUT}, {len(prs.slides)} slides, {len(fit_report)} boxes checked, {len(bad)} overflow")
