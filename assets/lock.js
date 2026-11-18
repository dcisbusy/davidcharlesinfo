/* davidcharles.info: open the subscriber-only ebooks and maps with the newsletter password.
   Two tiers: "free" (the password in every newsletter, assets/lock.json) and "paid" (the password in paid
   issues, assets/lock-paid.json, which also opens everything free). A password unlocks a key that this
   browser keeps, so readers type it once. See scripts/lock.py for how files are locked. */
(function () {
  "use strict";
  var TIERS = {
    free: { file: "/assets/lock.json", key: "dc-sub-key", id: "dc-sub-id", cls: "dc-unlocked" },
    paid: { file: "/assets/lock-paid.json", key: "dc-paid-key", id: "dc-paid-id", cls: "dc-paid" }
  };
  var te = new TextEncoder(), infos = {}, keys = {};

  function b64(s) { var b = atob(s), u = new Uint8Array(b.length); for (var i = 0; i < b.length; i++) u[i] = b.charCodeAt(i); return u; }
  function unb64(u) { var s = ""; u = new Uint8Array(u); for (var i = 0; i < u.length; i++) s += String.fromCharCode(u[i]); return btoa(s); }
  function store(k, v) { try { if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (e) {} }
  function read(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }

  function info(tier) {   // the tier's key file, or null if there isn't one
    if (!infos[tier]) infos[tier] = fetch(TIERS[tier].file, { cache: "no-cache" })
      .then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; });
    return infos[tier];
  }
  function importKey(raw) { return crypto.subtle.importKey("raw", raw, "AES-GCM", false, ["decrypt"]); }

  // the key this browser already has for a tier, if it's still the current one
  function savedKey(tier) {
    if (!keys[tier]) {
      keys[tier] = info(tier).then(function (li) {
        var t = TIERS[tier], raw = read(t.key);
        if (!li || !raw || read(t.id) !== li.id) return null;
        document.documentElement.classList.add(t.cls);
        return importKey(b64(raw));
      }).catch(function () { return null; });
    }
    return keys[tier];
  }

  function keep(tier, raw, id) {
    var t = TIERS[tier];
    store(t.key, unb64(raw)); store(t.id, id);
    keys[tier] = importKey(new Uint8Array(raw));
    document.documentElement.classList.add(t.cls);
  }

  function unwrapWith(password, li, field) {
    return crypto.subtle.importKey("raw", te.encode(password), "PBKDF2", false, ["deriveKey"]).then(function (base) {
      return crypto.subtle.deriveKey({ name: "PBKDF2", hash: "SHA-256", salt: b64(li.salt), iterations: li.iter },
                                     base, { name: "AES-GCM", length: 256 }, false, ["decrypt"]);
    }).then(function (kek) {
      var w = b64(li[field]);
      return crypto.subtle.decrypt({ name: "AES-GCM", iv: w.slice(0, 12), additionalData: te.encode("dc-lock") }, kek, w.slice(12));
    });
  }

  // Try the password on both tiers. Resolves to {free: bool, paid: bool}; rejects if it opens neither.
  function unlock(password) {
    password = String(password).toLowerCase().replace(/\s+/g, "");
    var got = { free: false, paid: false };
    return Promise.all([info("free"), info("paid")]).then(function (li) {
      var free = li[0], paid = li[1];
      var tryPaid = !paid ? Promise.resolve() : unwrapWith(password, paid, "wrapped").then(function (raw) {
        keep("paid", raw, paid.id); got.paid = true;
        if (free && paid.free_wrapped && paid.free_id === free.id)
          return unwrapWith(password, paid, "free_wrapped").then(function (r) { keep("free", r, free.id); got.free = true; });
      }).catch(function () {});
      return tryPaid.then(function () {
        if (got.free || !free) return;
        return unwrapWith(password, free, "wrapped").then(function (raw) { keep("free", raw, free.id); got.free = true; })
          .catch(function () {});
      });
    }).then(function () {
      if (!got.free && !got.paid) throw new Error("wrong password");
      if (window.goatcounter && goatcounter.count)
        goatcounter.count({ path: got.paid ? "subscriber-unlock-paid" : "subscriber-unlock", title: "Subscriber unlock", event: true });
      return got;
    });
  }

  function open(url, tier) {
    tier = tier || "free";
    return savedKey(tier).then(function (key) {
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

  function forget() {
    Object.keys(TIERS).forEach(function (k) {
      var t = TIERS[k]; store(t.key, null); store(t.id, null); delete keys[k];
      document.documentElement.classList.remove(t.cls);
    });
  }

  // A password form in `el`; calls onOpen() once this browser can open files of `tier` ("free" by default).
  function gate(el, onOpen, tier) {
    tier = tier || el.getAttribute("data-tier") || "free";
    savedKey(tier).then(function (key) {
      if (key) { onOpen(); return; }
      var sub = el.getAttribute("data-subscribe") || "https://davidcharles.substack.com/subscribe";
      var paid = tier === "paid";
      el.innerHTML =
        '<form class="lock-form"><p class="lock-title">' + (el.getAttribute("data-title") || (paid ? "For paid subscribers" : "For newsletter subscribers")) + '</p>' +
        '<p class="lock-text">' + (el.getAttribute("data-text") || (paid
          ? "Type the paid subscribers’ password from any paid issue. You only need to do it once on this device."
          : "Type the password from the bottom of any newsletter. You only need to do it once on this device.")) + '</p>' +
        '<label class="lock-label">Password <input type="password" autocomplete="current-password" autocapitalize="none" spellcheck="false" required></label>' +
        '<button type="submit" class="button primary">Unlock</button><p class="lock-msg" role="status"></p>' +
        (el.hasAttribute("data-no-join") ? "" : '<p class="lock-sub">' + (paid ? 'Not a paid subscriber yet? <a href="' + sub + '">Upgrade or subscribe</a> and the password comes with the next paid issue.'
                                      : 'Not a subscriber yet? <a href="' + sub + '">Join free</a> and the password comes with the next email.') + '</p>') + '</form>';
      var f = el.querySelector("form"), msg = el.querySelector(".lock-msg"), inp = el.querySelector("input");
      f.addEventListener("submit", function (e) {
        e.preventDefault();
        msg.textContent = "Checking…";
        unlock(inp.value).then(function (got) {
          if (!got[tier]) { msg.textContent = "That password opens the free ebooks and maps. These need the paid subscribers’ password, from any paid issue."; return; }
          el.innerHTML = ""; onOpen();
        }).catch(function () { msg.textContent = "That's not the password. Check the bottom of the newsletter and try again."; });
      });
    });
  }

  function download(url, name, type, tier) {
    return open(url, tier).then(function (buf) {
      var a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([buf], { type: type }));
      a.download = name;
      document.body.appendChild(a); a.click();
      setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 60000);
    });
  }

  // Download buttons for locked files:
  // <a href="/subscribers/" data-locked="/books/x/x.epub.locked" data-name="x.epub" data-type="…" data-tier="paid">
  document.addEventListener("click", function (e) {
    var a = e.target.closest && e.target.closest("a[data-locked]");
    if (!a) return;
    e.preventDefault();
    var tier = a.getAttribute("data-tier") || "free";
    savedKey(tier).then(function (key) {
      if (!key) { location.href = "/subscribers/?next=" + encodeURIComponent(location.pathname) + (tier === "paid" ? "&tier=paid" : ""); return; }
      var label = a.textContent; a.textContent = "Opening…";
      download(a.getAttribute("data-locked"), a.getAttribute("data-name"), a.getAttribute("data-type"), tier)
        .then(function () { a.textContent = label; },
              function () { a.textContent = "Sorry, that didn't work. Tap to try again."; });
    });
  });

  savedKey("free"); savedKey("paid");
  window.DCLock = { gate: gate, open: open, download: download, forget: forget, unlock: unlock };
})();
