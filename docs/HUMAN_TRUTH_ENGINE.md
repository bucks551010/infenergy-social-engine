# HUMAN TRUTH ENGINE v2 — Preemptive Content, Prompt-First Visuals, Earned Trust

> **Opus, agent mode, terminal access, effort HIGH.**
> **Save as:** `docs/HUMAN_TRUTH_ENGINE.md`
> **Do not begin until Phase 0 confirms production publishes.**
> Paste **PERMANENT CONTEXT + one phase at a time.** Fresh session per phase.

---

# PART I — THE PHILOSOPHY

## 1. The root inversion

The system currently generates from **facts**. Content that moves people generates from
**tension**.

```
CURRENT:  product → verified fact → safe claim → copy → image prompt derived from caption
TARGET:   human tension → real moment → what's at stake → what we truly know
          → does a product even belong here? → copy AND image prompt born from the same scene
```

This is a change of root, not of style.

**Why it also dissolves the current bottleneck:** a human tension makes *no factual claim*. It
cannot trigger `RESEARCH_REQUIRED`, cannot fail claim validation, cannot collapse under evidence
review. Tension-first generation does not merely produce better content — it produces content
the evidence system has no reason to block.

## 2. The business truth

This business does not sell watt-hours. It sells **the opposite of helplessness**.

The audience is not hypothetical. Gulf Coast households lived Harvey, Beryl, and Uri. In
February 2021 people died in their homes when the grid failed. The root sensation of this brand
is the moment the fridge stops humming and the house goes quiet. Everyone here knows that
silence.

Content that starts there will always outperform content that starts at a spec sheet.

## 3. THE PREEMPTIVE DOCTRINE — the governing principle of this entire build

> **Resolve every problem at the cheapest, earliest point where it can be resolved.**

Every failure this system has suffered came from discovering a constraint *after* paying for the
work. Blind selection collided after generation. Images were rendered before gates ran. Claims
were invented and then policed.

Apply preemption at every layer:

| Instead of | Do this |
|---|---|
| Generate, then check the claim | Start inside a known-safe claim envelope |
| Render an image, then review it | **Validate the image prompt before rendering** |
| Pick a product, then detect collision | Select only from eligible, non-recent options |
| Discover a knowledge gap at publish | Pre-resolve gaps into the package upstream |
| Write seasonal content when the season hits | **Pre-stage it weeks ahead** |
| Notice staleness in the feed | Track novelty telemetry before it degrades |
| Learn a post failed after publishing | Score craft mechanics before it enters the pool |

**Cost gradient — always fail left, never right:**

```
selection (free) → text generation (cents) → validation (free) → prompt construction (free)
  → prompt governance (free) → image render (expensive, rate-limited) → publish (reputational)
```

Nothing expensive or public may be reached by content that could have been stopped earlier.

## 4. THE READER VALUE CONTRACT — every post must earn its place

A post that does not pass all five is not publishable, regardless of score:

| Test | Question |
|---|---|
| **Useful** | Does someone leave knowing or able to do something they couldn't before? |
| **Captivating** | Does it hold attention past the first line, without a cheap hook? |
| **Caring** | Does it demonstrate we understand their actual situation? |
| **For them** | Is it oriented to the reader's need, not our sales need? |
| **Trust-building** | Does it make buying from us feel *safer*, not riskier? |

> **The standard:** someone should be glad they saw it even if they never buy anything.
> That is what makes them buy eventually.

Score all five. Store as telemetry. Correlate with real engagement in Phase 6.

## 5. TRUST ARCHITECTURE — how people come to feel safe buying

Trust is not a tone. It is a set of behaviors, and each is buildable:

- **State honest limits.** Say what the product cannot do, plainly and unprompted. Nothing
  builds credibility faster, and nothing is rarer in this category.
