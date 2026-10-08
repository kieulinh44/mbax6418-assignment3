/* AI Jukebox — player + jam orchestration */
"use strict";

const $ = (id) => document.getElementById(id);
const els = {
  genre: $("genre"), mood: $("mood"), bpm: $("bpm"), bpmVal: $("bpm-val"),
  theme: $("theme"), vocals: $("vocals"),
  tracks: $("tracks"), tracksVal: $("tracks-val"),
  duration: $("duration"), durationVal: $("duration-val"), dj: $("dj"),
  jamBtn: $("jam-btn"), playBtn: $("play-btn"), deckStatus: $("deck-status"),
  art: $("art"), artFallback: $("art-fallback"), vinyl: $("vinyl"),
  kind: $("kind"), title: $("title"), artist: $("artist"), bar: $("bar"),
  player: $("player"), queue: $("queue"), lights: $("status-lights"),
  singleBtn: $("single-btn"), libraryList: $("library-list"),
  lyricsBox: $("lyrics-box"), lyricsText: $("lyrics-text"),
  libraryCount: $("library-count"),
};

const session = { id: null, pollTimer: null, manifest: null, idx: -1 };

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch (_) { /* ignore */ }
    throw new Error(msg);
  }
  return r.json();
}

/* ---------------- boot ---------------- */

async function boot() {
  try {
    const p = await api("/api/presets");
    fillSelect(els.genre, p.genres.map(v => ({ value: v, label: v })), "synthwave");
    fillSelect(els.mood, p.moods.map(v => ({ value: v, label: v })), "energetic");
    fillSelect(els.dj, p.personas.map(x => ({ value: x.id, label: x.label })), "neon_nina");
    els.tracks.max = p.max_tracks;
    els.duration.max = p.max_duration;
  } catch (e) {
    els.deckStatus.textContent = "Could not load presets: " + e.message;
  }
  els.bpmVal.textContent = "auto";
  setInterval(health, 30000);
  health();
  refreshLibrary();
  bind();
}

function fillSelect(sel, entries, def) {
  sel.innerHTML = "";
  for (const e of entries) {
    const o = document.createElement("option");
    o.value = e.value; o.textContent = e.label;
    sel.appendChild(o);
  }
  sel.value = def;
}

function bind() {
  els.bpm.addEventListener("input", () =>
    els.bpmVal.textContent = els.bpm.value === "0" ? "auto" : els.bpm.value + " BPM");
  els.tracks.addEventListener("input", () => els.tracksVal.textContent = els.tracks.value);
  els.duration.addEventListener("input", () =>
    els.durationVal.textContent = els.duration.value + "s");
  els.jamBtn.addEventListener("click", startJam);
  els.singleBtn.addEventListener("click", () => startJam(true));
  els.playBtn.addEventListener("click", playSet);
  els.player.addEventListener("ended", next);
  els.player.addEventListener("timeupdate", () => {
    if (els.player.duration) {
      els.bar.style.width = (els.player.currentTime / els.player.duration * 100) + "%";
    }
  });
}

/* ---------------- jam lifecycle ---------------- */

async function startJam(single) {
  const options = {
    genre: els.genre.value,
    mood: els.mood.value,
    bpm: els.bpm.value === "0" ? null : parseInt(els.bpm.value, 10),
    theme: els.theme.value.trim(),
    vocals: els.vocals.checked,
    tracks: single ? 1 : parseInt(els.tracks.value, 10),
    duration_sec: parseInt(els.duration.value, 10),
    language: "en",
    dj_persona: els.dj.value,
  };
  setControls(false);
  els.playBtn.hidden = true;
  els.queue.innerHTML = "";
  renderQueuePlaceholder(options.tracks);
  els.deckStatus.innerHTML = single
    ? `<span class="spin">◉</span> Composing your song — hang tight…`
    : `<span class="spin">◉</span> Composing songs — hang tight, this takes a minute or two…`;
  try {
    const r = await api("/api/jam", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(options),
    });
    session.id = r.id;
    session.pollTimer = setInterval(poll, 2000);
    poll();
  } catch (e) {
    els.deckStatus.innerHTML = `<span class="err">✕</span> ${escapeHtml(e.message)}`;
    setControls(true);
  }
}

function renderQueuePlaceholder(n) {
  for (let i = 0; i < n; i++) {
    const li = document.createElement("li");
    li.innerHTML = `<span class="dot"></span><span class="tag song">song</span><span class="tt">…</span>`;
    els.queue.appendChild(li);
  }
}

async function poll() {
  if (!session.id) return;
  let s;
  try { s = await api("/api/session/" + session.id); }
  catch (e) {
    els.deckStatus.innerHTML = `<span class="err">✕</span> ${escapeHtml(e.message)}`;
    return;
  }
  const p = s.progress;
  const pct = p.total ? Math.round(p.done / p.total * 100) : 0;
  els.bar.style.width = pct + "%";

  if (s.state === "ready") {
    clearInterval(session.pollTimer); session.pollTimer = null;
    session.manifest = s.manifest;
    refreshLibrary();
    els.deckStatus.innerHTML = "Set is ready — 100%";
    els.playBtn.hidden = false;
    els.playBtn.textContent = `▶ Play the set (${s.manifest.playlist.length} clips)`;
    renderQueue(s.manifest.playlist);
    setControls(true);
  } else if (s.state === "error") {
    clearInterval(session.pollTimer); session.pollTimer = null;
    els.deckStatus.innerHTML = `<span class="err">✕</span> Generation failed: ${escapeHtml(s.error || "unknown")}`;
    setControls(true);
  } else {
    els.deckStatus.innerHTML = `<span class="spin">◉</span> ${escapeHtml(p.stage || "working")} — ${p.done}/${p.total}`;
  }
}

