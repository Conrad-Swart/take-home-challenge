# 0004. Email + password auth for the MVP, not Entra ID

## Context
Ideal end state: SSO via Entra so the team signs in with work accounts and IT
controls access. Global rules require a standalone Entra app registration
per project.

## Decision
Ship the MVP with email + password (bcrypt-hashed, signed httponly session
cookie). Name Entra as priority 1 in WRITEUP section 3.

## Why
- Creating an Entra app registration needs tenant admin clicks, redirect URIs
  agreed with the user, and MSAL wiring. All of that in a 4-6 hour window
  would crowd out the actual product.
- Email + password with bcrypt and signed cookies is not "wrong" — it's
  well-understood, and it demonstrates the auth model in a form the reviewer
  can create an account against in 10 seconds.
- The Entra swap is a routes-level replacement, not an architecture change.
  The rest of the app does not care which auth backend supplied the user.

## Cost accepted
No SSO, no MFA, no password reset. Passwords are stored bcrypt-hashed but the
account model is minimal (email + hash + created_at, no email verification,
no lockout). Fine for a scored take-home, not for production.
