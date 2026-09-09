const app = {
  authorId: "",
  offset: 0,
  limit: 200,
  groupId: "",
  type: "",
  minTime: "",
  maxTime: "",
  keyword: "",
  order: "desc",
  totalPages: 1,
};

const $ = (sel) => document.querySelector(sel);

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
}

const URL_RE = /https?:\/\/[^\s"'<>]+/g;

function renderContent(container, text) {
  const parts = String(text || "").split(URL_RE);
  const urls = String(text || "").match(URL_RE) || [];
  parts.forEach((part, i) => {
    container.appendChild(document.createTextNode(part));
    if (i < urls.length) {
      const a = el("a", "", urls[i]);
      a.href = urls[i];
      a.target = "_blank";
      a.rel = "noopener";
      a.textContent = urls[i];
      container.appendChild(a);
    }
  });
}

function buildPost(p) {
  const li = el("li", "post");

  const meta = el("div", "post-meta");
  const type = el("span", "post-type " + (p.type === "discussion" ? "discussion" : "reply"),
    p.type === "discussion" ? "主帖" : "回复");
  meta.appendChild(type);

  const a = el("a", "post-title", p.title || "(无标题)");
  a.href = p.url;
  a.target = "_blank";
  a.rel = "noopener";
  meta.appendChild(a);

  meta.appendChild(el("span", "post-time", p.time || ""));
  meta.appendChild(el("span", "post-group", p.group_name || p.group_id || ""));

  li.appendChild(meta);

  const content = el("div", "post-content");
  renderContent(content, p.content);
  li.appendChild(content);

  if (p.quote) {
    const q = el("div", "post-quote");
    if (p.quote_author) q.appendChild(el("b", "", p.quote_author + "："));
    renderContent(q, p.quote);
    li.appendChild(q);
  }

  return li;
}

function buildParams(offset) {
  const params = new URLSearchParams({ limit: String(app.limit), offset: String(offset) });
  if (app.groupId) params.set("group_id", app.groupId);
  if (app.type) params.set("type", app.type);
  if (app.minTime) params.set("min_time", app.minTime);
  if (app.maxTime) params.set("max_time", app.maxTime);
  if (app.keyword) params.set("q", app.keyword);
  params.set("order", app.order);
  return params;
}

async function fetchAuthor(id, offset) {
  const res = await fetch("/api/author/" + encodeURIComponent(id) + "?" + buildParams(offset));
  if (!res.ok) throw new Error("HTTP " + res.status);
  return res.json();
}

function updateTypeSeg() {
  document.querySelectorAll("#typeSeg .segment").forEach((b) => {
    b.classList.toggle("is-active", b.dataset.type === app.type);
  });
}

function updateOrderBtn() {
  document.querySelectorAll("#orderSeg .segment").forEach((b) => {
    b.classList.toggle("is-active", b.dataset.order === app.order);
  });
}

function renderSummary(d) {
  $("#result").classList.remove("hidden");
  $("#welcome").classList.add("hidden");
  $("#authorName").textContent = d.author_name || "(匿名)";
  $("#authorId").textContent = d.author_id;
  $("#mTotal").textContent = d.total.toLocaleString();
  $("#mDisc").textContent = d.discussions.toLocaleString();
  $("#mReply").textContent = d.replies.toLocaleString();
  const range = (d.first_time && d.last_time)
    ? d.first_time.slice(0, 10) + " ~ " + d.last_time.slice(0, 10)
    : "未知";
  $("#mRange").textContent = range;

  $("#homeBtn").href = "https://www.douban.com/people/" + d.author_id + "/";
  const exp = new URLSearchParams();
  if (app.groupId) exp.set("group_id", app.groupId);
  if (app.type) exp.set("type", app.type);
  if (app.minTime) exp.set("min_time", app.minTime);
  if (app.maxTime) exp.set("max_time", app.maxTime);
  if (app.keyword) exp.set("q", app.keyword);
  exp.set("order", app.order);
  const expQs = exp.toString();
  $("#exportBtn").href = "/api/author/" + encodeURIComponent(d.author_id) + "/export" + (expQs ? "?" + expQs : "");
  $("#exportBtn").setAttribute("download", "douban_author_" + d.author_id + ".csv");

  const totalAll = d.groups.reduce((s, g) => s + g.count, 0);
  const chips = $("#groupChips");
  chips.innerHTML = "";
  const allChip = el("button", "group-chip" + (app.groupId === "" ? " active" : ""));
  allChip.type = "button";
  allChip.appendChild(document.createTextNode("全部 "));
  allChip.appendChild(el("b", "", totalAll.toLocaleString()));
  allChip.addEventListener("click", () => {
    app.groupId = "";
    load(app.authorId, 0);
  });
  chips.appendChild(allChip);

  d.groups.forEach((g) => {
    const c = el("button", "group-chip" + (app.groupId === g.group_id ? " active" : ""));
    c.type = "button";
    c.appendChild(document.createTextNode((g.name || g.group_id) + " "));
    c.appendChild(el("b", "", g.count.toLocaleString()));
    c.addEventListener("click", () => {
      app.groupId = app.groupId === g.group_id ? "" : g.group_id;
      load(app.authorId, 0);
    });
    chips.appendChild(c);
  });

  updateTypeSeg();
}

function renderPosts(posts) {
  const list = $("#postList");
  list.innerHTML = "";
  posts.forEach((p) => list.appendChild(buildPost(p)));
}

function renderPager(d) {
  $("#postCount").textContent = "共 " + d.total.toLocaleString() + " 条发言";
  app.totalPages = Math.max(1, Math.ceil(d.total / app.limit));
  const cur = Math.floor(d.offset / app.limit) + 1;
  ["", "2"].forEach((suf) => {
    $("#pageInput" + suf).value = cur;
    $("#pageInput" + suf).max = app.totalPages;
    $("#pageTotal" + suf).textContent = app.totalPages;
    $("#prevBtn" + suf).disabled = d.offset === 0;
    $("#nextBtn" + suf).disabled = d.offset + app.limit >= d.total;
  });
}

async function load(id, offset) {
  app.authorId = id;
  app.offset = offset;
  const d = await fetchAuthor(id, offset);
  renderSummary(d);
  renderPosts(d.posts);
  renderPager(d);
  history.replaceState(null, "", "?author_id=" + encodeURIComponent(id));
  window.scrollTo({ top: 0 });
}

function showSuggest(items) {
  const box = $("#suggest");
  box.innerHTML = "";
  if (!items || !items.length) { box.classList.remove("show"); return; }
  items.forEach((it) => {
    const n = el("div", "suggest-item");
    n.appendChild(el("span", "", it.author_id));
    n.appendChild(el("span", "cnt", it.posts.toLocaleString() + " 条"));
    n.addEventListener("click", () => {
      box.classList.remove("show");
      $("#authorInput").value = it.author_id;
      resetFilter();
      load(it.author_id, 0);
    });
    box.appendChild(n);
  });
  box.classList.add("show");
}

function resetFilter() {
  app.groupId = "";
  app.type = "";
  app.minTime = "";
  app.maxTime = "";
  app.keyword = "";
  $("#minDate").value = "";
  $("#maxDate").value = "";
  $("#keywordInput").value = "";
  updateTypeSeg();
}

let suggestTimer = null;
$("#authorInput").addEventListener("input", (e) => {
  const v = e.target.value.trim();
  clearTimeout(suggestTimer);
  if (!v || !/^\d{3,}$/.test(v)) { showSuggest([]); return; }
  suggestTimer = setTimeout(async () => {
    try {
      const res = await fetch("/api/author-suggest?q=" + v);
      showSuggest(await res.json());
    } catch (err) { showSuggest([]); }
  }, 200);
});

document.addEventListener("click", (e) => {
  if (!$("#suggest").contains(e.target)) $("#suggest").classList.remove("show");
});

function doSearch() {
  const id = $("#authorInput").value.trim();
  if (!id) return;
  resetFilter();
  load(id, 0);
}

$("#searchForm").addEventListener("submit", (e) => {
  e.preventDefault();
  doSearch();
});

function jumpTo(page) {
  const n = Math.min(Math.max(page, 1), app.totalPages);
  load(app.authorId, (n - 1) * app.limit);
}

function bindPager(suffix) {
  $("#prevBtn" + suffix).addEventListener("click", () => load(app.authorId, Math.max(0, app.offset - app.limit)));
  $("#nextBtn" + suffix).addEventListener("click", () => load(app.authorId, app.offset + app.limit));
  $("#pageInput" + suffix).addEventListener("keydown", (e) => {
    if (e.key !== "Enter") return;
    const n = parseInt(e.target.value, 10);
    if (n && n >= 1) jumpTo(n);
  });
  $("#pageInput" + suffix).addEventListener("change", (e) => {
    const n = parseInt(e.target.value, 10);
    if (n && n >= 1) jumpTo(n);
  });
}
bindPager("");
bindPager("2");

document.querySelectorAll("#typeSeg .segment").forEach((b) => {
  b.addEventListener("click", () => {
    app.type = b.dataset.type;
    load(app.authorId, 0);
  });
});

document.querySelectorAll("#orderSeg .segment").forEach((b) => {
  b.addEventListener("click", () => {
    app.order = b.dataset.order;
    updateOrderBtn();
    load(app.authorId, 0);
  });
});

let dateTimer = null;
function onDateChange() {
  clearTimeout(dateTimer);
  dateTimer = setTimeout(() => {
    app.minTime = $("#minDate").value;
    app.maxTime = $("#maxDate").value;
    app.offset = 0;
    const min = $("#minDate").value ? new Date($("#minDate").value).getTime() : Infinity;
    const max = $("#maxDate").value ? new Date($("#maxDate").value).getTime() : -Infinity;
    if (min === 0 || max === 0) return;
    load(app.authorId, 0);
  }, 300);
}
$("#minDate").addEventListener("change", onDateChange);
$("#maxDate").addEventListener("change", onDateChange);

let kwTimer = null;
$("#keywordInput").addEventListener("input", () => {
  clearTimeout(kwTimer);
  kwTimer = setTimeout(() => {
    app.keyword = $("#keywordInput").value.trim();
    load(app.authorId, 0);
  }, 300);
});

$("#clearFilterBtn").addEventListener("click", () => {
  resetFilter();
  load(app.authorId, 0);
});

async function loadHot() {
  try {
    const res = await fetch("/api/stats");
    const d = await res.json();
    const wrap = $("#hotAuthors");
    wrap.innerHTML = "";
    d.top_authors.forEach((t) => {
      const c = el("button", "hot-chip");
      c.type = "button";
      c.appendChild(document.createTextNode(t.author_id + " "));
      c.appendChild(el("b", "", t.posts.toLocaleString() + " 条"));
      c.addEventListener("click", () => {
        $("#authorInput").value = t.author_id;
        resetFilter();
        load(t.author_id, 0);
      });
      wrap.appendChild(c);
    });
  } catch (err) { /* ignore */ }
}

loadHot();

function initFromUrl() {
  const params = new URLSearchParams(location.search);
  const qid = params.get("author_id") || (location.hash.length > 1 ? location.hash.slice(1) : "");
  if (qid) {
    $("#authorInput").value = qid;
    load(qid, 0).catch(() => {});
  }
}

initFromUrl();

const backTop = $("#backTop");
window.addEventListener("scroll", () => {
  backTop.classList.toggle("show", window.scrollY > 300);
});
backTop.addEventListener("click", () => {
  window.scrollTo({ top: 0, behavior: "smooth" });
});