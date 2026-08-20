# 0019. bcrypt direct, not through passlib

## Context
Initial code used `passlib[bcrypt]` for password hashing. Modern bcrypt
(4.0+) removed the `bcrypt.__about__` module. Passlib's internal
"wrap bug detection" routine reads that attribute, and when it fails
passlib retries by hashing a long test string, which triggers bcrypt's
72-byte password limit and throws:

    ValueError: password cannot be longer than 72 bytes ...

User hit this on register even with an 8-character password.

## Decision
Drop `passlib[bcrypt]`. Use the `bcrypt` library directly with two small
helpers:

    def _hash_password(pw):
        return bcrypt.hashpw(pw.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")

    def _verify_password(pw, hashed):
        try:
            return bcrypt.checkpw(pw.encode("utf-8")[:72], hashed.encode("utf-8"))
        except (ValueError, TypeError):
            return False

Truncate to 72 bytes defensively so long UTF-8 passwords do not blow up.

## Why
- Passlib was one indirection too many; the bcrypt library alone gives us
  exactly what we need in six lines.
- One fewer package in the dependency tree.
- The bcrypt 72-byte cap is a real bcrypt property. Trimming defensively
  matches the industry norm and prevents error paths that are impossible
  for the user to fix.

## Cost accepted
- No pluggable hash algorithms via passlib. If we later want argon2 we
  swap in `argon2-cffi` directly, and add a version prefix to the stored
  hash so old bcrypt hashes still verify. Deferred until it matters.
