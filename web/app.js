"use strict";

// ============================================================ constants / state
let NAMES = ["Ava", "Ben", "Cleo", "Dan", "Eve", "Finn", "Gwen"]; // replaced per game by the 'setup' event
const ROLE_META = {
  werewolf: { glyph: "🐺", team: "werewolf", color: "var(--wolf)" },
  seer: { glyph: "🔮", team: "village", color: "var(--seer)" },
  doctor: { glyph: "✚", team: "village", color: "var(--doctor)" },
  villager: { glyph: "🧑", team: "village", color: "var(--villager)" },
};
const DECEPTION_RE =
  /redirect|reframe|frame|deflect|cover|accuse .* instead|throw .* under|\blie\b|pretend|conceal|mislead|blend in|scapegoat|act (?:calm|innocent)|cast (?:doubt|suspicion)|pin it/i;

const REDUCE = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const state = {
  ws: null,
  phase: "night",
  day: 0,
  players: new Map(), // name -> { alive, role }
  votes: new Map(), // target -> count (reset each day)
  pending: null, // { actor, node, deception, pairId }
  pairSeq: 0,
  spotlight: null, // { a, b }
};

const wait = (ms) => (ms <= 0 ? Promise.resolve() : new Promise((r) => setTimeout(r, ms)));

// ============================================================ dom helpers
const $ = (id) => document.getElementById(id);
const roster = $("roster");
const publicFeed = $("publicFeed");
const privateFeed = $("privateFeed");
const phasePill = $("phasePill");
const phaseText = $("phaseText");
const connectorPath = $("connectorPath");

