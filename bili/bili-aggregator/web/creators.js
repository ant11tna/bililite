let creators = [];

function creatorDisplayName(c) {
  const name = (c.author_name || "").trim();
  return name || `uid=${c.uid}`;
}

function sortCreators(list) {
  return [...list].sort((a, b) => {
    if (b.priority !== a.priority) return b.priority - a.priority;
    if (Number(b.enabled) !== Number(a.enabled)) return Number(b.enabled) - Number(a.enabled);
    const an = creatorDisplayName(a).toLowerCase();
    const bn = creatorDisplayName(b).toLowerCase();
    return an.localeCompare(bn, "zh-CN");
  });
}

function formatNow() {
  return new Date().toLocaleTimeString();
}

function rowClassName(c) {
  const classes = [];
  if (c.priority > 0) classes.push("creator-must");
  if (!c.enabled) classes.push("creator-disabled");
  return classes.join(" ");
}

function render() {
  const body = document.getElementById("creatorsBody");
  body.innerHTML = "";

  for (const c of sortCreators(creators)) {
    const tr = document.createElement("tr");
    tr.dataset.uid = String(c.uid);
    tr.className = rowClassName(c);

    const weightMuted = c.priority > 0 ? "muted" : "";

    tr.innerHTML = `
      <td>${escapeHtml(creatorDisplayName(c))}</td>
      <td class="uid-cell">${c.uid}</td>
      <td>
        <label>
          <input type="checkbox" data-field="enabled" ${c.enabled ? "checked" : ""} />
        </label>
      </td>
      <td>
        <input type="number" class="num-input" data-field="priority" min="0" step="1" value="${Number(c.priority) || 0}" />
      </td>
      <td>
        <input type="number" class="num-input ${weightMuted}" data-field="weight" min="1" step="1" value="${Math.max(1, Number(c.weight) || 1)}" ${c.priority > 0 ? "disabled" : ""} />
      </td>
      <td class="save-status" data-role="status">-</td>
    `;

    body.appendChild(tr);
  }
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[ch]));
}

function setRowStatus(row, text, isError = false) {
  const status = row.querySelector('[data-role="status"]');
  if (!status) return;
  status.textContent = text;
  status.classList.toggle("status-error", isError);
  status.classList.toggle("status-ok", !isError && text !== "-");
}

async function saveField(uid, field, nextValue, prevValue, input, row) {
  const payload = [{ uid, [field]: nextValue }];

  try {
    const res = await fetch("/api/creators", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(text || `HTTP ${res.status}`);
    }

    const idx = creators.findIndex((x) => Number(x.uid) === Number(uid));
    if (idx >= 0) {
      creators[idx] = {
        ...creators[idx],
        [field]: nextValue,
      };
      if (field === "weight") {
        creators[idx].weight = Math.max(1, Number(nextValue) || 1);
      }
      if (field === "priority") {
        creators[idx].priority = Math.max(0, Number(nextValue) || 0);
      }
    }

    setRowStatus(row, `已保存 ${formatNow()}`);
    render();
  } catch (err) {
    console.warn("creator save failed", uid, field, err);

    if (input.type === "checkbox") {
      input.checked = Boolean(prevValue);
    } else {
      input.value = String(prevValue);
    }
    setRowStatus(row, "保存失败", true);
  }
}

function bindEvents() {
  const body = document.getElementById("creatorsBody");

  body.addEventListener("change", async (event) => {
    const input = event.target;
    if (!(input instanceof HTMLInputElement)) return;
    const field = input.dataset.field;
    if (!field) return;

    const row = input.closest("tr");
    if (!row) return;
    const uid = Number(row.dataset.uid);

    const creator = creators.find((x) => Number(x.uid) === uid);
    if (!creator) return;

    let prevValue;
    let nextValue;

    if (field === "enabled") {
      prevValue = !!creator.enabled;
      nextValue = !!input.checked;
    } else if (field === "priority") {
      prevValue = Number(creator.priority) || 0;
      nextValue = Math.max(0, Number(input.value) || 0);
      input.value = String(nextValue);
    } else if (field === "weight") {
      prevValue = Math.max(1, Number(creator.weight) || 1);
      nextValue = Math.max(1, Number(input.value) || 1);
      input.value = String(nextValue);
    } else {
      return;
    }

    if (prevValue === nextValue) return;

    setRowStatus(row, "保存中...");
    await saveField(uid, field, nextValue, prevValue, input, row);
  });
}

async function init() {
  try {
    const res = await fetch("/api/creators");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    creators = await res.json();
    render();
    bindEvents();
  } catch (err) {
    console.warn("load creators failed", err);
    const body = document.getElementById("creatorsBody");
    body.innerHTML = `<tr><td colspan="6">加载失败</td></tr>`;
  }
}

init();
