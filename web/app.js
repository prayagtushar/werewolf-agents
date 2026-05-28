"use strict";

// ----------------------------------------------------------------- constants
const NAMES = ["Ava", "Ben", "Cleo", "Dan", "Eve", "Finn", "Gwen"];
const ROLE_META = {
  werewolf: { glyph: "🐺", team: "werewolf", color: "var(--wolf)" },
  seer: { glyph: "🔮", team: "village", color: "var(--seer)" },
  doctor: { glyph: "✚", team: "village", color: "var(--doctor)" },
  villager: { glyph: "🧑", team: "village", color: "var(--villager)" },
};
// reasoning that reads like a cover story rather than honest deduction
const DECEPTION_RE =
  /redirect|reframe|frame|deflect|cover|accuse .* instead|throw .* under|\blie\b|pretend|conceal|mislead|blend in|scapegoat|act (?:calm|innocent)|cast (?:doubt|suspicion)|pin it/i;

// --------------------------------------------------------------------- state
const state = {
  ws: null,
  phase: "night",
  day: 0,
  players: new Map(), // name -> { alive, role, votes }
  votes: new Map(), // target -> count (reset each day)
  pending: null, // { actor, node, deception, pairId }
  pairSeq: 0,
  spotlight: null, // { a: node, b: node }
};

// --------------------------------------------------------------------- dom
const $ = (id) => document.getElementById(id);
const roster = $("roster");
const publicFeed = $("publicFeed");
const privateFeed = $("privateFeed");
const phasePill = $("phasePill");
const phaseText = $("phaseText");
const connector = $("connector");
const connectorPath = $("connectorPath");

// ------------------------------------------------------------------ roster
function hue(name) {
  let h = 0;
  for (const c of name) h = (h * 31 + c.charCodeAt(0)) % 360;
  return h;
}

