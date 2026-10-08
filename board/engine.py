"""Deterministic meeting logic. The AI proposes; these rules decide.

- A board member's stance moves at most one step per answer. The AI judges the direction;
  these rules decide whether it is allowed and how far.
- Short, off-topic, copied or manipulative answers can't win anyone over.
- An answer can also earn half a step from ONE other member whose concern it addresses.
- The chair gives the floor to whoever has spoken least, most sceptical first.
- Votes follow the final stances, not anything the AI says about voting.
- The overall grade is computed here from criterion scores, with rule-based caps.
"""
from __future__ import annotations

from dataclasses import dataclass

STANCES = {-2: "Opposed", -1: "Sceptical", 0: "Neutral", 1: "Leaning yes", 2: "Convinced"}

RUBRIC = [
    {"id": "clarity", "name": "Clear recommendation",
     "levels": {1: "No clear decision, or it changes during the meeting",
                3: "A clear decision, but the reasoning or the ask is vague",
                5: "A crisp decision, the logic behind it and a specific ask of the board"}},
    {"id": "evidence", "name": "Use of case evidence",
     "levels": {1: "Opinions without facts, or facts that aren't in the case",
                3: "Some case facts, used loosely or without numbers",
                5: "Accurate case figures used to make the argument, assumptions labelled"}},
    {"id": "framework", "name": "Framework thinking (SWOT / Porter)",
     "levels": {1: "No structure",
                3: "Framework named or listed, but not used to reach the conclusion",
                5: "Framework drives the argument and exposes the real trade-off"}},
    {"id": "objections", "name": "Handling objections",
     "levels": {1: "Dodges questions or repeats the pitch",
                3: "Answers most questions, but defensively or without new reasoning",
                5: "Answers the actual question, concedes fair points, adapts the plan"}},
    {"id": "stakeholders", "name": "Stakeholder awareness",
     "levels": {1: "Same answer for everyone",
                3: "Recognises different interests but doesn't address them",
                5: "Speaks to each member's priority and offers trade-offs they can accept"}},
]
RUBRIC_IDS = [r["id"] for r in RUBRIC]

FRAMEWORK_TERMS = ["strength", "weakness", "opportunit", "threat", "swot", "porter", "rivalry",
                   "substitute", "new entrant", "barrier", "bargaining power", "buyer power", "supplier power"]


def stance_label(s: int) -> str:
    return STANCES[max(-2, min(2, s))]


@dataclass
class TurnOutcome:
    applied: int
    note: str | None


def apply_reaction(stance: int, proposed, flags: list[str], on_topic: bool, answered: bool) -> tuple[int, TurnOutcome]:
    """Bound the model's suggested stance change with fixed rules."""
    try:
        p = int(proposed)
    except (TypeError, ValueError):
        p = 0
    p = max(-1, min(1, p))
    note = None
    if "injection" in flags:
        p, note = -1, "Trying to instruct the AI instead of persuading the board costs credibility."
    elif "copied" in flags and p > 0:
        p, note = 0, "Mostly copied from the case. Reading the case back isn't an argument."
    elif not on_topic:
        p, note = min(p, 0), "Off-topic answers can't move a board member."
    elif p > 0 and not answered:
        p, note = 0, "You didn't answer the question that was asked, so no movement."
    elif p > 0 and "short" in flags:
        p, note = 0, "Too short to persuade anyone. Give reasons and evidence."
    new = max(-2, min(2, stance + p))
    return new, TurnOutcome(new - stance, note)


SECONDARY_CREDIT = 0.5
SECONDARY_CEILING = 1          # half-steps alone can lift someone to "Leaning yes", never "Convinced"


def can_earn_secondary(flags: list[str], on_topic: bool, answered: bool) -> bool:
    return on_topic and answered and not ({"injection", "copied", "short"} & set(flags))


def apply_secondary(stance: int, credit: float) -> tuple[int, float, bool]:
    """Add half a step of credit; convert to a full step when it reaches 1. Returns (stance, credit, moved)."""
    if stance >= SECONDARY_CEILING:
        return stance, credit, False
    credit += SECONDARY_CREDIT
    if credit >= 1:
        return stance + 1, credit - 1, True
    return stance, credit, False


