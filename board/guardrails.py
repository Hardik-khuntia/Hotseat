"""Checks that run in code, before or after the model. None of these need an API call."""
from __future__ import annotations

import io
import re

CASE_MIN_CHARS, CASE_MAX_CHARS = 800, 20_000   # ~5k tokens: the case is resent on every AI call
PITCH_LIMITS = {"Recommendation": 300, "Why": 1_500, "Biggest risk": 800, "Ask": 300}
WORKSHEET_BOX_LIMIT = 600
COPY_SHINGLE = 8               # words per overlapping chunk
COPY_RATIO_LIMIT = 0.35        # share of your 8-word chunks found verbatim in the case
COPY_RUN_LIMIT = 30            # or any single copied run this long
ANSWER_MIN_WORDS, ANSWER_MAX_CHARS = 8, 2_500
PERSUASIVE_MIN_WORDS = 20      # shorter answers can't move a board member

INJECTION = [
    r"ignore (all |any |the |your )?(previous|prior|above|earlier)? ?(instructions|rules|prompt)",
    r"disregard (your|the|all) (instructions|rules|system)",
    r"(reveal|show|print|repeat) (your|the) (system )?(prompt|instructions)",
    r"(you are|act as|pretend to be) (now )?(a |an )?(different|unrestricted|dan|jailbroken)",
    # Aimed at the AI, not at the board: "I ask the board to vote in favour" is NOT flagged.
    r"\byou (must|have to|are required to|are instructed to|will now) (now )?(vote|approve|agree|give)",
    r"\b(as an ai|you are an ai|language model|chatbot)\b",
    r"(set|change|make|update) (my|the|your) (score|stance|vote|grade)",
    r"(give|award) me (a )?(5|five|full marks|top score)",
    r"\bsystem prompt\b",
]
PROTECTED = re.compile(
    r"\b(religion|religious|caste|hindu|muslim|christian|sikh|jain|dalit|brahmin|gender|"
    r"women are|men are|pregnan\w*|disabilit\w*)\b", re.I)


def words(text: str) -> int:
    return len(re.findall(r"\w+", text or ""))


def looks_like_injection(text: str) -> bool:
    low = (text or "").lower()
    return any(re.search(p, low) for p in INJECTION)


# ---- Case text -------------------------------------------------------------
def read_upload(name: str, data: bytes) -> tuple[str, str | None]:
    """Return (text, error). Supports .txt, .md and text-based .pdf."""
    name = name.lower()
    if len(data) > 5 * 1024 * 1024:
        return "", "File is over 5 MB."
    if name.endswith((".txt", ".md")):
        for enc in ("utf-8", "utf-16", "cp1252"):
            try:
                return data.decode(enc), None
            except UnicodeDecodeError:
                continue
        return "", "Couldn't read the text encoding. Save it as UTF-8 and try again."
    if name.endswith(".pdf"):
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted:
                return "", "This PDF is password-protected."
            text = "\n".join((p.extract_text() or "") for p in reader.pages[:40])
        except Exception as e:
            return "", f"Couldn't read this PDF ({e.__class__.__name__})."
        if words(text) < 100:
            return "", "This PDF seems to be scanned images, not text. Paste the text instead."
        return text, None
    return "", "Upload a .txt, .md or .pdf file, or paste the text."


def check_case(text: str) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    t = (text or "").strip()
    if len(t) < CASE_MIN_CHARS:
        errors.append(f"The case is too short ({len(t)} characters). Use at least {CASE_MIN_CHARS}, "
                      "about 150 words, so the board has facts to work with.")
    if len(t) > CASE_MAX_CHARS:
        errors.append(f"The case is too long ({len(t):,} characters, limit {CASE_MAX_CHARS:,}). "
                      "Trim exhibits and appendices to the facts needed for the decision.")
    if t and len(numbers_in(t)) < 3:
        warnings.append("The case has very few numbers, so the board can't test your use of evidence much.")
    if looks_like_injection(t):
        warnings.append("The case contains text that looks like instructions to an AI. It will be treated as "
                        "case content only, never as instructions.")
    return errors, warnings


# ---- Student answers ---------------------------------------------------------
def check_answer(text: str) -> tuple[str | None, list[str]]:
    """Return (blocking error, flags)."""
    t = (text or "").strip()
    if not t:
        return "Write your answer first.", []
    if len(t) > ANSWER_MAX_CHARS:
        return f"Keep each answer under {ANSWER_MAX_CHARS:,} characters. Boards reward focus.", []
    if words(t) < ANSWER_MIN_WORDS:
        return f"That's too short to count as an answer (under {ANSWER_MIN_WORDS} words).", []
    flags = []
    if looks_like_injection(t):
        flags.append("injection")
    if PROTECTED.search(t):
        flags.append("protected")
    if words(t) < PERSUASIVE_MIN_WORDS:
        flags.append("short")
    return None, flags


