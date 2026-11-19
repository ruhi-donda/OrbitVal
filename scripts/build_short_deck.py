#!/usr/bin/env python3
"""
Build results/slides/14_Ruhi_Donda.pptx: the 3-slide, 3-minute version of
the CS462 deck (no demo), in a spacious card layout.

Content is condensed from docs/slide-outline.md. Every number comes from
docs/ml-project-log.md, the README results section, or the held-out JSON
files in results/heldout/heldout/. Each slide's speaker notes hold a
~60-second script, then the details cut from the slide.

Figures come from scripts/make_short_deck_figures.py (run it first). Body
text is at least 18 pt and stat numbers at least 40 pt.

Fonts: Poppins SemiBold for titles and stat numbers, Inter for everything
else (both are Google Fonts, available in Google Slides). To warn about text
that won't fit its box, the script measures with the real font files, from
the folder given as FONT_DIR: Poppins-SemiBold.ttf and Inter-Variable.ttf
(Inter[opsz,wght].ttf), both from github.com/google/fonts (OFL). Without
FONT_DIR the deck is still built, but the fit check is skipped.

Needs python-pptx, not part of the project's extras:
    pip install python-pptx==1.0.2
Usage: python scripts/build_short_deck.py [FONT_DIR]
"""

import sys
from pathlib import Path

from PIL import Image, ImageFont
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "results" / "slides"
OUT = FIG / "14_Ruhi_Donda.pptx"

BG = RGBColor(0xF5, 0xF3, 0xEF)        # light warm gray
CARD = RGBColor(0xFF, 0xFF, 0xFF)
EDGE = RGBColor(0xE2, 0xDE, 0xD6)
INK = RGBColor(0x1F, 0x1E, 0x1C)
INK2 = RGBColor(0x5F, 0x5D, 0x58)
ACCENT = RGBColor(0x2A, 0x78, 0xD6)    # the one accent
DISPLAY_FONT = "Poppins SemiBold"     # titles and stat numbers
BODY_FONT = "Inter"
FONT_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else None
W, H = 13.333, 7.5
M = 0.6
MIN_BODY, MIN_STAT = 18, 40

_fonts = {}
fit_report = []


def font(size, bold=False, display=False):
    key = (size, bold, display)
    if key not in _fonts:
        if display:
            f = ImageFont.truetype(str(FONT_DIR / "Poppins-SemiBold.ttf"), size * 10)
        else:
            f = ImageFont.truetype(str(FONT_DIR / "Inter-Variable.ttf"), size * 10)
            f.set_variation_by_axes([14, 700 if bold else 400])   # opsz 14 is the widest spacing
        _fonts[key] = f
    return _fonts[key]


def lines_needed(text, size, bold, width_in, display=False):
    if FONT_DIR is None:
        return 0
    f, max_w, n = font(size, bold, display), width_in * 720, 0
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


def style_run(run, size, bold=False, color=INK, display=False):
    assert size >= MIN_BODY, size
    run.font.name = DISPLAY_FONT if display else BODY_FONT
    run.font.size = Pt(size)
    run.font.bold = False if display else bold
    run.font.color.rgb = color


def text(slide, x, y, w, h, paras, size=18, bold=False, color=INK, align=PP_ALIGN.LEFT,
         anchor=MSO_ANCHOR.TOP, space_after=4, name=None, display=False):
    """paras: list of str or dict(text, size, bold, color)."""
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Inches(0.05)
    tf.margin_top = tf.margin_bottom = Inches(0.03)
    used = 0.06
    for i, p_ in enumerate(paras):
        p_ = {"text": p_} if isinstance(p_, str) else p_
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(space_after)
        pPr = p._p.get_or_add_pPr()
        pPr.append(pPr.makeelement(qn("a:buNone"), {}))
        r = p.add_run()
        r.text = p_["text"]
        s, b = p_.get("size", size), p_.get("bold", bold)
        style_run(r, s, b, p_.get("color", color), display)
        used += lines_needed(p_["text"], s, b, w - 0.1, display) * s * 1.2 / 72 + space_after / 72
    fit_report.append((name or paras[0] if isinstance(paras[0], str) else paras[0]["text"], used - space_after / 72, h))
    return tb


def card(slide, x, y, w, h, fill=CARD, edge=EDGE, width=1.0):
    c = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    c.adjustments[0] = 0.08
    c.fill.solid()
    c.fill.fore_color.rgb = fill
    c.line.color.rgb = edge
    c.line.width = Pt(width)
    c.shadow.inherit = False
    return c


