"""The ShelfMates Movie Fest admin page — a single self-contained HTML/JS page
served at /admin (behind Cloudflare Access). No build step, no framework. All
fetches are same-origin to /admin/api/* so they ride the same Access session."""

ADMIN_PAGE_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>ShelfMates Movie Fest — Admin</title>
<style>
  :root {
    --bg:#1F1813; --card:#2D2620; --ink:#F0E6D5; --muted:#bdae97;
    --green:#6A9B7F; --amber:#E5A050; --border:#4a3f33; --danger:#c9694f;
  }
  * { box-sizing:border-box; }
  body { margin:0; font-family:-apple-system,Segoe UI,Roboto,sans-serif;
    background:var(--bg); color:var(--ink); padding:24px; }
  h1 { font-size:22px; letter-spacing:1px; }
  h2 { font-size:15px; letter-spacing:2px; text-transform:uppercase;
    color:var(--amber); margin-top:0; }
  h3 { font-size:13px; letter-spacing:1px; text-transform:uppercase;
    color:var(--muted); margin:14px 0 6px; }
  .wrap { max-width:880px; margin:0 auto; }
  .card { background:var(--card); border:2px solid var(--border);
    border-radius:10px; padding:18px; margin-bottom:22px; }
  label { display:block; font-size:12px; color:var(--muted); margin:10px 0 4px; }
  input[type=text], input[type=number], textarea {
    width:100%; padding:10px; border-radius:7px; border:2px solid var(--border);
    background:var(--bg); color:var(--ink); font-size:14px; }
  textarea { min-height:60px; }
  button { background:var(--green); color:#10261c; border:none; border-radius:7px;
    padding:10px 16px; font-weight:700; cursor:pointer; font-size:14px; }
  button.ghost { background:transparent; color:var(--muted);
    border:2px solid var(--border); }
  button.amber { background:var(--amber); color:#3a2410; }
  button.small { padding:6px 10px; font-size:12px; }
  .results { display:flex; flex-wrap:wrap; gap:10px; margin-top:10px; }
  .res { width:120px; cursor:pointer; border:2px solid var(--border);
    border-radius:8px; padding:6px; background:var(--bg); }
  .res img { width:100%; height:160px; object-fit:cover; border-radius:5px;
    background:#000; }
  .res.sel { border-color:var(--amber); }
  .res .t { font-size:11px; margin-top:4px; line-height:1.2; }
  .plats { display:flex; flex-wrap:wrap; gap:8px; margin-top:6px; }
  .plat { padding:6px 12px; border-radius:7px; border:2px solid var(--border);
    cursor:pointer; font-size:13px; user-select:none; }
  .plat.on { background:var(--green); color:#10261c; border-color:var(--green); }
  .chosen { display:flex; gap:10px; align-items:center; margin-top:8px;
    font-size:13px; color:var(--muted); }
  .chosen img { width:40px; height:60px; object-fit:cover; border-radius:4px; }
  .row { display:flex; gap:18px; }
  .col { flex:1; }
  .msg { font-size:13px; margin-top:8px; min-height:18px; }
  .ok { color:var(--green); } .err { color:var(--danger); }
  .current { font-size:14px; color:var(--ink); margin-bottom:6px; }
  .current b { color:var(--amber); }
  .dash-row { border-bottom:1px solid var(--border); padding:10px 0;
    font-size:13px; display:flex; justify-content:space-between;
    align-items:center; gap:10px; flex-wrap:wrap; }
  .dash-actions { display:flex; gap:8px; flex-wrap:wrap; }
  .pill { background:var(--green); color:#10261c; border-radius:10px;
    padding:1px 8px; font-size:11px; font-weight:700; margin-left:6px; }
</style>
</head>
<body>
<div class="wrap">
  <h1>ShelfMates Movie Fest — Admin</h1>

  <!-- MOVIE OF THE WEEK -->
  <div class="card">
    <h2>Movie of the Week</h2>
    <div class="current" id="motm-current">Loading current pick...</div>
    <div style="margin-bottom:10px">
      <button class="ghost small" id="motm-notify">Notify users of this pick</button>
    </div>
    <label>Search a movie (or edit the current pick below)</label>
    <input type="text" id="motm-q" placeholder="e.g. The Big Lebowski" />
    <div class="results" id="motm-results"></div>
    <div id="motm-chosen"></div>
    <label>Where to stream (you verify before pushing)</label>
    <div class="plats" id="motm-plats"></div>
    <label>Week (YYYY-Www, blank = this week)</label>
    <input type="text" id="motm-month" placeholder="2026-W27" />
    <label>Blurb (optional)</label>
    <textarea id="motm-blurb" placeholder="Why this one this week..."></textarea>
    <div style="margin-top:12px"><button id="motm-save">Save Movie of the Week</button></div>
    <div class="msg" id="motm-msg"></div>
  </div>

  <!-- BATTLE -->
  <div class="card">
    <h2>New Battle</h2>
    <label>Battle title</label>
    <input type="text" id="b-title" placeholder="July Battle" />
    <div class="row">
      <div class="col">
        <h3>Movie A</h3>
        <input type="text" id="ba-q" placeholder="Search movie A" />
        <div class="results" id="ba-results"></div>
        <div id="ba-chosen"></div>
        <div class="plats" id="ba-plats"></div>
      </div>
      <div class="col">
        <h3>Movie B</h3>
        <input type="text" id="bb-q" placeholder="Search movie B" />
        <div class="results" id="bb-results"></div>
        <div id="bb-chosen"></div>
        <div class="plats" id="bb-plats"></div>
      </div>
    </div>
    <label>Voting window (days)</label>
    <input type="number" id="b-days" value="30" min="1" max="90" />
    <div style="margin-top:12px"><button class="amber" id="b-save">Create Battle</button></div>
    <div class="msg" id="b-msg"></div>
  </div>

  <!-- NUMBERS -->
  <div class="card">
    <h2>Numbers</h2>
    <div id="stats-grid" style="display:flex;flex-wrap:wrap;gap:10px">Loading...</div>
    <div class="msg" id="stats-msg"></div>
  </div>

  <!-- DASHBOARD -->
  <div class="card">
    <h2>Dashboard</h2>
    <h3>Movie of the Week — history</h3>
    <div id="dash-weeks">Loading...</div>
    <h3 style="margin-top:18px">Battles</h3>
    <div id="dash-battles">Loading...</div>
    <div class="msg" id="dash-msg"></div>
  </div>
</div>

<script>
const PLATFORMS = ["netflix","hulu","amazon","hbo","disney","appletv","paramount","peacock","starz","showtime","amc","tubi","crunchyroll","other"];
const LABELS = {netflix:"Netflix",hulu:"Hulu",amazon:"Amazon",hbo:"HBO",disney:"Disney+",appletv:"Apple TV",paramount:"Paramount+",peacock:"Peacock",starz:"Starz",showtime:"Showtime",amc:"AMC+",tubi:"Tubi",crunchyroll:"Crunchyroll",other:"Other"};

// Throws on any non-OK response so failures are visible instead of silent.
async function api(path, opts={}) {
  const r = await fetch("/admin/api" + path, {
    headers: {"Content-Type":"application/json"},
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (!r.ok) {
    let m = "Error " + r.status;
    try { const j = await r.json(); if (j && j.message) m = j.message; } catch (e) {}
    throw new Error(m);
  }
  return r.json();
}
function setMsg(id, text, ok) {
  const el = document.getElementById(id);
  el.className = "msg " + (ok ? "ok" : "err");
  el.textContent = text;
}

// Movie-search widget bound to a state object.
function makeSearch(qId, resultsId, chosenId, platsId, state) {
  const q = document.getElementById(qId);
  const results = document.getElementById(resultsId);
  const chosen = document.getElementById(chosenId);
  const plats = document.getElementById(platsId);
  state.platforms = new Set();

  function renderPlats() {
    plats.innerHTML = "";
    PLATFORMS.forEach(p => {
      const el = document.createElement("div");
      el.className = "plat" + (state.platforms.has(p) ? " on" : "");
      el.textContent = LABELS[p];
      el.onclick = () => {
        if (state.platforms.has(p)) state.platforms.delete(p);
        else state.platforms.add(p);
        renderPlats();
      };
      plats.appendChild(el);
    });
  }
  function showChosen(m) {
    chosen.innerHTML = m
      ? '<div class="chosen"><img src="' + (m.poster||"") +
        '"/><span>Selected: <b>' + m.title + '</b> (' + (m.year||"?") + ')</span></div>'
      : "";
  }
  renderPlats();

  // Lets the caller prefill the form for editing an existing pick.
  state.setSelection = (movie, platformList) => {
    state.movie = movie;
    state.platforms = new Set(platformList || []);
    showChosen(movie);
    renderPlats();
  };

  let timer = null;
  q.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      if (!q.value.trim()) { results.innerHTML = ""; return; }
      let data = [];
      try { data = await api("/search?q=" + encodeURIComponent(q.value)); }
      catch (e) { return; }
      results.innerHTML = "";
      (data || []).slice(0, 8).forEach(m => {
        const el = document.createElement("div");
        el.className = "res";
        el.innerHTML = '<img src="' + (m.poster || "") + '" onerror="this.style.opacity=0" />' +
          '<div class="t">' + m.title + ' (' + (m.year || "?") + ')</div>';
        el.onclick = () => {
          state.movie = m;
          showChosen(m);
          [...results.children].forEach(c => c.classList.remove("sel"));
          el.classList.add("sel");
        };
        results.appendChild(el);
      });
    }, 300);
  });

  state.payload = () => state.movie ? ({
    imdb_id: state.movie.imdb_id, title: state.movie.title,
    year: state.movie.year, poster: state.movie.poster,
    streaming: [...state.platforms],
  }) : null;
}

// ---- Movie of the Week ----
const motm = {};
makeSearch("motm-q","motm-results","motm-chosen","motm-plats", motm);

async function loadCurrentMotm() {
  const el = document.getElementById("motm-current");
  let d;
  try { d = await api("/movie-of-week"); }
  catch (e) { el.innerHTML = '<span class="err">Could not load: ' + e.message + '</span>'; return; }
  if (d.movie_of_week) {
    const m = d.movie_of_week;
    el.innerHTML = "Currently in progress: <b>" + m.title + "</b> (" + (m.year||"?") +
      ") · week " + m.week_key + " · streaming: " +
      (m.streaming.map(p=>LABELS[p]).join(", ") || "none set");
    // Prefill the form so you can edit blurb / streaming mid-week and re-save.
    motm.setSelection(
      {imdb_id:m.imdb_id, title:m.title, year:m.year, poster:m.poster},
      m.streaming);
    document.getElementById("motm-month").value = m.week_key;
    document.getElementById("motm-blurb").value = m.blurb || "";
  } else {
    el.textContent = "No Movie of the Week set yet.";
  }
}

document.getElementById("motm-save").onclick = async () => {
  const p = motm.payload();
  if (!p) { setMsg("motm-msg", "Pick a movie first.", false); return; }
  p.week_key = document.getElementById("motm-month").value.trim();
  p.blurb = document.getElementById("motm-blurb").value.trim();
  try {
    await api("/movie-of-week", {method:"POST", body:p});
    setMsg("motm-msg", "Saved.", true);
    loadCurrentMotm();
    loadDashboard();
  } catch (e) { setMsg("motm-msg", e.message, false); }
};

document.getElementById("motm-notify").onclick = async () => {
  try {
    await api("/notify/movie-of-week", {method:"POST"});
    setMsg("motm-msg", "Notification sent.", true);
  } catch (e) { setMsg("motm-msg", e.message, false); }
};

// ---- Battle ----
const ba = {}, bb = {};
makeSearch("ba-q","ba-results","ba-chosen","ba-plats", ba);
makeSearch("bb-q","bb-results","bb-chosen","bb-plats", bb);
let editingBattleId = null;

document.getElementById("b-save").onclick = async () => {
  const pa = ba.payload(), pb = bb.payload();
  if (!pa || !pb) { setMsg("b-msg", "Pick both movies.", false); return; }
  const body = {
    title: document.getElementById("b-title").value.trim(),
    movie_a: pa, movie_b: pb,
    days: parseInt(document.getElementById("b-days").value) || 30,
  };
  try {
    if (editingBattleId) {
      await api("/battles/" + editingBattleId + "/update", {method:"POST", body});
      setMsg("b-msg", "Battle updated.", true);
      editingBattleId = null;
      document.getElementById("b-save").textContent = "Create Battle";
    } else {
      await api("/battles", {method:"POST", body});
      setMsg("b-msg", "Battle created.", true);
    }
    loadDashboard();
  } catch (e) { setMsg("b-msg", e.message, false); }
};

async function editBattle(id) {
  let d;
  try { d = await api("/battles"); }
  catch (e) { setMsg("dash-msg", e.message, false); return; }
  const b = (d.battles || []).find(x => x.id === id);
  if (!b) return;
  document.getElementById("b-title").value = b.title;
  ba.setSelection({imdb_id:b.movie_a.imdb_id, title:b.movie_a.title, year:b.movie_a.year, poster:b.movie_a.poster}, b.movie_a.streaming);
  bb.setSelection({imdb_id:b.movie_b.imdb_id, title:b.movie_b.title, year:b.movie_b.year, poster:b.movie_b.poster}, b.movie_b.streaming);
  editingBattleId = id;
  document.getElementById("b-save").textContent = "Update Battle";
  setMsg("b-msg", "Editing: " + b.title + ". Change anything and Update.", true);
  document.getElementById("b-title").scrollIntoView({behavior:"smooth", block:"center"});
}

// ---- Dashboard ----
async function loadDashboard() {
  let d;
  try { d = await api("/dashboard"); }
  catch (e) { setMsg("dash-msg", e.message, false); return; }
  setMsg("dash-msg", "", true);

  const weeks = document.getElementById("dash-weeks");
  weeks.innerHTML = "";
  if (!(d.movies_of_week || []).length) weeks.textContent = "No picks yet.";
  (d.movies_of_week || []).forEach(m => {
    const row = document.createElement("div");
    row.className = "dash-row";
    row.innerHTML = "<span>" + m.week_key + " · <b>" + m.title + "</b> (" +
      (m.year||"?") + ")" + (m.active ? '<span class="pill">current</span>' : "") +
      "</span><span>" + m.completed + " completed</span>";
    weeks.appendChild(row);
  });

  const battles = document.getElementById("dash-battles");
  battles.innerHTML = "";
  if (!(d.battles || []).length) battles.textContent = "No battles yet.";
  (d.battles || []).forEach(b => {
    const row = document.createElement("div");
    row.className = "dash-row";
    const status = b.closed ? "closed" : (b.active ? "voting open" : "ended");
    const winner = b.winner ? (" · winner: " + b.winner) : (b.a_votes===b.b_votes ? " · tie" : "");
    const info = document.createElement("span");
    info.innerHTML = "<b>" + b.title + "</b>: " + b.a_title + " (" + b.a_votes +
      ") vs " + b.b_title + " (" + b.b_votes + ") · " + status + winner;
    const actions = document.createElement("div");
    actions.className = "dash-actions";
    const edit = document.createElement("button");
    edit.className = "ghost small"; edit.textContent = "Edit";
    edit.onclick = () => editBattle(b.id);
    actions.appendChild(edit);
    const nNew = document.createElement("button");
    nNew.className = "ghost small"; nNew.textContent = "Notify new";
    nNew.onclick = async () => {
      try { await api("/notify/battle/"+b.id, {method:"POST"}); setMsg("dash-msg","Sent.",true); }
      catch (e) { setMsg("dash-msg", e.message, false); }
    };
    const nRes = document.createElement("button");
    nRes.className = "ghost small"; nRes.textContent = "Notify result";
    nRes.onclick = async () => {
      try { await api("/notify/battle/"+b.id+"/result", {method:"POST"}); setMsg("dash-msg","Sent.",true); }
      catch (e) { setMsg("dash-msg", e.message, false); }
    };
    actions.appendChild(nNew); actions.appendChild(nRes);
    if (b.active) {
      const close = document.createElement("button");
      close.className = "ghost small"; close.textContent = "Close";
      close.onclick = async () => {
        try { await api("/battles/"+b.id+"/close",{method:"POST"}); loadDashboard(); }
        catch (e) { setMsg("dash-msg", e.message, false); }
      };
      actions.appendChild(close);
    }
    row.appendChild(info); row.appendChild(actions);
    battles.appendChild(row);
  });
}

async function loadStats() {
  let s;
  try { s = await api("/stats"); }
  catch (e) { setMsg("stats-msg", e.message, false); return; }
  setMsg("stats-msg", "", true);
  const tiles = [
    ["Free accounts", s.users_free],
    ["Pro accounts", s.users_pro],
    ["Total users", s.users_total],
    ["Movies", s.movies],
    ["TV shows", s.tv],
    ["Books", s.books],
    ["Songs", s.songs],
    ["Watched", s.watched],
    ["Recs sent", s.recs],
    ["Movie nights", s.movie_nights],
    ["Nights rated", s.nights_rated],
    ["Likes", s.likes],
    ["MotW completions", s.mow_completions],
    ["Battle votes", s.battle_votes],
  ];
  const grid = document.getElementById("stats-grid");
  grid.innerHTML = "";
  tiles.forEach(([label, val]) => {
    const t = document.createElement("div");
    t.style.cssText = "min-width:108px;flex:1 0 108px;padding:12px 14px;border:1px solid #d7d0c4;border-radius:8px;text-align:center;background:#fffdf8";
    t.innerHTML = '<div style="font-size:26px;font-weight:800">' + (val ?? 0) +
      '</div><div style="font-size:12px;color:#777;margin-top:2px">' + label + '</div>';
    grid.appendChild(t);
  });
}

loadStats();
loadCurrentMotm();
loadDashboard();
</script>
</body>
</html>
"""
