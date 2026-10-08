"""Visual pieces for HotSeat: CSS, the board table, stage stepper and charts."""
from __future__ import annotations

import html

import altair as alt
import pandas as pd

from . import engine

INK, EMBER, MUTED = "#16181D", "#E4572E", "#6B7280"
STANCE_COLORS = {-2: "#B4432F", -1: "#D9822B", 0: "#9AA3AF", 1: "#6BA368", 2: "#2E7D5B"}
VERDICT_COLORS = {"Approved": "#2E7D5B", "Rejected": "#B4432F", "Sent back for more work": "#D9822B"}
STAGES = ["Case", "Prepare", "Boardroom", "Self-assess", "Vote", "Debrief"]
STAGE_LABELS = {"Case": "1 · Case", "Prepare": "2 · Prep", "Boardroom": "3 · Hot seat",
                "Self-assess": "4 · Self-score", "Vote": "5 · Verdict", "Debrief": "6 · Debrief"}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600;9..144,800&family=Inter:wght@400;500;600;700&display=swap');
html, body, .stApp, .stMarkdown, label, input, textarea, button { font-family: 'Inter', system-ui, sans-serif; }
.block-container { padding-top: 1.3rem; max-width: 1240px; }
@keyframes br-rise { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: none; } }
@keyframes br-glow { 0%,100% { box-shadow: 0 0 0 2px #E4572E, 0 0 18px rgba(228,87,46,.35); } 50% { box-shadow: 0 0 0 2px #E4572E, 0 0 30px rgba(228,87,46,.7); } }
@keyframes br-pop { 0% { transform: scale(.6); opacity: 0; } 70% { transform: scale(1.08); } 100% { transform: scale(1); opacity: 1; } }
@keyframes br-flip { from { transform: rotateY(90deg); opacity: 0; } to { transform: none; opacity: 1; } }

.br-hero { border-radius: 18px; padding: 1.45rem 1.8rem 1.25rem; margin-bottom: .9rem; color: #F3EEE4;
  background: radial-gradient(1200px 300px at 85% -40%, rgba(228,87,46,.45), transparent 60%),
              linear-gradient(135deg, #121418 0%, #1C2027 60%, #2A1712 100%);
  animation: br-rise .5s ease-out; }
.br-hero h1 { font-family: 'Fraunces', Georgia, serif; font-weight: 800; font-size: 2.4rem; letter-spacing: -.02em;
  margin: 0; padding: 0; color: #FFF4EE; }
.br-hero h1 em { font-style: normal; color: #FF9F68; }
.br-hero p { color: #C9C3B8; margin: .3rem 0 .8rem; max-width: 780px; font-size: 1rem; }
.br-chip { display: inline-block; border: 1px solid rgba(255,159,104,.35); border-radius: 999px; padding: .2rem .7rem;
  margin: 0 .35rem .3rem 0; font-size: .8rem; color: #F4D8CC; background: rgba(255,255,255,.04); }

.br-chip-light { display: inline-block; font-size: .72rem; font-weight: 700; letter-spacing: .04em;
  text-transform: uppercase; color: #9C3A20; background: #FBE3D9; border-radius: 999px; padding: .15rem .6rem; }
.br-steps { display: flex; gap: .35rem; margin: .2rem 0 1rem; flex-wrap: wrap; }
.br-step { flex: 1; min-width: 92px; text-align: center; font-size: .78rem; font-weight: 600; color: #9AA3AF;
  padding: .45rem .3rem; border-radius: 8px; background: #F3F4F6; position: relative; }
.br-step.done { background: #FBE3D9; color: #9C3A20; }
.br-step.now { background: #16181D; color: #FFD9C7; }

.br-table { border-radius: 22px; border: 1px solid #3A2A24; padding: 1.1rem; margin: .4rem 0 1rem;
  background: radial-gradient(ellipse at center, #2E2624 0%, #141211 70%); box-shadow: inset 0 0 40px rgba(0,0,0,.35); }
.br-table-title { color: #E9CFC4; text-align: center; font-family: 'Fraunces', serif; font-size: .95rem; letter-spacing: .06em;
  text-transform: uppercase; margin-bottom: .7rem; }
.br-seats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: .75rem; }
@media (max-width: 900px) { .br-seats { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
.br-seat { background: #FFFAF7; border-radius: 14px; padding: .75rem .8rem; animation: br-rise .45s ease-out both;
  transition: transform .2s; }
.br-seat.speaking { animation: br-glow 1.8s ease-in-out infinite; transform: translateY(-3px); }
.br-ava { width: 42px; height: 42px; border-radius: 50%; display: grid; place-items: center; font-size: 1.35rem;
  background: #16181D; margin-bottom: .35rem; }
.br-name { font-weight: 700; font-size: .92rem; color: #16181D; line-height: 1.2; }
.br-role { font-size: .76rem; color: #6B7280; margin-bottom: .45rem; min-height: 2em; }
.br-pips { display: flex; gap: 3px; margin: .25rem 0 .2rem; }
.br-pip { flex: 1; height: 7px; border-radius: 4px; background: #ECE4E0; }
.br-stance { font-size: .78rem; font-weight: 700; }
.br-move { font-size: .72rem; font-weight: 700; margin-left: .3rem; animation: br-pop .5s ease-out; display: inline-block; }
.br-lens { font-size: .7rem; color: #B5452A; margin-top: .3rem; }
.br-vote { margin-top: .45rem; font-weight: 800; font-size: .9rem; padding: .2rem .5rem; border-radius: 6px;
  display: inline-block; color: #fff; animation: br-flip .6s ease-out both; }

.br-verdict { border-radius: 16px; padding: 1.1rem 1.3rem; color: #fff; animation: br-pop .6s ease-out;
  font-family: 'Fraunces', serif; }
.br-verdict b { font-size: 1.8rem; display: block; }
.br-card { border: 1px solid #F0E6E1; border-radius: 14px; padding: .9rem 1rem; background: #fff; height: 100%;
  animation: br-rise .4s ease-out both; }
.br-card h4 { margin: 0 0 .35rem; font-size: .74rem; letter-spacing: .08em; text-transform: uppercase; color: #B5452A; }
.br-card p { margin: 0; font-size: .95rem; line-height: 1.45; color: #16181D; }
.br-quote { font-size: .8rem; color: #6B7280; margin-top: .35rem; border-left: 3px solid #FF9F68; padding-left: .5rem; }
.br-big { font-family: 'Fraunces', serif; font-size: 2.6rem; font-weight: 800; color: #16181D; line-height: 1; }
.br-label { font-size: .8rem; color: #6B7280; }
</style>
"""


def hero(has_key: bool, label: str = "AI") -> str:
    return f"""
<div class="br-hero">
  <h1>Hot<em>Seat</em> <span style="font-size:1.6rem">🔥</span></h1>
  <p>Take the hot seat and defend your case recommendation to a board that pushes back. Four members,
     four agendas, Socratic questions through SWOT and Porter's lenses. Earn their votes, score yourself,
     then find out how well you judged your own performance.</p>
  <span class="br-chip">🎯 Socratic, never gives answers</span><span class="br-chip">🧭 SWOT and Porter lenses</span>
  <span class="br-chip">🌡️ Choose how tough the board is</span><span class="br-chip">🪞 Self vs AI calibration</span>
  <span class="br-chip">{f'🟢 {label} connected' if has_key else '🟡 Offline: scripted questions only'}</span>
</div>"""


def stepper(current: str) -> str:
    i = STAGES.index(current)
    cells = "".join(f'<div class="br-step {"done" if j < i else "now" if j == i else ""}">'
                    f'{"✓ " if j < i else ""}{STAGE_LABELS[s]}</div>' for j, s in enumerate(STAGES))
    return f'<div class="br-steps">{cells}</div>'


def board_table(board, stances, speaking=None, last_moves=None, votes=None, title="The board", hidden=False) -> str:
    seats = ""
    for i, m in enumerate(board):
        s = stances[m["id"]]
        if hidden:
            spk = " speaking" if m["id"] == speaking else ""
            seats += (f'<div class="br-seat{spk}" style="animation-delay:{i * .07:.2f}s">'
                      f'<div class="br-ava">{html.escape(m["avatar"])}</div><div class="br-name">{html.escape(m["name"])}</div>'
                      f'<div class="br-role">{html.escape(m["role"])}</div><div class="br-pips">'
                      + '<div class="br-pip"></div>' * 5 + '</div><span class="br-stance" style="color:#9AA3AF">Hidden</span>'
                      f'<div class="br-lens">{html.escape(m["lens"])}</div></div>')
            continue
        pips = "".join(f'<div class="br-pip" style="background:{STANCE_COLORS[v] if v <= s else "#ECE4E0"}"></div>'
                       for v in range(-2, 3))
        mv = (last_moves or {}).get(m["id"])
        move = ""
        if mv:
            move = f'<span class="br-move" style="color:{"#2E7D5B" if mv > 0 else "#B4432F"}">{"▲" if mv > 0 else "▼"}</span>'
        vote = ""
        if votes:
            v = votes[m["id"]]
            vc = {"Yes": "#2E7D5B", "No": "#B4432F", "Abstain": "#9AA3AF"}[v]
            vote = f'<div class="br-vote" style="background:{vc};animation-delay:{.25 + i * .35:.2f}s">{v}</div>'
        seats += f"""
<div class="br-seat{' speaking' if m['id'] == speaking else ''}" style="animation-delay:{i * .07:.2f}s">
  <div class="br-ava">{html.escape(m['avatar'])}</div>
  <div class="br-name">{html.escape(m['name'])}</div>
  <div class="br-role">{html.escape(m['role'])}</div>
  <div class="br-pips">{pips}</div>
  <span class="br-stance" style="color:{STANCE_COLORS[s]}">{engine.stance_label(s)}</span>{move}
  <div class="br-lens">{html.escape(m['lens'])}</div>{vote}
</div>"""
    return f'<div class="br-table"><div class="br-table-title">{html.escape(title)}</div><div class="br-seats">{seats}</div></div>'


def card(title, body, quote=None, delay=0.0, border=None) -> str:
    q = f'<div class="br-quote">From the case: “{html.escape(quote)}”</div>' if quote else ""
    style = f"animation-delay:{delay:.2f}s;" + (f"border-left:4px solid {border};" if border else "")
    return f'<div class="br-card" style="{style}"><h4>{html.escape(title)}</h4><p>{html.escape(body)}</p>{q}</div>'


def verdict_banner(v: tuple[str, str]) -> str:
    return (f'<div class="br-verdict" style="background:{VERDICT_COLORS[v[0]]}">'
            f'<span style="opacity:.85;font-family:Inter">The board has voted</span><b>{v[0]}</b>'
            f'<span style="font-family:Inter">{v[1]}</span></div>')


def _axis(c):
    return c.configure_view(strokeWidth=0).configure_axis(grid=False, labelColor=MUTED, titleColor=MUTED,
                                                          domainColor="#E5E7EB", tickColor="#E5E7EB")


def calibration_chart(self_scores: dict, ai_scores: dict):
    rows = []
    for r in engine.RUBRIC:
        k = r["id"]
        rows += [{"Criterion": r["name"], "Who": "You", "Score": self_scores[k]},
                 {"Criterion": r["name"], "Who": "AI professor", "Score": ai_scores[k]}]
    d = pd.DataFrame(rows)
    order = [r["name"] for r in engine.RUBRIC]
    y = alt.Y("Criterion:N", sort=order, title=None, axis=alt.Axis(labelLimit=220))
    rule = alt.Chart(d).mark_rule(strokeWidth=3, color="#F3D3C6").encode(
        y=y, x=alt.X("min(Score):Q", scale=alt.Scale(domain=[0.5, 5.5]), title="Score (1-5)"), x2="max(Score):Q")
    pts = alt.Chart(d).mark_circle(size=260, opacity=1).encode(
        y=y, x="Score:Q",
        color=alt.Color("Who:N", scale=alt.Scale(domain=["You", "AI professor"], range=[EMBER, INK]),
                        legend=alt.Legend(orient="top", title=None)),
        tooltip=["Criterion", "Who", "Score"])
    return _axis(alt.layer(rule, pts).properties(height=260))


def stance_journey(history: list[dict], board: list[dict]):
    names = {m["id"]: m["name"] for m in board}
    d = pd.DataFrame([{"Round": h["round"], "Member": names[k], "Stance": v}
                      for h in history for k, v in h["stances"].items()])
    return _axis(alt.Chart(d).mark_line(point=alt.OverlayMarkDef(size=70), strokeWidth=3, interpolate="monotone").encode(
        x=alt.X("Round:O", title="Round (0 = before you spoke)"),
        y=alt.Y("Stance:Q", scale=alt.Scale(domain=[-2.2, 2.2]),
                axis=alt.Axis(values=[-2, -1, 0, 1, 2], labelExpr="['Opposed','Sceptical','Neutral','Leaning yes','Convinced'][datum.value+2]"),
                title=None),
        color=alt.Color("Member:N", legend=alt.Legend(orient="bottom", title=None)),
        tooltip=["Member", "Round", "Stance"]).properties(height=280))


def calibration_history(sessions: list[dict]):
    d = pd.DataFrame([{"Session": i + 1, "Case": s["case"], "Bias": s["bias"], "Gap": s["mae"]}
                      for i, s in enumerate(sessions)])
    zero = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(strokeDash=[5, 4], color="#9AA3AF").encode(y="y:Q")
    line = alt.Chart(d).mark_line(point=alt.OverlayMarkDef(size=90), strokeWidth=3, color=EMBER).encode(
        x=alt.X("Session:O"), y=alt.Y("Bias:Q", title="Self minus AI (avg points)", scale=alt.Scale(domain=[-2.5, 2.5])),
        tooltip=["Session", "Case", "Bias", "Gap"])
    band = alt.Chart(pd.DataFrame({"y": [-0.4], "y2": [0.4]})).mark_rect(opacity=.12, color="#2E7D5B").encode(y="y:Q", y2="y2:Q")
    return _axis(alt.layer(band, zero, line).properties(height=230))


def moment_card(title: str, quote: str, effect: str, color: str) -> str:
    return (f'<div class="br-card" style="border-left:4px solid {color}"><h4>{html.escape(title)}</h4>'
            f'<p style="font-style:italic">“{html.escape(quote)}”</p>'
            f'<div class="br-quote" style="border-color:{color}">{html.escape(effect)}</div></div>')
