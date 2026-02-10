const STATE = {
  NEW: "NEW",
  LATER: "LATER",
  STAR: "STAR",
  WATCHED: "WATCHED",
  HIDDEN: "HIDDEN",
};

let currentVideos = [];
let undoAction = null;

async function loadGroups() {
  const select = document.getElementById("group");
  try {
    const res = await fetch("/api/creator-groups");
    if (!res.ok) return;
    const groups = await res.json();
    for (const g of groups) {
      const opt = document.createElement("option");
      opt.value = g;
      opt.textContent = g;
      select.appendChild(opt);
    }
  } catch {
    // ignore load errors
  }
}

async function load() {
  const q = document.getElementById("q").value.trim();
  const tag = document.getElementById("tag").value.trim();
  const viewMin = document.getElementById("viewMin").value.trim();
  const viewMax = document.getElementById("viewMax").value.trim();
  const group = document.getElementById("group").value;
  const onlyWhitelist = document.getElementById("onlyWhitelist").checked;
  const sort = document.getElementById("sort").value;

  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (tag) params.set("tag", tag);
  if (viewMin) params.set("view_min", viewMin);
  if (viewMax) params.set("view_max", viewMax);
  if (group) params.set("group", group);
  if (!onlyWhitelist) params.set("only_whitelist", "false");
  params.set("sort", sort);
  params.set("limit", "50");

  const res = await fetch(`/api/videos?${params.toString()}`);
  const data = await res.json();
  currentVideos = data;
  renderList(currentVideos);
}

async function loadDaily() {
  const res = await fetch("/api/daily");
  const data = await res.json();
  currentVideos = data;
  renderList(currentVideos);
}

function renderList(data) {
  const list = document.getElementById("list");
  list.innerHTML = "";

  for (const v of data) {
    const div = document.createElement("div");
    div.className = "card";
    div.dataset.bvid = v.bvid;
    const topic = pickTopic(v);
    const cover = v.cover_url || `https://placehold.co/640x360/1d2532/cfd8eb?text=${encodeURIComponent("Bili Lite")}`;
    const state = v.state || STATE.NEW;
    div.innerHTML = `
      <div class="card-top">
        <button class="icon-pill state-btn" type="button" title="打开详情" data-action="open" data-bvid="${v.bvid}" data-url="${v.url}">☰</button>
        <button class="icon-pill state-btn ${state === STATE.STAR ? "active" : ""}" type="button" title="收藏" data-action="star" data-bvid="${v.bvid}">❤</button>
        <button class="icon-pill state-btn ${state === STATE.LATER ? "active" : ""}" type="button" title="稍后看" data-action="later" data-bvid="${v.bvid}">🕒</button>
        <span class="topic-pill ${topic.className}">${topic.text}</span>
      </div>
      <a class="cover" href="${v.url}" target="_blank" rel="noreferrer">
        <img src="${cover}" alt="${escapeHtml(v.title)}" loading="lazy" referrerpolicy="no-referrer" />
        <span class="duration">${formatDuration(v.duration_sec)}</span>
      </a>
      <div class="body">
        <div class="title"><a href="${v.url}" target="_blank" rel="noreferrer">${escapeHtml(v.title)}</a></div>
        <div class="meta">${formatAuthor(v)} · ${formatView(v.view)}播放 · ${timeAgo(v.pub_ts)} · ${escapeHtml(v.tname ?? "未分区")}</div>
        <div class="tags">${(v.tags || []).slice(0, 4).map((t) => `<span class="tag">${escapeHtml(t)}</span>`).join("")}</div>
      </div>
    `;
    list.appendChild(div);
  }
}