- **Show real specificity.** Exact numbers with provenance. Vagueness reads as hiding.
- **Answer the hard question** — the one a skeptical buyer would ask before purchasing.
- **Be useful before asking.** Value delivered before any request is made.
- **Never overclaim.** One caught exaggeration destroys more trust than ten good posts build.
- **Be consistently present.** Reliability is itself a trust signal. Silent slots cost trust.
- **Handle objections in the open**, not by avoiding them.

Build a `trust_signals` dimension into content jobs so this is generated deliberately rather
than hoped for.

## 6. THE STATIC / LIVING SPLIT — a governance boundary, not organization

| | **STATIC** | **LIVING** |
|---|---|---|
| Contains | Human truth, brand truth, boundaries, visual identity, prompt craft rules | Usage, freshness, performance, proposals, seasonal state |
| Author | **Owner only. Human-written.** | System-written, bounded |
| AI access | **READ ONLY — never writes** | Read + write |
| Changes | Rarely, deliberately | Continuously |
| If corrupted | Brand voice is lost permanently | Recoverable by replay |

> **An AI that can edit its own definition of truth has no definition of truth.**
> Enforce this in code with a guard test, not by convention.

The living repository may **propose** additions to the static repository. It may never write
them.

## 7. The rule that keeps it human

> **You cannot synthesize human connection. You can only store it and draw from it.**

Generic is the default failure mode of AI content. Specificity is the only cure, and real
specificity must come from a real person. That is what the Human Material Reserve exists for.

## 8. The rule that keeps it alive

> **A repository defines the BOUNDARY, never the CONTENT.**

It describes where safe, valuable creative territory *is*. It must never hold a phrase, hook, or
caption the generator can lift. Every field must pass: *does this expand what the generator may
explore, or narrow what it may say?* Build only the first kind.

---

# PART II — PERMANENT CONTEXT (paste with every phase)

## The system

Python 3.12 autonomous social publishing engine on Railway. Three posts daily (13:00 / 17:00 /
23:00 UTC) via Google Gemini, publishing to Facebook, Instagram, LinkedIn. Business sells
**portable power stations and charging accessories**. Location: Spring, TX — Gulf Coast.

`scripts/` is on `sys.path`: imports are `from conversion.engine import ...`, never
`from scripts.conversion.engine import ...`.

## Confirmed state — carry forward, do not re-derive

- Recent slots scored **97–98.5**, passed validation and governance, and were skipped by the
  duplicate gate. **Content quality is not the bottleneck.**
- `e3b05ef` made exact-caption the only blocking duplicate signal; others are advisory.
- **Root cause of the prior week:** `anti_repeat_config.json` was never authoritative — code
  hard-blocked regardless of config. **Always verify code reads a config before tuning it.**
- Rotation, candidate pool, deferred image generation, product eligibility: built and tested
  (388 passed). **Live status unconfirmed.**
- 13 of 49 catalog products have zero `verified_facts` and are excluded from selection.
- Existing brand assets may be underused: `founder_brand_manifesto.json`,
  `business_intelligence/brand.py`, `audience.py`, `profile.py`, `personas.json`,
  `transformations.json`, `objection_library.json`. **Determine whether generation reads them.**
- Claim governance fails closed on `RESEARCH_REQUIRED` and `HIGH_RISK_UNVERIFIED`.
- **Local has no Gemini key** — local runs fall back to templates the critic correctly rejects.
  **Railway is the only valid content and image verification environment.**
- `data/` persistence unconfirmed. Both repositories will live there.
- Local `master` is 85 commits behind `origin/master` and dirty. **Never build from, clean, or
  merge into it.**
- **Hurricane season peaks in roughly three weeks.**

---

# PHASE 0 — CONFIRM PUBLISHING (hard gate)

Starting new architecture on an unverified system is the exact pattern that has cost multiple
cycles. Do not skip this.

1. Report what is actually on deployed `master` — only `e3b05ef`, or the full pool/rotation
   rebuild? Give the SHA and contents.
2. Confirm Railway restarted on that SHA; report `/status`.
3. **Confirm a scheduled slot published to at least one platform**, with a receipt written and
   run status `published` — not `blocked_no_publish`.