def stat_card(slide, x, y, w, h, number, label, size=44, color=ACCENT):
    assert size >= MIN_STAT
    card(slide, x, y, w, h)
    nh = size * 1.2 / 72 + 0.1
    text(slide, x + 0.15, y + 0.08, w - 0.3, nh, [number], size=size, color=color, name="stat " + number,
         display=True)
    text(slide, x + 0.15, y + 0.08 + nh, w - 0.3, h - 0.14 - nh, [label],
         color=INK2, name="label " + label)


def new_slide(title, sub=None, size=30):
    s = prs.slides.add_slide(prs.slide_layouts[5])        # Title Only
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = BG
    t = s.shapes.title
    t.left, t.top, t.width, t.height = Inches(M), Inches(0.35), Inches(W - M - 0.3), Inches(0.75)
    tf = t.text_frame
    tf.margin_left = tf.margin_right = Inches(0.05)
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    tf.text = title
    tf.paragraphs[0].alignment = PP_ALIGN.LEFT
    style_run(tf.paragraphs[0].runs[0], size, display=True)
    fit_report.append(("TITLE " + title, lines_needed(title, size, False, W - M - 0.4, True) * size * 1.2 / 72, 0.75))
    if sub:
        text(s, M, 1.1, W - 2 * M, 0.42, [sub], color=INK2, name="sub")
    return s


def picture(slide, path, x, y, w):
    img = Image.open(path)
    h = w * img.height / img.width
    slide.shapes.add_picture(str(path), Inches(x), Inches(y), Inches(w), Inches(h))
    return h


def notes(slide, script, details):
    slide.notes_slide.notes_text_frame.text = script + "\n\nCut from the slide:\n" + "\n".join("- " + d for d in details)


prs = Presentation()
prs.slide_width, prs.slide_height = Inches(W), Inches(H)
TWIN_NOTE = "*LSTM: 1 of these catches also fires on the fault-free twin mission."

# ------------------------------------------------------------------ Slide 1
s = new_slide("Can a detector catch spacecraft faults before they matter?",
              "Validating spacecraft fault detection with OrbitVal · Ruhi Donda · CS462 · Nov 20, 2026",
              size=28)                     # 30 pt Poppins runs 12.5 in, wider than the slide allows
text(s, M, 1.5, W - 2 * M, 0.72,
     ["Satellites need early fault alarms, but faults are rare and every false alarm teaches operators to "
      "ignore the system."], name="motivation")
LW = 8.3                                     # left column width
gap = 0.2
cw = (LW - 2 * gap) / 3
for i, (num, label) in enumerate((("2", "real NASA missions"),
                                  ("5", "simulated fault types"),
                                  ("2", "orbits never seen in training"))):
    stat_card(s, M + i * (cw + gap), 2.3, cw, 1.66, num, label)

# solar power visual, right column
rx, rw = M + LW + 0.3, W - M - (M + LW + 0.3)
card(s, rx, 2.3, rw, 3.25)
ph = picture(s, FIG / "short_solar.png", rx + 0.12, 2.4, rw - 0.24)
text(s, rx + 0.12, 2.4 + ph + 0.05, rw - 0.24, 3.25 - ph - 0.2,
     ["Simulated solar power drops to 0 W on every pass through Earth's shadow (grey)."],
     color=INK2, name="solar caption")

# flow: 4 boxes
steps = ["Past readings", "Forecaster", "Surprise score", "Alarm"]
agap = 0.4
widths = [2.07, 1.72, 2.18, 1.13]           # each label's Inter Bold width plus 0.4 in padding
assert abs(sum(widths) + 3 * agap - LW) < 0.01
y, hb = 4.12, 0.75
x = M - agap
for i, (label, bw) in enumerate(zip(steps, widths)):
    x += (widths[i - 1] if i else 0) + agap
    on = label == "Forecaster"
    card(s, x, y, bw, hb, fill=ACCENT if on else CARD, edge=ACCENT, width=1.5)
    text(s, x, y, bw, hb, [label], bold=True, color=CARD if on else INK, align=PP_ALIGN.CENTER,
         anchor=MSO_ANCHOR.MIDDLE, name="flow " + label)
    if i < 3:
        a = s.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, Inches(x + bw + 0.08), Inches(y + hb / 2 - 0.12),
                               Inches(agap - 0.16), Inches(0.24))
        a.fill.solid()
        a.fill.fore_color.rgb = INK2
        a.line.fill.background()
text(s, M, 4.92, LW, 0.68,
     ["Only the forecaster differs; the scoring is shared. Alarm line set on clean data: "
      "at most 2 false alarms per 10,000 steps."], color=INK2, name="flow caption")