def next_speaker(board: list[dict], stances: dict, asked: dict, exclude: str | None) -> str:
    """Whoever has asked fewest questions, then the most sceptical, then seating order.
    Everyone gets a turn before anyone gets a second one."""
    cands = [m for m in board if m["id"] != exclude] or board
    order = {m["id"]: i for i, m in enumerate(board)}
    return min(cands, key=lambda m: (asked.get(m["id"], 0), stances[m["id"]], order[m["id"]]))["id"]


def votes(stances: dict) -> dict:
    return {k: ("Yes" if v >= 1 else "No" if v <= -1 else "Abstain") for k, v in stances.items()}


def verdict(v: dict) -> tuple[str, str]:
    yes = sum(1 for x in v.values() if x == "Yes")
    no = sum(1 for x in v.values() if x == "No")
    if yes > no and yes >= 2:
        return "Approved", f"{yes} for, {no} against"
    if no > yes:
        return "Rejected", f"{yes} for, {no} against"
    return "Sent back for more work", f"{yes} for, {no} against"


def rule_caps(student_text: str, worksheet_filled: int, case_nums_used: int, avg_answer_words: float) -> dict:
    """Upper limits the AI's scores cannot exceed, with the reason."""
    caps = {}
    low = student_text.lower()
    if case_nums_used == 0:
        caps["evidence"] = (2, "You never used a figure from the case.")
    if worksheet_filled == 0 and not any(t in low for t in FRAMEWORK_TERMS):
        caps["framework"] = (2, "No framework worksheet and no framework language in your answers.")
    if avg_answer_words < 25:
        caps["objections"] = (2, f"Answers averaged {avg_answer_words:.0f} words; too thin to handle objections.")
    return caps


def apply_caps(ai_scores: dict, caps: dict) -> dict:
    out = {}
    for k in RUBRIC_IDS:
        s = int(ai_scores.get(k, 0) or 0)
        if k in caps and s > caps[k][0]:
            out[k] = caps[k][0]
        else:
            out[k] = s
    return out


def overall(scores: dict) -> int:
    vals = [scores[k] for k in RUBRIC_IDS if scores.get(k)]
    return round(100 * sum(vals) / (5 * len(RUBRIC_IDS))) if vals else 0


def calibration(self_scores: dict, ai_scores: dict) -> dict:
    gaps = {k: self_scores[k] - ai_scores[k] for k in RUBRIC_IDS if k in self_scores and k in ai_scores}
    if not gaps:
        return {"gaps": {}, "bias": 0.0, "mae": 0.0, "label": "Not available"}
    bias = sum(gaps.values()) / len(gaps)
    mae = sum(abs(g) for g in gaps.values()) / len(gaps)
    if mae <= 0.6:
        label = "Well calibrated"
    elif bias > 0.4:
        label = "Overconfident"
    elif bias < -0.4:
        label = "Underconfident"
    else:
        label = "Mixed: right on average, wrong on specifics"
    return {"gaps": gaps, "bias": round(bias, 2), "mae": round(mae, 2), "label": label}


# ---- Board mood (difficulty) ---------------------------------------------------
MOODS = {"Friendly": 1, "Standard": 0, "Tough": -1}
MOOD_HELP = {"Friendly": "Everyone starts one step warmer (never above Neutral). Good for a first run.",
             "Standard": "Members start where the case puts them.",
             "Tough": "Everyone starts one step colder. Closer to a real cold call."}


def opening_stances(board: list[dict], mood: str = "Standard") -> dict:
    shift = MOODS.get(mood, 0)
    return {m["id"]: max(-2, min(0, m["opening_stance"] + shift)) for m in board}


# ---- Key moments (debrief) -----------------------------------------------------
def key_moments(transcript: list[dict]) -> dict:
    """Pair each answer with the reaction that followed it. Best = largest gain, costliest = largest loss."""
    pairs = []
    for i, x in enumerate(transcript):
        if x.get("who") == "Student" and i + 1 < len(transcript) and transcript[i + 1].get("kind") == "reaction":
            r = transcript[i + 1]
            gain = r.get("applied", 0) + (1 if r.get("also_moved") else 0)
            pairs.append({"answer": x["text"], "member": r.get("member"), "gain": gain,
                          "note": r.get("move_note", "")})
    best = max(pairs, key=lambda p: p["gain"], default=None)
    worst = min(pairs, key=lambda p: p["gain"], default=None)
    return {"best": best if best and best["gain"] > 0 else None,
            "worst": worst if worst and worst["gain"] < 0 else None}
