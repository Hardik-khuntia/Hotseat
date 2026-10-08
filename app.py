"""HotSeat: a case-study coach where you defend your recommendation to a board that pushes back.

Run locally:  python -m streamlit run app.py

Flow: pick or upload a case -> prepare a framework worksheet and a pitch -> answer Socratic questions
from four board members (stances move by fixed rules) -> you grade yourself while the vote is sealed ->
the AI grades you -> the vote is revealed -> calibration chart and a downloadable prep sheet.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

import streamlit as st

from board import ai, engine, guardrails, prepsheet, ui

BASE = Path(__file__).parent
CASES = json.loads((BASE / "data" / "cases.json").read_text(encoding="utf-8"))
for c in CASES:
    c["text"] = (BASE / "data" / "cases" / c["file"]).read_text(encoding="utf-8")

SWOT = ["Strengths", "Weaknesses", "Opportunities", "Threats"]
PORTER = ["Rivalry among competitors", "Threat of new entrants", "Threat of substitutes",
          "Bargaining power of buyers", "Bargaining power of suppliers"]
STUDENT_AVATAR = "🧑‍💼"

st.set_page_config(page_title="HotSeat: case coach", page_icon="🔥", layout="wide")
st.markdown(ui.CSS, unsafe_allow_html=True)
ss = st.session_state
ss.setdefault("stage", "Case")
ss.setdefault("sessions", [])


MAX_AI_CALLS = 60          # per browser session; protects the shared free quota on a public link


def can_spend(n: int = 1) -> bool:
    """Count AI calls in this session and refuse once the cap is reached."""
    if ss.get("ai_calls", 0) + n > MAX_AI_CALLS:
        return False
    ss.ai_calls = ss.get("ai_calls", 0) + n
    return True


def has_key() -> bool:
    return bool(ai.get_api_key())


@st.cache_data(show_spinner=False, ttl=6 * 3600, max_entries=50)
def cached_brief(case_text: str) -> dict:
    return ai.brief(case_text)


def reset_meeting(keep_case=True):
    keep = {"sessions": ss.get("sessions", [])}
    if keep_case:
        for k in ("case", "board", "saved_inputs"):
            if k in ss:
                keep[k] = ss[k]
    for k in list(ss.keys()):
        if k not in keep and not k.startswith("_"):
            del ss[k]
    for k, v in keep.items():
        ss[k] = v
    ss.stage = "Prepare" if keep_case and "case" in keep else "Case"


def who(m: dict) -> str:
    return f"{m['name']} ({m['role']})"


def member(mid: str) -> dict:
    return next(m for m in ss.board if m["id"] == mid)


def run_turn(reacting: dict | None, answer: str, flags_note: str, asking: dict | None) -> dict:
    """One AI call; falls back to scripted questions if the AI is unavailable."""
    if has_key() and not can_spend():
        ss.ai_note = (f"This session has used its {MAX_AI_CALLS} AI calls. Using a scripted question; "
                      "refresh the page to start a new session.")
    elif has_key():
        try:
            others = [m for m in ss.board if reacting and m["id"] != reacting["id"]]
            return ai.turn(ss.case["text"], ss.case["decision_question"], ss.pitch, ss.worksheet,
                           ss.transcript, reacting, answer, flags_note, asking, ss.round, ss.total, others=others)
        except Exception as e:
            ss.ai_note = f"The AI didn't respond ({str(e)[:160]}). Using a scripted question; stances won't move this round."
    return ai.offline_turn(reacting, asking, ss.asked.get(asking["id"], 0) if asking else 0)


def ask_next(asking: dict, q: dict):
    ss.asked[asking["id"]] = ss.asked.get(asking["id"], 0) + 1
    ss.speaker = asking["id"]
    ss.transcript.append({"who": who(asking), "member": asking["id"], "kind": "question", "text": q["text"],
                          "quote": q.get("case_quote", "") if q.get("quote_ok") else "",
                          "hook": q.get("framework_hook", ""), "unverified": q.get("unverified_numbers", [])})


# ---------------------------------------------------------------------------
st.markdown(ui.hero(has_key(), ai.provider_label()), unsafe_allow_html=True)

# Optional access code: set APP_PASSCODE in Secrets so only people you share it with can use your quota.
_code = ai._secret("APP_PASSCODE")
if _code and not ss.get("unlocked"):
    st.subheader("Enter the access code")
    st.caption("This deployment is limited to invited users to protect the free AI quota.")
    entered = st.text_input("Access code", type="password")
    if st.button("Enter", type="primary"):
        if entered.strip() == str(_code).strip():
            ss.unlocked = True
            st.rerun()
        else:
            st.error("That code isn't right.")
    st.stop()

with st.sidebar:
    st.markdown("### 🔥 HotSeat")
    if has_key():
        if st.button(f"Test {ai.provider_label()} connection", width="stretch"):
            ok, detail = ai.ping() if can_spend() else (False, "AI call limit reached for this session")
            ss.ping = (ok, detail)
        if ss.get("ping"):
            ok, detail = ss.ping
            (st.success if ok else st.error)(f"Working ({detail})" if ok else f"Not working: {detail}")
        st.caption(f"AI calls this session: {ss.get('ai_calls', 0)} of {MAX_AI_CALLS}")
    if "case" in ss:
        st.caption("Current case")
        st.markdown(f"**{ss.case['title']}**")
    if ss.stage not in ("Case",):
        if st.button("↺ Restart with this case", width="stretch"):
            reset_meeting(keep_case=True)
            st.rerun()
        if st.button("🗂️ Choose a different case", width="stretch"):
            reset_meeting(keep_case=False)
            st.rerun()
    if ss.sessions:
        st.caption(f"Meetings this session: {len(ss.sessions)}")
    st.divider()
    st.caption(f"Privacy: your case and answers are sent to {ai.provider_label()} to run the meeting. Free tiers "
               "may use them to improve the provider's products, so don't upload confidential cases. Nothing is "
               "stored here; refreshing the page clears everything except files you download.")
    st.caption("AI feedback can be wrong. Stance changes, votes and the final grade are computed by fixed rules "
               "in code; the AI only proposes.")

st.markdown(ui.stepper(ss.stage), unsafe_allow_html=True)

# ===========================================================================
# 1. CASE
# ===========================================================================
if ss.stage == "Case":
    st.subheader("Choose the case you'll present")
    t1, t2 = st.tabs(["📚 Sample cases", "⬆️ Upload or paste your own"])
    with t1:
        sectors = sorted({c["sector"] for c in CASES})
        f1, f2, f3 = st.columns([1.2, 1.6, 0.8])
        pick_sector = f1.selectbox("Sector", ["All sectors"] + sectors, key="lib_sector")
        query = f2.text_input("Search", key="lib_query", placeholder="e.g. pricing, expansion, regulator, India").strip().lower()
        f3.write("")
        surprise = f3.button("🎲 Surprise me", width="stretch")
        shown = [c for c in CASES
                 if (pick_sector == "All sectors" or c["sector"] == pick_sector)
                 and (not query or query in (c["title"] + " " + c["summary"] + " " + c["decision_question"]
                                             + " " + c["sector"]).lower())]
        st.caption(f"Showing {len(shown)} of {len(CASES)} cases across {len(sectors)} sectors. "
                   "All are original, fictional teaching cases written for this app.")

        def choose(c):
            ss.case = {k: c[k] for k in ("id", "title", "decision_question", "summary", "text")}
            ss.case["sector"] = c["sector"]
            ss.case["key_facts"] = []
            ss.board = c["board"]
            ss.stage = "Prepare"
            st.rerun()

        if surprise:
            import random
            choose(random.choice(shown or CASES))
        if not shown:
            st.info("No case matches. Try another word or clear the filters.")
        for i in range(0, len(shown), 3):
            cols = st.columns(3)
            for col, c in zip(cols, shown[i:i + 3]):
                with col:
                    with st.container(border=True):
                        st.markdown(f'<span class="br-chip-light">{c["sector"]}</span>', unsafe_allow_html=True)
                        st.markdown(f"**{c['title']}**")
                        st.caption(c["summary"])
                        st.markdown(f"*Decision:* {c['decision_question']}")
                        if st.button("Present this case", key=f"pick_{c['id']}", type="primary", width="stretch"):
                            choose(c)
    with t2:
        up = st.file_uploader("Case file (.pdf, .txt or .md, up to 5 MB)", type=["pdf", "txt", "md"])
        pasted = st.text_area("…or paste the case text", height=220, placeholder="Paste the full case, including exhibits.")
        if st.button("Build my board", type="primary"):
            text, err = ("", None)
            if up is not None:
                text, err = guardrails.read_upload(up.name, up.getvalue())
            elif pasted.strip():
                text = pasted
            else:
                err = "Upload a file or paste the case text first."
            if err:
                st.error(err)
            else:
                errors, warns = guardrails.check_case(text)
                for e in errors:
                    st.error(e)
                if not errors:
                    for w in warns:
                        st.warning(w)
                    if has_key() and not can_spend():
                        st.error(f"This session has used its {MAX_AI_CALLS} AI calls. Refresh the page to continue.")
                    elif not has_key():
                        st.error("Building a board for your own case needs the AI. Add GROQ_API_KEY (or GEMINI_API_KEY), or use a sample case.")
                    else:
                        try:
                            with st.spinner("Reading the case and seating the board..."):
                                b = cached_brief(text.strip())
                            ss.case = {"id": "upload_" + hashlib.sha1(text.encode()).hexdigest()[:8],
                                       "title": b.get("title") or "Your case", "decision_question": b["decision_question"],
                                       "summary": b.get("summary", ""), "text": text.strip(), "key_facts": b.get("key_facts", [])}
                            ss.board = b["board"]
                            if b.get("dropped_facts"):
                                st.toast(f"Dropped {b['dropped_facts']} key fact(s) whose quotes weren't in the case.")
                            ss.stage = "Prepare"
                            st.rerun()
                        except Exception as e:
                            st.error(f"Couldn't build the board ({str(e)[:160]}). Try again in a minute, or use a sample case.")

# ===========================================================================
# 2. PREPARE
# ===========================================================================
elif ss.stage == "Prepare":
    # Streamlit forgets widget values once a widget is off-screen, so restore a saved pitch on retry.
    for k, v in ss.get("saved_inputs", {}).items():
        if k not in ss:
            ss[k] = v
    c = ss.case
    st.subheader(c["title"])
    a, b = st.columns([1.15, 1], gap="large")
    with a:
        st.markdown(ui.card("The decision", c["decision_question"]), unsafe_allow_html=True)
        if c.get("summary"):
            st.caption(c["summary"])
        with st.expander("📄 Read the full case", expanded=False):
            st.markdown(c["text"])
        if c.get("key_facts"):
            with st.expander("Key facts (each checked against the case text)"):
                for f in c["key_facts"]:
                    st.markdown(f"- {f['fact']}  \n  <span style='color:#6B7280;font-size:.85em'>“{f['quote']}”</span>",
                                unsafe_allow_html=True)
    with b:
        mood = st.radio("How tough should the board be?", list(engine.MOODS), index=1, horizontal=True, key="p_mood")
        st.caption(engine.MOOD_HELP[mood])
        blind = st.toggle("Blind mode: hide stance meters during the meeting", key="p_blind",
                          help="You won't see who you're winning over, so your self-score can't just copy the room.")
        st.markdown(ui.board_table(ss.board, engine.opening_stances(ss.board, mood), title="Meet your board"),
                    unsafe_allow_html=True)
        with st.expander("What each member cares about"):
            for m in ss.board:
                st.markdown(f"**{m['avatar']} {m['name']}, {m['role']}**: {m['priority']}. *Worried about:* {m['concern']}")

    st.markdown("#### 1 · Work through a framework")
    fw = st.radio("Framework", ["SWOT", "Porter's Five Forces"], horizontal=True, label_visibility="collapsed")
    boxes = SWOT if fw == "SWOT" else PORTER
    cols = st.columns(2 if fw == "SWOT" else 3)
    ws = {}
    for i, name in enumerate(boxes):
        with cols[i % len(cols)]:
            ws[name] = st.text_area(name, key=f"ws_{fw}_{name}", height=95, max_chars=guardrails.WORKSHEET_BOX_LIMIT,
                                    placeholder="Use facts and figures from the case.")
    st.caption("Optional but scored: board members will test your framework thinking either way.")

    st.markdown("#### 2 · Your pitch to the board")
    p1, p2 = st.columns(2)
    with p1:
        rec = st.text_input("Your recommendation (one sentence)", key="p_rec", max_chars=guardrails.PITCH_LIMITS["Recommendation"],
                            placeholder="e.g. Keep the app as a premium channel in 3 areas for 12 months, then decide.")
        why = st.text_area("Why: your top reasons, with case evidence", key="p_why", height=150,
                           max_chars=guardrails.PITCH_LIMITS["Why"])
    with p2:
        risk = st.text_area("Biggest risk, and how you'll handle it", key="p_risk", height=95,
                            max_chars=guardrails.PITCH_LIMITS["Biggest risk"])
        ask_ = st.text_input("What you're asking the board to approve", key="p_ask", max_chars=guardrails.PITCH_LIMITS["Ask"],
                             placeholder="e.g. ₹3.2 crore for phase 1, with a review in month 6")
        rounds = st.slider("Questions from the board", 4, 8, 6,
                           help="Each question is one AI call. 6 takes about 10 minutes.")

    if st.button("Take the hot seat →", type="primary"):
        pitch = f"Recommendation: {rec}\nWhy: {why}\nBiggest risk: {risk}\nAsk: {ask_}"
        problems = []
        if guardrails.words(rec) < 5:
            problems.append("Write a one-sentence recommendation (at least 5 words).")
        if guardrails.words(why) < 25:
            problems.append("Give your reasons in at least 25 words. The board needs something to test.")
        if guardrails.words(risk) < 8:
            problems.append("Name your biggest risk and how you'll handle it (at least 8 words). The board will ask.")
        if guardrails.words(ask_) < 4:
            problems.append("Say what you're asking the board to approve (at least 4 words).")
        if guardrails.looks_like_injection(pitch + " ".join(ws.values())):
            problems.append("Your pitch contains instructions aimed at the AI. Pitch the case, not the model.")
        copied = [n for n, t in [("Why", why), ("Biggest risk", risk)] + list(ws.items())
                  if guardrails.is_copied(t, ss.case["text"])]
        if copied:
            problems.append("These parts are mostly copied from the case: " + ", ".join(copied)
                            + ". Put the facts in your own words and say what they mean for the decision.")
        for p in problems:
            st.error(p)
        if not problems:
            ss.saved_inputs = {k: ss[k] for k in list(ss.keys())
                               if isinstance(k, str) and (k.startswith("p_") or k.startswith("ws_"))}
            ss.framework = fw
            ss.worksheet = "\n".join(f"{k}: {v.strip()}" for k, v in ws.items() if v.strip())
            ss.worksheet_filled = sum(1 for v in ws.values() if guardrails.words(v) >= 3)
            ss.pitch = pitch
            ss.pitch_unsupported = guardrails.unsupported_numbers(pitch + " " + ss.worksheet, ss.case["text"])
            ss.total, ss.round = rounds, 1
            ss.mood = mood
            ss.blind = blind
            ss.stances = engine.opening_stances(ss.board, mood)
            ss.asked, ss.transcript, ss.last_moves, ss.notes = {}, [], {}, []
            ss.credit = {m["id"]: 0.0 for m in ss.board}
            ss.history = [{"round": 0, "stances": dict(ss.stances)}]
            ss.ai_note = None
            first = member(engine.next_speaker(ss.board, ss.stances, ss.asked, None))
            with st.spinner(f"{first['name']} is reading your pitch..."):
                out = run_turn(None, "", "", first)
            ask_next(first, out["next_question"])
            ss.stage = "Boardroom"
            st.rerun()

# ===========================================================================
# 3. BOARDROOM
# ===========================================================================
elif ss.stage == "Boardroom":
    st.markdown(ui.board_table(ss.board, ss.stances, speaking=ss.speaker, last_moves=ss.last_moves,
                               title=f"In session · question {ss.round} of {ss.total}"
                                     + (" · blind mode" if ss.get("blind") else ""),
                               hidden=ss.get("blind", False)), unsafe_allow_html=True)
    st.progress((ss.round - 1) / ss.total)
    if ss.get("pitch_unsupported") and ss.round == 1:
        st.info("Figures in your pitch that aren't in the case: " + ", ".join(ss.pitch_unsupported)
                + ". If they're your own calculations or assumptions, say so when asked.")
    if ss.get("ai_note"):
        st.warning(ss.ai_note)
        ss.ai_note = None

    left, right = st.columns([1.6, 1], gap="large")
    with left:
        with st.chat_message("user", avatar=STUDENT_AVATAR):
            st.markdown(f"**Your pitch**  \n{ss.pitch.replace(chr(10), '  ' + chr(10))}")
        for x in ss.transcript:
            if x["who"] == "Student":
                with st.chat_message("user", avatar=STUDENT_AVATAR):
                    st.write(x["text"])
                    for n in x.get("notes", []):
                        st.caption(f"⚠️ {n}")
            else:
                m = member(x["member"])
                with st.chat_message("assistant", avatar=m["avatar"]):
                    st.markdown(f"**{m['name']}** · {m['role']}")
                    st.write(x["text"])
                    if x.get("quote"):
                        st.caption(f"📎 From the case: “{x['quote']}”")
                    if x.get("hook") and x["kind"] == "question":
                        st.caption(f"🧭 Lens: {x['hook']}")
                    if x.get("unverified"):
                        st.caption("⚠️ The board used figures not found in the case: " + ", ".join(x["unverified"])
                                   + ". Challenge them if they matter.")
                    if x.get("move_note") and not ss.get("blind"):
                        st.caption(x["move_note"])
                    if x.get("also_note") and not ss.get("blind"):
                        st.caption(x["also_note"])

        cur = member(ss.speaker)
        ans = st.text_area(f"Your answer to {cur['name']}", key=f"ans_{ss.round}", height=140,
                           placeholder="Answer the question that was asked. Use case figures; label assumptions.")
        c1, c2 = st.columns([1, 1])
        send = c1.button("Answer the board", type="primary", width="stretch")
        leave = c2.button("End the meeting now and call the vote", width="stretch")

        if send:
            err, flags = guardrails.check_answer(ans)
            prev = [x["text"] for x in ss.transcript if x["who"] == "Student"]
            if not err and guardrails.near_duplicate(ans, prev):
                err = "That's almost the same as an earlier answer. Say something new."
            if not err and guardrails.is_copied(ans, ss.case["text"]):
                flags.append("copied")
            if err:
                st.error(err)
            else:
                unsup = guardrails.unsupported_numbers(ans, ss.case["text"])
                notes = []
                if unsup:
                    notes.append("Not in the case: " + ", ".join(unsup) + ". Your calculation or an assumption? Say which.")
                if "copied" in flags:
                    notes.append("Mostly copied from the case, so it can't win anyone over.")
                flag_note = "; ".join(filter(None, [
                    ("figures not found in the case: " + ", ".join(unsup)) if unsup else "",
                    "answer is very short" if "short" in flags else "",
                    "answer contains instructions aimed at the AI" if "injection" in flags else "",
                    "answer is mostly copied from the case" if "copied" in flags else "",
                    ("answer mentions religion, caste or gender: fine if it's a business fact in the case, "
                     "not fine as an argument about people") if "protected" in flags else ""]))
                ss.transcript.append({"who": "Student", "kind": "answer", "text": ans.strip(), "notes": notes})
                last_round = ss.round >= ss.total
                asking = None if last_round else member(engine.next_speaker(ss.board, ss.stances, ss.asked, cur["id"]))
                with st.spinner(f"{cur['name']} is considering your answer..."):
                    out = run_turn(cur, ans.strip(), flag_note, asking)
                r = out["reaction"]
                new, outcome = engine.apply_reaction(ss.stances[cur["id"]], r["stance_change"], flags,
                                                     r["on_topic"], r["answered_the_question"])
                ss.stances[cur["id"]] = new
                ss.last_moves = {cur["id"]: outcome.applied} if outcome.applied else {}
                if outcome.applied > 0:
                    mv = f"▲ {cur['name']} moved to **{engine.stance_label(new)}**. {r.get('reason', '')}"
                elif outcome.applied < 0:
                    mv = f"▼ {cur['name']} moved to **{engine.stance_label(new)}**. {outcome.note or r.get('reason', '')}"
                else:
                    mv = f"● {cur['name']} stays **{engine.stance_label(new)}**. {outcome.note or r.get('reason', '')}"
                also_note, also_moved = None, False
                for oid in r.get("also_addresses", []):
                    if engine.can_earn_secondary(flags, r["on_topic"], r["answered_the_question"]):
                        before = ss.stances[oid]
                        ss.stances[oid], ss.credit[oid], moved = engine.apply_secondary(before, ss.credit.get(oid, 0.0))
                        om = member(oid)
                        if moved:
                            ss.last_moves[oid] = 1
                            also_moved = True
                            also_note = f"➕ {om['name']} was listening too and moved to **{engine.stance_label(ss.stances[oid])}**."
                        elif before < engine.SECONDARY_CEILING:
                            also_note = f"➕ {om['name']} noted that this also answers their concern (half a step)."
                ss.transcript.append({"who": who(cur), "member": cur["id"], "kind": "reaction", "text": r["text"],
                                      "quote": r.get("case_quote", "") if r.get("quote_ok") else "", "move_note": mv,
                                      "also_note": also_note, "unverified": r.get("unverified_numbers", []),
                                      "applied": outcome.applied, "also_moved": also_moved})
                ss.history.append({"round": ss.round, "stances": dict(ss.stances)})
                if last_round:
                    ss.stage = "Self-assess"
                else:
                    ss.round += 1
                    ask_next(asking, out["next_question"])
                st.rerun()
        if leave:
            answered = sum(1 for x in ss.transcript if x["who"] == "Student")
            if answered < 3:
                st.error(f"Answer at least 3 questions before calling the vote (you've answered {answered}).")
            else:
                ss.transcript = ss.transcript[:-1] if ss.transcript and ss.transcript[-1]["kind"] == "question" else ss.transcript
                ss.stage = "Self-assess"
                st.rerun()

    with right:
        st.markdown(ui.card("Current question from", f"{cur['avatar']} {cur['name']}, {cur['role']}. "
                                                      f"Cares about: {cur['priority']}."), unsafe_allow_html=True)
        st.write("")
        with st.expander("📄 Case text", expanded=False):
            st.markdown(ss.case["text"])
        with st.expander("📝 Your worksheet"):
            st.text(ss.worksheet or "Not filled.")
        st.caption("How stances move: the AI judges whether your answer convinced the member; fixed rules then "
                   "limit it to one step, and block any gain for short, off-topic, copied or manipulative answers. "
                   "A strong answer can earn half a step from one other member whose concern it covers. Everyone "
                   "gets a question before anyone gets a second; sceptics go first.")

# ===========================================================================
# 4. SELF-ASSESS (the vote and the AI grade are both sealed)
# ===========================================================================
elif ss.stage == "Self-assess":
    ss.votes = engine.votes(ss.stances)              # decided now, revealed only after you grade yourself
    ss.verdict = engine.verdict(ss.votes)
    st.subheader("You're out of the hot seat. Score yourself before anything is revealed.")
    st.caption("The board's vote and the AI's grade are both sealed until you submit, so neither can anchor you. "
               "Pick a score for every criterion; there is no default.")
    self_scores, self_notes = {}, {}
    for r in engine.RUBRIC:
        with st.container(border=True):
            c1, c2 = st.columns([1.3, 1])
            with c1:
                st.markdown(f"**{r['name']}**")
                st.caption("  \n".join(f"**{k}** · {v}" for k, v in r["levels"].items()))
            with c2:
                self_scores[r["id"]] = st.radio("Your score", [1, 2, 3, 4, 5], index=None, horizontal=True,
                                                key=f"self_{r['id']}")
                self_notes[r["id"]] = st.text_input("Why (optional)", key=f"selfwhy_{r['id']}",
                                                    label_visibility="collapsed", placeholder="Why this score?")
    missing = [r["name"] for r in engine.RUBRIC if self_scores[r["id"]] is None]
    if st.button("Submit, then reveal the vote →", type="primary"):
        if missing:
            st.error("Score every criterion first: " + ", ".join(missing) + ".")
        else:
            ss.self, ss.self_notes = self_scores, self_notes
            student_answers = [x["text"] for x in ss.transcript if x["who"] == "Student"]
            own = guardrails.strip_copied(" ".join([ss.pitch, ss.worksheet] + student_answers), ss.case["text"])
            own_answers = [a for a in student_answers if not guardrails.is_copied(a, ss.case["text"])]
            avg_words = (sum(guardrails.words(t) for t in own_answers) / len(student_answers)) if student_answers else 0
            ss.caps = engine.rule_caps(own, ss.worksheet_filled,
                                       guardrails.case_numbers_used(own, ss.case["text"]), avg_words)
            ss.ai, ss.final, ss.calib, ss.regrades = None, {}, None, []
            if has_key() and not can_spend():
                ss.grade_error = f"this session has used its {MAX_AI_CALLS} AI calls"
            elif has_key():
                try:
                    with st.spinner("The professor is reading the transcript..."):
                        ss.ai = ai.grade(ss.case["text"], ss.case["decision_question"], ss.pitch, ss.worksheet,
                                         ss.transcript)
                    raw = {k: v["score"] for k, v in ss.ai["scores"].items()}
                    ss.final = engine.apply_caps(raw, ss.caps)
                    ss.calib = engine.calibration(ss.self, ss.final)
                    ss.sessions.append({"case": ss.case["title"], "time": datetime.now().strftime("%d %b %H:%M"),
                                        "self": ss.self, "ai": ss.final, "bias": ss.calib["bias"],
                                        "mae": ss.calib["mae"], "overall": engine.overall(ss.final),
                                        "verdict": ss.verdict[0]})
                except Exception as e:
                    ss.grade_error = str(e)[:160]
            ss.stage = "Vote"
            st.rerun()

# ===========================================================================
# 5. VOTE
# ===========================================================================
elif ss.stage == "Vote":
    st.markdown(ui.board_table(ss.board, ss.stances, votes=ss.votes, title="The board votes"), unsafe_allow_html=True)
    a, b = st.columns([1, 1.6], gap="large")
    with a:
        st.markdown(ui.verdict_banner(ss.verdict), unsafe_allow_html=True)
        st.write("")
        st.caption("Votes follow final stances: Leaning yes or Convinced votes Yes, Sceptical or Opposed votes No, "
                   "Neutral abstains. Approval needs at least two Yes votes and more Yes than No.")
    with b:
        st.markdown("**How the room moved**")
        st.altair_chart(ui.stance_journey(ss.history, ss.board), width="stretch")
    if st.button("See my debrief and the AI's grade →", type="primary"):
        ss.stage = "Debrief"
        st.rerun()

# ===========================================================================
# 6. DEBRIEF
# ===========================================================================
elif ss.stage == "Debrief":
    ai_res = ss.get("ai")
    a, b, c = st.columns([1.2, 1, 1])
    with a:
        st.markdown(ui.verdict_banner(ss.verdict), unsafe_allow_html=True)
    with b:
        st.markdown(f'<div class="br-card"><h4>AI grade</h4><div class="br-big">'
                    f'{engine.overall(ss.final) if ai_res else "–"}<span style="font-size:1rem">/100</span></div>'
                    f'<div class="br-label">Computed in code from the five criteria</div></div>', unsafe_allow_html=True)
    with c:
        lab = ss.calib["label"] if ss.calib else "–"
        sub = (f"You were {abs(ss.calib['bias']):.1f} points {'above' if ss.calib['bias'] > 0 else 'below'} the AI on average"
               if ss.calib and ss.calib["bias"] else "Self and AI scores match on average" if ss.calib else "Needs the AI grade")
        st.markdown(f'<div class="br-card"><h4>Calibration</h4><div class="br-big" style="font-size:1.6rem">{lab}</div>'
                    f'<div class="br-label">{sub}</div></div>', unsafe_allow_html=True)

    if not ai_res:
        st.warning("The AI grade isn't available"
                   + (f" ({ss.grade_error})" if ss.get("grade_error") else " (no API key)")
                   + ". Your self-assessment and the board's vote are still below and in the prep sheet.")
    else:
        st.markdown("#### You vs the AI professor")
        g1, g2 = st.columns([1.3, 1], gap="large")
        with g1:
            st.altair_chart(ui.calibration_chart(ss.self, ss.final), width="stretch")
        with g2:
            biggest = max(ss.calib["gaps"].items(), key=lambda kv: abs(kv[1]))
            name = next(r["name"] for r in engine.RUBRIC if r["id"] == biggest[0])
            if biggest[1]:
                st.markdown(ui.card("Biggest gap", f"{name}: you gave yourself {ss.self[biggest[0]]}, the AI gave "
                                    f"{ss.final[biggest[0]]}. That's the skill to watch most."), unsafe_allow_html=True)
            st.write("")
            st.markdown(ui.card("What calibration means", "Being able to tell a strong answer from a weak one in "
                                "your own work. Within ±0.6 points on average counts as well calibrated."),
                        unsafe_allow_html=True)

        st.markdown("#### Criterion by criterion")
        for r in engine.RUBRIC:
            k, item = r["id"], ai_res["scores"][r["id"]]
            capped = k in ss.caps and item["score"] > ss.caps[k][0]
            with st.expander(f"{r['name']}: you {ss.self[k]} · AI {ss.final[k]}" + ("  (capped by rule)" if capped else "")):
                st.write(item.get("why", ""))
                if capped:
                    st.info(f"The AI gave {item['score']}, capped at {ss.caps[k][0]} by a fixed rule: {ss.caps[k][1]}")
                if item.get("evidence"):
                    tag = "✅ found in your words" if item.get("evidence_ok") else "⚠️ not found in your words, treat with caution"
                    st.caption(f"Evidence: “{item['evidence']}” ({tag})")
                if ss.self_notes.get(k):
                    st.caption(f"Your reason: {ss.self_notes[k]}")

        st.markdown("#### How stable is the AI's grade?")
        st.caption("The calibration chart treats the AI's grade as the reference, but an AI can score the same "
                   "transcript differently on another run. Re-grade to measure that (one more AI call each).")
        if st.button("Re-grade the same transcript", disabled=len(ss.regrades) >= 3):
            if not can_spend():
                st.error(f"This session has used its {MAX_AI_CALLS} AI calls.")
                st.stop()
            try:
                with st.spinner("Grading again..."):
                    g2 = ai.grade(ss.case["text"], ss.case["decision_question"], ss.pitch, ss.worksheet, ss.transcript)
                ss.regrades.append(engine.apply_caps({k: v["score"] for k, v in g2["scores"].items()}, ss.caps))
            except Exception as e:
                st.error(f"The AI didn't respond ({str(e)[:100]}).")
        if ss.regrades:
            runs = [ss.final] + ss.regrades
            rows = [{"Criterion": r["name"], **{f"Run {i + 1}": run[r["id"]] for i, run in enumerate(runs)},
                     "Spread": max(run[r["id"]] for run in runs) - min(run[r["id"]] for run in runs)}
                    for r in engine.RUBRIC]
            st.dataframe(rows, hide_index=True, width="stretch")
            spread = max(r["Spread"] for r in rows)
            overall_runs = [engine.overall(run) for run in runs]
            st.markdown(f"Overall grade across runs: **{', '.join(map(str, overall_runs))}**. Largest change on one "
                        f"criterion: **{spread} point{'s' if spread != 1 else ''}**. "
                        + ("Treat calibration gaps of 1 point or less as noise." if spread >= 1 else
                           "The grade was stable on these runs."))

        x1, x2, x3 = st.columns(3)
        for col, (title, key) in zip((x1, x2, x3), (("What went well", "strengths"), ("Improve next time", "improvements"),
                                                    ("Questions to prepare for", "likely_questions"))):
            with col:
                body = "".join(f"<li>{ui.html.escape(t)}</li>" for t in ai_res.get(key, []))
                st.markdown(f'<div class="br-card"><h4>{title}</h4><ul style="margin:0;padding-left:1.1rem">{body}</ul></div>',
                            unsafe_allow_html=True)

    st.markdown("#### Key moments")
    km = engine.key_moments(ss.transcript)
    k1, k2 = st.columns(2)
    with k1:
        if km["best"]:
            m = member(km["best"]["member"])
            st.markdown(ui.moment_card("Your best answer", km["best"]["answer"][:300],
                                       f"Won over {m['name']} ({m['role']}). Do more of this.", "#2E7D5B"),
                        unsafe_allow_html=True)
        else:
            st.markdown(ui.card("Your best answer", "No answer moved anyone up this time. Next time, tie each answer "
                                "to the member's stated concern and back it with a case figure."), unsafe_allow_html=True)
    with k2:
        if km["worst"]:
            m = member(km["worst"]["member"])
            st.markdown(ui.moment_card("Your costliest answer", km["worst"]["answer"][:300],
                                       f"Lost ground with {m['name']} ({m['role']}). Ask yourself what they needed to hear.",
                                       "#B4432F"), unsafe_allow_html=True)
        else:
            st.markdown(ui.card("Your costliest answer", "No answer cost you ground. Good discipline."),
                        unsafe_allow_html=True)

    st.markdown("#### How the room moved")
    st.altair_chart(ui.stance_journey(ss.history, ss.board), width="stretch")

    st.markdown("#### Your calibration over time")
    hist_up = st.file_uploader("Add earlier meetings (a hotseat_history.json you downloaded before)", type="json")
    if hist_up is not None and not ss.get("_hist_loaded") == hist_up.file_id:
        try:
            old = json.loads(hist_up.getvalue())
            ok = []
            for item in old if isinstance(old, list) else []:
                try:
                    ok.append({"case": str(item["case"])[:120], "time": str(item.get("time", "")),
                               "bias": max(-4.0, min(4.0, float(item["bias"]))),
                               "mae": max(0.0, min(4.0, float(item["mae"]))),
                               "overall": int(item.get("overall", 0)), "verdict": str(item.get("verdict", ""))})
                except (KeyError, TypeError, ValueError):
                    continue
            ss.sessions = ok + ss.sessions
            ss._hist_loaded = hist_up.file_id
            st.toast(f"Added {len(ok)} earlier meeting(s).")
            st.rerun()
        except Exception:
            st.error("That file isn't a HotSeat history file.")
    if len(ss.sessions) >= 2:
        st.altair_chart(ui.calibration_history(ss.sessions), width="stretch")
        st.caption("Above zero means you graded yourself higher than the AI did. The green band is well calibrated.")
    elif ss.sessions:
        st.caption("Run another meeting (or load your history file) to see the trend. One point isn't a trend.")

    st.markdown("#### Take it with you")
    sheet = {"case": ss.case, "board": ss.board, "start": ss.history[0]["stances"], "mood": ss.get("mood", "Standard"), "pitch": ss.pitch, "worksheet": ss.worksheet,
             "transcript": ss.transcript, "stances": ss.stances, "votes": ss.votes, "verdict": ss.verdict,
             "self": ss.self, "ai": ai_res, "final": ss.final, "calib": ss.calib}
    html_doc, md_doc = prepsheet.build(sheet)
    slug = ss.case["id"]
    d1, d2, d3 = st.columns(3)
    d1.download_button("📄 Prep sheet (HTML, print to PDF)", html_doc, f"hotseat_{slug}.html", "text/html",
                       type="primary", width="stretch")
    d2.download_button("📝 Prep sheet (Markdown)", md_doc, f"hotseat_{slug}.md", "text/markdown", width="stretch")
    d3.download_button("📈 Calibration history (JSON)", json.dumps(ss.sessions, indent=2), "hotseat_history.json",
                       "application/json", width="stretch", disabled=not ss.sessions)
    st.write("")
    n1, n2 = st.columns(2)
    if n1.button("↺ Present the same case again", width="stretch"):
        reset_meeting(keep_case=True)
        st.rerun()
    if n2.button("🗂️ Try another case", width="stretch"):
        reset_meeting(keep_case=False)
        st.rerun()
