const STATE = {
  NEW: "NEW",
  READ: "READ",
  STAR: "STAR",
  HIDDEN: "HIDDEN",
};

let currentVideos = [];

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
    const isStarred = !!v.__starred;

    div.innerHTML = `
      <div class="card-top">
        <button class="icon-pill state-btn" type="button" title="更多操作" data-action="open" data-bvid="${v.bvid}">☰</button>
        <button class="icon-pill state-btn ${isStarred ? "active" : ""}" type="button" title="收藏（仅前端高亮）" data-action="star" data-bvid="${v.bvid}">❤</button>
        <button class="icon-pill state-btn" type="button" title="稍后看（标记已读）" data-action="later" data-bvid="${v.bvid}">🕒</button>
        <span class="topic-pill ${topic.className}">${topic.text}</span>
      </div>
      <div class="inline-menu hidden" data-menu="video" data-bvid="${v.bvid}">
        <button class="menu-item" type="button" data-action="mark-read" data-bvid="${v.bvid}">标记已读</button>
        <button class="menu-item" type="button" data-action="hide-video" data-bvid="${v.bvid}">隐藏此视频</button>
      </div>
      <a class="cover" href="${v.url}" target="_blank" rel="noreferrer">
        <img src="${cover}" alt="${escapeHtml(v.title)}" loading="lazy" referrerpolicy="no-referrer" />
        <span class="duration">${formatDuration(v.duration_sec)}</span>
      </a>
      <div class="body">
        <div class="title"><a href="${v.url}" target="_blank" rel="noreferrer">${escapeHtml(v.title)}</a></div>
        <div class="meta-row">
          <div class="meta">${formatAuthor(v)} · ${formatView(v.view)}播放 · ${timeAgo(v.pub_ts)} · ${escapeHtml(v.tname ?? "未分区")}</div>
          <button class="creator-mini-btn" type="button" title="创作者操作" data-action="creator-open" data-uid="${v.uid}">⋯</button>
        </div>
        <div class="inline-menu hidden" data-menu="creator" data-uid="${v.uid}">
          <button class="menu-item" type="button" data-action="creator-must" data-uid="${v.uid}">设为必看</button>
          <button class="menu-item" type="button" data-action="creator-unmust" data-uid="${v.uid}">取消必看</button>
          <button class="menu-item" type="button" data-action="creator-hide" data-uid="${v.uid}">隐藏该作者</button>
        </div>
        <div class="tags">${(v.tags || []).slice(0, 4).map((t) => `<span class="tag">${escapeHtml(t)}</span>`).join("")}</div>
      </div>
    `;
    list.appendChild(div);
  }
}

async function postVideoState(bvid, state) {
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

async function postCreatorUpdate(uid, patch) {
  const payload = [{ uid, ...patch }];
  const res = await fetch("/api/creators", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json();
}

function removeVideoFromCurrentList(bvid) {
  currentVideos = currentVideos.filter((item) => item.bvid !== bvid);
  renderList(currentVideos);
}

function removeCreatorVideosFromCurrentList(uid) {
  currentVideos = currentVideos.filter((item) => Number(item.uid) !== Number(uid));
  renderList(currentVideos);
}

function closeAllMenus() {
  document.querySelectorAll(".inline-menu").forEach((el) => el.classList.add("hidden"));
}

function toggleVideoMenu(bvid) {
  const target = document.querySelector(`.inline-menu[data-menu='video'][data-bvid='${CSS.escape(bvid)}']`);
  if (!target) return;
  const willOpen = target.classList.contains("hidden");
  closeAllMenus();
  if (willOpen) target.classList.remove("hidden");
}

function toggleCreatorMenu(uid) {
  const target = document.querySelector(`.inline-menu[data-menu='creator'][data-uid='${CSS.escape(String(uid))}']`);
  if (!target) return;
  const willOpen = target.classList.contains("hidden");
  closeAllMenus();
  if (willOpen) target.classList.remove("hidden");
}

async function handleVideoRead(bvid) {
  try {
    await postVideoState(bvid, STATE.READ);
    removeVideoFromCurrentList(bvid);
  } catch (err) {
    console.warn("mark read failed", bvid, err);
  }
}

async function handleVideoHidden(bvid) {
  try {
    await postVideoState(bvid, STATE.HIDDEN);
    removeVideoFromCurrentList(bvid);
  } catch (err) {
    console.warn("hide video failed", bvid, err);
  }
}

function handleStarToggle(bvid) {
  const v = currentVideos.find((item) => item.bvid === bvid);
  if (!v) return;
  v.__starred = !v.__starred;
  renderList(currentVideos);
}

async function handleCreatorMust(uid) {
  try {
    await postCreatorUpdate(uid, { priority: 10 });
    removeCreatorVideosFromCurrentList(uid);
  } catch (err) {
    console.warn("set must-watch failed", uid, err);
  }
}

async function handleCreatorUnMust(uid) {
  try {
    await postCreatorUpdate(uid, { priority: 0 });
    removeCreatorVideosFromCurrentList(uid);
  } catch (err) {
    console.warn("unset must-watch failed", uid, err);
  }
}

async function handleCreatorHide(uid) {
  try {
    await postCreatorUpdate(uid, { enabled: false });
    removeCreatorVideosFromCurrentList(uid);
  } catch (err) {
    console.warn("hide creator failed", uid, err);
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
document.addEventListener("click", (event) => {
  if (!event.target.closest(".inline-menu") && !event.target.closest(".state-btn") && !event.target.closest(".creator-mini-btn")) {
    closeAllMenus();
  }
});

document.getElementById("list").addEventListener("click", async (event) => {
  const btn = event.target.closest("button");
  if (!btn) return;

  const action = btn.dataset.action;
  if (!action) return;
  event.preventDefault();

  const bvid = btn.dataset.bvid;
  const uid = btn.dataset.uid;

  if (action === "open" && bvid) {
    toggleVideoMenu(bvid);
    return;
  }
  if (action === "star" && bvid) {
    handleStarToggle(bvid);
    return;
  }
  if (action === "later" && bvid) {
    await handleVideoRead(bvid);
    return;
  }

  if (action === "mark-read" && bvid) {
    await handleVideoRead(bvid);
    return;
  }
  if (action === "hide-video" && bvid) {
    await handleVideoHidden(bvid);
    return;
  }

  if (action === "creator-open" && uid) {
    toggleCreatorMenu(uid);
    return;
  }
  if (action === "creator-must" && uid) {
    await handleCreatorMust(Number(uid));
    return;
  }
  if (action === "creator-unmust" && uid) {
    await handleCreatorUnMust(Number(uid));
    return;
  }
  if (action === "creator-hide" && uid) {
    await handleCreatorHide(Number(uid));
  }
});

loadGroups();
load();