4. **Confirm `data/` survives redeploy.** Check that `candidate_pool.json` and history persist
   across a restart. If they do not, **stop and escalate** — neither repository will persist and
   this entire plan is void.

## 🛑 GATE 0 — no proof of publishing, no further work.

---

# PHASE 1 — THE STATIC REPOSITORY

**Build the structure and the intake. Do not write the human content.** Every human entry comes
from the owner, verbatim.

## 1.1 Human Material Reserve — the highest-value asset in the system

Raw, unpolished, first-person material only the owner can supply:

- **Lived memories** — Uri, Harvey, Beryl. What it sounded like, smelled like, how long it
  lasted, what broke, what he wished he'd had.
- **Founder origin** — the honest reason this business exists.
- **Customer voice** — verbatim quotes, questions, complaints, thank-yous. Never paraphrased.
- **Local knowledge** — what only someone in this region would know.
- **Convictions** — what the owner believes about preparedness, self-reliance, family.

Rules:
- Stored **verbatim**. Never rewritten, summarized, or "improved" on intake.
- The generator may **draw from and adapt** it — that is its purpose.
- It must never contain a finished caption or hook ready to paste.
- Every entry carries provenance and consent-to-use.

Generate `docs/HUMAN_MATERIAL_INTAKE.md` — a plain-language sheet the owner fills in. Ask for
raw and specific, explicitly not polished.

## 1.2 Tension Library

The specific, felt contradictions this audience already carries. Examples of the *shape*:

- "I'm the one everyone will look to, and I've done nothing."
- "I don't want to be the doomsday guy. I just don't want to be caught out."
- "We say we'll get ready before hurricane season every single year."
- "The kids think it's an adventure until hour six."

Each entry: the tension · who feels it · when it surfaces · what is genuinely at stake · whether
a product is relevant at all (often: no).

**A tension makes no factual claim.** That is precisely the point.

## 1.3 Brand Truth

Derive from `founder_brand_manifesto.json` and the BI brand modules — **do not invent.** If they
are thin, report exactly what is missing and request it.

Positions held · positions refused · voice boundaries · **the mission expressed as territory**:

> "Nobody should lose power to their life" → outage preparedness · staying connected · work
> continuity · family safety · what to do before a storm

None requires a SKU. All are unmistakably this brand.

## 1.4 Visual Identity + Prompt Craft Rules

The static half of the image system. Owner-supplied, AI read-only:

- Palette, light quality, time of day, grain, texture
- Framing and composition preferences
- **Real regional environments** — Gulf Coast homes, garages, trucks, kitchens. Not generic
  stock settings.
- **Never-appears list** — glossy studio product on white · stock-photo smiling families ·
  disaster spectacle · anything implying a capability the product lacks
- Approved product photography references
- **Prompt craft rules** — house style for how prompts are constructed (see Phase 4)

## 1.5 Reader Value + Trust definitions

Store the five Reader Value tests and the seven Trust behaviors as scored, versioned criteria —
not prose in a README. They must be machine-checkable.

## 1.6 Enforce read-only in code

Any write attempt to the static repository must fail loudly and log. Add a guard test.

## 🛑 GATE 1 — schema · intake docs · read-only enforcement · report of what already exists
in brand files versus what the owner must supply.

---

# PHASE 2 — TENSION-FIRST GENERATION

## 2.1 Invert the flow

```
select tension (rotation-aware, from static repo)
  → select moment / trigger (seasonal, weather, calendar, audience question)
    → name what is at stake
      → draw specificity from Human Material Reserve
        → decide: does a product belong here? (often NO)
          → if yes: pull verified facts + safe claim envelope
            → generate copy
              → derive ART DIRECTION FROM THE SAME TENSION (never from the caption)
```

**Critical:** art direction derives from the tension and scene, **never from the finished
caption.** Caption-derived prompts produce literal, lifeless images. Scene-derived prompts carry
the same emotional root as the words.

