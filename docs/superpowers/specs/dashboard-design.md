# AI Werewolf — Live Dashboard Design

**Aesthetic direction: nocturnal surveillance dossier.** Two voices in tension:

- **THE SQUARE** (left, ~58%) — the public record. Editorial serif (Fraunces), warm; flips to **parchment/light by day**. What everyone hears.
- **INTERCEPTED** (right, ~42%) — the agents' private minds, leaked. Monospace (JetBrains Mono), **amber-on-black**, redacted "classified" hatch, statements "decrypt" left-to-right as they arrive. What agents never see.

The serif-vs-mono, lit-vs-wiretap contrast carries the whole concept and is the screenshot.

## Implementation notes
- **No build step, no Tailwind.** Hand-written CSS in an inline `<style>`; two Google Fonts via `<link>`. Served by FastAPI StaticFiles. Files: `web/index.html`, `web/app.js`.
- **Theme keystone:** `document.documentElement.dataset.phase = "night"|"day"` drives every color via CSS custom properties (smooth ~1.1s transition). JS only flips `data-*` attributes + inserts nodes — never synthesizes classes.
- **Event contract:** WS `ws://<host>/ws/game` emits `{kind, day, actor, text, data}`; kinds `phase|speak|reasoning|death|vote|result`. Roles revealed only on death/result. Fixed names: Ava, Ben, Cleo, Dan, Eve, Finn, Gwen.
- **Roster strip** of 7 cards on top: alive/dead, speaking ring, vote-count badge + growing fill bar, most-voted red pulse, role-reveal avatar flip on death.
- **Motion (CSS keyframes + tiny JS, all behind `prefers-reduced-motion`):** night↔day sweep wipe; speak `bubbleIn`; reasoning `decrypt` clip-path unmask; vote tracer + bar fill; death flip + red flash + sliding plaque; result overlay + confetti + cascade reveal.
- **Demo moment:** pair a `reasoning` with the immediately-following public action from the same actor. Heuristic deception flag (regex) → red-tint the public bubble, add a `⚠ COVER STORY` chip (spin, not ground-truth), draw a pulsing connector between the pair, dim the rest. On `result`, confirmed wolves' pairs upgrade to `CONFIRMED LIE`.
- **A11y:** `role="log" aria-live="polite"` feeds; color never the only signal (glyphs + text); full reduced-motion fallback; two-column ≥1024px, stacks below.