function el(tag, cls, html) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (html != null) n.innerHTML = html;
  return n;
}
const esc = (s) =>
  (s || "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[c]);

function hue(name) {
  let h = 0;
  for (const c of name) h = (h * 31 + c.charCodeAt(0)) % 360;
  return h;
}

// ============================================================ roster
function renderRoster() {
  roster.innerHTML = "";
  for (const name of NAMES) {
    const p = state.players.get(name) || { alive: true, role: null };
    const card = el("div", "player");
    card.dataset.name = name;
    card.dataset.alive = String(p.alive);
    if (p.role) {
      card.dataset.role = p.role;
      card.dataset.team = ROLE_META[p.role]?.team || "village";
    }
    const meta = p.role ? ROLE_META[p.role] : null;
    card.innerHTML = `
      <div class="speaking-ring"></div>
      <span class="vote-badge">0</span>
      <span class="think-badge" aria-hidden="true">···</span>
      <div class="avatar" style="background:hsl(${hue(name)} 70% 62%)">
        <span class="front">${name[0]}</span>
        <span class="back" style="color:${meta ? meta.color : "#fff"}">${meta ? meta.glyph : ""}</span>
      </div>
      <div class="pname">${p.alive ? name : "💀 " + name}</div>
      <div class="prole">${p.role || ""}</div>
      <div class="vote-track"><div class="vote-fill"></div></div>`;
    roster.appendChild(card);
  }
}
const cardOf = (name) => roster.querySelector(`.player[data-name="${name}"]`);

function markSpeaking(actor) {
  roster
    .querySelectorAll(".player[data-speaking]")
    .forEach((c) => c.removeAttribute("data-speaking"));
  const c = cardOf(actor);
  if (c && c.dataset.alive === "true") c.dataset.speaking = "true";
}

const livingNames = () => NAMES.filter((n) => state.players.get(n)?.alive);

// ============================================================ feed utils
function nearBottom(feed) {
  return feed.scrollHeight - feed.scrollTop - feed.clientHeight < 90;
}
function pinIfStuck(feed, stuck) {
  if (stuck && nearBottom(feed)) feed.scrollTop = feed.scrollHeight;
}
function appendTo(feed, node, pill) {
  const stick = nearBottom(feed);
  feed.appendChild(node);
  while (feed.childElementCount > 220) feed.removeChild(feed.firstElementChild);
  if (stick) feed.scrollTop = feed.scrollHeight;
  else if (pill) pill.classList.add("show");
  node._stuck = stick;
  return node;
}

// ============================================================ Typewriter
const Typewriter = {
  active: null,
  type(feed, span, text) {
    if (REDUCE || Queue.speed === Infinity) {
      span.textContent = text;
      this.active = null;
      return Promise.resolve();
    }
    const node = span.closest(".bubble") || span.parentElement;
    const stuck = node ? node._stuck : true;
    const words = text.split(/(\s+)/);
    let i = 0;
    this.active = new Promise((res) => {
      const step = () => {
        span.textContent += words[i++] ?? "";
        pinIfStuck(feed, stuck);
        if (state.spotlight) scheduleRedraw();
        if (i < words.length) setTimeout(step, 20 / Queue.speed);
        else {
          this.active = null;
          res();
        }
      };
      step();
    });
    return this.active;
  },
  idle() {
    return this.active || Promise.resolve();
  },
};

// ============================================================ Queue / pacing
const PRE = {
  setup: 0,
  phase: 1000,
  thinking: 150,
  reasoning: 320,
  speak: 260,
  vote: 340,
  death: 1100,
  result: 1300,
  no_elimination: 750,
};
const POST = { phase: 1150, reasoning: 140, speak: 560, vote: 430, death: 850, no_elimination: 650 };
const preDelay = (ev) => (ev.kind === "phase" && ev.text === "no_elimination" ? PRE.no_elimination : PRE[ev.kind] || 0);
const postDelay = (ev) => (ev.kind === "phase" && ev.text === "no_elimination" ? POST.no_elimination : POST[ev.kind] || 0);

const Queue = {
  q: [],
  draining: false,
  speed: 1,
  enqueue(ev) {
    this.q.push(ev);
    if (!this.draining) this.drain();
  },
  reset() {
    this.q = [];
    this.draining = false;
  },
  async drain() {
    this.draining = true;
    while (this.q.length) {
      await Typewriter.idle();
      const ev = this.q[0];
      const pre = preDelay(ev) / this.speed;
      if (pre) await wait(pre);
      this.q.shift();
      handle(ev);
      if (ev.kind === "reasoning" || ev.kind === "speak") await Typewriter.idle();
      const post = postDelay(ev) / this.speed;
      if (post) await wait(post);
    }
    this.draining = false;
  },
};

// ============================================================ Thinking indicator
const Thinking = {
  map: new Map(), // actor -> ghost node
  current: null,
  chip() {
    return $("thinkChip");
  },
  showChip(actor) {
    this.current = actor;
    const chip = this.chip();
    chip.querySelector(".who").textContent = actor;
    chip.dataset.show = "true";
  },
  hideChip(actor) {
    if (actor && this.current !== actor) return;
    this.current = null;
    this.chip().dataset.show = "false";
  },
  show(actor) {
    const c = cardOf(actor);
    if (c && c.dataset.alive === "true") c.dataset.thinking = "true";
    this.showChip(actor);
    const ghost = el(
      "div",
      "private-bubble ghost",
      `<div class="tagline">🧠 ${esc(actor)} is deciding<span class="dots"></span></div>
       <div class="brainwave"><span></span><span></span><span></span><span></span><span></span></div>`
    );
    ghost.dataset.thinkingActor = actor;
    appendTo(privateFeed, ghost, $("privatePill"));
    this.map.set(actor, ghost);
  },
  // turn the ghost into a real bubble (reused so there's no flicker); returns the node or null
  consume(actor) {
    const c = cardOf(actor);
    if (c) c.removeAttribute("data-thinking");
    this.hideChip(actor);
    const g = this.map.get(actor);
    this.map.delete(actor);
    return g || null;
  },
  clear(actor) {
    const c = cardOf(actor);
    if (c) c.removeAttribute("data-thinking");
    this.hideChip(actor);
    const g = this.map.get(actor);
    if (g) g.remove();
    this.map.delete(actor);
  },
  clearAll() {
    for (const [, g] of this.map) g.remove();
    this.map.clear();
    this.current = null;
    if (this.chip()) this.chip().dataset.show = "false";
    roster.querySelectorAll(".player[data-thinking]").forEach((c) => c.removeAttribute("data-thinking"));
  },
};

// ============================================================ handlers
function onSetup(ev) {
  const names = ev.data && ev.data.players;
  if (Array.isArray(names) && names.length) NAMES = names;
  state.players.clear();
  for (const n of NAMES) state.players.set(n, { alive: true, role: null });
  renderRoster();
  Graph.edges.clear();
  if (Graph.running || REDUCE) Graph.resize();
}

function onPhase(ev) {
  Thinking.clearAll();
  if (ev.text === "no_elimination") {
    appendTo(publicFeed, el("div", "plaque", "⚖&nbsp; A tie — no one was eliminated"), $("publicPill"));
    return;
  }
  state.phase = ev.text;
  state.day = ev.day;
  document.documentElement.dataset.phase = ev.text;
  setPhasePill(ev.text, ev.day);
  runSweep();
  narrate(ev.text, ev.day);
  phasePill.dataset.live = "true";
  if (ev.text === "day") {
    state.votes.clear();
    clearVoteBars();
  }
  Atmosphere.onPhase(ev.text);
  SoundKit.gong(ev.text);
  SoundKit.ambient(ev.text);
  const label = `${ev.text === "night" ? "🌙 Night" : "☀ Day"} ${ev.day}`;
  appendTo(publicFeed, el("div", "divider", label), $("publicPill"));
  appendTo(privateFeed, el("div", "divider", label), $("privatePill"));
}

function onThinking(ev) {
  Thinking.show(ev.actor);
}

function onReasoning(ev) {
  markSpeaking(ev.actor);
  const pairId = "p" + ++state.pairSeq;
  const deception = DECEPTION_RE.test(ev.text || "");
  // reuse the thinking ghost if present (no flicker), else make a fresh bubble
  let node = Thinking.consume(ev.actor);
  if (node) node.classList.remove("ghost");
  else node = appendTo(privateFeed, el("div", "private-bubble"), $("privatePill"));
  node.classList.add("decrypt");
  node.dataset.pair = pairId;
  node.dataset.pairActor = ev.actor;
  if (deception) node.dataset.deception = "true";
  node.innerHTML = `
    <div class="tagline">🔒 ${esc(ev.actor)} · ${deception ? "⚠ cover story" : "true thought"}</div>
    <span class="body"></span>`;
  SoundKit.whisper();
  state.pending = { actor: ev.actor, node, deception, pairId };
  return Typewriter.type(privateFeed, node.querySelector(".body"), ev.text || "");
}

function onSpeak(ev) {
  Thinking.clear(ev.actor);
  markSpeaking(ev.actor);
  const pend = state.pending;
  const paired = pend && pend.actor === ev.actor;
  const node = el("div", "bubble public-bubble", `<span class="who">${esc(ev.actor)}</span><span class="body"></span>`);
  if (paired) {
    node.dataset.pair = pend.pairId;
    node.dataset.pairActor = ev.actor;
    if (pend.deception) {
      node.dataset.deception = "true";
      spotlightPair(pend.node, node);
    }
  }
  appendTo(publicFeed, node, $("publicPill"));
  Graph.mentions(ev.actor, ev.text);
  state.pending = null;
  return Typewriter.type(publicFeed, node.querySelector(".body"), ev.text || "");
}

function onVote(ev) {
  Thinking.clear(ev.actor);
  const target = ev.text;
  state.votes.set(target, (state.votes.get(target) || 0) + 1);
  updateVoteBar(target);
  recomputeLead();
  voteTracer(ev.actor, target);
  Graph.bump(ev.actor, target, "vote");
  SoundKit.tension(state.votes.get(target) || 1);
  appendTo(publicFeed, el("div", "vote-line", `🗳 ${esc(ev.actor)} → <b>${esc(target)}</b>`), $("publicPill"));
  state.pending = null;
}

function onDeath(ev) {
  const role = parseRole(ev.text);
  const p = state.players.get(ev.actor) || { alive: true, role: null };
  p.alive = false;
  p.role = role;
  state.players.set(ev.actor, p);
  flipCard(ev.actor, role);
  if (role === "werewolf") confirmLies(ev.actor);
  Graph.poke();
  SoundKit.sting();
  deathFlash();
  appendTo(publicFeed, el("div", "plaque death", "💀&nbsp; " + esc(ev.text)), $("publicPill"));
}

function onResult(ev) {
  Thinking.clearAll();
  const winner = (ev.data && ev.data.winner) || "village";
  revealAll();
  clearSpotlight();
  Graph.poke();
  SoundKit.fanfare(winner);
  SoundKit.stopAmbient();
  showWin(winner);
  phasePill.dataset.live = "false";
}

function onClosed() {
  appendTo(publicFeed, el("div", "divider", "— stream closed —"), $("publicPill"));
}

const HANDLERS = {
  setup: onSetup,
  phase: onPhase,
  thinking: onThinking,
  reasoning: onReasoning,
  speak: onSpeak,
  vote: onVote,
  death: onDeath,
  result: onResult,
  _closed: onClosed,
};
function handle(ev) {
  (HANDLERS[ev.kind] || (() => {}))(ev);
}

// ============================================================ vote visuals
const aliveCount = () => livingNames().length || 1;

function updateVoteBar(target) {
  const card = cardOf(target);
  if (!card) return;
  const count = state.votes.get(target) || 0;
  card.querySelector(".vote-fill").style.width = Math.min(100, (count / aliveCount()) * 100) + "%";
  const badge = card.querySelector(".vote-badge");
  badge.textContent = String(count);
  badge.classList.add("show");
  badge.classList.remove("bump");
  void badge.offsetWidth;
  badge.classList.add("bump");
}
function recomputeLead() {
  let max = 0;
  for (const v of state.votes.values()) max = Math.max(max, v);
  roster.querySelectorAll(".player").forEach((c) => {
    const n = state.votes.get(c.dataset.name) || 0;
    if (max > 0 && n === max) c.dataset.leadtarget = "true";
    else c.removeAttribute("data-leadtarget");
  });
}
function clearVoteBars() {
  roster.querySelectorAll(".player").forEach((c) => {
    c.querySelector(".vote-fill").style.width = "0%";
    const b = c.querySelector(".vote-badge");
    b.classList.remove("show");
    b.textContent = "0";
    c.removeAttribute("data-leadtarget");
  });
}
function voteTracer(from, to) {
  if (REDUCE) return;
  const a = cardOf(from);
  const b = cardOf(to);
  if (!a || !b) return;
  const ra = a.getBoundingClientRect();
  const rb = b.getBoundingClientRect();
  const dot = document.createElement("div");
  dot.className = "tracer";
  dot.style.left = ra.left + ra.width / 2 + "px";
  dot.style.top = ra.top + ra.height / 2 + "px";
  document.body.appendChild(dot);
  requestAnimationFrame(() => {
    dot.style.transform = `translate(${rb.left + rb.width / 2 - (ra.left + ra.width / 2)}px, ${
      rb.top + rb.height / 2 - (ra.top + ra.height / 2)
    }px)`;
    dot.style.opacity = "0.15";
  });
  setTimeout(() => dot.remove(), 650);
}

// ============================================================ role reveal
function parseRole(text) {
  const m = /(werewolf|seer|doctor|villager)/i.exec(text || "");
  return m ? m[1].toLowerCase() : null;
}
function paintRole(card, role) {
  card.dataset.role = role;
  card.dataset.team = ROLE_META[role]?.team || "village";
  const meta = ROLE_META[role];
  if (meta) {
    const back = card.querySelector(".avatar .back");
    back.textContent = meta.glyph;
    back.style.color = meta.color;
  }
  card.querySelector(".prole").textContent = role;
}
function flipCard(name, role) {
  const card = cardOf(name);
  if (!card) return;
  card.dataset.alive = "false";
  card.removeAttribute("data-thinking");
  if (role) paintRole(card, role);
  card.querySelector(".pname").innerHTML = "💀 " + name;
}
function revealAll() {
  let i = 0;
  for (const name of NAMES) {
    const p = state.players.get(name);
    if (!p || !p.role) continue;
    const card = cardOf(name);
    if (!card || card.dataset.role) continue;
    setTimeout(() => paintRole(card, p.role), 70 * i++);
  }
}
function confirmLies(actor) {
  document
    .querySelectorAll(`.private-bubble[data-pair-actor="${actor}"][data-deception="true"] .tagline`)
    .forEach((t) => (t.innerHTML = `🩸 ${esc(actor)} · CONFIRMED LIE`));
}

// ============================================================ spotlight + connector
function spotlightPair(a, b) {
  clearSpotlight();
  a.dataset.spotlight = "true";
  b.dataset.spotlight = "true";
  document.body.classList.add("has-spotlight");
  state.spotlight = { a, b };
  drawConnector();
}
function clearSpotlight() {
  if (state.spotlight) {
    state.spotlight.a.removeAttribute("data-spotlight");
    state.spotlight.b.removeAttribute("data-spotlight");
  }
  state.spotlight = null;
  document.body.classList.remove("has-spotlight");
  connectorPath.setAttribute("d", "");
}
function drawConnector() {
  if (!state.spotlight) return;
  const ra = state.spotlight.a.getBoundingClientRect();
  const rb = state.spotlight.b.getBoundingClientRect();
  if (ra.width === 0 || rb.width === 0) {
    connectorPath.setAttribute("d", "");
    return;
  }
  const x1 = ra.left;
  const y1 = ra.top + ra.height / 2;
  const x2 = rb.right;
  const y2 = rb.top + rb.height / 2;
  const mx = (x1 + x2) / 2;
  connectorPath.setAttribute("d", `M ${x2} ${y2} C ${mx} ${y2}, ${mx} ${y1}, ${x1} ${y1}`);
}
let raf = 0;
function scheduleRedraw() {
  if (raf) return;
  raf = requestAnimationFrame(() => {
    raf = 0;
    drawConnector();
  });
}
window.addEventListener("resize", scheduleRedraw);
publicFeed.addEventListener("scroll", scheduleRedraw);
privateFeed.addEventListener("scroll", scheduleRedraw);

// ============================================================ The Web (suspicion graph)
function mentionedNames(text, living, self) {
  const out = [];
  for (const n of living) {
    if (n === self) continue;
    if (new RegExp(`\\b${n}\\b`, "i").test(text || "")) out.push(n);
  }
  return out;
}
const Graph = {
  edges: new Map(), // "from>to" -> {from,to,weight,kind,appear,flash}
  canvas: null,
  ctx: null,
  pos: null,
  rafId: 0,
  running: false,
  t: 0,
  reset() {
    this.edges.clear();
    if (this.ctx) this.draw();
  },
  bump(from, to, kind) {
    if (!from || !to || from === to) return;
    const k = from + ">" + to;
    const e = this.edges.get(k);
    if (e) {
      e.weight++;
      e.flash = 1; // pulse on reinforcement
      if (kind === "vote") e.kind = "vote";
    } else {
      this.edges.set(k, { from, to, weight: 1, kind, appear: 0, flash: 1 });
    }
    if ((REDUCE || !this.running) && this.ctx) this.draw();
  },
  mentions(actor, text) {
    for (const n of mentionedNames(text, livingNames(), actor)) this.bump(actor, n, "mention");
  },
  incoming(name) {
    let s = 0;
    for (const e of this.edges.values())
      if (e.to === name) s += e.kind === "vote" ? e.weight * 1.6 : e.weight;
    return s;
  },
  ensure() {
    if (this.canvas) return;
    this.canvas = $("webCanvas");
    if (!this.canvas) return;
    this.ctx = this.canvas.getContext("2d");
    window.addEventListener("resize", () => {
      if (this.running || REDUCE) this.resize();
    });
  },
  resize() {
    if (!this.canvas || !this.ctx) return;
    const r = this.canvas.getBoundingClientRect();
    if (r.width === 0) return;
    const dpr = window.devicePixelRatio || 1;
    this.canvas.width = r.width * dpr;
    this.canvas.height = r.height * dpr;
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.w = r.width;
    this.h = r.height;
    const cx = r.width / 2;
    const cy = r.height / 2 - 4;
    this.rad = Math.min(cx, cy) - 46;
    this.pos = {};
    NAMES.forEach((n, i) => {
      const a = -Math.PI / 2 + (i / NAMES.length) * Math.PI * 2;
      this.pos[n] = { x: cx + this.rad * Math.cos(a), y: cy + this.rad * Math.sin(a), a };
    });
    this.cx = cx;
    this.cy = cy;
    this.draw();
  },
  start() {
    this.ensure();
    this.resize();
    if (REDUCE || !this.canvas) {
      this.draw();
      return;
    }
    if (this.running) return;
    this.running = true;
    const loop = () => {
      if (!this.running) return;
      this.t += 0.016;
      this.draw();
      this.rafId = requestAnimationFrame(loop);
    };
    loop();
  },
  stop() {
    this.running = false;
    cancelAnimationFrame(this.rafId);
  },
  poke() {
    // redraw on a data change when the live loop isn't running (panel closed / reduced motion)
    if (!this.running && this.ctx) this.draw();
  },
  _ctrl(a, b) {
    // consistent clockwise bow so reciprocal edges don't overlap
    const mx = (a.x + b.x) / 2;
    const my = (a.y + b.y) / 2;
    return { x: mx + (a.y - b.y) * 0.22, y: my + (b.x - a.x) * 0.22 };
  },
  _pt(a, c, b, u) {
    const v = 1 - u;
    return {
      x: v * v * a.x + 2 * v * u * c.x + u * u * b.x,
      y: v * v * a.y + 2 * v * u * c.y + u * u * b.y,
    };
  },
  draw() {
    if (!this.ctx || !this.pos) return;
    const ctx = this.ctx;
    const t = this.t;
    ctx.clearRect(0, 0, this.w, this.h);

    // ---- faint web backdrop: concentric rings + spokes ----
    ctx.save();
    ctx.strokeStyle = "rgba(150,170,230,0.06)";
    ctx.lineWidth = 1;
    for (let i = 1; i <= 3; i++) {
      ctx.beginPath();
      ctx.arc(this.cx, this.cy, (this.rad * i) / 3, 0, Math.PI * 2);
      ctx.stroke();
    }
    for (const n of NAMES) {
      const p = this.pos[n];
      ctx.beginPath();
      ctx.moveTo(this.cx, this.cy);
      ctx.lineTo(p.x, p.y);
      ctx.stroke();
    }
    ctx.restore();

    // ---- edges: flowing, weight-scaled, arrowed ----
    let topName = null;
    let topVal = 0;
    for (const n of NAMES) {
      const inc = this.incoming(n);
      if (inc > topVal && (state.players.get(n)?.alive ?? true)) {
        topVal = inc;
        topName = n;
      }
    }

    for (const e of this.edges.values()) {
      const a = this.pos[e.from];
      const b = this.pos[e.to];
      if (!a || !b) continue;
      e.appear += (1 - e.appear) * 0.12;
      e.flash *= 0.92;
      const c = this._ctrl(a, b);
      const vote = e.kind === "vote";
      const base = Math.min(0.85, 0.22 + e.weight * 0.16) * e.appear;
      const rgb = vote ? "229,72,77" : "120,150,235";

      ctx.save();
      ctx.lineCap = "round";
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.quadraticCurveTo(c.x, c.y, b.x, b.y);
      ctx.strokeStyle = `rgba(${rgb},${base + e.flash * 0.4})`;
      ctx.lineWidth = ((vote ? 1.6 : 0.8) + e.weight * 0.9) * e.appear;
      if (vote && !REDUCE) {
        ctx.setLineDash([5, 9]);
        ctx.lineDashOffset = -t * 36; // accusation "flows" toward target
        ctx.shadowColor = `rgba(${rgb},0.7)`;
        ctx.shadowBlur = 6 + e.flash * 10;
      }
      ctx.stroke();
      ctx.restore();

      // arrowhead at target
      const near = this._pt(a, c, b, 0.92);
      const ang = Math.atan2(b.y - near.y, b.x - near.x);
      ctx.fillStyle = `rgba(${rgb},${Math.min(0.95, base + 0.25)})`;
      ctx.beginPath();
      ctx.moveTo(b.x, b.y);
      ctx.lineTo(b.x - 10 * Math.cos(ang - 0.42), b.y - 10 * Math.sin(ang - 0.42));
      ctx.lineTo(b.x - 10 * Math.cos(ang + 0.42), b.y - 10 * Math.sin(ang + 0.42));
      ctx.closePath();
      ctx.fill();

      // travelling pulse along vote edges
      if (vote && !REDUCE) {
        const u = (t * 0.45 + (e.from.charCodeAt(0) % 7) / 7) % 1;
        const pp = this._pt(a, c, b, u);
        ctx.beginPath();
        ctx.arc(pp.x, pp.y, 2.6, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(255,150,150,${0.9 * e.appear})`;
        ctx.shadowColor = "rgba(229,72,77,0.9)";
        ctx.shadowBlur = 8;
        ctx.fill();
        ctx.shadowBlur = 0;
      }
    }

    // ---- nodes ----
    for (const n of NAMES) {
      const p = this.pos[n];
      const pl = state.players.get(n) || { alive: true };
      const inc = this.incoming(n);
      const radius = 11 + Math.min(9, inc * 1.4);
      const lead = n === topName && topVal > 0;
      ctx.globalAlpha = pl.alive ? 1 : 0.38;

      // glow halo
      const pulse = pl.alive ? 0.5 + 0.5 * Math.sin(t * 2.2 + hue(n)) : 0;
      const halo = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, radius + 14 + pulse * 6);
      const hc = lead ? "229,72,77" : `hsl(${hue(n)} 70% 60%)`;
      halo.addColorStop(0, lead ? `rgba(229,72,77,${0.35 + pulse * 0.25})` : `hsla(${hue(n)},70%,60%,0.28)`);
      halo.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = halo;
      ctx.beginPath();
      ctx.arc(p.x, p.y, radius + 14 + pulse * 6, 0, Math.PI * 2);
      ctx.fill();

      // node body
      ctx.beginPath();
      ctx.arc(p.x, p.y, radius, 0, Math.PI * 2);
      ctx.fillStyle = pl.alive ? `hsl(${hue(n)} 70% 60%)` : "#3a3a44";
      ctx.fill();
      if (lead) {
        ctx.strokeStyle = `rgba(229,72,77,${0.7 + pulse * 0.3})`;
        ctx.lineWidth = 2.5;
        ctx.beginPath();
        ctx.arc(p.x, p.y, radius + 5 + pulse * 2, 0, Math.PI * 2);
        ctx.stroke();
      }
      // initial
      ctx.fillStyle = pl.alive ? "#0a0a12" : "#cfcfe0";
      ctx.font = "700 12px 'JetBrains Mono', monospace";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(pl.alive ? n[0] : "✕", p.x, p.y);

      // label outside
      const lx = p.x + (radius + 11) * Math.cos(p.a);
      const ly = p.y + (radius + 11) * Math.sin(p.a);
      ctx.font = "600 10px 'JetBrains Mono', monospace";
      ctx.textAlign = Math.cos(p.a) >= 0.2 ? "left" : Math.cos(p.a) <= -0.2 ? "right" : "center";
      ctx.fillStyle = pl.alive ? "rgba(233,236,255,.9)" : "rgba(150,150,170,.55)";
      ctx.fillText(n, lx, ly);
      ctx.globalAlpha = 1;
    }

    // ---- center readout ----
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillStyle = "rgba(233,236,255,.4)";
    ctx.font = "700 9px 'JetBrains Mono', monospace";
    ctx.fillText(`DAY ${state.day || 1}`, this.cx, this.cy - 7);
    if (topName) {
      ctx.fillStyle = "rgba(229,72,77,.85)";
      ctx.font = "700 11px 'JetBrains Mono', monospace";
      ctx.fillText(`▼ ${topName}`, this.cx, this.cy + 7);
    }
  },
};

// ============================================================ SoundKit (Web Audio)
const SoundKit = {
  ctx: null,
  master: null,
  ambientGain: null,
  ambientFilter: null,
  ready: false,
  muted: localStorage.getItem("ww.mute") === "1" || REDUCE,
  noiseBuf: null,
  lastWhisper: 0,
  init() {
    if (this.ready) return;
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    this.ctx = new AC();
    if (this.ctx.state === "suspended") this.ctx.resume();
    this.master = this.ctx.createGain();
    this.master.gain.value = this.muted ? 0 : 0.55;
    this.master.connect(this.ctx.destination);
    // shared white-noise buffer
    const len = this.ctx.sampleRate * 2;
    this.noiseBuf = this.ctx.createBuffer(1, len, this.ctx.sampleRate);
    const d = this.noiseBuf.getChannelData(0);
    for (let i = 0; i < len; i++) d[i] = Math.random() * 2 - 1;
    this.ready = true;
  },
  setMuted(m) {
    this.muted = m;
    localStorage.setItem("ww.mute", m ? "1" : "0");
    if (this.master)
      this.master.gain.linearRampToValueAtTime(m ? 0 : 0.55, this.ctx.currentTime + 0.15);
  },
  _tone({ type = "sine", freq, dur = 0.4, attack = 0.01, peak = 0.3, glide = 0, dest = null }) {
    const t = this.ctx.currentTime;
    const o = this.ctx.createOscillator();
    const g = this.ctx.createGain();
    o.type = type;
    o.frequency.setValueAtTime(freq, t);
    if (glide) o.frequency.exponentialRampToValueAtTime(freq * glide, t + dur);
    g.gain.setValueAtTime(0.0001, t);
    g.gain.linearRampToValueAtTime(peak, t + attack);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.connect(g).connect(dest || this.master);
    o.start(t);
    o.stop(t + dur + 0.05);
  },
  _noise({ dur = 0.2, type = "bandpass", freq = 3000, q = 6, peak = 0.15 }) {
    const t = this.ctx.currentTime;
    const src = this.ctx.createBufferSource();
    src.buffer = this.noiseBuf;
    const f = this.ctx.createBiquadFilter();
    f.type = type;
    f.frequency.value = freq;
    f.Q.value = q;
    const g = this.ctx.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.linearRampToValueAtTime(peak, t + 0.008);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    src.connect(f).connect(g).connect(this.master);
    src.start(t);
    src.stop(t + dur + 0.05);
  },
  gong(phase) {
    if (!this.ready || this.muted) return;
    if (phase === "night") {
      this._tone({ type: "triangle", freq: 110, dur: 1.6, peak: 0.34, glide: 0.96 });
      this._tone({ type: "sine", freq: 146.8, dur: 1.6, peak: 0.22, glide: 0.96 });
    } else {
      this._tone({ type: "triangle", freq: 196, dur: 1.1, peak: 0.3 });
      this._tone({ type: "sine", freq: 294, dur: 1.1, peak: 0.18 });
      this._tone({ type: "sine", freq: 392, dur: 0.9, peak: 0.08 });
    }
  },
  whisper() {
    if (!this.ready || this.muted) return;
    const now = performance.now();
    if (now - this.lastWhisper < 120) return;
    this.lastWhisper = now;
    this._noise({ dur: 0.11, freq: 2600 + Math.random() * 1200, q: 7, peak: 0.07 });
  },
  tension(count) {
    if (!this.ready || this.muted) return;
    this._tone({ type: "sine", freq: 52 + count * 4, dur: 0.6, attack: 0.12, peak: 0.18 });
  },
  sting() {
    if (!this.ready || this.muted) return;
    this._tone({ type: "sawtooth", freq: 220, dur: 0.7, attack: 0.005, peak: 0.22, glide: 0.4 });
    this._tone({ type: "sawtooth", freq: 311, dur: 0.7, attack: 0.005, peak: 0.18, glide: 0.4 });
    this._noise({ dur: 0.25, type: "lowpass", freq: 1200, q: 1, peak: 0.18 });
  },
  fanfare(winner) {
    if (!this.ready || this.muted) return;
    const notes = winner === "werewolf" ? [392, 466, 587, 466] : [523, 659, 784, 1047];
    const type = winner === "werewolf" ? "sawtooth" : "triangle";
    notes.forEach((f, i) =>
      setTimeout(
        () => this._tone({ type, freq: f, dur: 0.5, attack: 0.02, peak: 0.22 }),
        i * 110
      )
    );
  },
  ambient(phase) {
    if (!this.ready || this.muted || REDUCE) return;
    if (!this.ambientSrc) {
      this.ambientSrc = this.ctx.createBufferSource();
      this.ambientSrc.buffer = this.noiseBuf;
      this.ambientSrc.loop = true;
      this.ambientFilter = this.ctx.createBiquadFilter();
      this.ambientFilter.type = "lowpass";
      this.ambientGain = this.ctx.createGain();
      this.ambientGain.gain.value = 0.05;
      this.ambientSrc.connect(this.ambientFilter).connect(this.ambientGain).connect(this.master);
      this.ambientSrc.start();
    }
    const target = phase === "day" ? 900 : 480;
    this.ambientFilter.frequency.linearRampToValueAtTime(target, this.ctx.currentTime + 1.1);
    // restore bed level (a prior game's stopAmbient may have ramped it to silence)
    this.ambientGain.gain.linearRampToValueAtTime(0.05, this.ctx.currentTime + 1.1);
  },
  stopAmbient() {
    if (this.ambientGain) this.ambientGain.gain.linearRampToValueAtTime(0.0001, this.ctx.currentTime + 1.2);
  },
};

// ============================================================ Atmosphere (canvas sky)
const Atmosphere = {
  cv: null,
  ctx: null,
  parts: [],
  rafId: 0,
  running: false,
  mix: 0, // 0 = night, 1 = day
  target: 0,
  init() {
    if (this.cv) {
      this.start();
      return;
    }
    this.cv = $("sky");
    if (!this.cv) return;
    this.ctx = this.cv.getContext("2d");
    this.resize();
    this.seed();
    window.addEventListener("resize", () => this.resize());
    document.addEventListener("visibilitychange", () =>
      document.hidden ? this.stop() : this.start()
    );
    if (REDUCE) this.frame();
    else this.start();
  },
  resize() {
    if (!this.cv) return;
    const dpr = window.devicePixelRatio || 1;
    this.cv.width = window.innerWidth * dpr;
    this.cv.height = window.innerHeight * dpr;
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  },
  seed() {
    const n = window.innerWidth < 700 ? 50 : 90;
    this.parts = [];
    for (let i = 0; i < n; i++) this.parts.push(this.mk(true));
  },
  mk(spread) {
    const W = window.innerWidth;
    const H = window.innerHeight;
    return {
      x: Math.random() * W,
      y: spread ? Math.random() * H : H + 10,
      r: 0.6 + Math.random() * 1.8,
      vx: (Math.random() - 0.5) * 0.18,
      vy: -(0.1 + Math.random() * 0.5),
      tw: Math.random() * Math.PI * 2,
      star: Math.random() < 0.55,
    };
  },
  onPhase(phase) {
    this.target = phase === "day" ? 1 : 0;
  },
  start() {
    if (this.running || REDUCE || !this.cv) return;
    this.running = true;
    const loop = () => {
      if (!this.running) return;
      this.frame();
      this.rafId = requestAnimationFrame(loop);
    };
    loop();
  },
  stop() {
    this.running = false;
    cancelAnimationFrame(this.rafId);
  },
  frame() {
    const ctx = this.ctx;
    if (!ctx) return;
    const W = window.innerWidth;
    const H = window.innerHeight;
    this.mix += (this.target - this.mix) * 0.02;
    ctx.clearRect(0, 0, W, H);
    // ambient glow: moon (night) -> warm haze (day)
    const gx = this.mix > 0.5 ? W * 0.8 : W * 0.18;
    const glow = ctx.createRadialGradient(gx, H * 0.2, 0, gx, H * 0.2, Math.max(W, H) * 0.5);
    const night = `rgba(150,170,255,${0.1 * (1 - this.mix)})`;
    const day = `rgba(255,210,140,${0.12 * this.mix})`;
    glow.addColorStop(0, this.mix > 0.5 ? day : night);
    glow.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = glow;
    ctx.fillRect(0, 0, W, H);
    for (const p of this.parts) {
      p.tw += 0.05;
      if (p.star && this.mix < 0.5) {
        // night star: twinkle in place
        const a = (0.3 + 0.4 * Math.abs(Math.sin(p.tw))) * (1 - this.mix);
        ctx.fillStyle = `rgba(220,228,255,${a})`;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r * 0.7, 0, Math.PI * 2);
        ctx.fill();
      } else {
        // ember (night) / mote (day): drift
        p.x += p.vx;
        p.y += p.vy * (this.mix > 0.5 ? 0.5 : 1);
        if (p.y < -10 || p.x < -10 || p.x > W + 10) Object.assign(p, this.mk(false));
        const warm = this.mix;
        const a = 0.18 + 0.18 * Math.abs(Math.sin(p.tw));
        ctx.fillStyle = `rgba(${255},${170 + 50 * warm},${90 + 110 * warm},${a})`;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fill();
      }
    }
  },
};

// ============================================================ phase chrome / win
function setPhasePill(phase, day) {
  phaseText.textContent = `${phase} · day ${day}`;
}
function runSweep() {
  if (REDUCE) return;
  const s = $("sweep");
  const day = document.documentElement.dataset.phase === "day";
  s.style.background = day
    ? "radial-gradient(circle at 30% 50%, rgba(255,214,130,.5), transparent 40%)"
    : "radial-gradient(circle at 30% 50%, rgba(120,150,255,.45), transparent 40%)";
  s.classList.remove("run");
  void s.offsetWidth;
  s.classList.add("run");
}
function narrate(phase, day) {
  const n = $("narrator");
  if (!n) return;
  n.innerHTML =
    phase === "night"
      ? `<span class="big">🌙 Night ${day}</span><span class="sub">the village sleeps — wolves, seer and doctor move in secret</span>`
      : `<span class="big">☀ Day ${day}</span><span class="sub">the town gathers to accuse, defend, and vote</span>`;
  n.classList.remove("run");
  void n.offsetWidth;
  n.classList.add("run");
}
function deathFlash() {
  if (REDUCE) return;
  const f = $("flash");
  if (!f) return;
  f.classList.remove("run");
  void f.offsetWidth;
  f.classList.add("run");
}
function showWin(winner) {
  const win = $("win");
  win.dataset.winner = winner;
  $("winTitle").textContent = winner === "werewolf" ? "Werewolves win" : "Village wins";
  $("winSub").textContent =
    winner === "werewolf" ? "deception prevailed" : "the town rooted out the wolves";
  win.classList.add("show");
  confetti(winner === "werewolf" ? ["#e5484d", "#7a1f22"] : ["#46c08a", "#4cc2ff", "#ffd592"]);
}
function confetti(colors) {
  if (REDUCE) return;
  for (let i = 0; i < 80; i++) {
    const c = document.createElement("i");
    c.className = "confetti";
    c.style.left = Math.random() * 100 + "vw";
    c.style.background = colors[i % colors.length];
    c.style.animationDuration = 2.4 + Math.random() * 2 + "s";
    c.style.animationDelay = Math.random() * 0.6 + "s";
    c.style.transform = `rotate(${Math.random() * 360}deg)`;
    document.body.appendChild(c);
    setTimeout(() => c.remove(), 5200);
  }
}

// ============================================================ lifecycle
function resetState() {
  state.phase = "night";
  state.day = 0;
  state.pending = null;
  state.pairSeq = 0;
  state.players.clear();
  state.votes.clear();
  for (const n of NAMES) state.players.set(n, { alive: true, role: null });
  document.documentElement.dataset.phase = "night";
  clearSpotlight();
  Queue.reset();
  Thinking.clearAll();
  Graph.reset();
  publicFeed.innerHTML = "";
  privateFeed.innerHTML = "";
  $("win").classList.remove("show");
  $("publicPill").classList.remove("show");
  $("privatePill").classList.remove("show");
  renderRoster();
}

$("start").addEventListener("click", () => {
  if (state.ws && state.ws.readyState <= 1) state.ws.close();
  SoundKit.init();
  Atmosphere.init();
  resetState();
  const btn = $("start");
  btn.disabled = true;
  btn.textContent = "Connecting…";
  phaseText.textContent = "connecting";
  const ws = new WebSocket(`ws://${location.host}/ws/game`);
  state.ws = ws;
  ws.onopen = () => {
    btn.textContent = "Live";
    phasePill.dataset.live = "true";
  };
  ws.onmessage = (m) => {
    try {
      Queue.enqueue(JSON.parse(m.data));
    } catch (e) {
      console.error("bad event", e, m.data);
    }
  };
  ws.onerror = () => {
    phaseText.textContent = "connection error";
  };
  ws.onclose = () => {
    btn.disabled = false;
    btn.textContent = "Run again";
    phasePill.dataset.live = "false";
    Queue.enqueue({ kind: "_closed" });
  };
});

// speed control
$("speedCtl").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-speed]");
  if (!b) return;
  const v = b.dataset.speed;
  Queue.speed = v === "inf" ? Infinity : Number(v);
  localStorage.setItem("ww.speed", v);
  $("speedCtl")
    .querySelectorAll("button")
    .forEach((x) => x.classList.toggle("on", x === b));
});
(function initSpeed() {
  const v = localStorage.getItem("ww.speed") || "1";
  Queue.speed = v === "inf" ? Infinity : Number(v);
  $("speedCtl")
    .querySelectorAll("button")
    .forEach((x) => x.classList.toggle("on", x.dataset.speed === v));
})();

// mute toggle
const muteBtn = $("muteToggle");
function paintMute() {
  muteBtn.textContent = SoundKit.muted ? "🔇" : "🔊";
  muteBtn.setAttribute("aria-pressed", String(SoundKit.muted));
}
muteBtn.addEventListener("click", () => {
  SoundKit.setMuted(!SoundKit.muted);
  if (!SoundKit.muted) SoundKit.ambient(state.phase);
  paintMute();
});
paintMute();

// web toggle
$("webToggle").addEventListener("click", () => {
  const on = document.body.dataset.web === "on";
  document.body.dataset.web = on ? "off" : "on";
  $("webToggle").setAttribute("aria-pressed", String(!on));
  if (!on) requestAnimationFrame(() => Graph.start());
  else Graph.stop();
});

// instructions / help
const help = $("help");
const openHelp = () => help.classList.add("show");
const closeHelp = () => help.classList.remove("show");
$("helpToggle").addEventListener("click", openHelp);
$("helpClose").addEventListener("click", closeHelp);
help.addEventListener("click", (e) => {
  if (e.target === help) closeHelp();
});
window.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeHelp();
});
if (!localStorage.getItem("ww.seen")) {
  openHelp();
  localStorage.setItem("ww.seen", "1");
}

// scroll pills
[$("publicPill"), $("privatePill")].forEach((pill) => {
  const feed = pill.previousElementSibling;
  pill.addEventListener("click", () => {
    feed.scrollTo({ top: feed.scrollHeight, behavior: "smooth" });
    pill.classList.remove("show");
  });
  feed.addEventListener("scroll", () => {
    if (nearBottom(feed)) pill.classList.remove("show");
  });
});

// keyboard speed shortcuts
window.addEventListener("keydown", (e) => {
  if (e.key === "1") $("speedCtl").querySelector('[data-speed="1"]').click();
  else if (e.key === "2") $("speedCtl").querySelector('[data-speed="2"]').click();
  else if (e.key === "0") $("speedCtl").querySelector('[data-speed="inf"]').click();
});

renderRoster();
