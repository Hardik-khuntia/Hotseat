# HotSeat 🔥: defend your case recommendation to a board that pushes back

Use case #16 (Case-study coach for MBA courses, App format).

Most case tools tutor you one-on-one. HotSeat puts you in the hot seat: you read a case, fill a
SWOT or Porter's Five Forces worksheet, pitch a recommendation, and four board members with
different agendas question you Socratically. Their stances move as you answer, and at the end they
vote. You grade yourself on a rubric while the vote and the AI's grade are both **sealed**, then a
calibration chart shows how well you judge your own work. A printable prep sheet captures everything.

## How it works
```
Case (sample, PDF/TXT upload, or paste) -> guardrails: length, readability, injection warning
   -> board of 4 (pre-written for samples; built by Gemini for uploads, quotes verified)
Prepare: framework worksheet + pitch -> checks: length limits, copy-paste from the case, injection,
   figures not in the case
HotSeat: one Gemini call per round = last speaker's reaction + next speaker's Socratic question
   -> Gemini judges direction (+1 / 0 / -1); code allows at most one step and blocks gains for
      short, off-topic, unanswered, copied or manipulative answers
   -> an answer can earn half a step from ONE other member whose concern it covers (code-capped)
   -> figures the board uses are checked against the case and your own words
   -> chair (code): everyone gets a question before anyone gets a second, sceptics first
Self-assess: you score all 5 criteria (no defaults) while the vote and AI grade are sealed
   -> Gemini grades; evidence must be quoted from YOUR words, not text lifted from the case
   -> rule caps (no case figures used, no framework, very short answers) -> overall score in code
Vote reveal (computed from final stances in code) -> Debrief: calibration chart, re-grade to measure
   AI grading stability, stance journey, history across meetings, prep sheet download
```