function renderRoster() {
  roster.innerHTML = "";
  for (const name of NAMES) {
    const p = state.players.get(name) || { alive: true, role: null };
    const card = document.createElement("div");
    card.className = "player";
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
      <div class="avatar" style="background:hsl(${hue(name)} 70% 62%)">
        <span class="front">${name[0]}</span>
        <span class="back" style="color:${meta ? meta.color : "#fff"}">${meta ? meta.glyph : ""}</span>
      </div>
      <div class="pname">${p.alive ? name : "💀 " + name}</div>
      <div class="prole">${p.role ? p.role : ""}</div>
      <div class="vote-track"><div class="vote-fill"></div></div>`;
    roster.appendChild(card);
  }
}

const cardOf = (name) => roster.querySelector(`.player[data-name="${name}"]`);

function markSpeaking(actor) {
  roster.querySelectorAll(".player[data-speaking]").forEach((c) =>
    c.removeAttribute("data-speaking")
  );
  const c = cardOf(actor);
  if (c && c.dataset.alive === "true") c.dataset.speaking = "true";
}

// --------------------------------------------------------------- feed utils
function nearBottom(feed) {
  return feed.scrollHeight - feed.scrollTop - feed.clientHeight < 90;
}

function appendTo(feed, node, pill) {
  const stick = nearBottom(feed);
  feed.appendChild(node);
  while (feed.childElementCount > 200) feed.removeChild(feed.firstElementChild);
  if (stick) feed.scrollTo({ top: feed.scrollHeight, behavior: "smooth" });
  else if (pill) pill.classList.add("show");
  return node;
}

function el(tag, cls, html) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (html != null) n.innerHTML = html;
  return n;
}

const esc = (s) =>
  (s || "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[c]);

// ----------------------------------------------------------------- handlers
function onPhase(ev) {
  if (ev.text === "no_elimination") {
    appendTo(publicFeed, el("div", "plaque", "⚖&nbsp; A tie — no one was eliminated"), $("publicPill"));
    return;
  }
  state.phase = ev.text;
  state.day = ev.day;
  document.documentElement.dataset.phase = ev.text;
  setPhasePill(ev.text, ev.day);
  runSweep();
  $("phaseText").parentElement.dataset.live = "true";
  if (ev.text === "day") {
    state.votes.clear();
    clearVoteBars();
  }
  const label = `${ev.text === "night" ? "🌙 Night" : "☀ Day"} ${ev.day}`;
  appendTo(publicFeed, el("div", "divider", label), $("publicPill"));
  appendTo(privateFeed, el("div", "divider", label), $("privatePill"));
}

function onReasoning(ev) {
  markSpeaking(ev.actor);
  const pairId = "p" + ++state.pairSeq;
  const deception = DECEPTION_RE.test(ev.text || "");
  const node = el("div", "private-bubble decrypt");
  node.dataset.pair = pairId;
  node.dataset.pairActor = ev.actor;
  if (deception) node.dataset.deception = "true";
  node.innerHTML = `
    <div class="tagline">🔒 ${esc(ev.actor)} · ${deception ? "⚠ cover story" : "true thought"}</div>
    <span class="body">${esc(ev.text)}</span>`;
  appendTo(privateFeed, node, $("privatePill"));
  state.pending = { actor: ev.actor, node, deception, pairId };
}

function onSpeak(ev) {
  markSpeaking(ev.actor);
  const pend = state.pending;
  const paired = pend && pend.actor === ev.actor;
  const node = el("div", "bubble public-bubble");
  node.innerHTML = `<span class="who">${esc(ev.actor)}</span>${esc(ev.text)}`;
  if (paired) {
    node.dataset.pair = pend.pairId;
    node.dataset.pairActor = ev.actor;
    if (pend.deception) {
      node.dataset.deception = "true";
      spotlightPair(pend.node, node);
    }
  }
  appendTo(publicFeed, node, $("publicPill"));
  state.pending = null;
}

function onVote(ev) {
  const target = ev.text;
  state.votes.set(target, (state.votes.get(target) || 0) + 1);
  updateVoteBar(target);
  recomputeLead();
  voteTracer(ev.actor, target);
  appendTo(
    publicFeed,
    el("div", "vote-line", `🗳 ${esc(ev.actor)} → <b>${esc(target)}</b>`),
    $("publicPill")
  );
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
  appendTo(publicFeed, el("div", "plaque death", "💀&nbsp; " + esc(ev.text)), $("publicPill"));
}

function onResult(ev) {
  const winner = (ev.data && ev.data.winner) || "village";
  revealAll();
  clearSpotlight();
  showWin(winner);
  phasePill.dataset.live = "false";
}

const HANDLERS = {
  phase: onPhase,
  reasoning: onReasoning,
  speak: onSpeak,
  vote: onVote,
  death: onDeath,
  result: onResult,
};

function handle(ev) {
  (HANDLERS[ev.kind] || (() => {}))(ev);
}

// -------------------------------------------------------------- vote visuals
function aliveCount() {
  let n = 0;
  for (const p of state.players.values()) if (p.alive) n++;
  return n || 1;
}

function updateVoteBar(target) {
  const card = cardOf(target);
  if (!card) return;
  const count = state.votes.get(target) || 0;
  card.querySelector(".vote-fill").style.width =
    Math.min(100, (count / aliveCount()) * 100) + "%";
  const badge = card.querySelector(".vote-badge");
  badge.textContent = String(count);
  badge.classList.add("show");
  badge.classList.remove("bump");
  void badge.offsetWidth; // restart animation
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
  const a = cardOf(from);
  const b = cardOf(to);
  if (!a || !b) return;
  const ra = a.getBoundingClientRect();
  const rb = b.getBoundingClientRect();
  const dot = document.createElement("div");
  dot.style.cssText = `position:fixed;z-index:25;width:8px;height:8px;border-radius:50%;
    background:var(--wolf);box-shadow:0 0 10px var(--wolf);pointer-events:none;
    left:${ra.left + ra.width / 2}px;top:${ra.top + ra.height / 2}px;
    transition:transform .55s cubic-bezier(.4,.1,.2,1),opacity .55s ease;`;
  document.body.appendChild(dot);
  requestAnimationFrame(() => {
    dot.style.transform = `translate(${rb.left + rb.width / 2 - (ra.left + ra.width / 2)}px,
      ${rb.top + rb.height / 2 - (ra.top + ra.height / 2)}px)`;
    dot.style.opacity = "0.2";
  });
  setTimeout(() => dot.remove(), 650);
}

// --------------------------------------------------------------- role reveal
function parseRole(text) {
  const m = /(werewolf|seer|doctor|villager)/i.exec(text || "");
  return m ? m[1].toLowerCase() : null;
}

function flipCard(name, role) {
  const card = cardOf(name);
  if (!card) return;
  card.dataset.alive = "false";
  if (role) {
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
  card.querySelector(".pname").innerHTML = "💀 " + name;
}

function revealAll() {
  let i = 0;
  for (const name of NAMES) {
    const p = state.players.get(name);
    if (!p || !p.role) continue;
    const card = cardOf(name);
    if (!card || card.dataset.role) continue;
    setTimeout(() => {
      card.dataset.role = p.role;
      card.dataset.team = ROLE_META[p.role]?.team || "village";
      const meta = ROLE_META[p.role];
      const back = card.querySelector(".avatar .back");
      back.textContent = meta.glyph;
      back.style.color = meta.color;
      card.querySelector(".prole").textContent = p.role;
    }, 70 * i++);
  }
}

// retro-upgrade a confirmed wolf's flagged pairs
function confirmLies(actor) {
  document
    .querySelectorAll(`.private-bubble[data-pair-actor="${actor}"][data-deception="true"] .tagline`)
    .forEach((t) => (t.innerHTML = `🩸 ${esc(actor)} · CONFIRMED LIE`));
}

// ----------------------------------------------------------- spotlight / link
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
  const { a, b } = state.spotlight;
  const ra = a.getBoundingClientRect();
  const rb = b.getBoundingClientRect();
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

// ------------------------------------------------------------- phase chrome
function setPhasePill(phase, day) {
  phaseText.textContent = `${phase} · day ${day}`;
}

function runSweep() {
  const s = $("sweep");
  const day = document.documentElement.dataset.phase === "day";
  s.style.background = day
    ? "radial-gradient(circle at 30% 50%, rgba(255,214,130,.5), transparent 40%)"
    : "radial-gradient(circle at 30% 50%, rgba(120,150,255,.45), transparent 40%)";
  s.classList.remove("run");
  void s.offsetWidth;
  s.classList.add("run");
}

// ------------------------------------------------------------------ win
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
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduce) return;
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

// ------------------------------------------------------------- ws lifecycle
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
  publicFeed.innerHTML = "";
  privateFeed.innerHTML = "";
  $("win").classList.remove("show");
  $("publicPill").classList.remove("show");
  $("privatePill").classList.remove("show");
  renderRoster();
}

$("start").addEventListener("click", () => {
  if (state.ws && state.ws.readyState <= 1) state.ws.close();
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
      handle(JSON.parse(m.data));
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
    appendTo(publicFeed, el("div", "divider", "— stream closed —"), $("publicPill"));
  };
});

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

renderRoster();
