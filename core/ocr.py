"""OCR for the cash/wave HUD readouts (Phase 3).

HUD digits have dark outlines that break raw OCR, so the ROI is thresholded
to black/white first. Measured against a real capture, both readouts are
light-on-dark (white wave digits, gold cash digits), but _normalize still
flips whichever polarity it gets so a restyled HUD can't break the read.

Two readers, deliberately: read_int joins every digit group it finds,
read_leading_int takes only the leftmost. Which one a caller wants depends
on the region - see their docstrings.
"""

import re

import cv2
import numpy as np

try:
    import pytesseract
    HAS_TESSERACT = True
except ImportError:
    HAS_TESSERACT = False

_WHITELIST = "-c tessedit_char_whitelist=0123456789"
# Slash KEPT in the whitelist for the "N/M" readouts (wave, upgrade level).
# Tesseract returns "N/M" as a single token, so with a digits-only whitelist
# the slash is stripped and N,M concatenate into one number ("0/8" -> "08") -
# any reader that must SEPARATE the two has to keep the slash and split on it.
_SLASH_WHITELIST = "-c tessedit_char_whitelist=0123456789/"
# psm 7 = one text line, 8 = one word, 13 = raw line (no layout heuristics).
# A lone HUD number reads best on 7/8; 13 is the fallback for odd spacing.
_PSMS = (7, 8, 13)
_CONFIDENT = 80.0   # stop early once a read is at least this confident


def configure(tesseract_cmd: str | None):
    if HAS_TESSERACT and tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd


def tesseract_ready(tesseract_cmd: str | None = None) -> bool:
    """True only if the Tesseract ENGINE actually runs. HAS_TESSERACT just
    means the pytesseract wrapper imported - the engine is a separate install
    (the #1 thing users miss), so the readiness check must probe the binary,
    not the import. Returns False on any failure rather than raising."""
    if not HAS_TESSERACT:
        return False
    configure(tesseract_cmd)
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def _normalize(bw: np.ndarray) -> np.ndarray:
    """Tesseract wants dark text on a light background with a quiet border.
    Flip the image if it's mostly dark (so digits are dark-on-light either
    way), then pad with white so glyphs aren't touching the edge."""
    if float(bw.mean()) < 127:
        bw = cv2.bitwise_not(bw)
    return cv2.copyMakeBorder(bw, 12, 12, 12, 12, cv2.BORDER_CONSTANT, value=255)


def _binarizations(gray: np.ndarray):
    """Two normalized candidates: Otsu (clean, high-contrast HUD) and adaptive
    (survives a gradient / busy background behind the number)."""
    _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    yield _normalize(otsu)
    try:
        adap = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                     cv2.THRESH_BINARY, 31, 5)
        yield _normalize(adap)
    except cv2.error:
        return


def _read_candidate(bw: np.ndarray, psm: int):
    """(groups, mean_confidence) for one binary image + psm, or None.
    Confidence-scored via image_to_data so a longer-but-garbage read no longer
    beats a short clean one (the old 'longest string wins' failure).

    `groups` stays a LIST of separate left-to-right digit runs rather than one
    pre-joined string, because the two HUD readouts need opposite handling -
    see read_int vs read_leading_int. Sorted by x because image_to_data's
    reading order isn't guaranteed to be left-to-right."""
    config = f"--psm {psm} {_WHITELIST}"
    try:
        data = pytesseract.image_to_data(
            bw, config=config, output_type=pytesseract.Output.DICT)
    except Exception:
        return None
    found, confs = [], []
    lefts = data.get("left", [])
    for i, (txt, conf) in enumerate(zip(data.get("text", []), data.get("conf", []))):
        t = re.sub(r"[^0-9]", "", txt or "")
        if not t:
            continue
        found.append((lefts[i] if i < len(lefts) else 0, t))
        try:
            c = float(conf)
        except (TypeError, ValueError):
            c = -1.0
        if c >= 0:
            confs.append(c)
    if not found:
        return None
    groups = [t for _, t in sorted(found, key=lambda p: p[0])]
    return groups, (sum(confs) / len(confs) if confs else 0.0)


def _scan(img: np.ndarray) -> list[str] | None:
    """Highest-confidence read of the ROI, as separate digit groups."""
    if not HAS_TESSERACT or img is None or img.size == 0:
        return None
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)

    best, best_conf = None, -1.0
    for bw in _binarizations(gray):
        for psm in _PSMS:
            res = _read_candidate(bw, psm)
            if res is None:
                continue
            groups, conf = res
            better = conf > best_conf or (
                conf == best_conf
                and (best is None or len("".join(groups)) > len("".join(best))))
            if better:
                best, best_conf = groups, conf
            # The common case (clean HUD number) hits this on the first try,
            # so this stays ~1 tesseract call instead of 6 unless it's unsure.
            if best_conf >= _CONFIDENT:
                return best
    return best