# ---- Copy-paste and repetition --------------------------------------------
def _tokens(text: str) -> list[str]:
    return re.findall(r"[\w₹%.,']+", (text or "").lower())


def _shingles(tokens: list[str], n: int) -> set[tuple]:
    return {tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)}


def copy_stats(text: str, case_text: str) -> tuple[float, int]:
    """(share of the text's 8-word chunks that appear verbatim in the case, longest copied run in words)."""
    t, c = _tokens(text), _tokens(case_text)
    if len(t) < COPY_SHINGLE:
        return 0.0, 0
    case_sh = _shingles(c, COPY_SHINGLE)
    hits = [tuple(t[i:i + COPY_SHINGLE]) in case_sh for i in range(len(t) - COPY_SHINGLE + 1)]
    longest = run = 0
    for h in hits:
        run = run + 1 if h else 0
        longest = max(longest, run)
    return sum(hits) / len(hits), (longest + COPY_SHINGLE - 1) if longest else 0


def is_copied(text: str, case_text: str) -> bool:
    ratio, run = copy_stats(text, case_text)
    return ratio > COPY_RATIO_LIMIT or run >= COPY_RUN_LIMIT


def strip_copied(text: str, case_text: str) -> str:
    """Drop sentences that are mostly lifted from the case, so they can't count as 'your words'."""
    keep = [s for s in re.split(r"(?<=[.!?\n])\s+", text or "") if not is_copied(s, case_text) or words(s) < COPY_SHINGLE]
    return " ".join(keep)


def near_duplicate(new: str, previous: list[str], limit: float = 0.7) -> bool:
    a = _shingles(_tokens(new), 4)
    if not a:
        return False
    return any(len(a & _shingles(_tokens(p), 4)) / len(a) >= limit for p in previous)


# ---- Numbers: are the student's figures actually in the case? ---------------
NUM_RE = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{2,3})+|\d+(?:\.\d+)?)(\s?%)?")


def _norm_num(s: str) -> str:
    s = s.replace(",", "")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


UNIT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(lakh|lakhs|lac|crore|crores|cr)\b", re.I)
UNIT_SCALE = {"lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "crore": 1e7, "crores": 1e7, "cr": 1e7}


def numbers_in(text: str) -> set[str]:
    """All figures in a text, plus lakh/crore amounts expanded, so '3.1 lakh' matches '3,10,000'."""
    out = set()
    for m in NUM_RE.finditer(text or ""):
        n = _norm_num(m.group(1))
        out.add(n)
        if m.group(2):
            out.add(n + "%")          # "15%" only matches a percentage in the case, not "15 minutes"
    for m in UNIT_RE.finditer(text or ""):
        out.add(_norm_num(f"{float(m.group(1)) * UNIT_SCALE[m.group(2).lower()]:.0f}"))
    return out


def unsupported_numbers(answer: str, case_text: str) -> list[str]:
    """Figures in the answer that never appear in the case. Small counts (0-10) are ignored
    because 'three reasons' or '2 options' are not claims about the case."""
    case_nums = numbers_in(case_text)
    out = []
    for m in NUM_RE.finditer(answer or ""):
        n = _norm_num(m.group(1))
        is_pct = bool(m.group(2))
        try:
            val = float(n)
        except ValueError:
            continue
        if not is_pct and val <= 10 and "." not in n:
            continue
        key = n + "%" if is_pct else n
        if key in case_nums or m.group(0).strip() in out:
            continue
        unit = UNIT_RE.match((answer or "")[m.start():])          # "45 lakh" -> 4500000
        if unit and _norm_num(f"{float(unit.group(1)) * UNIT_SCALE[unit.group(2).lower()]:.0f}") in case_nums:
            continue
        out.append(m.group(0).strip())
    return out


def case_numbers_used(answer: str, case_text: str) -> int:
    """How many distinct figures from the case the student actually used."""
    case_nums, used = numbers_in(case_text), set()
    for m in NUM_RE.finditer(answer or ""):
        n = _norm_num(m.group(1))
        try:
            val = float(n)
        except ValueError:
            continue
        if n in case_nums and (val > 10 or m.group(2) or "." in n):
            used.add(n)
    return len(used)


# ---- Quotes ----------------------------------------------------------------
def _norm_text(s: str) -> str:
    s = (s or "").replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace("–", "-")
    return re.sub(r"\s+", " ", s).strip().lower().strip(".\"' ")


def verify_quote(quote: str, source: str) -> bool:
    """A quote counts only if it appears word for word (ignoring case, spacing, curly quotes)."""
    q = _norm_text(quote)
    return len(q) >= 6 and q in _norm_text(source)