/* ---------------- playback ---------------- */

function renderQueue(playlist) {
  els.queue.innerHTML = "";
  playlist.forEach((item, i) => {
    const li = document.createElement("li");
    const tag = item.kind === "song" ? "song" : "dj";
    const tt = item.kind === "song" ? `${item.title} — ${item.artist}` : item.title;
    li.innerHTML = `<span class="dot"></span><span class="tag ${tag}">${tag}</span><span class="tt"></span>`;
    li.querySelector(".tt").textContent = tt;
    li.dataset.idx = i;
    els.queue.appendChild(li);
  });
}

function playSet() {
  session.idx = -1;
  els.playBtn.hidden = true;
  next();
}

function next() {
  if (!session.manifest) return; // a lone library track ended; nothing queued
  session.idx++;
  const items = session.manifest.playlist;
  if (session.idx >= items.length) {
    els.deckStatus.textContent = "Set finished — thanks for listening!";
    els.bar.style.width = "0%";
    els.vinyl.classList.remove("spin");
    return;
  }
  const item = items[session.idx];
  els.player.src = item.audio;

  setNowPlaying(item);
  [...els.queue.children].forEach(li => {
    const i = parseInt(li.dataset.idx, 10);
    li.classList.toggle("current", i === session.idx);
    li.classList.toggle("playing", i === session.idx);
    li.classList.toggle("done", i < session.idx);
  });
  els.player.play().catch(() => {
    els.deckStatus.textContent = "⚠ Browser blocked autoplay — hit ▶ Resume to keep going.";
    els.playBtn.hidden = false;
    els.playBtn.textContent = "▶ Resume";
    els.playBtn.onclick = () => { els.playBtn.hidden = true; els.player.play(); };
  });
}

function playSetAt(idx) { session.idx = idx - 1; next(); }

function setNowPlaying(item) {
  const isSong = item.kind === "song";
  els.kind.textContent = isSong ? "now spinning" : (item.kind === "intro" ? "dj · intro" : item.kind === "outro" ? "dj · outro" : "dj · interlude");
  els.title.textContent = item.title;
  els.artist.textContent = item.artist || "—";
  if (item.lyrics) {
    els.lyricsBox.hidden = false;
    els.lyricsText.textContent = item.lyrics;
  } else {
    els.lyricsBox.hidden = true;
  }
  if (isSong && item.art) {
    els.art.src = item.art;
    els.art.classList.add("show");
    els.vinyl.classList.add("spin");
  } else {
    els.art.classList.remove("show");
    els.art.removeAttribute("src");
    els.vinyl.classList.add("spin");
  }
}

/* ---------------- library ---------------- */

async function refreshLibrary() {
  try {
    const d = await api("/api/library");
    renderLibrary(d.tracks || []);
  } catch (_) { /* server not reachable yet */ }
}

function renderLibrary(tracks) {
  els.libraryCount.textContent = tracks.length ? `(${tracks.length})` : "";
  els.libraryList.innerHTML = "";
  if (!tracks.length) {
    const li = document.createElement("li");
    li.className = "empty";
    li.textContent = "No songs yet — generate one!";
    els.libraryList.appendChild(li);
    return;
  }
  for (const t of tracks) {
    const li = document.createElement("li");
    const thumb = t.art_url
      ? `<img class="thumb" src="${t.art_url}" alt=""/>`
      : `<span class="thumb no-art">♪</span>`;
    const vocal = t.vocals
      ? '<span class="chip vocal">vocal</span>'
      : '<span class="chip inst">instrumental</span>';
    li.innerHTML =
      `${thumb}<div class="tt"><div class="t">${escapeHtml(t.title)}</div>` +
      `<div class="a">${escapeHtml(t.artist)}</div></div>` +
      `<span class="chip">${t.bpm || "?"} BPM</span>${vocal}` +
      `<button class="mini play-li" title="Play">▶</button>`;
    li.querySelector(".play-li").addEventListener("click", () => playLibraryTrack(t));
    els.libraryList.appendChild(li);
  }
}

function playLibraryTrack(t) {
  session.manifest = null; // exit set mode; play this single library track
  [...els.queue.children].forEach(li => li.classList.remove("current", "playing", "done"));
  els.player.src = t.audio_url;
  els.vinyl.classList.add("spin");
  setNowPlaying({ kind: "song", title: t.title, artist: t.artist, art: t.art_url, lyrics: t.lyrics });
  els.player.play().catch(() => {
    els.deckStatus.textContent = "⚠ Click ▶ Resume to start playback.";
    els.playBtn.hidden = false;
    els.playBtn.textContent = "▶ Resume";
    els.playBtn.onclick = () => { els.playBtn.hidden = true; els.player.play(); };
  });
}

/* ---------------- health lights ---------------- */

async function health() {
  let data = { services: [] };
  try { data = await api("/api/health"); }
  catch (_) { /* leave lights gray */ }
  els.lights.innerHTML = "";
  for (const s of data.services) {
    const d = document.createElement("div");
    d.className = "dot " + (s.ok ? "ok" : "bad");
    d.title = `${s.name} — ${s.model}${s.ok ? "" : " (down)"}`;
    els.lights.appendChild(d);
  }
}

/* ---------------- misc ---------------- */

function setControls(on) {
  els.jamBtn.disabled = !on;
  els.jamBtn.textContent = on ? "⚡ Start the jam" : "⚡ Jamming…";
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

boot();
