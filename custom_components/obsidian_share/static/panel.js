// Obsidian Share – Seitenleisten-Panel (Vanilla Web Component, kein Build-Schritt)
//
// Notizbaum mit Suche, gerenderte Ansicht mit Inhaltsverzeichnis, Editor mit
// ETag-Konflikterkennung und Freigabe-Dialog. Das HTML der Notizen kommt
// bereits bereinigt vom Server (markdown-it mit html=False).

const API = "/api/obsidian_share";

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

const store = {
  get(k) {
    try { return window.localStorage.getItem(`obsidian_share.${k}`); } catch (_) { return null; }
  },
  set(k, v) {
    try { window.localStorage.setItem(`obsidian_share.${k}`, v); } catch (_) { /* egal */ }
  },
};

const STYLE = `
:host{display:block;height:100%;background:var(--primary-background-color);color:var(--primary-text-color);
  font-family:var(--paper-font-body1_-_font-family,Roboto,sans-serif)}
*{box-sizing:border-box}
.toolbar{display:flex;align-items:center;gap:4px;height:var(--header-height,56px);padding:0 8px 0 4px;
  background:var(--app-header-background-color,var(--primary-color));color:var(--app-header-text-color,#fff);
  border-bottom:var(--app-header-border-bottom,none)}
.toolbar .title{flex:1;font-size:20px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-left:4px}
.toolbar button{background:none;border:0;color:inherit;font:inherit;font-size:14px;padding:8px 10px;border-radius:6px;cursor:pointer}
.toolbar button:hover{background:rgba(255,255,255,.12)}
.toolbar button[hidden]{display:none}
.wrap{display:flex;height:calc(100% - var(--header-height,56px))}
.side{width:320px;min-width:240px;border-right:1px solid var(--divider-color);display:flex;flex-direction:column;
  background:var(--card-background-color)}
.side input{margin:10px;padding:9px 12px;border-radius:8px;border:1px solid var(--divider-color);
  background:var(--primary-background-color);color:var(--primary-text-color);font-size:15px}
.tree{flex:1;overflow:auto;padding:0 6px 24px;font-size:14px}
.tree details>summary{list-style:none;cursor:pointer;padding:5px 6px;border-radius:6px;color:var(--secondary-text-color);
  font-weight:500;user-select:none}
.tree details>summary::before{content:"▸";display:inline-block;width:1em;transition:transform .15s}
.tree details[open]>summary::before{transform:rotate(90deg)}
.tree details>.children{padding-left:12px}
.tree .note{display:flex;align-items:center;gap:6px;padding:5px 8px;border-radius:6px;cursor:pointer;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tree .note:hover{background:var(--secondary-background-color)}
.tree .note.active{background:rgba(var(--rgb-primary-color,3,169,244),.15);color:var(--primary-color)}
.tree .note .name{overflow:hidden;text-overflow:ellipsis}
.tree .note .dir{color:var(--secondary-text-color);font-size:12px;margin-left:auto;overflow:hidden;text-overflow:ellipsis}
.badge{font-size:11px;padding:1px 6px;border-radius:9px;background:var(--success-color,#43a047);color:#fff;flex:none}
.main{flex:1;overflow:auto;min-width:0}
.content{max-width:820px;margin:0 auto;padding:20px 20px 80px}
.empty{color:var(--secondary-text-color);text-align:center;margin-top:20vh}
.path{color:var(--secondary-text-color);font-size:13px;word-break:break-all}
h1.title{font-size:1.8em;line-height:1.25;margin:.2em 0 .6em}
.note-html{font-size:16px;line-height:1.6;word-wrap:break-word}
.note-html h1,.note-html h2,.note-html h3,.note-html h4{line-height:1.3;scroll-margin-top:12px}
.note-html a{color:var(--primary-color)}
.note-html img{max-width:100%;height:auto}
.note-html pre{background:var(--code-editor-background-color,var(--secondary-background-color));padding:12px;border-radius:6px;overflow-x:auto}
.note-html code{background:var(--code-editor-background-color,var(--secondary-background-color));padding:.1em .3em;border-radius:4px;font-size:.9em}
.note-html pre code{padding:0;background:none}
.note-html table{border-collapse:collapse;display:block;overflow-x:auto;max-width:100%}
.note-html th,.note-html td{border:1px solid var(--divider-color);padding:6px 10px;text-align:left}
.note-html blockquote{margin:1em 0;padding:0 1em;border-left:3px solid var(--divider-color);color:var(--secondary-text-color)}
.note-html hr{border:0;border-top:1px solid var(--divider-color)}
.note-html ul.contains-task-list{list-style:none;padding-left:1.2em}
.note-html .unresolved,.note-html .missing{opacity:.6}
.note-html .callout{--c:68,138,255;border-left:4px solid rgb(var(--c));background:rgba(var(--c),.08);border-radius:6px;padding:8px 14px;margin:1em 0}
.note-html .callout-title{font-weight:600;color:rgb(var(--c))}
.note-html details.callout>summary{cursor:pointer}
.note-html .callout[data-callout=tip],.note-html .callout[data-callout=success],.note-html .callout[data-callout=check],
.note-html .callout[data-callout=done],.note-html .callout[data-callout=hint]{--c:8,185,78}
.note-html .callout[data-callout=warning],.note-html .callout[data-callout=question],.note-html .callout[data-callout=help],
.note-html .callout[data-callout=caution],.note-html .callout[data-callout=attention],.note-html .callout[data-callout=faq]{--c:236,117,0}
.note-html .callout[data-callout=danger],.note-html .callout[data-callout=error],.note-html .callout[data-callout=bug],
.note-html .callout[data-callout=failure],.note-html .callout[data-callout=fail]{--c:233,49,71}
.note-html .callout[data-callout=example]{--c:120,82,238}
.note-html .callout[data-callout=quote],.note-html .callout[data-callout=cite]{--c:158,158,158}
.toc{border:1px solid var(--divider-color);border-radius:8px;padding:8px 14px;margin:0 0 1.5em;background:var(--card-background-color)}
.toc summary{cursor:pointer;font-weight:600}
.toc ul{list-style:none;padding:0;margin:.5em 0 0}
.toc li{padding:2px 0}
.toc a{color:var(--primary-text-color);text-decoration:none}
.toc a:hover{color:var(--primary-color)}
.card{border:1px solid var(--divider-color);border-radius:10px;padding:14px 16px;margin:0 0 18px;background:var(--card-background-color)}
.card h3{margin:0 0 8px;font-size:16px}
.row{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:8px}
.btn{border:1px solid var(--divider-color);background:var(--card-background-color);color:var(--primary-text-color);
  padding:8px 14px;border-radius:8px;font:inherit;font-size:14px;cursor:pointer}
.btn.primary{background:var(--primary-color);border-color:var(--primary-color);color:var(--text-primary-color,#fff)}
.btn.danger{color:var(--error-color,#db4437);border-color:var(--error-color,#db4437)}
.btn:disabled{opacity:.5;cursor:default}
select{padding:7px 10px;border-radius:8px;border:1px solid var(--divider-color);background:var(--card-background-color);color:var(--primary-text-color);font-size:14px}
.link{display:flex;gap:8px;margin-top:8px}
.link input{flex:1;min-width:0;padding:8px 10px;border-radius:8px;border:1px solid var(--divider-color);
  background:var(--primary-background-color);color:var(--primary-text-color);font-size:13px}
.msg{padding:10px 14px;border-radius:8px;margin:0 0 14px;font-size:14px}
.msg.err{background:rgba(219,68,55,.12);color:var(--error-color,#db4437)}
.msg.ok{background:rgba(67,160,71,.12);color:var(--success-color,#43a047)}
textarea{width:100%;min-height:calc(100vh - 260px);padding:12px;border-radius:8px;border:1px solid var(--divider-color);
  background:var(--card-background-color);color:var(--primary-text-color);
  font:14px/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;resize:vertical;tab-size:2}
.muted{color:var(--secondary-text-color);font-size:13px}
:host([narrow]) .side{width:100%;border-right:0}
:host([narrow]) .content{padding:14px 14px 80px}
:host([narrow][mode=note]) .side,:host([narrow][mode=list]) .main{display:none}
`;

