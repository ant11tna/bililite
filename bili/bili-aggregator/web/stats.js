let currentDays = 7;
let creators = [];
let overview = null;

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[ch]));
}

function formatTs(ts) {
  if (!ts) return "-";
  const d = new Date(Number(ts) * 1000);
  if (Number.isNaN(d.getTime())) return "-";
  return d.toLocaleString();
}

function formatTopTnames(top) {
  if (!top || !top.length) return "(无)";
  return top.slice(0, 5).map((x) => `${x.tname}:${x.cnt}`).join(" | ");
}

function renderOverview() {
  const cards = document.getElementById("overviewCards");
  const note = document.getElementById("overviewNote");
  if (!overview) {
    cards.innerHTML = "";
    note.textContent = "";
    return;
  }

  cards.innerHTML = `
    <div class="sub">window_days: ${overview.window_days}</div>
    <div class="sub">pushed_in_window: ${overview.pushed_in_window}</div>
    <div class="sub">distinct_creators_pushed: ${overview.distinct_creators_pushed}</div>
    <div class="sub">top_tnames_pushed: ${escapeHtml(formatTopTnames(overview.top_tnames_pushed || []))}</div>
  `;

  note.textContent = overview.note || "";
}

function applyFilter(rows) {
  const q = document.getElementById("q").value.trim().toLowerCase();
  const onlySuppressed = document.getElementById("onlySuppressed").checked;

  return rows.filter((r) => {
    const matchQ = !q || (String(r.uid).includes(q) || String(r.author_name || "").toLowerCase().includes(q));
    if (!matchQ) return false;

    if (!onlySuppressed) return true;

    const inWindow = r.last_pub_ts != null && Number(r.last_pub_ts) >= (Math.floor(Date.now() / 1000) - currentDays * 86400);
    return Number(r.pushed_count || 0) === 0 && !!r.enabled && inWindow;
  });
}

function renderCreators() {
  const body = document.getElementById("statsBody");
  const note = document.getElementById("creatorNote");
  const filtered = applyFilter(creators);

  body.innerHTML = "";
  if (!filtered.length) {
    body.innerHTML = '<tr><td colspan="10">暂无数据</td></tr>';
  } else {
    for (const r of filtered) {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${r.uid}</td>
        <td>${escapeHtml(r.author_name || "-")}</td>
        <td>${r.enabled ? "true" : "false"}</td>
        <td>${Number(r.priority || 0)}</td>
        <td>${Number(r.weight || 1)}</td>
        <td>${Number(r.pushed_count || 0)}</td>
        <td>${formatTs(r.last_pushed_ts)}</td>
        <td>${formatTs(r.last_pub_ts)}</td>
        <td>${r.freshness_hours == null ? "-" : Number(r.freshness_hours).toFixed(1)}</td>
        <td>${escapeHtml(r.suppression_hint || "")}</td>
      `;
      body.appendChild(tr);
    }
  }

  note.textContent = creators[0]?.note || "";
}

async function load() {
  const [ovRes, creatorsRes] = await Promise.all([
    fetch(`/api/stats/overview?days=${encodeURIComponent(currentDays)}&channel=serverchan`),
    fetch(`/api/stats/creators?days=${encodeURIComponent(currentDays)}&channel=serverchan&limit=200`),
  ]);

  if (!ovRes.ok) throw new Error(`overview HTTP ${ovRes.status}`);
  if (!creatorsRes.ok) throw new Error(`creators HTTP ${creatorsRes.status}`);

  overview = await ovRes.json();
  creators = await creatorsRes.json();

  renderOverview();
  renderCreators();
}

async function refresh() {
  try {
    await load();
  } catch (err) {
    console.warn("load stats failed", err);
  }
}

document.getElementById("days7").addEventListener("click", async () => {
  currentDays = 7;
  await refresh();
});

document.getElementById("days30").addEventListener("click", async () => {
  currentDays = 30;
  await refresh();
});

document.getElementById("btnRefresh").addEventListener("click", refresh);
document.getElementById("q").addEventListener("input", renderCreators);
document.getElementById("onlySuppressed").addEventListener("change", renderCreators);

refresh();
