/* davidcharles.info: edit a post in place, from any browser, and save it straight to GitHub.

   Only loads for someone who has set up a GitHub token at /edit/ (site.js checks for it).
   It edits just the story itself: the part of the page file between <!--content:start--> and
   <!--content:end-->. Saving commits that one file to the main branch; the "Build site" workflow
   then republishes the site within a few minutes. Every save is a normal commit, so any edit can
   be undone from the repository's history. */
(function () {
  "use strict";
  var REPO = "dcisbusy/davidcharlesinfo", BRANCH = "main", API = "https://api.github.com/repos/" + REPO + "/contents/";
  var token;
  try { token = localStorage.getItem("dc-edit-token"); } catch (e) { return; }
  if (!token) return;
  var host = document.querySelector(".entry-content");
  if (!host) return;

  function markers() {
    var s = null, e = null;
    for (var n = host.firstChild; n; n = n.nextSibling) {
      if (n.nodeType === 8 && n.data === "content:start") s = n;
      if (n.nodeType === 8 && n.data === "content:end") e = n;
    }
    return s && e ? [s, e] : null;
  }
  var m = markers();
  if (!m) return;

  var path = decodeURIComponent(location.pathname).replace(/^\/+/, "");
  if (path && !/\/$/.test(path)) path += "/";
  var file = path + "index.html";
  var title = (document.querySelector(".entry-head h1") || document.querySelector("h1") || {}).textContent || file;

  // ---------- Look ----------
  var css = document.createElement("style");
  css.textContent =
    ".dc-edit-btn{position:fixed;right:16px;bottom:16px;z-index:9999;font:600 15px/1 system-ui,sans-serif;padding:12px 18px;" +
    "border-radius:999px;border:0;background:#2f6b4f;color:#fff;box-shadow:0 2px 10px rgba(0,0,0,.25);cursor:pointer}" +
    ".dc-bar{position:fixed;left:0;right:0;bottom:0;z-index:9999;display:flex;flex-wrap:wrap;gap:6px;align-items:center;" +
    "padding:8px 10px calc(8px + env(safe-area-inset-bottom));background:#1d2622;color:#fff;font:14px/1.2 system-ui,sans-serif;" +
    "box-shadow:0 -2px 10px rgba(0,0,0,.25)}" +
    ".dc-bar button{font:600 15px/1 system-ui,sans-serif;min-width:44px;min-height:40px;padding:0 12px;border-radius:8px;" +
    "border:1px solid rgba(255,255,255,.35);background:transparent;color:#fff;cursor:pointer}" +
    ".dc-bar button.dc-save{background:#e2a13d;border-color:#e2a13d;color:#1d2622}" +
    ".dc-bar button:disabled{opacity:.5}" +
    ".dc-bar .dc-msg{flex:1 1 100%;font-size:13px;opacity:.9}" +
    ".dc-bar .dc-gap{flex:1}" +
    ".dc-editing{outline:2px dashed #e2a13d;outline-offset:8px;border-radius:2px;min-height:2em}" +
    ".dc-editing:focus{outline-style:solid}" +
    "body.dc-on{padding-bottom:140px}";
  document.head.appendChild(css);

  var btn = document.createElement("button");
  btn.type = "button";
  btn.className = "dc-edit-btn";
  btn.textContent = "Edit";
  btn.setAttribute("aria-label", "Edit this post");
  document.body.appendChild(btn);

  var bar, msg, wrap, original;

  function el(tag, cls, text) {
    var x = document.createElement(tag);
    if (cls) x.className = cls;
    if (text) x.textContent = text;
    return x;
  }
  function say(t) { if (msg) msg.textContent = t; }

  function tool(label, aria, fn) {
    var b = el("button", "", label);
    b.type = "button";
    b.setAttribute("aria-label", aria);
    // keep the text selection when a button is pressed
    b.addEventListener("mousedown", function (e) { e.preventDefault(); });
    b.addEventListener("click", fn);
    return b;
  }
  function cmd(name, value) {
    return function () { wrap.focus(); document.execCommand(name, false, value || null); };
  }

  function start() {
    if (bar) bar.remove();
    m = markers();
    if (!m) return;
    wrap = el("div", "dc-editing");
    host.insertBefore(wrap, m[1]);
    while (m[0].nextSibling && m[0].nextSibling !== wrap) wrap.appendChild(m[0].nextSibling);
    original = wrap.innerHTML;
    wrap.contentEditable = "true";
    try { document.execCommand("styleWithCSS", false, false); } catch (e) {}
    wrap.addEventListener("paste", plainPaste);

    bar = el("div", "dc-bar");
    bar.setAttribute("role", "toolbar");
    bar.setAttribute("aria-label", "Editing this post");
    var bold = tool("B", "Bold", cmd("bold")); bold.style.fontWeight = "800";
    var ital = tool("I", "Italic", cmd("italic")); ital.style.fontStyle = "italic";
    bar.appendChild(bold);
    bar.appendChild(ital);
    bar.appendChild(tool("Link", "Add a link", function () {
      var u = prompt("Link address (https://…)");
      if (u) { wrap.focus(); document.execCommand("createLink", false, u.trim()); }
    }));
    bar.appendChild(tool("Unlink", "Remove a link", cmd("unlink")));
    bar.appendChild(tool("Undo", "Undo", cmd("undo")));
    bar.appendChild(el("span", "dc-gap"));
    bar.appendChild(tool("Cancel", "Cancel and throw away changes", cancel));
    var save = tool("Save", "Save to the website", function () { saveIt(save); });
    save.className = "dc-save";
    bar.appendChild(save);
    msg = el("div", "dc-msg", "Tap into the text to change it. Save publishes it in a few minutes.");
    msg.setAttribute("role", "status");
    bar.appendChild(msg);
    document.body.appendChild(bar);
    document.body.classList.add("dc-on");
    btn.hidden = true;
    window.addEventListener("beforeunload", guard);
    wrap.focus();
  }

  function guard(e) {
    if (wrap && wrap.innerHTML !== original) { e.preventDefault(); e.returnValue = ""; }
  }

  function plainPaste(e) {
    // paste words only, never the styling of wherever they were copied from
    e.preventDefault();
    var t = (e.clipboardData || window.clipboardData).getData("text/plain");
    document.execCommand("insertText", false, t);
  }

  function finish(keep) {
    if (!keep) wrap.innerHTML = original;
    wrap.removeAttribute("contenteditable");
    wrap.removeEventListener("paste", plainPaste);
    while (wrap.firstChild) host.insertBefore(wrap.firstChild, wrap);
    wrap.remove();
    wrap = null;
    window.removeEventListener("beforeunload", guard);
    document.body.classList.remove("dc-on");
    btn.hidden = false;
  }

  function cancel() {
    if (wrap.innerHTML !== original && !confirm("Throw away your changes?")) return;
    bar.remove();
    finish(false);
  }

  // ---------- GitHub ----------
  function b64ToText(b64) {
    var bin = atob(b64.replace(/\s/g, "")), bytes = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return new TextDecoder("utf-8").decode(bytes);
  }
  function textToB64(text) {
    var bytes = new TextEncoder().encode(text), out = "", CH = 0x8000;
    for (var i = 0; i < bytes.length; i += CH) out += String.fromCharCode.apply(null, bytes.subarray(i, i + CH));
    return btoa(out);
  }
  function gh(method, body) {
    return fetch(API + file.split("/").map(encodeURIComponent).join("/") + (method === "GET" ? "?ref=" + BRANCH : ""), {
      method: method,
      headers: { "Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28" },
      body: body ? JSON.stringify(body) : undefined,
      cache: "no-store"
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) { j._status = r.status; return j; });
    });
  }
  // the story as a browser reads it, so the version on GitHub can be compared with what was opened
  function normalise(html) {
    var t = document.createElement("template");
    t.innerHTML = html;
    return t.innerHTML;
  }

  function saveIt(save) {
    var html = wrap.innerHTML.replace(/&nbsp;/g, "\u00a0");   // keep the file as it was written
    if (wrap.innerHTML === original) { say("No changes to save."); return; }
    save.disabled = true;
    say("Saving…");
    gh("GET").then(function (f) {
      if (f._status === 401 || f._status === 403) throw new Error("GitHub didn't accept the token. Set it up again at davidcharles.info/edit/");
      if (f._status !== 200 || !f.content) throw new Error("Couldn't fetch this page from GitHub (" + f._status + ").");
      var text = b64ToText(f.content), a = "<!--content:start-->", z = "<!--content:end-->";
      var i = text.indexOf(a), j = text.indexOf(z);
      if (i < 0 || j < i) throw new Error("This page can't be edited here: its story markers are missing.");
      if (normalise(text.slice(i + a.length, j)) !== normalise(original)) {
        throw new Error("This post changed on GitHub since you opened it. Copy your changes somewhere, reload, and edit again.");
      }
      var updated = text.slice(0, i + a.length) + html + text.slice(j);
      return gh("PUT", { message: "Edit “" + title.trim() + "” from the site editor",
                         content: textToB64(updated), sha: f.sha, branch: BRANCH });
    }).then(function (r) {
      if (r._status === 409) throw new Error("Someone saved this file a moment ago. Reload and try again.");
      if (r._status !== 200 && r._status !== 201) throw new Error("GitHub refused the save (" + r._status + (r.message ? ": " + r.message : "") + ").");
      original = wrap.innerHTML;
      finish(true);
      say("Saved. The website updates in about 3 minutes.");
      save.remove();
      setTimeout(function () { if (bar) bar.remove(); }, 6000);
    }).catch(function (err) {
      save.disabled = false;
      say(err.message || "Couldn't save. Check your connection and try again.");
    });
  }

  btn.addEventListener("click", start);
})();
