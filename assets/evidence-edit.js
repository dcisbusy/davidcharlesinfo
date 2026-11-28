/* davidcharles.info: David's editor for the Nature Evidence Library (/evidence/edit/).
   Opens the library's Markdown (evidence/library.md.locked, locked with the paid key) straight from GitHub, lets him
   edit it, then locks it again in this browser and saves it to GitHub with his site-editor token. The "Evidence
   library" workflow then rebuilds /evidence/ from it (scripts/make_evidence.py). Nothing is sent anywhere unlocked. */
(function () {
  "use strict";
  var REPO = "dcisbusy/davidcharlesinfo", API = "https://api.github.com/repos/" + REPO;
  var FILE = "evidence/library.md.locked", PAGE = "evidence/library.locked", DRAFT = "dc-evidence-draft";
  var $ = function (id) { return document.getElementById(id); };
  var token = null, sha = null, saved = "", busy = false;
  try { token = localStorage.getItem("dc-edit-token"); } catch (e) {}

  var gate = $("eve-gate"), box = $("eve"), ta = $("eve-text"), msg = $("eve-msg"), jump = $("eve-jump");
  function say(t, cls) { msg.textContent = t; msg.className = "eve-msg" + (cls ? " " + cls : ""); }

  function gh(path, opts) {
    opts = opts || {};
    return fetch(API + path, {
      method: opts.method || "GET", cache: "no-store",
      headers: { "Authorization": "Bearer " + token, "Accept": "application/vnd.github+json" },
      body: opts.body ? JSON.stringify(opts.body) : undefined
    }).then(function (r) {
      if (r.status === 401 || r.status === 403) throw new Error("GitHub didn’t accept your editing token. Set it up again at davidcharles.info/edit/");
      return r.json().then(function (j) { j._status = r.status; return j; });
    });
  }
  function bytesOf(b64) { var s = atob(b64.replace(/\s/g, "")), u = new Uint8Array(s.length); for (var i = 0; i < s.length; i++) u[i] = s.charCodeAt(i); return u; }
  function b64Of(u) { var s = "", c = 0x8000; for (var i = 0; i < u.length; i += c) s += String.fromCharCode.apply(null, u.subarray(i, i + c)); return btoa(s); }
  function unlockBytes(u) {   // DCLock.open() takes a URL, so hand it the bytes as one
    var url = URL.createObjectURL(new Blob([u]));
    return DCLock.open(url, "paid").then(function (buf) { URL.revokeObjectURL(url); return new TextDecoder().decode(buf); });
  }
  function getDraft() { try { return JSON.parse(localStorage.getItem(DRAFT) || "null"); } catch (e) { return null; } }
  function putDraft(v) { try { if (v) localStorage.setItem(DRAFT, JSON.stringify(v)); else localStorage.removeItem(DRAFT); } catch (e) {} }

  function load() {
    say("Opening the library…");
    return gh("/contents/" + FILE + "?ref=main").then(function (f) {
      if (f._status !== 200) throw new Error("Couldn’t find the library on GitHub (" + f._status + ").");
      sha = f.sha;
      return unlockBytes(bytesOf(f.content));
    }).then(function (text) {
      saved = text; ta.value = text; box.hidden = false;
      var d = getDraft();
      if (d && d.text && d.text !== text) {
        $("eve-draft").hidden = false;
        $("eve-draft-when").textContent = new Date(d.when).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" });
      }
      headings(); say("");
    });
  }

  // the "Jump to" list: every ## and ### heading, so a long file is quick to get around
  function headings() {
    var lines = ta.value.split("\n"), pos = 0, opts = ['<option value="">Jump to…</option>'];
    lines.forEach(function (l) {
      var m = /^(#{2,3}) (.+)/.exec(l);
      if (m) opts.push('<option value="' + pos + '">' + (m[1].length === 3 ? " " : "") +
        m[2].replace(/[&<>]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]; }) + "</option>");
      pos += l.length + 1;
    });
    jump.innerHTML = opts.join("");
  }
  jump.addEventListener("change", function () {
    if (jump.value === "") return;
    var at = +jump.value;
    ta.focus(); ta.setSelectionRange(at, at);
    // scroll the box so the heading sits at the top
    var before = ta.value.slice(0, at).split("\n").length - 1;
    ta.scrollTop = before * parseFloat(getComputedStyle(ta).lineHeight) - 8;
    jump.value = "";
  });

  var timer;
  ta.addEventListener("input", function () {
    clearTimeout(timer);
    timer = setTimeout(function () {
      putDraft(ta.value === saved ? null : { text: ta.value, when: Date.now() });
      headings();
    }, 600);
    if (!busy) say(ta.value === saved ? "" : "Unsaved changes");
  });
  window.addEventListener("beforeunload", function (e) { if (ta.value !== saved) { e.preventDefault(); e.returnValue = ""; } });
  document.addEventListener("keydown", function (e) {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); save(); }
  });

  $("eve-draft-yes").addEventListener("click", function () {
    var d = getDraft(); if (d) { ta.value = d.text; headings(); say("Unsaved changes"); }
    $("eve-draft").hidden = true;
  });
  $("eve-draft-no").addEventListener("click", function () { putDraft(null); $("eve-draft").hidden = true; });

  // checks that catch the slips that would break the page
  function problems(text) {
    var p = [];
    if (text.trim().length < 2000) p.push("The library looks almost empty.");
    if (!/^## References\s*$/m.test(text)) p.push("There’s no “## References” heading, so citations won’t link.");
    var bad = text.split("\n").filter(function (l) { return /^###? \S/.test(l) === false && /^#{2,3}\S/.test(l); });
    if (bad.length) p.push("A heading needs a space after the #: “" + bad[0].slice(0, 40) + "”");
    return p;
  }

  function save() {
    if (busy) return;
    var text = ta.value;
    if (text === saved) { say("Nothing to save."); return; }
    var p = problems(text);
    if (p.length && !confirm(p.join("\n") + "\n\nSave anyway?")) return;
    busy = true; $("eve-save").disabled = true; say("Saving…");
    var started = new Date();
    gh("/contents/" + FILE + "?ref=main").then(function (f) {
      if (f.sha !== sha && !confirm("The library was changed somewhere else since you opened it. Save yours over it?")) throw new Error("Not saved.");
      return DCLock.seal(new TextEncoder().encode(text), "paid").then(function (locked) {
        return gh("/contents/" + FILE, { method: "PUT", body: {
          message: "Edit the evidence library", content: b64Of(locked), sha: f.sha, branch: "main" } });
      });
    }).then(function (r) {
      if (r._status !== 200 && r._status !== 201) throw new Error("GitHub said no (" + r._status + "): " + (r.message || ""));
      sha = r.content.sha; saved = text; putDraft(null);
      say("Saved. Rebuilding the page (about a minute)…", "ok");
      watch(started, 0);
    }).catch(function (err) {
      say(err.message === "locked" ? "This browser needs the paid password again. Reload the page." : err.message, "bad");
    }).then(function () { busy = false; $("eve-save").disabled = false; });
  }
  $("eve-save").addEventListener("click", save);

  // wait for the workflow's "Rebuild the evidence library" commit, then GitHub Pages
  function watch(since, n) {
    if (n > 40) { say("Saved. The rebuild is taking a while: check the Actions tab on GitHub if the page hasn’t changed in 10 minutes.", "ok"); return; }
    setTimeout(function () {
      gh("/commits?path=" + PAGE + "&per_page=1").then(function (c) {
        var when = c[0] && new Date(c[0].commit.committer.date);
        if (when && when > since) say("Done. The page shows your changes within a minute or two (GitHub Pages).", "ok");
        else watch(since, n + 1);
      }).catch(function () { watch(since, n + 1); });
    }, 15000);
  }

  $("eve-download").addEventListener("click", function () {
    var a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([ta.value], { type: "text/markdown" }));
    a.download = "Nature Evidence Library " + new Date().toISOString().slice(0, 10) + ".md";
    document.body.appendChild(a); a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 60000);
  });
  $("eve-file").addEventListener("change", function () {
    var f = this.files[0]; if (!f) return;
    f.text().then(function (t) {
      if (!confirm("Replace everything in the editor with “" + f.name + "”? Nothing is saved until you press Save.")) return;
      ta.value = t.replace(/\r\n/g, "\n"); headings(); say("Loaded " + f.name + ". Press Save to put it live.");
      putDraft({ text: ta.value, when: Date.now() });
    });
    this.value = "";
  });

  if (!token) {
    gate.innerHTML = '<p class="lock-title">Set up editing first</p><p>This browser doesn’t have your GitHub editing token yet. ' +
      'Add it at <a href="/edit/">davidcharles.info/edit/</a> (the same one the site editor uses), then come back here.</p>';
    return;
  }
  DCLock.gate(gate, function () {
    load().catch(function (err) { say(err.message, "bad"); box.hidden = false; });
  }, "paid");
})();
