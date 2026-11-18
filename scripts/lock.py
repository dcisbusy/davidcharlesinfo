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

Command line:  python scripts/lock.py file IN OUT     (needs SUBSCRIBER_PASSWORD in the environment)
"""
import base64, hashlib, hmac, json, os, sys

LOCK_FILE = "assets/lock.json"
MAGIC = b"DCLK1"
ITERATIONS = 250_000
_KEY = None


class NoPassword(Exception):
    pass


def _aes():
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    return AESGCM


def _kek(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS, 32)


def content_key(create=True):
    """The content key, unwrapped with SUBSCRIBER_PASSWORD. Makes a new one (and a new lock.json) if there
    is none or the password has changed. Returns (key, is_new)."""
    global _KEY
    if _KEY:
        return _KEY, False
    password = "".join(os.environ.get("SUBSCRIBER_PASSWORD", "").lower().split())   # as lock.js reads it
    if not password:
        raise NoPassword("SUBSCRIBER_PASSWORD isn't set, so nothing can be locked")
    AESGCM = _aes()
    try:
        lk = json.load(open(LOCK_FILE, encoding="utf-8"))
        wrapped = base64.b64decode(lk["wrapped"])
        key = AESGCM(_kek(password, base64.b64decode(lk["salt"]))).decrypt(wrapped[:12], wrapped[12:], b"dc-lock")
        _KEY = key
        return key, False
    except Exception:
        if not create:
            raise
    key, salt, nonce = os.urandom(32), os.urandom(16), os.urandom(12)
    wrapped = nonce + AESGCM(_kek(password, salt)).encrypt(nonce, key, b"dc-lock")
    with open(LOCK_FILE, "w", encoding="utf-8") as f:
        json.dump({"v": 1, "id": base64.b64encode(os.urandom(6)).decode(), "iter": ITERATIONS,
                   "salt": base64.b64encode(salt).decode(), "wrapped": base64.b64encode(wrapped).decode()}, f, indent=1)
        f.write("\n")
    _KEY = key
    return key, True


def lock_bytes(data):
    key, _ = content_key()
    nonce = hmac.new(key, data, hashlib.sha256).digest()[:12]
    return MAGIC + nonce + _aes()(key).encrypt(nonce, data, None)


def unlock_bytes(blob):
    key, _ = content_key(create=False)
    if not blob.startswith(MAGIC):
        raise ValueError("not a locked file")
    return _aes()(key).decrypt(blob[5:17], blob[17:], None)


def lock_file(src, dst, remove=True):
    data = open(src, "rb").read()
    out = lock_bytes(data)
    if not os.path.exists(dst) or open(dst, "rb").read() != out:
        with open(dst, "wb") as f:
            f.write(out)
    if remove and os.path.abspath(src) != os.path.abspath(dst):
        os.remove(src)


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "file":
        lock_file(sys.argv[2], sys.argv[3])
    elif len(sys.argv) == 2 and sys.argv[1] == "check":
        print("new key" if content_key()[1] else "key ok")
    else:
        print(__doc__)