## 2.2 The Job dimension

Same material, different job, entirely different post:

`teach` · `reassure` · `correct a misconception` · `answer a real question` · `take a position` ·
`demonstrate` · `tell a story` · **`state an honest limit`** · **`answer the skeptic`**

The last two exist specifically to build trust.

Territory × Job × Persona × Moment yields hundreds of genuinely distinct starting points —
multiplication, not enumeration.

## 2.3 Craft mechanics — scored, not vibes

| Mechanic | Question |
|---|---|
| **Tension** | Is there an unresolved gap pulling the reader forward? |
| **Stakes** | Is what's at risk named concretely? |
| **Specificity** | One sensory detail proving a human was there? |
| **Recognition** | Will someone feel *seen* rather than sold to? |
| **Reframe** | Does it turn something the reader already believes? |
| **Takeaway** | Can the reader *do* something with this? |

`Reframe` is what makes people think. `Takeaway` is what makes them save it.

## 2.4 Reader Value + Trust gates

Score every candidate against the five Reader Value tests and detect which Trust behaviors it
exhibits. **A candidate failing Reader Value does not enter the pool**, regardless of critic
score — this is preemption: reject worthless content before it costs an image render.

## 2.5 Content mix

Roughly **40% product · 40% education and human situation · 20% brand point of view.**

Report: the schedule maps morning→awareness, midday→consideration, evening→decision. If every
post is product-anchored, the awareness slot is being fed decision-grade material. Awareness
content should often name no product at all.

Every territory maps to a funnel stage and a business objective. Alignment without business
linkage produces a popular account that sells nothing.

## 2.6 Ethical line — enforced, not documented

Storm content sits adjacent to real trauma.

- Content must help people feel **capable**, never afraid so they will buy.
- No fear leverage · no disaster spectacle · no exploiting a named event's casualties.
- Add a review step that **fails** content trading on fear rather than capability.

Audiences punish this instantly, and it would poison the trust everything else depends on.

## 🛑 GATE 2 — 10 posts generated tension-first on Railway. Report craft scores, Reader Value
scores, product/non-product split, and gate-failure rate versus current baseline.

---

# PHASE 3 — THE LIVING REPOSITORY

System-written, bounded, always recoverable.

- **Usage and freshness** — which tensions, moments, jobs, angles, and visual scenes are used;
  what remains untouched. **Extend the existing rotation ledger; do not build a parallel store.**
- **Audience harvest** — real questions, comments, objections captured from platforms and
  promoted into candidate tensions **for owner approval only.**
- **Seasonal context** — hurricane season, heat, holidays, back-to-school, regional weather.
  Auto-surfaces relevant territory.
  > **Preemptive requirement:** peak hurricane season is ~3 weeks out. The system must
  > **pre-stage** seasonal content *before* the window opens, not react once it arrives. Build
  > seasonal lookahead so relevant territory surfaces weeks ahead.
- **Proposed facts** — research writes here with provenance and confidence. **Never usable for
  claims.** Only an explicit owner action promotes to `verified_facts`. Surface pending
  proposals for review.
- **Performance memory** — see Phase 6.

**Non-negotiable:** the living repository may propose static additions. It may never write them.

---

# PHASE 4 — THE IMAGE PROMPT ENGINE

> **The prompt is the image.** Model choice matters far less than prompt quality. This phase
> treats prompt construction as the primary craft, and validates the prompt — never the
> rendered image — because that is the cheapest point at which a bad image can be prevented.

## 4.1 Art direction as a structured artifact

Replace the prompt string with a structured art direction derived from the tension:

| Field | Contains |
|---|---|
| `scene` | The human moment — what is happening |
| `subject` | Who or what the frame is about |
| `environment` | Real regional specificity, never generic |
| `light` | Time of day, source, quality, direction |
| `emotional_register` | What the viewer should feel |
| `composition` | Framing, depth, focal point, negative space |
| `product_presence` | `absent` · `incidental` · `hero` |
| `texture` | Grain, surface, material realism |
| `must_not_appear` | Explicit negative constraints |

