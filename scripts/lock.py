"""Subscriber lock: encrypt files so only people with the newsletter password can open them.

How it works
- Every locked file is encrypted with one random content key (AES-256-GCM).
- assets/lock.json holds that key, itself encrypted with a key made from the subscriber password
  (PBKDF2-SHA256). A reader types the password once; assets/lock.js unwraps the content key in their
  browser, keeps it in that browser, and decrypts the files it fetches.
- The password is never in this repository: workflows get it from the SUBSCRIBER_PASSWORD secret.
- Changing the password: change the secret, then run "Build site". The build sees the old key can't be
  unwrapped, makes a new key, locks the rides map again, and starts "Make ebook" and "Update tree data"
  so the ebooks and tree map are locked with the new key too.

Locked file format: b"DCLK1" + 12-byte nonce + ciphertext. The nonce comes from the content (an HMAC of it),
so locking the same file twice gives the same bytes and the nightly build doesn't churn.

Two tiers: "free" (every newsletter subscriber, SUBSCRIBER_PASSWORD, assets/lock.json) and "paid" (paying
subscribers, PAID_SUBSCRIBER_PASSWORD, assets/lock-paid.json). The paid key file also carries the free key, so
the paid password opens everything.

Command line:  python scripts/lock.py [--paid] file IN OUT   (needs the tier's password in the environment)
               python scripts/lock.py [--paid] check
               NEW_PASSWORD='…' python scripts/lock.py --paid rewrap   (change the paid password, same files)
"""
import base64, hashlib, hmac, json, os, sys

TIERS = {   # tier: (key file, secret holding its password)
    "free": ("assets/lock.json", "SUBSCRIBER_PASSWORD"),
    "paid": ("assets/lock-paid.json", "PAID_SUBSCRIBER_PASSWORD"),
}
MAGIC = b"DCLK1"
ITERATIONS = 250_000
_KEYS = {}


class NoPassword(Exception):
    pass


def _aes():
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    return AESGCM


def _kek(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS, 32)


def _password(tier):
    p = "".join(os.environ.get(TIERS[tier][1], "").lower().split())   # as lock.js reads it
    if not p:
        raise NoPassword(f"{TIERS[tier][1]} isn't set, so nothing can be locked for {tier} subscribers")
    return p


def _unwrap(password, salt_b64, wrapped_b64):
    wrapped = base64.b64decode(wrapped_b64)
    return _aes()(_kek(password, base64.b64decode(salt_b64))).decrypt(wrapped[:12], wrapped[12:], b"dc-lock")


def _wrap(password, salt_b64, key):
    nonce = os.urandom(12)
    return base64.b64encode(nonce + _aes()(_kek(password, base64.b64decode(salt_b64))).encrypt(nonce, key, b"dc-lock")).decode()


def content_key(create=True, tier="free"):
    """The tier's content key, unwrapped with its password. Makes a new one (and a new key file) if there
    is none or the password has changed. Returns (key, is_new)."""
    if tier in _KEYS:
        return _KEYS[tier], False
    file, _ = TIERS[tier]
    password = _password(tier)
    try:
        lk = json.load(open(file, encoding="utf-8"))
        key = _unwrap(password, lk["salt"], lk["wrapped"])
        _KEYS[tier] = key
        return key, False
    except Exception:
        if not create:
            raise
    key, salt = os.urandom(32), base64.b64encode(os.urandom(16)).decode()
    lk = {"v": 1, "id": base64.b64encode(os.urandom(6)).decode(), "iter": ITERATIONS, "salt": salt,
          "wrapped": _wrap(password, salt, key)}
    with open(file, "w", encoding="utf-8") as f:
        json.dump(lk, f, indent=1)
        f.write("\n")
    _KEYS[tier] = key
    return key, True


def link_paid_to_free():
    """Let the paid password open the free files too: assets/lock-paid.json also carries the free key,
    wrapped with the paid password. Needs both passwords; only rewrites the file when the free key changed."""
    try:   # the paid key is only ever made on David's computer (its books can't be remade on GitHub)
        free, _ = content_key(tier="free")
        content_key(create=False, tier="paid")
    except Exception:
        return False
    file = TIERS["paid"][0]
    lk = json.load(open(file, encoding="utf-8"))
    free_id = json.load(open(TIERS["free"][0], encoding="utf-8"))["id"]
    try:
        if lk.get("free_id") == free_id and _unwrap(_password("paid"), lk["salt"], lk["free_wrapped"]) == free:
            return False
    except Exception:
        pass
    lk["free_id"], lk["free_wrapped"] = free_id, _wrap(_password("paid"), lk["salt"], free)
    with open(file, "w", encoding="utf-8") as f:
        json.dump(lk, f, indent=1)
        f.write("\n")
    return True


def rewrap(tier, new_password):
    """Change a tier's password but keep its content key, so its locked files still open (with the new password
    only: the new id makes every browser ask again). Needs the old password in the tier's secret variable."""
    key, _ = content_key(create=False, tier=tier)
    new_password = "".join(new_password.lower().split())
    file = TIERS[tier][0]
    lk = json.load(open(file, encoding="utf-8"))
    lk["salt"] = base64.b64encode(os.urandom(16)).decode()
    lk["wrapped"] = _wrap(new_password, lk["salt"], key)
    lk["id"] = base64.b64encode(os.urandom(6)).decode()
    for k in ("free_id", "free_wrapped"):
        lk.pop(k, None)
    with open(file, "w", encoding="utf-8") as f:
        json.dump(lk, f, indent=1)
        f.write("\n")


def lock_bytes(data, tier="free"):
    key, _ = content_key(tier=tier)
    nonce = hmac.new(key, data, hashlib.sha256).digest()[:12]
    return MAGIC + nonce + _aes()(key).encrypt(nonce, data, None)


def unlock_bytes(blob, tier="free"):
    key, _ = content_key(create=False, tier=tier)
    if not blob.startswith(MAGIC):
        raise ValueError("not a locked file")
    return _aes()(key).decrypt(blob[5:17], blob[17:], None)


def lock_file(src, dst, remove=True, tier="free"):
    data = open(src, "rb").read()
    out = lock_bytes(data, tier)
    if not os.path.exists(dst) or open(dst, "rb").read() != out:
        with open(dst, "wb") as f:
            f.write(out)
    if remove and os.path.abspath(src) != os.path.abspath(dst):
        os.remove(src)


if __name__ == "__main__":
    a = sys.argv[1:]
    tier = "free"
    if "--paid" in a:
        a.remove("--paid")
        tier = "paid"
    if len(a) == 3 and a[0] == "file":
        lock_file(a[1], a[2], tier=tier)
    elif len(a) == 1 and a[0] == "rewrap":   # new password in NEW_PASSWORD, old one in the tier's variable
        rewrap(tier, os.environ["NEW_PASSWORD"])
        print("rewrapped: now run with the new password so the paid key file carries the free key again")
    elif len(a) == 1 and a[0] == "check":
        print("new key" if content_key(tier=tier)[1] else "key ok")
    else:
        print(__doc__)
