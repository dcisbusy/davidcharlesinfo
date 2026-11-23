/* davidcharles.info: edit a page in place, from any browser, and save it straight to GitHub.

   Only loads for someone who has set up a GitHub token at /edit/ (site.js checks for it).
   It edits the words on a page where they are kept:
   - a post or page: the part of its file between <!--content:start--> and <!--content:end-->
   - a block with data-edit-file: the same markers, in the file it names (the homepage intro, Work with me)
   - text with data-edit-json + data-edit-key: one line in a data file (book and series descriptions,
     Start here notes, timeline milestones, short page intros in data/page-text.json)
   Saving commits each changed file to the main branch; the "Build site" workflow then republishes the
   site within a few minutes. Every save is a normal commit, so any edit can be undone from the history. */
(function () {
  "use strict";
  var REPO = "dcisbusy/davidcharlesinfo", BRANCH = "main", API = "https://api.github.com/repos/" + REPO + "/contents/";
  var token;
  try { token = localStorage.getItem("dc-edit-token"); } catch (e) { return; }
  if (!token) return;

  var path = decodeURIComponent(location.pathname).replace(/^\/+/, "");
  if (path && !/\/$/.test(path)) path += "/";
  var pageTitle = ((document.querySelector(".entry-head h1") || document.querySelector("h1") || {}).textContent || path).trim();

  function markers(host) {
    var s = null, e = null;
    for (var n = host.firstChild; n; n = n.nextSibling) {
      if (n.nodeType === 8 && n.data === "content:start") s = n;
      if (n.nodeType === 8 && n.data === "content:end") e = n;
    }
    return s && e ? [s, e] : null;
  }

  // ---------- Find everything editable on this page ----------
  var regions = [];
  Array.prototype.forEach.call(document.querySelectorAll("[data-edit-file], .entry-content"), function (host) {
    if (host.matches(".entry-content") && host.closest("[data-edit-file]")) return;
    if (!markers(host)) return;
    regions.push({ kind: "file", host: host, file: host.getAttribute("data-edit-file") || path + "index.html" });
  });
  Array.prototype.forEach.call(document.querySelectorAll("[data-edit-json]"), function (el) {
    var keys;
    try { keys = JSON.parse(el.getAttribute("data-edit-key")); } catch (e) { return; }
    regions.push({ kind: "json", host: el, file: el.getAttribute("data-edit-json"), keys: keys,
                   rich: el.hasAttribute("data-edit-rich") });   // rich: bold, italic and links allowed
  });
  if (!regions.length) return;

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
    ".dc-editing{outline:2px dashed #e2a13d;outline-offset:6px;border-radius:2px;min-height:1.2em;cursor:text}" +
    ".dc-editing:focus{outline-style:solid}" +
    "body.dc-on{padding-bottom:140px}";
  document.head.appendChild(css);

  var btn = document.createElement("button");
  btn.type = "button";
  btn.className = "dc-edit-btn";
  btn.textContent = "Edit";
  btn.setAttribute("aria-label", "Edit this page");
  document.body.appendChild(btn);

  var bar, msg, editing = false, focused = null;

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
    b.addEventListener("mousedown", function (e) { e.preventDefault(); });   // keep the text selection
    b.addEventListener("click", fn);
    return b;
  }
  function cmd(name, value) {
    return function () {
      if (!focused || (focused.kind !== "file" && !focused.rich)) { say("Bold, italic and links don't work in this line."); return; }
      focused.target.focus();
      document.execCommand(name, false, value || null);
    };
  }
  // a one-line field with links: keep only <a href>, <strong>/<b>, <em>/<i>; everything else becomes plain text
  function cleanInline(node) {
    var out = "";
    Array.prototype.forEach.call(node.childNodes, function (n) {
      if (n.nodeType === 3) { out += n.textContent.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); return; }
      if (n.nodeType !== 1) return;
      var t = n.tagName.toLowerCase(), inner = cleanInline(n);
      if (t === "a" && n.getAttribute("href")) out += '<a href="' + n.getAttribute("href").replace(/"/g, "&quot;") + '">' + inner + "</a>";
      else if (t === "b" || t === "strong") out += "<strong>" + inner + "</strong>";
      else if (t === "i" || t === "em") out += "<em>" + inner + "</em>";
      else out += inner;
    });
    return out.replace(/\s+/g, " ");
  }
  function current(r) {
    if (r.kind === "file") return r.wrap.innerHTML;
    if (r.rich) return cleanInline(r.host).trim();
    return r.host.textContent.replace(/\s+/g, " ").trim();
  }
  function plainOf(htmlText) { var d = document.createElement("div"); d.innerHTML = htmlText; return d.textContent.replace(/\s+/g, " ").trim(); }
  function changed() { return regions.filter(function (r) { return current(r) !== r.original; }); }

  // while editing, tapping text inside a link edits it instead of following the link
  document.addEventListener("click", function (e) {
    if (editing && e.target.closest && e.target.closest(".dc-editing")) e.preventDefault();
  }, true);

  function start() {
    if (bar) bar.remove();
    regions.forEach(function (r) {
      if (r.kind === "file") {
        var m = markers(r.host);
        if (!m) return;
        r.wrap = el("div", "dc-editing");
        r.host.insertBefore(r.wrap, m[1]);
        while (m[0].nextSibling && m[0].nextSibling !== r.wrap) r.wrap.appendChild(m[0].nextSibling);
        r.target = r.wrap;
      } else {
        r.target = r.host;
        r.host.classList.add("dc-editing");
        r.saved = r.host.innerHTML;
      }
      r.original = current(r);
      r.target.contentEditable = "true";
      r.target.addEventListener("paste", plainPaste);
      r.target.addEventListener("focus", function () { focused = r; });
      if (r.kind === "json") r.target.addEventListener("keydown", noEnter);
    });
    try { document.execCommand("styleWithCSS", false, false); } catch (e) {}
    editing = true;

    bar = el("div", "dc-bar");
    bar.setAttribute("role", "toolbar");
    bar.setAttribute("aria-label", "Editing this page");
    var bold = tool("B", "Bold", cmd("bold")); bold.style.fontWeight = "800";
    var ital = tool("I", "Italic", cmd("italic")); ital.style.fontStyle = "italic";
    bar.appendChild(bold);
    bar.appendChild(ital);
    bar.appendChild(tool("Link", "Add a link", function () {
      if (!focused || (focused.kind !== "file" && !focused.rich)) { say("Links don't work in this line."); return; }
      var u = prompt("Link address (https://…)");
      if (u) { focused.target.focus(); document.execCommand("createLink", false, u.trim()); }
    }));
    bar.appendChild(tool("Unlink", "Remove a link", cmd("unlink")));
    bar.appendChild(tool("Undo", "Undo", function () { document.execCommand("undo"); }));
    bar.appendChild(el("span", "dc-gap"));
    bar.appendChild(tool("Cancel", "Cancel and throw away changes", cancel));
    var save = tool("Save", "Save to the website", function () { saveAll(save); });
    save.className = "dc-save";
    bar.appendChild(save);
    msg = el("div", "dc-msg", "Tap any outlined text to change it. Save publishes it in a few minutes.");
    msg.setAttribute("role", "status");
    bar.appendChild(msg);
    document.body.appendChild(bar);
    document.body.classList.add("dc-on");
    btn.hidden = true;
    window.addEventListener("beforeunload", guard);
  }

  function noEnter(e) { if (e.key === "Enter") e.preventDefault(); }   // a data line is one paragraph
  function guard(e) { if (changed().length) { e.preventDefault(); e.returnValue = ""; } }
  function plainPaste(e) {
    // paste words only, never the styling of wherever they were copied from
    e.preventDefault();
    var t = (e.clipboardData || window.clipboardData).getData("text/plain");
    document.execCommand("insertText", false, t);
  }

  function finishOne(r, keep) {
    if (!r.target) return;
    if (!keep) {
      if (r.kind === "file") r.wrap.innerHTML = r.original; else r.host.innerHTML = r.saved;
    }
    r.target.removeAttribute("contenteditable");
    r.target.removeEventListener("paste", plainPaste);
    r.target.removeEventListener("keydown", noEnter);
    if (r.kind === "file") {
      while (r.wrap.firstChild) r.host.insertBefore(r.wrap.firstChild, r.wrap);
      r.wrap.remove();
      r.wrap = null;
    } else {
      r.host.classList.remove("dc-editing");
    }
    r.target = null;
  }
  function finish(keep) {
    regions.forEach(function (r) { finishOne(r, keep); });
    editing = false;
    focused = null;
    window.removeEventListener("beforeunload", guard);
    document.body.classList.remove("dc-on");
    btn.hidden = false;
  }
  function cancel() {
    if (changed().length && !confirm("Throw away your changes?")) return;
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
  function gh(file, method, body) {
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
  function normalise(html) {   // the HTML as a browser reads it, to compare GitHub's version with what was opened
    var t = document.createElement("template");
    t.innerHTML = html;
    return t.innerHTML;
  }
  function getKey(obj, keys) {
    return keys.reduce(function (o, k) { return o == null ? undefined : o[k]; }, obj);
  }

  // change one file's text for all the regions of this page kept in it
  function apply(text, rs) {
    rs.forEach(function (r) {
      if (r.kind === "file") {
        var a = "<!--content:start-->", z = "<!--content:end-->", i = text.indexOf(a), j = text.indexOf(z);
        if (i < 0 || j < i) throw new Error("This page can't be edited here: its markers are missing.");
        if (normalise(text.slice(i + a.length, j)) !== normalise(r.original)) {
          throw new Error("This page changed on GitHub since you opened it. Copy your changes somewhere, reload, and edit again.");
        }
        text = text.slice(0, i + a.length) + r.wrap.innerHTML.replace(/&nbsp;/g, " ") + text.slice(j);
      } else {
        var data = JSON.parse(text), was = getKey(data, r.keys), now = current(r);
        var parent0 = getKey(data, r.keys.slice(0, -1));
        if (was === undefined && parent0 && typeof parent0 === "object" && !Array.isArray(parent0)) {
          // text the site shows by default but that isn't in the file yet: add it rather than refuse
          parent0[r.keys[r.keys.length - 1]] = now;
          text = JSON.stringify(data, null, 1) + "\n";
          return;
        }
        var same = typeof was === "string" && (r.rich ? plainOf(was) === plainOf(r.original)
                                                       : was.replace(/\s+/g, " ").trim() === r.original);
        if (!same) {
          throw new Error("“" + r.original.slice(0, 40) + "…” changed on GitHub since you opened it. Reload and edit again.");
        }
        // swap just that string in the file, so the rest of its layout stays as it was
        var from = JSON.stringify(was), to = JSON.stringify(now), at = text.indexOf(from);
        if (at >= 0 && text.indexOf(from, at + 1) < 0) {
          text = text.slice(0, at) + to + text.slice(at + from.length);
        } else {
          var parent = getKey(data, r.keys.slice(0, -1));
          parent[r.keys[r.keys.length - 1]] = now;
          text = JSON.stringify(data, null, 1) + "\n";
        }
        if (getKey(JSON.parse(text), r.keys) !== now) throw new Error("Couldn't change that line safely; nothing was saved.");
      }
    });
    return text;
  }

  function saveAll(save) {
    var todo = changed();
    if (!todo.length) { say("No changes to save."); return; }
    var files = [];
    todo.forEach(function (r) { if (files.indexOf(r.file) < 0) files.push(r.file); });
    save.disabled = true;
    say("Saving…");
    var chain = Promise.resolve();
    files.forEach(function (file) {
      chain = chain.then(function () {
        return gh(file, "GET").then(function (f) {
          if (f._status === 401 || f._status === 403) throw new Error("GitHub didn't accept the token. Set it up again at davidcharles.info/edit/");
          if (f._status !== 200 || !f.content) throw new Error("Couldn't fetch " + file + " from GitHub (" + f._status + ").");
          var updated = apply(b64ToText(f.content), todo.filter(function (r) { return r.file === file; }));
          return gh(file, "PUT", { message: "Edit “" + pageTitle + "” from the site editor",
                                   content: textToB64(updated), sha: f.sha, branch: BRANCH });
        }).then(function (r) {
          if (r._status === 409) throw new Error("Someone saved " + file + " a moment ago. Reload and try again.");
          if (r._status !== 200 && r._status !== 201) throw new Error("GitHub refused the save (" + r._status + (r.message ? ": " + r.message : "") + ").");
          todo.forEach(function (x) { if (x.file === file) { x.original = current(x); x.saved = x.host.innerHTML; } });
        });
      });
    });
    chain.then(function () {
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