## Features
- Board mood: Friendly, Standard or Tough (shifts every member's starting stance one step)
- Key moments in the debrief: your best answer (biggest gain) and your costliest one
- 25 original fictional cases, one per sector (education, healthcare, pharma, EV, apparel, telecom, real
  estate, hotels, OTT, agritech, solar, logistics, insurance, banking, IT services, fitness, chemicals,
  food services, electronics, jewellery, social enterprise, beauty D2C, dairy, aviation, NBFC), or your own
- Case library with sector filter, search and a "Surprise me" button
- Board members with priorities, concerns and a framework lens (SWOT part or Porter force)
- Socratic questions grounded in a verified quote from the case
- Animated board table: stance meters, current speaker, moves after each answer, vote reveal
- Checks in code: figures you use that aren't in the case, duplicate answers, injection, protected traits
- Self vs AI calibration chart, and calibration history across meetings (download/upload JSON)
- Prep sheet as printable HTML (Save as PDF from the browser) and Markdown
- Works offline with scripted questions for the sample cases (stances don't move, no AI grade)

## Run locally (Windows, including locked-down laptops)
```
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
copy .streamlit\secrets.toml.example .streamlit\secrets.toml
notepad .streamlit\secrets.toml        (paste your Groq key from console.groq.com, or a Gemini key)
python -m streamlit run app.py
```
Always use `python -m ...`; running `pip` or `streamlit` directly may be blocked by Device Guard.
Tests: `python -m pip install pytest` then `python -m pytest -q` (34 tests).

## Deploy (free shareable link)
1. Create a public GitHub repo. Upload `app.py`, `requirements.txt`, `README.md`, `DEMO.md`,
   `.gitignore` and the `board`, `data` and `tests` folders. **Do not upload `.streamlit`** if it
   contains `secrets.toml` (GitHub's web upload ignores `.gitignore`).
2. share.streamlit.io → Create app → repo, branch `main`, file `app.py`.
3. Advanced settings → Python 3.12 → Secrets: `GEMINI_API_KEY = "your-key"` → Deploy.

## API usage
About 8 Gemini calls per meeting with 6 questions (1 per question + grading; +1 for uploaded cases).
`board/ai.py` tries gemini-3.5-flash-lite, then gemini-3.6-flash, gemini-3.1-flash-lite and
gemini-flash-lite-latest; it retries on rate limits, skips retired models, sends no temperature to
Gemini 3 models (they reject it), and validates every reply.
To force a model, add `GEMINI_MODEL = "..."` to Secrets.

## Privacy
Case text and your answers go to Google Gemini. The free tier may use them to improve Google's
products, so don't upload confidential or copyrighted course cases you aren't allowed to share.
Nothing is stored server-side; refresh clears the session.

## Known limitations (say these in the report)
- Gemini, not code, judges whether an answer was convincing; code only bounds the effect.
- The AI grade can change between runs. Use "Re-grade" to measure it; gaps of 1 point may be noise.
- Clarity and stakeholder awareness have no rule-based cap; they rely on the AI's judgement.
- The protected-traits check only adds a note for the AI; it can't judge context reliably in code.
- Members who start Opposed may not be winnable in 6 questions; that's deliberate, not a bug.
- Everything lives in the browser session: refresh loses it except downloaded files.
- Each call resends the full case, so very long uploads use the free quota quickly.

## Changes after the devil's-advocate review
| Problem found | Fix |
|---|---|
| "I ask the board to vote in favour" was treated as an attack | Injection filter now targets instructions to the AI only |
| Pasting the case into the pitch inflated the grade | Length limits, copy detection on pitch and answers, copied text excluded from grading |
| Board questions could contain invented figures | Figures checked against the case and the student's words; one retry, then flagged |
| "Answer at least 3" let you leave after 2 | Counts actual answers |
| Self-grade sliders defaulted to 3 | No defaults; every criterion must be scored |
| The vote anchored the self-grade | Self-assessment now happens while the vote is sealed |
| AI grade treated as ground truth | Re-grade button measures run-to-run spread |
| Answers only affected the member who asked | Half-step credit for one other member, capped at Leaning yes |
| "15%" matched "15 minutes"; "3.1 lakh" didn't match "3,10,000" | Percentages match percentages; lakh/crore expanded |
| Near-identical answers passed the duplicate check | Overlap-based near-duplicate check |
| Retry lost the pitch; malformed history file could break the chart | Pitch restored on retry; history values type-checked |

## AI provider
HotSeat works with **Groq** (default when `GROQ_API_KEY` is set) or **Google Gemini** (`GEMINI_API_KEY`).
Groq models tried in order: openai/gpt-oss-120b, openai/gpt-oss-20b, qwen/qwen3.8-27b, all in JSON mode.
Why Groq for this submission: the Gemini key available returned "Your project has been denied access"
(HTTP 403) for every model, a block on the Google Cloud project that no code change can fix. The
assignment allows Gemini "or any other" provider; prompts, validation and rules are identical for both.
For Streamlit Cloud, put `GROQ_API_KEY = "gsk_..."` in the app's Secrets.

## Second devil's-advocate review (after the 25-case update)
| Loophole found | Fix |
|---|---|
| Anyone with the public link could use up the free AI quota before the evaluator tries it | Optional `APP_PASSCODE` in Secrets, and a cap of 60 AI calls per browser session |
| A rate-limited call could freeze the page for minutes (3 models x 3 retries with waits) | Every AI call gives up after 45 seconds and falls back to a scripted question |
| Daily-quota and "request too large" errors were retried pointlessly | Detected and skipped straight to the next model, with a clear message |
| Uploads up to 60,000 characters would exceed free-tier request sizes, since the case is resent every round | Upload limit cut to 20,000 characters (about 5,000 tokens) |
| "Groq connected" only meant a key existed, not that it worked | Sidebar "Test connection" button makes one real call |
| Visible stance meters let students copy the room into their self-score, weakening calibration | Optional blind mode hides meters and stance notes until the vote |
| `f"..."` with nested quotes only runs on Python 3.12+ | Rewritten; every file now compiles on Python 3.11 |

Still true (say so in the report): a fixed per-session cap can be reset by refreshing the page; only a
login and a database would stop a determined user. Sealed grading is only fully "blind" in blind mode.