async function updateVideoState(bvid, nextState) {
  const video = currentVideos.find((item) => item.bvid === bvid);
  if (!video) return;

  const oldState = video.state || STATE.NEW;
  if (oldState === nextState) return;

  // optimistic update
  video.state = nextState;
  if (nextState === STATE.HIDDEN) {
    currentVideos = currentVideos.filter((item) => item.bvid !== bvid);
  }
  renderList(currentVideos);

  try {
    await persistState(bvid, nextState);
    showUndoToast(messageForState(nextState), { bvid, fromState: oldState, toState: nextState });
  } catch (err) {
    const rollbackVideo = currentVideos.find((item) => item.bvid === bvid);
    if (rollbackVideo) {
      rollbackVideo.state = oldState;
    } else {
      await load();
      showToast(`保存失败：${err.message || "请稍后重试"}`);
      return;
    }
    renderList(currentVideos);
    showToast(`保存失败：${err.message || "请稍后重试"}`);
  }
}

async function persistState(bvid, state) {
  const res = await fetch("/api/state", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ bvid, state }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json();
}

function messageForState(state) {
  if (state === STATE.LATER) return "已加入稍后看";
  if (state === STATE.STAR) return "已加入收藏";
  if (state === STATE.WATCHED) return "已标记已看";
  if (state === STATE.HIDDEN) return "已隐藏";
  return "状态已更新";
}

function showUndoToast(message, action) {
  undoAction = action;
  showToast(message, true);
}

function showToast(message, canUndo = false) {
  const root = document.getElementById("toast");
  if (!root) return;
  root.innerHTML = "";

  const msg = document.createElement("span");
  msg.className = "toast-message";
  msg.textContent = message;
  root.appendChild(msg);

  if (canUndo && undoAction) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "toast-undo";
    btn.textContent = "撤销";
    btn.addEventListener("click", undoLatestAction);
    root.appendChild(btn);
  }

  root.classList.add("show");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => {
    root.classList.remove("show");
    root.innerHTML = "";
    undoAction = null;
  }, 3600);
}

async function undoLatestAction() {
  if (!undoAction) return;
  const { bvid, fromState, toState } = undoAction;
  undoAction = null;

  const video = currentVideos.find((item) => item.bvid === bvid);
  if (toState === STATE.HIDDEN && !video) {
    await load();
  }

  const rollbackVideo = currentVideos.find((item) => item.bvid === bvid);
  if (rollbackVideo) {
    rollbackVideo.state = fromState;
    renderList(currentVideos);
  }

  try {
    await persistState(bvid, fromState);
    showToast("已撤销");
  } catch (err) {
    await load();
    showToast(`撤销失败：${err.message || "请稍后重试"}`);
  }
}

function formatDuration(durationSec) {
  if (durationSec == null || Number.isNaN(Number(durationSec))) return "--:--";
  const sec = Math.max(0, Math.floor(Number(durationSec)));
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function pickTopic(v) {
  const tagLen = (v.tags || []).length;
  if ((v.view || 0) > 1000000) return { text: "今日热门", className: "topic-hot" };
  if (tagLen >= 4) return { text: "推荐", className: "topic-rec" };
  if ((v.tname || "").includes("动态")) return { text: "动态", className: "topic-feed" };
  if ((v.title || "").includes("合集")) return { text: "稍后再看", className: "topic-later" };
  return { text: "追番", className: "topic-follow" };
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[c]));
}

function formatView(v) {
  if (v == null) return "-";
  if (v < 10000) return `${v}`;
  if (v < 100000000) return `${(v / 10000).toFixed(1)}万`;
  return `${(v / 100000000).toFixed(1)}亿`;
}

function timeAgo(ts) {
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
document.getElementById("dailyBtn").addEventListener("click", loadDaily);
document.getElementById("list").addEventListener("click", (event) => {
  const btn = event.target.closest(".state-btn");
  if (!btn) return;
  event.preventDefault();

  const bvid = btn.dataset.bvid;
  const action = btn.dataset.action;
  if (!bvid || !action) return;

  if (action === "open") {
    const url = btn.dataset.url;
    if (url) window.open(url, "_blank", "noopener,noreferrer");
    return;
  }
  if (action === "later") {
    updateVideoState(bvid, STATE.LATER);
    return;
  }
  if (action === "star") {
    updateVideoState(bvid, STATE.STAR);
  }
});

loadGroups();
load();
