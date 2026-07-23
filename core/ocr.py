"""OCR for the HUD readouts (cash, wave) and the unit panel's labels.

Backed by RapidOCR (ONNX models shipped inside the pip package) rather than
Tesseract. That swap is the point of this module's design: Tesseract is a
SEPARATE system install, and "the user didn't install the binary" was the
single most common way OCR silently did nothing - the pytesseract wrapper
imports fine on its own, so every read just returned empty forever and
upgrade-to-max never detected "maxed" (see git history for that bug).
RapidOCR has no external dependency at all: `pip install rapidocr
onnxruntime` is the whole setup, on every platform.

It also reads these HUD strings better. Tesseract needed a character
whitelist to cope, and a whitelist that keeps the slash for the "N/M"
readouts (it returns "N/M" as one token, so a digits-only whitelist merged
"0/8" into "08"). RapidOCR returns "Upgrade 0/3" verbatim, so the readers
below are plain regex over real text.

Recognition runs with detection DISABLED (use_det=False): every caller
passes an already-cropped, tight, single-line ROI, so the detector has
nothing useful to do and returns nothing at all on crops this small - the
whole image IS the text line.
"""

import re

import cv2
import numpy as np

try:
    from rapidocr import RapidOCR
    HAS_RAPIDOCR = True
except ImportError:
    HAS_RAPIDOCR = False

#: True once the OCR engine has actually loaded and can run. Callers on hot
#: paths (upgrade max-detection, priority reads) must check this rather than
#: assuming the import succeeded - a missing/broken model would otherwise
#: fail silently inside the broad except in _read_text and read as "no text",
#: which upstream can't tell apart from "the region is genuinely empty".
READY = False

_engine = None

#: The ROI is upscaled this much before recognition. These HUD crops are tiny
#: (~20px tall) and the recognizer is trained on larger text; scaling up first
#: is what the reference macro does too, and it measurably improves reads.
_SCALE = 4


def _load_engine():
    """Build the RapidOCR engine once, lazily. Costs ~1s (ONNX model load),
    so it happens on the first read rather than at import - the dashboard
    starts up without paying for it, and a run that never reads OCR never
    pays for it at all."""
    global _engine, READY
    if _engine is not None:
        return _engine
    if not HAS_RAPIDOCR:
        READY = False
        return None
    try:
        _engine = RapidOCR()
        READY = True
    except Exception:
        _engine = None
        READY = False
    return _engine


def configure(_legacy_tesseract_cmd: str | None = None):
    """Warm the engine and set READY. The argument is the old
    vision.tesseract_cmd config value - accepted and ignored so an existing
    config.yaml keeps loading, since RapidOCR needs no binary path."""
    _load_engine()


def engine_ready() -> bool:
    """True only if the OCR engine actually loads and runs. Probes (and warms)
    on first call; cheap afterwards."""
    _load_engine()
    return READY


def _read_text(img: np.ndarray) -> str | None:
    """Raw recognized text for an already-cropped single-line ROI, or None.

    Upscaled first (see _SCALE) and run with detection/classification off -
    the crop IS the line, so there is no layout to detect and no orientation
    to classify."""
    if img is None or img.size == 0:
        return None
    engine = _load_engine()
    if engine is None:
        return None
    try:
        big = cv2.resize(img, None, fx=_SCALE, fy=_SCALE,
                         interpolation=cv2.INTER_CUBIC)
        result = engine(big, use_det=False, use_cls=False)
    except Exception:
        return None
    if result is None or not getattr(result, "txts", None):
        return None
    return " ".join(t for t in result.txts if t).strip() or None


def read_int(img: np.ndarray) -> int | None:
    """The whole ROI as one integer, with separators and stray non-digits
    dropped - a cash value drawn as "1,050" or "¥1,050" reads as 1050. Only
    use this on a region holding exactly one number."""
    text = _read_text(img)
    if not text:
        return None
    digits = re.sub(r"[^0-9]", "", text)
    return int(digits) if digits else None


def read_leading_int(img: np.ndarray) -> int | None:
    """Only the LEFTMOST number in the ROI. The wave HUD reads
    "<current> / <total>" ("3 / 15"); joining those digits the way read_int
    does gives 315, so every `wave >= N` precondition passes on the first
    poll and the whole run desynchronizes silently - the exact failure the
    preconditions exist to prevent (HANDOFF 2.6)."""
    text = _read_text(img)
    if not text:
        return None
    m = re.search(r"\d+", text)
    return int(m.group()) if m else None


def read_fraction(img: np.ndarray) -> tuple[int | None, int | None]:
    """(current, max) from an "N/M" readout, e.g. the unit panel's
    "Upgrade 0/3".

    The ROI usually also holds a text label ("Upgrade"); that's fine here
    because the regex only takes digit/digit pairs. If more than one pair
    survives, the LAST wins - the label precedes the numbers, so a stray pair
    can only appear to their left."""
    text = _read_text(img)
    if not text:
        return None, None
    pairs = re.findall(r"(\d+)\s*/\s*(\d+)", text)
    if not pairs:
        return None, None
    n, m = pairs[-1]
    return int(n), int(m)


def read_word(img: np.ndarray) -> str | None:
    """Best-effort short word read - used for the priority button's
    current-selection label ('None', 'First', ...). Strips anything that
    isn't a letter so a stray glyph from the button's border can't turn a
    clean 'First' into a non-match."""
    text = _read_text(img)
    if not text:
        return None
    letters = re.sub(r"[^A-Za-z]", "", text)
    return letters or None