text(s, M, 5.62, W - 2 * M, 0.40,
     ["Interactive demo: inject a fault, set its severity, and watch each detector respond."],
     name="demo")

# detectors
dw = (W - 2 * M - 2 * gap) / 3
for i, (name, desc) in enumerate((("Persistence", "next = current; no learning"),
                                  ("LSTM", "trained recurrent network"),
                                  ("GRU", "trained recurrent network"))):
    x = M + i * (dw + gap)
    card(s, x, 6.04, dw, 0.86, edge=ACCENT if i else EDGE, width=1.5 if i else 1.0)
    text(s, x + 0.15, 6.07, dw - 0.3, 0.80,
         [{"text": name, "bold": True, "size": 22}, {"text": desc, "color": INK2}],
         space_after=0, name="det " + name)
text(s, M, 6.96, W - 2 * M, 0.42,
     ["LSTM/GRU gating · backprop through time · gradient clipping · Adam · early stopping · 3 seeds"],
     color=INK2, name="techniques")
notes(s,
      "Satellites need early fault alarms, but faults are rare and every false alarm teaches operators to ignore "
      "the system. So which faults can a deep learning detector actually catch? I test on real data from two NASA "
      "missions, SMAP and MSL, and on simulated OrbitVal missions with five fault types, flown on two orbits the "
      "models never saw in training. Every detector forecasts the next reading; when the error is unusually large, "
      "the surprise score crosses a line and raises an alarm. The scoring is shared, so the only difference is the "
      "forecaster: persistence, which repeats the last value, against a small LSTM and GRU trained on normal data "
      "only, with backpropagation through time, Adam, gradient clipping and early stopping, three seeds each.",
      ["Also used in training: MSE loss (= Gaussian likelihood); trained on normal data only.",
       "LSTM and GRU: one layer, hidden size 32, 64-step window; 4,513 and 3,393 parameters.",
       "Surprise score: absolute forecast error, smoothed, then a rolling z-score over the recent past.",
       "NASA SMAP/MSL: real spacecraft telemetry with expert-labeled anomalies. Results were viewed only on 30% "
       "of channels (dev) while building; final numbers come from the other 70%, held out (SMAP 37 channels, "
       "MSL 19). Alarm lines were set from normal data only.",
       "OrbitVal: real orbit propagation drives sun and shadow, which drive solar power, battery and "
       "temperature; the magnetometer follows the ground track. 4 of the 5 fault types have a 0-1 severity "
       "knob; stuck sensor has none."])

# ------------------------------------------------------------------ Slide 2
s = new_slide("Result: trained models catch much smaller sudden faults",
              "Brownout at severity 0.1, held-out orbits: missions where the fault was caught")
sw = (W - 2 * M - 2 * gap) / 3
for i, (num, label, col) in enumerate((("0/20", "persistence (no learning)", INK),
                                       ("59/60*", "LSTM, 3 seeds × 20 missions", ACCENT),
                                       ("60/60", "GRU, 3 seeds × 20 missions", ACCENT))):
    stat_card(s, M + i * (sw + gap), 1.65, sw, 1.45, num, label, size=48, color=col)
fw = 11.2
fh = picture(s, FIG / "short_brownout_stuck.png", (W - fw) / 2, 3.3, fw)
assert 3.3 + fh <= 6.45, fh
text(s, M, 6.5, W - 2 * M, 0.45,
     ["Real NASA data: gains within seed noise on SMAP, +2–3 events on MSL."], size=20, bold=True,
     name="nasa")
text(s, M, 6.98, W - 2 * M, 0.42, [TWIN_NOTE], color=INK2, name="s2 note")
notes(s,
      "This is the main result, on two orbits the models never trained on. At brownout severity 0.1, persistence "
      "catches none of 20 missions, the LSTM 59 of 60 over three seeds, the GRU all 60. Persistence needs severity "
      "0.2 to catch most brownouts. So on sudden simulated faults, learning a forecast clearly pays off. The bottom "
      "row is a frozen sensor, where every detector does badly; that's the next slide. On real NASA data the gain "
      "is modest. On SMAP the models land between 28 and 35 of 49 events, against 30 for persistence, within the "
      "spread between seeds. On MSL every model run beats persistence, but only by two or three of 25 events.",
      ["Sensor noise at 0.1: persistence 0/20, LSTM 54/60, GRU 60/60.",
       "Persistence needs severity 0.2 to catch most brownouts (17/20).",
       "Eclipse stress at 0.1: a small edge (LSTM 13/60, GRU 12/60, persistence 0/20); at 0.2 the models "
       "catch 60/60, persistence 0/20.",
       "SMAP, 49 held-out events: persistence 30; LSTM 31, 34, 28; GRU 30, 32, 35 (per seed). "
       "MSL, 25 held-out events: persistence 4; LSTM 7, 6, 6; GRU 7, 6, 6.",
       "The models forecast better, but that doesn't reliably turn into catching more real faults.",
       "The sensor-noise, eclipse-stress and drift rows are in the full heatmap, heldout_detectability.png."])