## 4.2 Prompt construction discipline

Compile the structured art direction into a rendering prompt using rules stored in the **static**
repository. The house style must specify:

- **Order of information** — most models weight early tokens more heavily. Lead with subject and
  scene, then environment, then light, then style.
- **Concrete over abstract.** "Kitchen counter at 6am, one candle, storm light through blinds"
  beats "cozy emergency atmosphere."
- **Sensory and material language** — surfaces, wear, weather, temperature.
- **Explicit negatives** — the never-appears list compiled into the prompt itself, not left to
  post-hoc QA.
- **Camera and optical language** where it helps realism — focal length, depth of field, angle.
- **Human authenticity** — real people in real conditions, never stock-photo affect.
- **Brand palette and light quality** injected from visual identity.

Store this as versioned prompt craft rules. When a prompt pattern proves to render well,
**propose** the improvement to the static repo for owner approval — never self-write.

## 4.3 Generate multiple prompts, render one

Generate **3 candidate art directions and their compiled prompts as text.** Score them. Render
**only the winner.**

Text is nearly free; rendering is expensive and rate-limited. This buys real visual variety at
almost no cost and preserves the one-image-per-published-post economics.

Score each prompt on: **scene truth** (does it match the tension) · **specificity** ·
**brand fit** · **visual novelty vs. recent posts** · **claim safety**.

## 4.4 PROMPT GOVERNANCE — validate the prompt, never the image

**This is the critical gap in the system today.** Claim governance checks copy. It does not
check what images assert — and an image showing a power station lighting an entire house is a
claim, a stronger one than any sentence, because viewers accept it without parsing.

**Run governance on the prompt text before any render.** Never review the rendered image as the
gate — by then the money is spent and the claim already exists.

Check the prompt for:

- Does the described scene imply a capability outside `verified_facts`?
- Does it imply runtime, whole-home backup, or unverified device compatibility?
- Does it show the product powering something it cannot power?
- Does it imply a use context the product is not rated for?
- Does it violate the never-appears list?
- Does it trade on fear or disaster spectacle?

**Fail closed**, exactly as copy governance does. On failure: revise the art direction,
recompile, re-check. Only a prompt that passes may be rendered.

Log every prompt governance verdict with the reason.

## 4.5 Visual novelty tracking

Anti-repeat covers copy, not imagery. Track scene, environment, composition, palette, and time
of day across recent posts. Prefer unused visual territory. Report a 30-day visual similarity
trend — a feed can go stale visually while every caption stays fresh.

## 4.6 Quality, identity, and failure ladder

- Reference-image conditioning from approved product photography for product-present scenes.
- Extend visual QA to score **scene truth** alongside existing technical criteria — as a
  *quality* check, not the claim gate. Claims are already settled at 4.4.
- Failure ladder: retry once with QA feedback → next candidate → product photo.
  **A failed image never causes a silent slot.**

## 4.7 Platform-native framing

Aspect ratio and composition are decided at art-direction time, not by cropping afterward. Frame
the scene for its destination.

## 🛑 GATE 4 — present 5 posts with images. Report: art directions generated vs. rendered ·
prompt governance verdicts and rejections · confirmed image count (one per published post) ·
visual novelty baseline.

---

# PHASE 5 — PREEMPTIVE OPERATIONS

Anticipate failure rather than reacting to it.

- **Pool depth floor.** If the candidate pool drops below N days of slots, trigger a batch
  early. Never discover an empty pool at slot time.
- **Seasonal lookahead.** Surface upcoming windows weeks ahead and pre-stage content.
  *Hurricane peak is ~3 weeks out — this is live and urgent.*
- **Token expiry pre-warning.** Meta tokens expire on a 60-day timer. Alert 7 days out; expose
  token age on `/status`.