class ObsidianSharePanel extends HTMLElement {
  constructor() {
    super();
    this._hass = null;
    this._narrow = false;
    this._notes = [];
    this._canEdit = false;
    this._note = null; // {path,text,etag,html,toc,shared,can_edit}
    this._editing = false;
    this._dirty = false;
    this._shareOpen = false;
    this._link = null;
    this._msg = null;
    this._filter = "";
    this._openDirs = new Set(JSON.parse(store.get("open_dirs") || "[]"));
    this.attachShadow({ mode: "open" });
    this._onBeforeUnload = (e) => { if (this._dirty) { e.preventDefault(); e.returnValue = ""; } };
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (this._menu) this._menu.hass = hass;
    if (first) this._init();
  }

  set narrow(narrow) {
    this._narrow = !!narrow;
    this.toggleAttribute("narrow", this._narrow);
    if (this._menu) this._menu.narrow = this._narrow;
  }

  set panel(_p) { /* nicht benötigt */ }
  set route(_r) { /* nicht benötigt */ }

  connectedCallback() { window.addEventListener("beforeunload", this._onBeforeUnload); }
  disconnectedCallback() { window.removeEventListener("beforeunload", this._onBeforeUnload); }

  // -- Grundgerüst --------------------------------------------------------

  _init() {
    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <div class="toolbar">
        <span id="menu"></span>
        <button id="back" hidden title="Zur Liste">‹ Liste</button>
        <span class="title" id="title">Obsidian</span>
        <button id="reload" title="Neu laden">↻</button>
      </div>
      <div class="wrap">
        <div class="side">
          <input id="search" type="search" placeholder="Notizen suchen …" autocomplete="off">
          <div class="tree" id="tree"></div>
        </div>
        <div class="main" id="main"><div class="content"><p class="empty">Notiz auswählen</p></div></div>
      </div>`;
    const $ = (id) => this.shadowRoot.getElementById(id);
    this._menu = document.createElement("ha-menu-button");
    this._menu.hass = this._hass;
    this._menu.narrow = this._narrow;
    $("menu").appendChild(this._menu);
    $("search").addEventListener("input", (e) => { this._filter = e.target.value.trim().toLowerCase(); this._renderTree(); });
    $("back").addEventListener("click", () => this._guard() && this._showList());
    $("reload").addEventListener("click", () => this._guard() && this._reload());
    $("tree").addEventListener("click", (e) => this._onTreeClick(e));
    $("tree").addEventListener("toggle", (e) => this._onDirToggle(e), true);
    $("main").addEventListener("click", (e) => this._onMainClick(e));
    $("main").addEventListener("change", (e) => this._onMainChange(e));
    $("main").addEventListener("input", (e) => { if (e.target.id === "editor") this._dirty = true; });
    this.setAttribute("mode", "list");
    this._reload();
  }

  async _api(method, path, body) {
    const opts = { method, headers: {} };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    const resp = await this._hass.fetchWithAuth(`${API}/${path}`, opts);
    let data = null;
    try { data = await resp.json(); } catch (_) { data = null; }
    return { status: resp.status, ok: resp.ok, data };
  }

  _guard() {
    if (!this._dirty) return true;
    if (!window.confirm("Ungespeicherte Änderungen verwerfen?")) return false;
    this._dirty = false;
    return true;
  }

  async _reload() {
    const res = await this._api("GET", "tree");
    if (!res.ok) {
      this._notes = [];
      this._renderTree(res.status === 403 ? "Kein Zugriff. Ein Admin muss dich in den Optionen der Integration eintragen." : "Notizen konnten nicht geladen werden.");
      return;
    }
    this._notes = res.data.notes || [];
    this._canEdit = !!res.data.can_edit;
    this._renderTree();
    const wanted = new URLSearchParams(window.location.search).get("note") || (this._note && this._note.path) || store.get("last");
    if (wanted && this._notes.some((n) => n.path === wanted)) this._open(wanted, "", { keepList: !this._note && this._narrow });
  }

  _showList() {
    this.setAttribute("mode", "list");
    this.shadowRoot.getElementById("back").hidden = true;
  }

  // -- Baum ---------------------------------------------------------------

  _renderTree(error) {
    const el = this.shadowRoot.getElementById("tree");
    if (error) { el.innerHTML = `<p class="muted" style="padding:8px">${esc(error)}</p>`; return; }
    const active = this._note && this._note.path;
    const noteHtml = (n, showDir) => {
      const parts = n.path.split("/");
      const name = parts.pop().replace(/\.md$/i, "");
      return `<div class="note${n.path === active ? " active" : ""}" data-path="${esc(n.path)}" title="${esc(n.path)}">
        <span class="name">${esc(name)}</span>${n.shared ? '<span class="badge">geteilt</span>' : ""}
        ${showDir && parts.length ? `<span class="dir">${esc(parts.join("/"))}</span>` : ""}</div>`;
    };
    if (this._filter) {
      const words = this._filter.split(/\s+/);
      const hits = this._notes.filter((n) => words.every((w) => n.path.toLowerCase().includes(w)));
      el.innerHTML = hits.length ? hits.slice(0, 300).map((n) => noteHtml(n, true)).join("") : '<p class="muted" style="padding:8px">Keine Treffer</p>';
      return;
    }
    const root = { dirs: new Map(), notes: [] };
    for (const n of this._notes) {
      const parts = n.path.split("/");
      parts.pop();
      let node = root;
      for (const p of parts) {
        if (!node.dirs.has(p)) node.dirs.set(p, { dirs: new Map(), notes: [] });
        node = node.dirs.get(p);
      }
      node.notes.push(n);
    }
    const activeDirs = active ? active.split("/").slice(0, -1).map((_, i, a) => a.slice(0, i + 1).join("/")) : [];
    const walk = (node, prefix) => {
      let out = "";
      for (const name of [...node.dirs.keys()].sort((a, b) => a.localeCompare(b, "de"))) {
        const full = prefix ? `${prefix}/${name}` : name;
        const open = this._openDirs.has(full) || activeDirs.includes(full);
        out += `<details data-dir="${esc(full)}"${open ? " open" : ""}><summary>${esc(name)}</summary>
          <div class="children">${walk(node.dirs.get(name), full)}</div></details>`;
      }
      return out + node.notes.map((n) => noteHtml(n, false)).join("");
    };
    el.innerHTML = walk(root, "") || '<p class="muted" style="padding:8px">Keine Notizen gefunden</p>';
  }

  _onTreeClick(e) {
    const item = e.target.closest(".note");
    if (item && this._guard()) this._open(item.dataset.path);
  }

  _onDirToggle(e) {
    const d = e.target;
    if (!(d instanceof HTMLDetailsElement) || !d.dataset.dir) return;
    if (d.open) this._openDirs.add(d.dataset.dir); else this._openDirs.delete(d.dataset.dir);
    store.set("open_dirs", JSON.stringify([...this._openDirs]));
  }

  // -- Notiz --------------------------------------------------------------

  async _open(path, anchor = "", { keepList = false } = {}) {
    const res = await this._api("GET", `note?path=${encodeURIComponent(path)}`);
    this._editing = false;
    this._dirty = false;
    this._shareOpen = false;
    this._link = null;
    this._msg = null;
    if (!res.ok) {
      this._note = null;
      this._msg = { err: true, text: res.status === 403 ? "Kein Zugriff auf diese Notiz." : `Notiz nicht gefunden: ${path}` };
      this._renderMain();
      return;
    }
    this._note = res.data;
    store.set("last", path);
    const url = new URL(window.location.href);
    url.searchParams.set("note", path);
    window.history.replaceState(window.history.state, "", url);
    if (!keepList) {
      this.setAttribute("mode", "note");
      this.shadowRoot.getElementById("back").hidden = !this._narrow;
    }
    this._renderTree();
    this._renderMain();
    this._scrollTo(anchor);
  }

  _scrollTo(anchor) {
    const main = this.shadowRoot.getElementById("main");
    if (!anchor) { main.scrollTop = 0; return; }
    const target = this.shadowRoot.getElementById(anchor);
    if (target) target.scrollIntoView({ block: "start" }); else main.scrollTop = 0;
  }

  _title() {
    return this._note ? this._note.path.split("/").pop().replace(/\.md$/i, "") : "Obsidian";
  }

  _renderMain() {
    const n = this._note;
    this.shadowRoot.getElementById("title").textContent = this._title();
    const main = this.shadowRoot.getElementById("main");
    const msg = this._msg ? `<div class="msg ${this._msg.err ? "err" : "ok"}">${this._msg.html || esc(this._msg.text)}</div>` : "";
    if (!n) {
      main.innerHTML = `<div class="content">${msg}<p class="empty">Notiz auswählen</p></div>`;
      return;
    }
    const canEdit = !!n.can_edit;
    if (this._editing) {
      main.innerHTML = `<div class="content">${msg}
        <div class="path">${esc(n.path)}</div>
        <div class="row" style="margin:10px 0">
          <button class="btn primary" data-act="save">Speichern</button>
          <button class="btn" data-act="cancel">Abbrechen</button>
          <span class="muted">Strg+S speichert</span>
        </div>
        <textarea id="editor" spellcheck="false"></textarea></div>`;
      const ta = this.shadowRoot.getElementById("editor");
      ta.value = this._draft ?? n.text;
      ta.addEventListener("keydown", (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); this._save(); }
      });
      ta.focus();
      return;
    }
    const toc = (n.toc || []).length >= 3
      ? `<details class="toc"${this._narrow ? "" : " open"}><summary>Inhalt</summary><ul>${n.toc.map((t) => {
          const top = Math.min(...n.toc.map((x) => x.level));
          return `<li style="padding-left:${(t.level - top) * 14}px"><a href="#" data-anchor="${esc(t.id)}">${esc(t.text)}</a></li>`;
        }).join("")}</ul></details>`
      : "";
    const actions = canEdit
      ? `<div class="row" style="margin:6px 0 16px">
          <button class="btn" data-act="edit">Bearbeiten</button>
          <button class="btn${n.shared ? "" : " primary"}" data-act="share">${n.shared ? "Freigabe …" : "Teilen …"}</button>
          ${n.shared ? '<span class="badge">öffentlich geteilt</span>' : ""}
        </div>`
      : n.shared ? '<div class="row" style="margin:6px 0 16px"><span class="badge">öffentlich geteilt</span></div>' : "";
    main.innerHTML = `<div class="content">${msg}
      <div class="path">${esc(n.path)}</div>
      <h1 class="title">${esc(this._title())}</h1>
      ${actions}${this._shareOpen ? this._shareCard() : ""}${toc}
      <article class="note-html">${n.html}</article></div>`;
  }

  _shareCard() {
    const n = this._note;
    const days = store.get("days") || "";
    const opt = (v, l) => `<option value="${v}"${v === days ? " selected" : ""}>${l}</option>`;
    const link = this._link
      ? `<div class="link"><input id="link" readonly value="${esc(this._link.url)}">
           <button class="btn primary" data-act="copy">Kopieren</button></div>
         <div class="muted" style="margin-top:6px">${this._link.expires
           ? `Gültig bis ${esc(new Date(this._link.expires * 1000).toLocaleString("de-DE"))}`
           : "Ohne Ablaufdatum"}. Wer den Link hat, kann die Notiz ohne Login lesen.</div>`
      : "";
    return `<div class="card">
      <h3>${n.shared ? "Notiz ist öffentlich freigegeben" : "Notiz öffentlich teilen"}</h3>
      <div class="muted">${n.shared
        ? "Jeder neue Link ist zusätzlich gültig. Freigabe beenden macht alle Links dieser Notiz sofort ungültig."
        : "Setzt <code>ha_share: true</code> im Frontmatter und erzeugt einen Nur-Lese-Link."}</div>
      <div class="row">
        <select id="days">${opt("", "Unbegrenzt")}${opt("7", "7 Tage")}${opt("30", "30 Tage")}${opt("90", "90 Tage")}</select>
        <button class="btn primary" data-act="mklink">${n.shared ? "Neuen Link erzeugen" : "Freigeben und Link erzeugen"}</button>
        ${n.shared ? '<button class="btn danger" data-act="unshare">Freigabe beenden</button>' : ""}
        <button class="btn" data-act="closeshare">Schließen</button>
      </div>${link}</div>`;
  }

  _onMainChange(e) {
    if (e.target.id === "days") store.set("days", e.target.value);
  }

  _onMainClick(e) {
    const a = e.target.closest("a");
    if (a) {
      if (a.dataset.note) {
        e.preventDefault();
        if (this._guard()) this._open(a.dataset.note, a.dataset.anchor || "");
        return;
      }
      if (a.dataset.anchor) { e.preventDefault(); this._scrollTo(a.dataset.anchor); return; }
      const href = a.getAttribute("href") || "";
      if (href.startsWith("#") && href.length > 1) { e.preventDefault(); this._scrollTo(decodeURIComponent(href.slice(1))); return; }
      if (href === "#") { e.preventDefault(); return; }
    }
    const btn = e.target.closest("[data-act]");
    if (!btn) return;
    const act = btn.dataset.act;
    if (act === "edit") { this._editing = true; this._draft = null; this._msg = null; this._renderMain(); }
    else if (act === "cancel") { if (this._guard()) { this._editing = false; this._draft = null; this._msg = null; this._renderMain(); } }
    else if (act === "save") this._save();
    else if (act === "share") { this._shareOpen = true; this._link = null; this._msg = null; this._renderMain(); }
    else if (act === "closeshare") { this._shareOpen = false; this._link = null; this._renderMain(); }
    else if (act === "mklink") this._share(true);
    else if (act === "unshare") {
      if (window.confirm("Freigabe beenden? Alle bisher verschickten Links auf diese Notiz funktionieren dann nicht mehr.")) this._share(false);
    }
    else if (act === "copy") this._copy(this._link && this._link.url);
    else if (act === "copydraft") this._copy(this._draft);
    else if (act === "reloadnote") { this._dirty = false; this._draft = null; this._open(this._note.path); }
  }

  async _copy(text) {
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      this._msg = { text: "In die Zwischenablage kopiert." };
    } catch (_) {
      const input = this.shadowRoot.getElementById("link") || this.shadowRoot.getElementById("editor");
      if (input) { input.focus(); input.select(); }
      this._msg = { err: true, text: "Kopieren nicht möglich. Text ist markiert, bitte manuell kopieren." };
    }
    const keepDraft = this._editing ? this.shadowRoot.getElementById("editor")?.value : null;
    if (keepDraft !== null && keepDraft !== undefined) this._draft = keepDraft;
    this._renderMain();
  }

  async _save() {
    const ta = this.shadowRoot.getElementById("editor");
    if (!ta || !this._note) return;
    const text = ta.value;
    this._draft = text;
    const res = await this._api("PUT", "note", { path: this._note.path, text, etag: this._note.etag });
    if (res.status === 409) {
      this._msg = {
        err: true,
        html: `Die Datei wurde inzwischen geändert (z. B. per Syncthing vom Handy). Nicht gespeichert.
          <div class="row"><button class="btn" data-act="copydraft">Meine Version kopieren</button>
          <button class="btn danger" data-act="reloadnote">Neu laden (meine Änderungen verwerfen)</button></div>`,
      };
      this._renderMain();
      return;
    }
    if (!res.ok) {
      this._msg = { err: true, text: res.status === 413 ? "Notiz ist zu groß (max. 2 MB)." : res.status === 403 ? "Keine Schreibrechte." : "Speichern fehlgeschlagen." };
      this._renderMain();
      return;
    }
    this._dirty = false;
    this._draft = null;
    const path = this._note.path;
    await this._open(path);
    this._msg = { text: "Gespeichert." };
    this._renderMain();
    this._reloadTreeQuietly();
  }

  async _share(enabled) {
    const n = this._note;
    const daysValue = this.shadowRoot.getElementById("days")?.value || "";
    const body = { path: n.path, enabled, etag: n.etag };
    if (enabled && daysValue) body.days = parseInt(daysValue, 10);
    const res = await this._api("POST", "share", body);
    if (res.status === 409) {
      this._msg = { err: true, text: "Die Datei wurde inzwischen geändert. Bitte neu laden und erneut versuchen." };
      this._renderMain();
      return;
    }
    if (!res.ok) {
      this._msg = { err: true, text: "Freigabe konnte nicht geändert werden." };
      this._renderMain();
      return;
    }
    n.etag = res.data.etag;
    n.shared = res.data.shared;
    // Frontmatter hat sich ggf. geändert: Rohtext/ETag neu holen, damit späteres Bearbeiten passt
    const fresh = await this._api("GET", `note?path=${encodeURIComponent(n.path)}`);
    if (fresh.ok) Object.assign(n, fresh.data);
    this._link = enabled ? { url: res.data.url, expires: res.data.expires } : null;
    this._shareOpen = enabled;
    this._msg = enabled ? null : { text: "Freigabe beendet." };
    this._renderMain();
    this._reloadTreeQuietly();
  }

  async _reloadTreeQuietly() {
    const res = await this._api("GET", "tree");
    if (res.ok) { this._notes = res.data.notes || []; this._renderTree(); }
  }
}

if (!customElements.get("obsidian-share-panel")) {
  customElements.define("obsidian-share-panel", ObsidianSharePanel);
}