# ------------------------------------------------------------------ Slide 3
s = new_slide("In steady sun, a frozen sensor fools every detector")
text(s, M, 1.0, W - 2 * M, 0.9, ["0/20 · 6/60* · 20/60"], size=48, color=ACCENT, name="big stat",
     display=True)
text(s, M, 1.86, W - 2 * M, 0.40,
     ["Persistence · LSTM · GRU, held-out orbits: frozen sensor, caught only at eclipse crossings"],
     color=INK2, name="big label")
text(s, M, 2.26, W - 2 * M, 0.76,
     ["Why: a frozen reading is easy to predict, so the forecast error drops and nothing fires. "
      "To this score, a frozen sensor looks like an eclipse."], size=20, name="why")
cws = [3.55, 4.35, 3.83]                     # sized so each body wraps to at most 2 lines
assert abs(sum(cws) + 2 * gap - (W - 2 * M)) < 0.01
x = M
for (head, body), cw3 in zip((("Slow drift, severity 1.0", "persistence 0/20, LSTM 12/60, GRU 4/60 caught"),
                              ("Two-sided alarms", "No attributable low-side catch; SMAP loses 1–9 events per run"),
                              ("Alarm lines on new orbits", "Persistence and LSTM noisier, GRU quieter")), cws):
    card(s, x, 3.06, cw3, 1.10)
    text(s, x + 0.15, 3.09, cw3 - 0.3, 1.04,
         [{"text": head, "bold": True}, {"text": body, "color": INK2}], space_after=2, name="small " + head)
    x += cw3 + gap
text(s, M, 4.22, W - 2 * M, 0.40,
     ["The blind spot is in the scoring, not the model: better training can't fix it."], bold=True,
     name="takeaway")
card(s, M, 4.64, W - 2 * M, 1.72, fill=CARD, edge=ACCENT, width=2.0)
text(s, M + 0.2, 4.66, W - 2 * M - 0.4, 1.68,
     [{"text": "OrbitVal: before a satellite's fault detection flies, it tells the team which faults the "
               "detector misses and how late it catches the rest.", "bold": True, "color": ACCENT, "size": 20},
      {"text": "For small-satellite teams who need to know what their onboard fault detection misses before "
               "launch. This project is the first version of that feature in OrbitVal, an open-source (MIT) "
               "CubeSat stress-testing tool."}], space_after=2, name="orbitval")
REPO_URL = "https://github.com/ruhi-donda/OrbitVal/tree/v1.2.2-cs462"
foot = text(s, M, 6.42, W - 2 * M, 0.98,
            [TWIN_NOTE, "Code and slides drafted with Claude Code under a staged plan I reviewed; details in the repo log.",
             REPO_URL], color=INK2, space_after=0, name="s3 foot")
foot.text_frame.paragraphs[2].runs[0].hyperlink.address = REPO_URL
notes(s,
      "In steady sun, no detector catches a frozen sensor. A frozen reading is easy to predict, so the "
      "forecast error drops and nothing fires: to this score, a frozen sensor looks like an eclipse. Catches happen "
      "only when the freeze crosses an eclipse. Slow drift is mostly missed too. Alarming on unusually low error "
      "caught nothing attributable to the low side and cost SMAP up to nine events per run. And alarm lines don't "
      "transfer predictably: on new orbits, persistence and the LSTM got noisier, the GRU quieter. The blind spot "
      "is in the scoring, not the model, so better training can't fix it. This matters for OrbitVal: "
      "before a satellite's fault detection flies, the team sees which faults it misses and how late it catches "
      "the rest.",
      ["Slow drift numbers are persistence · LSTM · GRU.",
       "False alarms per 10k on clean missions, dev orbits → held-out orbits: persistence 2.23 → 4.46, "
       "LSTM 2.83 → 4.76, GRU 3.57 → 2.83 (budget 2).",
       "Two-sided: also alarm on unusually low error, with the false-alarm budget split between the sides."])

prs.save(OUT)
bad = [(n, u, h) for n, u, h in fit_report if u > h]
for n, u, h in bad:
    print(f"OVERFLOW {u:.2f}in > {h:.2f}in: {n}")
print(f"saved {OUT}, {len(prs.slides)} slides, {len(fit_report)} boxes checked, {len(bad)} overflow")
