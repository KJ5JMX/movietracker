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
  .current { font-size:13px; color:var(--muted); }
  .battle-row { border-bottom:1px solid var(--border); padding:8px 0;
    font-size:13px; display:flex; justify-content:space-between; align-items:center; }
</style>
</head>
<body>
<div class="wrap">
  <h1>ShelfMates Movie Fest — Admin</h1>

  <!-- MOVIE OF THE WEEK -->
  <div class="card">
    <h2>Movie of the Week</h2>
    <div class="current" id="motm-current">Loading current pick...</div>
    <label>Search a movie</label>
    <input type="text" id="motm-q" placeholder="e.g. The Shawshank Redemption" />
    <div class="results" id="motm-results"></div>
    <div id="motm-chosen"></div>
    <label>Where to stream (you verify before pushing)</label>
    <div class="plats" id="motm-plats"></div>
    <div class="row">
      <div class="col">
        <label>Week (YYYY-Www, blank = this week)</label>
        <input type="text" id="motm-month" placeholder="2026-W27" />
      </div>
    </div>
    <label>Blurb (optional)</label>
    <textarea id="motm-blurb" placeholder="Why this one this month..."></textarea>
    <div style="margin-top:12px"><button id="motm-save">Set Movie of the Month</button></div>
    <div class="msg" id="motm-msg"></div>
  </div>

  <!-- BATTLE -->
  <div class="card">
    <h2>New Battle</h2>
    <label>Battle title</label>
    <input type="text" id="b-title" placeholder="July Battle" />
    <div class="row">
      <div class="col">
        <h2 style="font-size:13px">Movie A</h2>
        <input type="text" id="ba-q" placeholder="Search movie A" />
        <div class="results" id="ba-results"></div>
        <div id="ba-chosen"></div>
        <div class="plats" id="ba-plats"></div>
      </div>
      <div class="col">
        <h2 style="font-size:13px">Movie B</h2>
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
    <h2 style="margin-top:18px; font-size:13px">Active battles</h2>
    <div id="b-list"></div>
  </div>
</div>

<script>
const PLATFORMS = ["netflix","hulu","amazon","hbo","disney","appletv","other"];
const LABELS = {netflix:"Netflix",hulu:"Hulu",amazon:"Amazon",hbo:"HBO",disney:"Disney+",appletv:"Apple TV",other:"Other"};

async function api(path, opts={}) {
  const r = await fetch("/admin/api" + path, {
    headers: {"Content-Type":"application/json"},
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  return r.json();
}

// Generic movie-search widget bound to a state object.
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
  renderPlats();

  let timer = null;
  q.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      if (!q.value.trim()) { results.innerHTML = ""; return; }
      const data = await api("/search?q=" + encodeURIComponent(q.value));
      results.innerHTML = "";
      (data || []).slice(0, 8).forEach(m => {
        const el = document.createElement("div");
        el.className = "res";
        el.innerHTML = '<img src="' + (m.poster || "") + '" onerror="this.style.opacity=0" />' +
          '<div class="t">' + m.title + ' (' + (m.year || "?") + ')</div>';
        el.onclick = () => {
          state.movie = m;
          chosen.innerHTML = '<div class="chosen"><img src="' + (m.poster||"") +
            '"/><span>Selected: <b>' + m.title + '</b> (' + (m.year||"?") + ')</span></div>';
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

// ---- Movie of the Month ----
const motm = {};
makeSearch("motm-q","motm-results","motm-chosen","motm-plats", motm);

async function loadCurrentMotm() {
  const d = await api("/movie-of-week");
  const el = document.getElementById("motm-current");
  if (d.movie_of_week) {
    const m = d.movie_of_week;
    el.textContent = "Current: " + m.title + " (" + (m.year||"?") + ") · " + m.week_key +
      " · streaming: " + (m.streaming.map(p=>LABELS[p]).join(", ") || "none set");
  } else { el.textContent = "No Movie of the Week set yet."; }
}

document.getElementById("motm-save").onclick = async () => {
  const msg = document.getElementById("motm-msg");
  const p = motm.payload();
  if (!p) { msg.className="msg err"; msg.textContent="Pick a movie first."; return; }
  p.week_key = document.getElementById("motm-month").value.trim();
  p.blurb = document.getElementById("motm-blurb").value.trim();
  const d = await api("/movie-of-week", {method:"POST", body:p});
  if (d.movie_of_week) { msg.className="msg ok"; msg.textContent="Saved."; loadCurrentMotm(); }
  else { msg.className="msg err"; msg.textContent = d.message || "Failed."; }
};

// ---- Battle ----
const ba = {}, bb = {};
makeSearch("ba-q","ba-results","ba-chosen","ba-plats", ba);
makeSearch("bb-q","bb-results","bb-chosen","bb-plats", bb);

async function loadBattles() {
  const d = await api("/battles");
  const list = document.getElementById("b-list");
  list.innerHTML = "";
  (d.battles || []).forEach(b => {
    if (!b.active) return;
    const row = document.createElement("div");
    row.className = "battle-row";
    row.innerHTML = "<span>" + b.title + ": <b>" + b.movie_a.title + "</b> (" +
      b.movie_a.votes + ") vs <b>" + b.movie_b.title + "</b> (" + b.movie_b.votes +
      ")" + (b.closed ? " · closed" : "") + "</span>";
    const btn = document.createElement("button");
    btn.className = "ghost"; btn.textContent = "Close";
    btn.onclick = async () => { await api("/battles/"+b.id+"/close",{method:"POST"}); loadBattles(); };
    row.appendChild(btn);
    list.appendChild(row);
  });
}

document.getElementById("b-save").onclick = async () => {
  const msg = document.getElementById("b-msg");
  const pa = ba.payload(), pb = bb.payload();
  if (!pa || !pb) { msg.className="msg err"; msg.textContent="Pick both movies."; return; }
  const d = await api("/battles", {method:"POST", body:{
    title: document.getElementById("b-title").value.trim(),
    movie_a: pa, movie_b: pb,
    days: parseInt(document.getElementById("b-days").value) || 30,
  }});
  if (d.id) { msg.className="msg ok"; msg.textContent="Battle created."; loadBattles(); }
  else { msg.className="msg err"; msg.textContent = d.message || "Failed."; }
};

loadCurrentMotm();
loadBattles();
</script>
</body>
</html>
"""
