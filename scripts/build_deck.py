#!/usr/bin/env python3
"""
Build results/slides/cs462_deck.pptx from docs/slide-outline.md.

The slide text is typed in below and follows the outline; every number is
traced in the outline's sources (log, README results, held-out JSON). Uses
the figures in results/slides/, including clean_solar_power.png
(scripts/make_solar_figure.py) and demo_brownout_light.png
(scripts/screenshot_demo.py). Fonts are measured with macOS Arial to warn
about text that won't fit its box.

Needs python-pptx, not part of the project's extras:
    pip install python-pptx==1.0.2
Usage: python scripts/build_deck.py
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
OUT = FIG / "cs462_deck.pptx"

INK = RGBColor(0x0B, 0x0B, 0x0B)
INK2 = RGBColor(0x52, 0x51, 0x4E)
ACCENT = RGBColor(0x2A, 0x78, 0xD6)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
FONT = "Arial"
W, H = 13.333, 7.5
M = 0.6                       # side margin
BODY_TOP = 1.75
MIN_PT = 20

_font_cache = {}
fit_report = []


def font(size, bold=False):
    key = (size, bold)
    if key not in _font_cache:
        path = "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf"
        _font_cache[key] = ImageFont.truetype(path, size * 10)   # 10x for precision
    return _font_cache[key]


def lines_needed(text, size, bold, width_in):
    """Greedy word wrap with real Arial metrics; returns line count."""
    f = font(size, bold)
    max_w = width_in * 72 * 10          # points x10
    n, cur = 0, ""
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


prs = Presentation()
prs.slide_width, prs.slide_height = Inches(W), Inches(H)
TITLE_ONLY = prs.slide_layouts[5]
TITLE = prs.slide_layouts[0]


def style_run(run, size, bold=False, color=INK):
    assert size >= MIN_PT, size
    run.font.name = FONT
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color


def set_bullet(p, level_indent=0.3, char="•"):
    pPr = p._p.get_or_add_pPr()
    pPr.set("marL", str(Emu(Inches(level_indent))))
    pPr.set("indent", str(-Emu(Inches(level_indent))))
    for tag in ("a:buNone", "a:buChar", "a:buAutoNum"):
        for el in pPr.findall(qn(tag)):
            pPr.remove(el)
    bu = pPr.makeelement(qn("a:buChar"), {"char": char})
    pPr.append(bu)


def no_bullet(p):
    pPr = p._p.get_or_add_pPr()
    pPr.append(pPr.makeelement(qn("a:buNone"), {}))


def text_box(slide, x, y, w, h, items, size=22, space_after=10, anchor=MSO_ANCHOR.TOP,
             align=PP_ALIGN.LEFT, name=""):
    """items: list of str or dict(text, bullet, bold, color, size)."""
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    inset = 0.1
    tf.margin_left = tf.margin_right = Inches(inset)
    tf.margin_top = tf.margin_bottom = Inches(0.05)
    used = 0.1
    for i, it in enumerate(items):
        if isinstance(it, str):
            it = {"text": it}
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        s = it.get("size", size)
        bullet = it.get("bullet", False)
        if bullet:
            set_bullet(p, char=it.get("char", "•"))
        else:
            no_bullet(p)
        p.alignment = align
        p.space_after = Pt(it.get("space_after", space_after))
        r = p.add_run()
        r.text = it["text"]
        style_run(r, s, it.get("bold", False), it.get("color", INK))
        width = w - 2 * inset - (0.3 if bullet else 0)
        used += lines_needed(it["text"], s, it.get("bold", False), width) * s * 1.2 / 72
        used += it.get("space_after", space_after) / 72
    used -= it.get("space_after", space_after) / 72      # last paragraph's spacing is free
    fit_report.append((name or items[0] if isinstance(items[0], str) else items[0]["text"], used, h))
    return tb


def title(slide, text, size=32):
    t = slide.shapes.title
    t.left, t.top, t.width, t.height = Inches(M), Inches(0.35), Inches(W - 2 * M), Inches(1.2)
    tf = t.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    tf.text = text
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.LEFT
    for r in p.runs:
        style_run(r, size, bold=True)
    fit_report.append(("TITLE " + text, lines_needed(text, size, True, W - 2 * M - 0.2) * size * 1.2 / 72 + 0.1, 1.2))
    # accent bar under the title
    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(M + 0.1), Inches(1.55), Inches(1.2), Inches(0.07))
    bar.fill.solid()
    bar.fill.fore_color.rgb = ACCENT
    bar.line.fill.background()


def notes(slide, text):
    slide.notes_slide.notes_text_frame.text = text


def new_slide(t, say=None, tsize=32):
    s = prs.slides.add_slide(TITLE_ONLY)
    title(s, t, tsize)
    if say:
        notes(s, say)
    return s


def picture(slide, path, x, y, w):
    img = Image.open(path)
    h = w * img.height / img.width
    slide.shapes.add_picture(str(path), Inches(x), Inches(y), Inches(w), Inches(h))
    return h


def B(text, **kw):
    return {"text": text, "bullet": True, **kw}


def tag(slide, text):
    text_box(slide, W - M - 3.2, 0.1, 3.2, 0.5, [{"text": text, "color": INK2, "size": 20}],
             align=PP_ALIGN.RIGHT, name="tag " + text)


# ---------------------------------------------------------------- 1. Title
s = prs.slides.add_slide(TITLE)
t = s.shapes.title
t.left, t.top, t.width, t.height = Inches(M), Inches(1.9), Inches(W - 2 * M), Inches(1.4)
t.text_frame.text = "Can a detector catch this fault?"
t.text_frame.paragraphs[0].alignment = PP_ALIGN.LEFT
for r in t.text_frame.paragraphs[0].runs:
    style_run(r, 48, bold=True)
sub = s.placeholders[1]
sub.left, sub.top, sub.width, sub.height = Inches(M), Inches(3.5), Inches(W - 2 * M), Inches(2.0)
tf = sub.text_frame
tf.text = "Validating spacecraft fault detection with OrbitVal"
tf.add_paragraph().text = "Ruhi Donda · CS462 · Nov 20, 2026"
for p, (sz, col) in zip(tf.paragraphs, [(30, ACCENT), (24, INK2)]):
    p.alignment = PP_ALIGN.LEFT
    p.space_after = Pt(14)
    for r in p.runs:
        style_run(r, sz, color=col)
bar = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(M + 0.1), Inches(3.35), Inches(1.2), Inches(0.07))
bar.fill.solid(); bar.fill.fore_color.rgb = ACCENT; bar.line.fill.background()
notes(s, "I built a way to measure which spacecraft faults a deep learning detector catches, how fast, and which ones it can't see at all.")

# ---------------------------------------------------------------- 2. Problem
s = new_slide("The problem",
              "A satellite streams sensor readings all day. When something breaks, you want to know fast, "
              "but every false alarm teaches operators to ignore the system.")
picture(s, FIG / "clean_solar_power.png", M, BODY_TOP, 7.6)
text_box(s, 8.5, BODY_TOP + 0.3, W - M - 8.5, 4.5, [
    B("Faults are rare"),
    B("Most are unlabeled"),
    B("Operators need early alarms without constant false ones"),
], size=26, space_after=18)

# ---------------------------------------------------------------- 3. Approach
s = new_slide("Approach: forecast, then flag",
              "Each model predicts the next reading. If the error is unusually large compared with the recent past, "
              "that's an alarm. All detectors share the same scoring, so the only difference between them is the forecast.")
steps = ["Past window", "Forecaster", "Error", "Smoothing + rolling z-score", "Alarm line", "Alarm"]
widths = [1.6, 1.6, 1.4, 2.45, 1.6, 1.4]
gap = 0.36
x = (W - sum(widths) - gap * 5) / 2
y, hbox = 2.6, 1.6
for i, (label, bw) in enumerate(zip(steps, widths)):
    box = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(bw), Inches(hbox))
    box.line.color.rgb = ACCENT
    box.line.width = Pt(2)
    box.fill.solid()
    box.fill.fore_color.rgb = ACCENT if label == "Forecaster" else WHITE
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Inches(0.08)
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    tf.text = label
    tf.paragraphs[0].alignment = PP_ALIGN.CENTER
    style_run(tf.paragraphs[0].runs[0], 20, bold=True, color=WHITE if label == "Forecaster" else INK)
    fit_report.append(("box " + label, lines_needed(label, 20, True, bw - 0.16) * 20 * 1.2 / 72, hbox))
    for word in label.split():
        assert font(20, True).getlength(word) <= (bw - 0.16) * 720, f"word too wide: {word}"
    x += bw
    if i < len(steps) - 1:
        arr = s.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, Inches(x + 0.05), Inches(y + hbox / 2 - 0.15),
                                 Inches(gap - 0.1), Inches(0.3))
        arr.fill.solid(); arr.fill.fore_color.rgb = INK2; arr.line.fill.background()
        x += gap
text_box(s, M, 4.65, W - 2 * M, 2.4, [
    "Every detector only produces a forecast. The scoring after it is shared, "
    "so the only difference between detectors is the forecaster.",
    "An alarm fires when the forecast error is unusually large compared with the recent past.",
], size=24, space_after=14)

# ---------------------------------------------------------------- 4. Models
s = new_slide("Models and deep learning techniques",
              "Persistence is the baseline that matters. If a trained model can't beat 'nothing changes', "
              "it hasn't learned anything.")
cols = [("Persistence", "next = current; no learning"),
        ("LSTM", "recurrent network with forget, input and output gates"),
        ("GRU", "recurrent network with reset and update gates")]
cw = (W - 2 * M - 0.4) / 3
for i, (name, desc) in enumerate(cols):
    cx = M + i * (cw + 0.2)
    box = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(cx), Inches(BODY_TOP), Inches(cw), Inches(1.45))
    box.fill.background()
    box.line.color.rgb = ACCENT if i else INK2
    box.line.width = Pt(2)
    text_box(s, cx + 0.05, BODY_TOP + 0.05, cw - 0.1, 1.35,
             [{"text": name, "bold": True, "size": 26, "space_after": 4}, {"text": desc, "size": 20}],
             name="col " + name)
text_box(s, M, 3.35, W - 2 * M, 0.95, [
    "Shapes: each channel is windowed separately and stacked along the batch axis: "
    "input (batch, L, 1) → hidden (batch, H) → prediction (batch, 1)",
], size=20)
text_box(s, M, 4.25, W - 2 * M, 0.6, [{"text": "Techniques", "bold": True, "size": 22}], name="tech head")
tech = ["Recurrent networks (LSTM, GRU)", "Gating", "Backpropagation through time",
        "Gradient clipping", "Adam optimizer", "MSE loss (= Gaussian likelihood)",
        "Early stopping", "3 random seeds", "Trained on normal data only"]
half = (W - 2 * M) / 2
text_box(s, M, 4.8, half, 2.5, [B(t_) for t_ in tech[:5]], size=20, space_after=2, name="tech L")
text_box(s, M + half, 4.8, half, 2.5, [B(t_) for t_ in tech[5:]], size=20, space_after=2, name="tech R")

# ---------------------------------------------------------------- 5. Data
s = new_slide("Data: real and synthetic",
              "Real data proves it works on real spacecraft. Synthetic data gives exact fault start times and "
              "controlled severity, which real labels can't.")
half = (W - 2 * M - 0.4) / 2
text_box(s, M, BODY_TOP, half, 5.4, [
    {"text": "NASA SMAP/MSL", "bold": True, "size": 26, "color": ACCENT},
    B("Real spacecraft telemetry with expert-labeled anomalies"),
    B("Results viewed only on 30% of channels (dev) while building"),
    B("Final numbers come from the other 70% (held out)"),
    B("Alarm lines set from normal data only"),
], size=22, space_after=10, name="data L")
text_box(s, M + half + 0.4, BODY_TOP, half, 5.4, [
    {"text": "OrbitVal (simulated)", "bold": True, "size": 26, "color": ACCENT},
    B("Real orbit propagation drives sun and shadow, which drive solar power, battery and temperature"),
    B("The magnetometer follows the ground track"),
    B("5 fault types; 4 have a 0–1 severity knob, stuck sensor has no severity"),
    B("Test missions fly 2 orbits never seen in training"),
], size=22, space_after=10, name="data R")

# ---------------------------------------------------------------- 6. Evaluation rules
s = new_slide("Evaluation rules")
text_box(s, M, BODY_TOP, W - 2 * M, 5.4, [
    B("Alarm line set on clean data, allowing at most 2 false alarms per 10,000 steps"),
    B("Metrics: event recall, false alarms per 10k, median detection delay, plus point F1 and PR-AUC"),
    B("No point-adjusted F1: it can make even random scores look strong (Kim et al., AAAI 2022)"),
    B("Held-out results come from one locked run, recorded with the commit and the hash of every "
      "checkpoint; the runner refuses to overwrite it"),
    B("Dev results rebuild exactly with scripts/reproduce.sh"),
], size=24, space_after=16)

# ---------------------------------------------------------------- 7. Demo
s = new_slide("Live demo",
              "Walk through the presets in order: brownout in sun, stuck in sun, stuck at eclipse edge, sensor drift.")
ph = picture(s, FIG / "demo_brownout_light.png", M, BODY_TOP, 8.7)
rx = M + 8.9
text_box(s, rx, BODY_TOP, W - M - rx, 5.4, [
    {"text": "Four scenes", "bold": True, "size": 24},
    B("1. Brownout in sun", char=" "),
    B("2. Stuck in sun", char=" "),
    B("3. Stuck at eclipse edge", char=" "),
    B("4. Sensor drift", char=" "),
    {"text": "The demo flies dev missions only; counts shown in it are dev.", "size": 20, "color": INK2},
], size=22, space_after=10, name="demo list")

# ---------------------------------------------------------------- 8. Result 1
s = new_slide("Result 1: trained models catch much smaller sudden faults",
              "On orbits the models never trained on, they catch brownouts and sensor noise at severity 0.1, where "
              "'nothing changes' catches none. Persistence needs severity 0.2 for most brownouts (17/20) and 0.5 "
              "for most sensor noise (19/20).", tsize=30)
tag(s, "Held-out orbits")
picture(s, FIG / "heldout_detectability.png", M, BODY_TOP, 7.6)
rx = M + 7.75
text_box(s, rx, BODY_TOP, W - M - rx, 5.5, [
    B("Brownout at 0.1: persistence 0/20, LSTM 59/60, GRU 60/60"),
    B("Sensor noise at 0.1: 0/20, 54/60, 60/60"),
    B("Brownout at 0.05: GRU 37/60, steadier across seeds (11, 15, 11) than LSTM 26/60 (13, 10, 3)"),
    B("Eclipse stress at 0.1: small edge (LSTM 13/60, GRU 12/60, persistence 0/20). At 0.2: models 60/60, persistence 0/20"),
], size=20, space_after=10, name="r1")

# ---------------------------------------------------------------- 9. Result 2
s = new_slide("Result 2: on real NASA data, the gain is small",
              "The trained models forecast better but don't reliably detect more on SMAP. "
              "On MSL the gain is consistent but small.")
tag(s, "Held-out channels")
picture(s, FIG / "heldout_recall.png", M, BODY_TOP, 7.6)
text_box(s, rx, BODY_TOP, W - M - rx, 5.5, [
    B("SMAP, 49 held-out events: persistence 30; LSTM 31, 34, 28; GRU 30, 32, 35 (per seed). Within seed-to-seed spread"),
    B("MSL, 25 held-out events: persistence 4; LSTM 7, 6, 6; GRU 7, 6, 6. Every model run beats persistence, by 2–3 events"),
    B("MSL false alarms over budget in 2 of 7 runs"),
], size=20, space_after=12, name="r2")

# ---------------------------------------------------------------- 10. Result 3
s = new_slide("Result 3: the shared blind spot",
              "To this score, a frozen solar sensor looks like an eclipse. This is a scoring problem, "
              "not a model problem: better training can't fix it.")
tag(s, "Held-out data")
text_box(s, M, BODY_TOP, W - 2 * M, 5.4, [
    B("Frozen sensor: caught only at eclipse crossings (persistence 0/20, LSTM 6/60, GRU 20/60). "
      "In steady sun the error drops, so nothing fires"),
    B("Slow drift at severity 1.0: persistence 0/20, LSTM 12/60, GRU 4/60"),
    B("Two-sided alarms (also alarm on unusually low error): 0 catches attributable to the low side; "
      "cost SMAP 1–9 events per run"),
], size=26, space_after=22)

# ---------------------------------------------------------------- 11. Result 4
s = new_slide("Result 4: alarm lines don't transfer predictably to new orbits",
              "The same alarm line behaves differently on orbits it wasn't set on. Persistence and LSTM got noisier; "
              "GRU got quieter. A budget set on one set of orbits isn't guaranteed on another.", tsize=30)
tag(s, "Dev vs held-out")
picture(s, FIG / "false_alarms_dev_vs_heldout.png", M, BODY_TOP, 7.6)
text_box(s, rx, BODY_TOP, W - M - rx, 5.5, [
    {"text": "False alarms per 10k steps, clean missions, dev orbits → held-out orbits:", "size": 20},
    B("Persistence 2.23 → 4.46"),
    B("LSTM 2.83 → 4.76"),
    B("GRU 3.57 → 2.83"),
    {"text": "Persistence and LSTM got noisier; GRU got quieter.", "size": 20},
], size=22, space_after=10, name="r4")

# ---------------------------------------------------------------- 12. Limitations
s = new_slide("Limitations")
text_box(s, M, BODY_TOP, W - 2 * M, 5.5, [
    B("OrbitVal data is synthetic; models may partly learn the simulator"),
    B("SMAP/MSL uses one shared model on the telemetry value only, simplified from the original paper "
      "(telemanom) for compute, so not directly comparable"),
    B("Small event counts: 49 SMAP and 25 MSL held-out events"),
    B("Alarm lines set on clean data don't fully transfer: false alarms exceed the budget on new orbits "
      "and faulted missions"),
    B("Demo scenes are chosen by written rules on seed 0, not randomly"),
], size=22, space_after=12)

# ---------------------------------------------------------------- 13. What I learned
s = new_slide("What I learned")
text_box(s, M, BODY_TOP, W - 2 * M, 5.5, [
    B("1. Better forecasting isn't better detection (dev). Longer training (30 → 80 epochs) cut forecast "
      "error on MSL and one SMAP run, but recall moved no more than seed noise. On OrbitVal it changed nothing.", char=" "),
    B("2. Evaluation choices can matter more than the model. Point-adjusted scoring can make even random "
      "scores look strong (Kim et al., AAAI 2022; not measured here).", char=" "),
    B("3. Some blind spots are in the scoring, not the network.", char=" "),
    {"text": "Next: multi-step forecasting for drift; a flatline check for frozen sensors; a multichannel model.",
     "color": ACCENT, "bold": True},
], size=22, space_after=14)

# ---------------------------------------------------------------- 14. OrbitVal
s = new_slide("Why this matters: OrbitVal",
              "This project is the first version of a validation feature for OrbitVal, my open-source CubeSat "
              "stress-testing tool.")
text_box(s, M, BODY_TOP, W - 2 * M, 1.6, [
    {"text": "Before a satellite's fault detection flies, OrbitVal tells the team which faults it misses "
             "and how late it catches the rest.", "size": 28, "bold": True, "color": ACCENT},
], name="quote")
text_box(s, M, 3.45, W - 2 * M, 3.6, [
    {"text": "What it showed here:", "bold": True, "size": 22},
    B("The detectability map: which faults are caught, at which severity"),
    B("The blind spot it exposed: frozen sensors and slow drift"),
    B("Alarm lines that don't transfer to new orbits"),
    {"text": "Planned next: an evaluate-detector command and hashed detector reports.", "size": 22, "color": INK2},
], size=22, space_after=10, name="orbitval")

# ---------------------------------------------------------------- 15. AI use
s = new_slide("AI-use disclosure")
text_box(s, M, BODY_TOP, W - 2 * M, 5.5, [
    B("Claude Code wrote most of the code under a staged plan I approved stage by stage, and drafted this deck"),
    B("I reviewed each stage before the next started and made the design decisions, recorded in "
      "docs/ml-project-log.md"),
    B("What I did myself: [FILL IN, e.g. traced the windowing and LSTM tensor shapes by hand]"),
    B("Numbers in this deck were checked against the raw result files before presenting."),
], size=22, space_after=14)

# ---------------------------------------------------------------- Backup divider
s = prs.slides.add_slide(TITLE)
s.shapes.title.left, s.shapes.title.top = Inches(M), Inches(2.8)
s.shapes.title.width, s.shapes.title.height = Inches(W - 2 * M), Inches(1.4)
s.shapes.title.text_frame.text = "Backup"
s.shapes.title.text_frame.paragraphs[0].alignment = PP_ALIGN.LEFT
style_run(s.shapes.title.text_frame.paragraphs[0].runs[0], 48, bold=True)
s.placeholders[1]._element.getparent().remove(s.placeholders[1]._element)

# ---------------------------------------------------------------- B1-B9
s = new_slide("B1. Tensor shapes")
text_box(s, M, BODY_TOP, W - 2 * M, 5.5, [
    "Each channel of each series, shape (T,), is windowed on its own",
    {"text": "→ windows (N, L, 1), targets (N, 1), N = T − L", "bold": True},
    "Windows from every channel and series are concatenated along the batch axis",
    {"text": "→ batch (B, L, 1) → LSTM → last hidden (B, H) → linear → (B, 1)", "bold": True},
    "L = 64, H = 32. No window spans two channels or two missions.",
], size=24, space_after=16)

s = new_slide("B2. LSTM vs GRU gates, tanh, gradient clipping")
text_box(s, M, BODY_TOP, W - 2 * M, 5.5, [
    B("LSTM: two states (hidden h, cell c) and three gates: forget, input, output"),
    B("GRU: one state h and two gates: reset, update. 3 sets of gate weights against the LSTM's 4 "
      "(3,393 vs 4,513 parameters)"),
    B("Each gate is a sigmoid between 0 and 1 that decides how much to keep, write or pass on"),
    B("tanh inside the recurrence keeps the state between −1 and 1, so it can't grow without bound over "
      "the 64-step window"),
    B("Gradient clipping (norm 1.0) caps an update when gradients through time explode"),
], size=22, space_after=12)

s = new_slide("B3. Threshold calibration")
text_box(s, M, BODY_TOP, W - 2 * M, 5.5, [
    B("The alarm line is the lowest one that keeps clean-data false alarms at or under 2 per 10k steps"),
    B("…and stays at or under budget for every higher line too, because the count isn't strictly monotone"),
    B("A false alarm is an alarm run, not a step: consecutive alarm steps count once"),
    B("Only normal data is used. Thresholds that maximise F1 were rejected because they tune on the labels "
      "being measured"),
], size=22, space_after=14)

s = new_slide("B4. False alarms at grace period 10 vs 74 steps (dev)")
tag(s, "Dev data")
text_box(s, M, BODY_TOP, W - 2 * M, 0.9, [
    "OrbitVal faulted dev missions, false alarms per 10k steps (budget 2):"], size=22, name="b4 head")
rows = [("Detector", "Grace 74: mean, max", "Grace 10: mean, max"),
        ("Persistence", "2.49, 2.95", "2.34, 2.78"),
        ("LSTM", "2.99, 4.43", "3.00, 6.02"),
        ("GRU", "3.61, 4.43", "4.13, 9.72")]
tbl = s.shapes.add_table(len(rows), 3, Inches(M), Inches(2.7), Inches(W - 2 * M), Inches(0.6 * len(rows))).table
for i, row in enumerate(rows):
    for j, val in enumerate(row):
        cell = tbl.cell(i, j)
        cell.text = val
        cell.fill.solid()
        cell.fill.fore_color.rgb = ACCENT if i == 0 else WHITE
        style_run(cell.text_frame.paragraphs[0].runs[0], 22, bold=(i == 0), color=WHITE if i == 0 else INK)
text_box(s, M, 5.4, W - 2 * M, 1.5, [
    "A recovery alarm starting within the grace period after a fault ends is blamed on that fault. "
    "Grace never changes recall."], size=20, name="b4 foot")

s = new_slide("B5. 30 vs 80 epochs (dev)")
tag(s, "Dev data")
text_box(s, M, BODY_TOP, W - 2 * M, 5.5, [
    B("OrbitVal: nothing changed. Every run stopped before the old cap mattered; tensors, thresholds and "
      "the whole map are identical"),
    B("SMAP: 1 of 6 runs changed (GRU seed 2): lower validation error, recall 15/18 → 13/18"),
    B("MSL: 5 of 6 runs changed, validation error 3–6% lower"),
    B("Across the six changed runs, recall rose once, fell three times and held twice: within seed noise"),
], size=22, space_after=14)

s = new_slide("B6. Dataset quirks")
text_box(s, M, BODY_TOP, W - 2 * M, 5.5, [
    B("Original download link returns 403; the Kaggle mirror was used"),
    B("P-2 has two conflicting label rows, so the channel is skipped"),
    B("Unlabeled T-10 is ignored"),
    B("320-step warm-up, the same for every detector"),
    B("0 unscoreable events"),
], size=24, space_after=14)

s = new_slide("B7. Why no transformer")
text_box(s, M, BODY_TOP, W - 2 * M, 5.5, [
    B("Dropped for time"),
    B("My analysis suggests it wouldn't fix either failure, since it would share the one-step forecast "
      "and the high-error-only score (untested)"),
], size=24, space_after=16)

s = new_slide("B8. Clean-twin check")
text_box(s, M, BODY_TOP, W - 2 * M, 5.5, [
    B("Each fault mission is also flown without the fault, on identical noise"),
    B("A separate check, reported next to the headline counts, not a filter on them"),
    B("It shows which catches also fire on the twin and so may be chance"),
    B("Held out: persistence and GRU have none; LSTM about one mission per fault row"),
], size=24, space_after=16)

s = new_slide("B9. Locked test run")
text_box(s, M, BODY_TOP, W - 2 * M, 5.5, [
    B("Before scoring, the held-out run recorded the commit and the hash of every checkpoint"),
    B("It refuses uncommitted code, code or weights changed since then, and a folder that already holds "
      "a held-out run"),
    B("So the result can't be overwritten"),
], size=24, space_after=16)

prs.save(OUT)
bad = [(n, u, h) for n, u, h in fit_report if u > h]
for n, u, h in bad:
    print(f"OVERFLOW {u:.2f}in > {h:.2f}in: {n[:70]}")
print(f"saved {OUT}, {len(prs.slides)} slides, {len(fit_report)} boxes checked, {len(bad)} overflow")
