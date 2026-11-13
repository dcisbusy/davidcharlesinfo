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
