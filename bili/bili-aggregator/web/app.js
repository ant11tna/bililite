async function load() {
  const q = document.getElementById("q").value.trim();
  const tag = document.getElementById("tag").value.trim();
  const viewMin = document.getElementById("viewMin").value.trim();
  const viewMax = document.getElementById("viewMax").value.trim();
  const sort = document.getElementById("sort").value;

  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (tag) params.set("tag", tag);
  if (viewMin) params.set("view_min", viewMin);
  if (viewMax) params.set("view_max", viewMax);
  params.set("sort", sort);
  params.set("limit", "50");

  const res = await fetch(`http://127.0.0.1:9000/api/videos?${params.toString()}`);
  const data = await res.json();

  const list = document.getElementById("list");
  list.innerHTML = "";

  for (const v of data) {
    const div = document.createElement("div");
    div.className = "card";
    const dt = new Date(v.pub_ts * 1000).toLocaleString();
    div.innerHTML = `
      <div class="title"><a href="${v.url}" target="_blank" rel="noreferrer">${escapeHtml(v.title)}</a></div>
      <div class="meta">${formatAuthor(v)} · ${formatView(v.view)}播放 · ${formatRelativeTime(v.pub_ts)} · ${escapeHtml(v.tname ?? "未分区")}</div>
      <div class="tags">${(v.tags || []).map(t => `<span class="tag">${escapeHtml(t)}</span>`).join("")}</div>
    `;
    list.appendChild(div);
  }
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
  }[c]));
}

function formatView(v) {
  if (v == null) return "-";
  if (v < 10000) return `${v}`;
  return `${(v / 10000).toFixed(1)}万`;
}

function formatRelativeTime(ts) {
  const diff = Math.floor(Date.now() / 1000) - ts;
  if (diff < 60) return "刚刚";
  if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`;
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)}天前`;
  return new Date(ts * 1000).toLocaleDateString();
}

function formatAuthor(v) {
  return v.author_name ? escapeHtml(v.author_name) : `uid=${v.uid}`;
}

document.getElementById("btn").addEventListener("click", load);
load();