- **Budget pre-check.** Verify remaining Gemini budget *before* calling, not after failing.
- **Gap pre-resolution.** When research identifies a knowledge gap, resolve it into the package
  so future posts never hit it again.
- **Degradation ladder, everywhere.** Every step has a defined fallback. **Silence is the worst
  outcome except for governance and claim failures, which still block absolutely.**

---

# PHASE 6 — LEARNING LOOP, RETARGETED

`engagement_ingestion.py`, `analytics_ingestion.py`, `performance_learning.py`, and
`performance_memory.py` exist. **Determine whether any actually pull platform metrics.** Report
honestly.

## 6.1 Measure the right thing

> Likes measure scroll reflex. **Saves** measure usefulness. **Shares** measure identity.
> **Substantive comments** measure whether you made someone think. **Profile visits and DMs**
> measure trust.

Optimizing raw engagement converges on bland crowd-pleasers. Optimize a composite weighted
toward **saves, shares, comment depth, and trust signals**.

## 6.2 Attribute performance to decisions

Join metrics to `candidate_id`. Report top and bottom performers by tension · job · craft
mechanic · Reader Value score · trust behavior · product presence · visual scene · platform.

**State statistical confidence honestly.** At 20 posts nothing is significant. Say so rather
than manufacturing insight.

## 6.3 Feed back without collapsing

Weight selection toward proven territory **only past a defined data threshold** — and reserve a
fixed **25–30% exploration share** outside proven ground. A system that only repeats winners
stops discovering and goes stale. Rotation cooldowns still apply; performance weighting selects
among eligible options and never overrides freshness.

## 6.4 Critic versus reality

If the critic consistently disagrees with real engagement, **the critic is miscalibrated.**
Report it. Do not silently trust either signal.

---

# PHASE 7 — ANTI-OSSIFICATION

Track weekly: distinct tensions · human situations · jobs · visual scenes · 30-day repeat rate
per dimension · **semantic similarity of recent copy** · **visual similarity of recent imagery**.
Rising similarity means ossification even while every post passes its gates.

Guard tests that fail loudly if:

- The AI writes to the static repository
- A repository field contains a paste-ready caption
- A `proposed_fact` reaches `verified_facts` without owner promotion
- **An image renders without its prompt passing prompt governance**
- A candidate enters the pool failing Reader Value
- The exploration reserve drops below its floor
- Copy novelty or visual novelty falls below threshold
- Pool depth falls below its floor without triggering a batch

## 🛑 FINAL — `docs/HUMAN_TRUTH_REPORT.md`

Repository schemas and enforcement · owner-required inputs · existing-module mapping ·
before/after gate-failure rate · 10 posts with images · prompt governance rejection examples ·
craft, Reader Value, and engagement attribution with stated confidence · exploration reserve ·
novelty baselines · remaining debt.

---

# HARD RULES

**Never:** let the AI write to the static repository · paraphrase human material on intake ·
store paste-ready copy in either repository · **render an image whose prompt has not passed
governance** · use the rendered image as the claim gate · derive the image prompt from the
finished caption instead of the scene · let research promote its own facts · use fear leverage or
disaster spectacle · publish content failing the Reader Value Contract · weaken claim governance
or exact-caption protection · optimize toward winners without an exploration reserve · build
parallel structures alongside existing BI/conversion/rotation modules · invent specifications,
endpoints, config keys, or env vars · verify content locally · deploy without confirming the
previous deploy landed · refactor `generate_posts.py` · build from, clean, or merge into stale
local `master`.

**Always:** verify code actually reads a config before tuning that config · quote source as
evidence · assemble from existing modules first · fail at the cheapest point in the cost gradient
· state confidence honestly · prefer another supported angle over abstaining · degrade rather
than fail.

---

**Objective: a system rooted in real human truth, generating from tension rather than
specification, validating every image prompt before a pixel is paid for, delivering content
people are glad they saw, earning the trust that makes buying feel safe, learning what genuinely
moves people, and never repeating itself into staleness.**