def read_int(img: np.ndarray) -> int | None:
    """The whole ROI as one integer - digit groups are JOINED, so a cash value
    drawn with a thousands separator ("1,050") still reads as 1050. Only use
    this on a region holding exactly one number."""
    groups = _scan(img)
    return int("".join(groups)) if groups else None


def _read_slashed(img: np.ndarray) -> str | None:
    """Recognize a digits-and-slash readout as a RAW string, slash kept
    (e.g. "3/15", "0/8"). The digit-only _scan strips the slash and merges
    N,M into one number, so the two slash readers below - which must tell N
    from M - go through this instead. Not confidence-scored like _scan; it
    takes the first binarization/psm that yields any digit, which is enough
    for these small fixed HUD readouts."""
    if not HAS_TESSERACT or img is None or img.size == 0:
        return None
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    for bw in _binarizations(gray):
        for psm in _PSMS:
            try:
                raw = pytesseract.image_to_string(
                    bw, config=f"--psm {psm} {_SLASH_WHITELIST}").strip()
            except Exception:
                continue
            if any(ch.isdigit() for ch in raw):
                return raw
    return None


def read_leading_int(img: np.ndarray) -> int | None:
    """Only the LEFTMOST number in the ROI. The wave HUD reads "<current> /
    <total>" ("3 / 15"); Tesseract returns that as one token that a digits-
    only read merges into 315, so every `wave >= N` precondition passes on
    the first poll and the whole run desynchronizes silently - the exact
    failure the preconditions exist to prevent (HANDOFF 2.6). Reading with
    the slash kept and taking the first digit run gives the current wave."""
    raw = _read_slashed(img)
    if not raw:
        return None
    m = re.search(r"\d+", raw)
    return int(m.group()) if m else None


def read_fraction(img: np.ndarray) -> tuple[int | None, int | None]:
    """(current, max) from an "N/M" readout, e.g. the unit panel's
    "Upgrade 0/8".

    Reads with the slash KEPT and splits on it (_read_slashed): Tesseract
    returns "N/M" as a single token, so a digits-only read merges it into one
    number and the two values can't be recovered. The ROI usually also holds
    a text label ("Upgrade"), but that's letters and the slash whitelist drops
    it; if more than one "d/d" pair survives, the LAST wins - the label
    precedes the numbers, so a stray pair can only appear to their left."""
    raw = _read_slashed(img)
    if not raw:
        return None, None
    pairs = re.findall(r"(\d+)\s*/\s*(\d+)", raw)
    if not pairs:
        return None, None
    n, m = pairs[-1]
    return int(n), int(m)


_LETTERS = "-c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
_WORD_PSMS = (8, 7)   # 8 = single word (the common case), 7 = single line fallback


def _read_word_candidate(bw: np.ndarray, psm: int):
    config = f"--psm {psm} {_LETTERS}"
    try:
        data = pytesseract.image_to_data(
            bw, config=config, output_type=pytesseract.Output.DICT)
    except Exception:
        return None
    letters, confs = [], []
    for txt, conf in zip(data.get("text", []), data.get("conf", [])):
        t = re.sub(r"[^A-Za-z]", "", txt or "")
        if not t:
            continue
        letters.append(t)
        try:
            c = float(conf)
        except (TypeError, ValueError):
            c = -1.0
        if c >= 0:
            confs.append(c)
    if not letters:
        return None
    return "".join(letters), (sum(confs) / len(confs) if confs else 0.0)


def read_word(img: np.ndarray) -> str | None:
    """Best-effort short word/phrase read - letters only, no digit whitelist.
    Used for the priority button's current-selection label ('None', 'First',
    ...) - see read_int's docstring pattern, but for text instead of digits.
    Same binarization + confidence-scored search as the digit readers."""
    if not HAS_TESSERACT or img is None or img.size == 0:
        return None
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)

    best, best_conf = None, -1.0
    for bw in _binarizations(gray):
        for psm in _WORD_PSMS:
            res = _read_word_candidate(bw, psm)
            if res is None:
                continue
            word, conf = res
            if conf > best_conf:
                best, best_conf = word, conf
            if best_conf >= _CONFIDENT:
                return best
    return best
