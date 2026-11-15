/* davidcharles.info: dark mode toggle and "Listen to this post" */
(function () {
  var root = document.documentElement;

  // ---------- Dark mode toggle ----------
  function current() {
    return root.dataset.theme || (window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  }
  function label(btn) {
    var dark = current() === "dark";
    btn.textContent = dark ? "Light" : "Dark";
    btn.setAttribute("aria-label", dark ? "Switch to light mode" : "Switch to dark mode");
  }
  document.querySelectorAll(".theme-toggle").forEach(function (btn) {
    label(btn);
    btn.addEventListener("click", function () {
      var next = current() === "dark" ? "light" : "dark";
      root.dataset.theme = next;
      try { localStorage.setItem("theme", next); } catch (e) {}
      document.querySelectorAll(".theme-toggle").forEach(label);
      document.dispatchEvent(new CustomEvent("themechange"));
    });
  });

  // ---------- Newsletter sign-up box ----------
  // "Subscribe free" opens Substack's own sign-up form right here. Nothing loads from Substack until tapped.
  document.querySelectorAll(".subscribe-open").forEach(function (a) {
    a.addEventListener("click", function (ev) {
      var box = a.closest(".subscribe-box"), slot = box && box.querySelector(".subscribe-embed");
      if (!slot || slot.firstChild) return;
      ev.preventDefault();
      var f = document.createElement("iframe");
      f.src = "https://davidcharles.substack.com/embed";
      f.title = "Subscribe to David Charles's newsletter";
      f.width = "100%"; f.height = "320"; f.loading = "lazy";
      f.style.border = "1px solid var(--line)"; f.style.borderRadius = "8px"; f.style.background = "#fff";
      f.setAttribute("frameborder", "0"); f.setAttribute("scrolling", "no");
      slot.appendChild(f);
      a.style.display = "none";
    });
  });
  var latestBox = document.querySelector(".subscribe-box .latest");
  if (latestBox && window.fetch) {
    fetch("/assets/latest.json").then(function (r) { return r.json(); }).then(function (d) {
      var link = latestBox.querySelector("a");
      link.href = d.url; link.textContent = d.title; latestBox.hidden = false;
    }).catch(function () {});
  }

  // ---------- Continue where you left off (series) ----------
  // Remembered in this browser only; nothing is sent anywhere.
  function getProgress() {
    try { return JSON.parse(localStorage.getItem("series-progress") || "{}"); } catch (e) { return {}; }
  }
  var box = document.querySelector(".series-box[data-progress]");
  if (box) {
    try {
      var d = JSON.parse(box.getAttribute("data-progress")), all = getProgress(), old = all[d.slug];
      if (!old || d.part >= old.part) {
        d.url = location.pathname; d.t = Date.now(); all[d.slug] = d;
        localStorage.setItem("series-progress", JSON.stringify(all));
      }
    } catch (e) {}
  }
  function resumeLink(p) {
    var frag = document.createDocumentFragment(), a = document.createElement("a");
    if (p.next) {
      frag.appendChild(document.createTextNode("You’ve read up to part " + p.part + " of " + p.total + ". "));
      a.href = p.next; a.textContent = "Carry on with part " + (p.part + 1) + ": " + p.nextTitle + " →";
    } else {
      frag.appendChild(document.createTextNode("You’ve finished all " + p.total + " parts. "));
      a.href = p.url; a.textContent = "Back to the last part";
    }
    frag.appendChild(a);
    return frag;
  }
  var cont = document.querySelector(".continue[data-series]");
  if (cont) {
    var p = getProgress()[cont.getAttribute("data-series")];
    if (p) { cont.appendChild(resumeLink(p)); cont.hidden = false; }
  }
  var home = document.querySelector(".continue-home");
  if (home) {
    var list = Object.keys(getProgress()).map(function (k) { return getProgress()[k]; })
      .filter(function (p) { return p.next; }).sort(function (a, b) { return b.t - a.t; }).slice(0, 2);
    if (list.length) {
      var ul = home.querySelector("ul");
      list.forEach(function (p) {
        var li = document.createElement("li"), s = document.createElement("strong");
        s.textContent = p.name + ": ";
        li.appendChild(s); li.appendChild(resumeLink(p)); ul.appendChild(li);
      });
      home.hidden = false;
    }
  }

  // ---------- Listen to this post ----------
  var listen = document.querySelector(".listen");
  if (!listen) return;
  if (!("speechSynthesis" in window) || !window.SpeechSynthesisUtterance) { listen.hidden = true; return; }
  listen.hidden = false;
  var play = listen.querySelector(".listen-play"), stop = listen.querySelector(".listen-stop");
  var synth = window.speechSynthesis, queue = [], idx = 0, state = "idle";

  function chunks() {
    var title = (document.querySelector(".entry-head h1") || {}).innerText || "";
    var body = document.querySelector(".entry-content");
    var text = title + ". " + (body ? body.innerText : "");
    var parts = text.replace(/\s+/g, " ").match(/[^.!?…]+[.!?…]+["'’”)]*\s*|[^.!?…]+$/g) || [text];
    var out = [], buf = "";
    parts.forEach(function (p) {
      if ((buf + p).length > 220 && buf) { out.push(buf); buf = ""; }
      buf += p;
    });
    if (buf.trim()) out.push(buf);
    return out;
  }
  function voice() {
    var vs = synth.getVoices();
    return vs.filter(function (v) { return /en[-_]GB/i.test(v.lang); })[0] ||
           vs.filter(function (v) { return /^en/i.test(v.lang); })[0] || null;
  }
  function speakNext() {
    if (state !== "playing") return;
    if (idx >= queue.length) { reset(); return; }
    var u = new SpeechSynthesisUtterance(queue[idx]);
    var v = voice(); if (v) { u.voice = v; u.lang = v.lang; } else { u.lang = "en-GB"; }
    u.rate = 1;
    u.onend = function () { idx++; speakNext(); };
    u.onerror = function () { idx++; speakNext(); };
    synth.speak(u);
  }
  function reset() {
    state = "idle"; idx = 0; synth.cancel();
    play.textContent = "▶ Listen"; stop.hidden = true;
  }
  play.addEventListener("click", function () {
    if (state === "idle") {
      queue = chunks(); idx = 0; state = "playing";
      play.textContent = "❚❚ Pause"; stop.hidden = false;
      synth.cancel(); speakNext();
    } else if (state === "playing") {
      state = "paused"; synth.pause(); play.textContent = "▶ Resume";
    } else {
      state = "playing"; synth.resume(); play.textContent = "❚❚ Pause";
      if (!synth.speaking) speakNext();
    }
  });
  stop.addEventListener("click", reset);
  window.addEventListener("pagehide", function () { synth.cancel(); });
})();

// ---------- Site editor: only in a browser where David has set it up at /edit/ ----------
(function () {
  try {
    if (localStorage.getItem("dc-edit-token") && document.querySelector(".entry-content, [data-edit-file]")) {
      var s = document.createElement("script");
      s.src = "/assets/editor.js?v=2";
      document.head.appendChild(s);
    }
  } catch (e) {}
})();
