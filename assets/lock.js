/* davidcharles.info: open the subscriber-only ebooks and maps with the newsletter password.
   The password unlocks a key (assets/lock.json) that this browser keeps, so readers type it once.
   See scripts/lock.py for how files are locked. */
(function () {
  "use strict";
  var KEY = "dc-sub-key", KID = "dc-sub-id", te = new TextEncoder();
  var lockInfo = null, keyPromise = null;

  function b64(s) { var b = atob(s), u = new Uint8Array(b.length); for (var i = 0; i < b.length; i++) u[i] = b.charCodeAt(i); return u; }
  function unb64(u) { var s = ""; u = new Uint8Array(u); for (var i = 0; i < u.length; i++) s += String.fromCharCode(u[i]); return btoa(s); }
  function store(k, v) { try { if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (e) {} }
  function read(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }

  function info() {
    if (!lockInfo) lockInfo = fetch("/assets/lock.json", { cache: "no-cache" }).then(function (r) { return r.json(); });
    return lockInfo;
  }
  function importKey(raw) { return crypto.subtle.importKey("raw", raw, "AES-GCM", false, ["decrypt"]); }

  // the key this browser already has, if it's still the current one
  function savedKey() {
    if (!keyPromise) {
      keyPromise = info().then(function (li) {
        var raw = read(KEY);
        if (!raw || read(KID) !== li.id) return null;
        return importKey(b64(raw));
      }).catch(function () { return null; });
    }
    return keyPromise;
  }

  function unlock(password) {
    return info().then(function (li) {
      return crypto.subtle.importKey("raw", te.encode(password), "PBKDF2", false, ["deriveKey"]).then(function (base) {
        return crypto.subtle.deriveKey({ name: "PBKDF2", hash: "SHA-256", salt: b64(li.salt), iterations: li.iter },
                                       base, { name: "AES-GCM", length: 256 }, false, ["decrypt"]);
      }).then(function (kek) {
        var w = b64(li.wrapped);
        return crypto.subtle.decrypt({ name: "AES-GCM", iv: w.slice(0, 12), additionalData: te.encode("dc-lock") }, kek, w.slice(12));
      }).then(function (raw) {
        store(KEY, unb64(raw)); store(KID, li.id);
        keyPromise = importKey(new Uint8Array(raw));
        document.documentElement.classList.add("dc-unlocked");
        if (window.goatcounter && goatcounter.count) goatcounter.count({ path: "subscriber-unlock", title: "Subscriber unlock", event: true });
        return keyPromise;
      });
    });
  }

  function open(url) {
    return savedKey().then(function (key) {
      if (!key) throw new Error("locked");
      return fetch(url).then(function (r) {
        if (!r.ok) throw new Error("http " + r.status);
        return r.arrayBuffer();
      }).then(function (buf) {
        var u = new Uint8Array(buf);
        if (String.fromCharCode.apply(null, u.slice(0, 5)) !== "DCLK1") throw new Error("not locked");
        return crypto.subtle.decrypt({ name: "AES-GCM", iv: u.slice(5, 17) }, key, u.slice(17));
      });
    });
  }

  function forget() { store(KEY, null); store(KID, null); keyPromise = null; document.documentElement.classList.remove("dc-unlocked"); }

  // A password form in `el`; calls onOpen() once this browser can open locked files.
  function gate(el, onOpen) {
    savedKey().then(function (key) {
      if (key) { document.documentElement.classList.add("dc-unlocked"); onOpen(); return; }
      var sub = el.getAttribute("data-subscribe") || "https://davidcharles.substack.com/subscribe";
      el.innerHTML =
        '<form class="lock-form"><p class="lock-title">For newsletter subscribers</p>' +
        '<p class="lock-text">' + (el.getAttribute("data-text") ||
          "Type the password from the bottom of any newsletter. You only need to do it once on this device.") + '</p>' +
        '<label class="lock-label">Password <input type="password" autocomplete="current-password" autocapitalize="none" spellcheck="false" required></label>' +
        '<button type="submit" class="button primary">Unlock</button><p class="lock-msg" role="status"></p>' +
        '<p class="lock-sub">Not a subscriber yet? <a href="' + sub + '">Join free</a> and the password comes with the next email.</p></form>';
      var f = el.querySelector("form"), msg = el.querySelector(".lock-msg"), inp = el.querySelector("input");
      f.addEventListener("submit", function (e) {
        e.preventDefault();
        msg.textContent = "Checking…";
        unlock(inp.value.trim().toLowerCase().replace(/\s+/g, "")).then(function () {
          el.innerHTML = ""; onOpen();
        }).catch(function () { msg.textContent = "That's not the password. Check the bottom of the newsletter and try again."; });
      });
    });
  }

  function download(url, name, type) {
    return open(url).then(function (buf) {
      var a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([buf], { type: type }));
      a.download = name;
      document.body.appendChild(a); a.click();
      setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 60000);
    });
  }

  // Download buttons for locked files: <a href="/subscribers/" data-locked="/books/x/x.epub.locked" data-name="x.epub" data-type="…">
  document.addEventListener("click", function (e) {
    var a = e.target.closest && e.target.closest("a[data-locked]");
    if (!a) return;
    e.preventDefault();
    savedKey().then(function (key) {
      if (!key) { location.href = "/subscribers/?next=" + encodeURIComponent(location.pathname); return; }
      var label = a.textContent; a.textContent = "Opening…";
      download(a.getAttribute("data-locked"), a.getAttribute("data-name"), a.getAttribute("data-type"))
        .catch(function () { alert("Sorry, that download didn't work. Try again in a moment."); })
        .then(function () { a.textContent = label; });
    });
  });

  savedKey().then(function (k) { if (k) document.documentElement.classList.add("dc-unlocked"); });
  window.DCLock = { gate: gate, open: open, download: download, forget: forget, unlock: unlock };
})();
