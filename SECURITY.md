# Security Policy

## What Sightware is (and is not)

Sightware is a **local-only** desktop application. By design:

- It talks **only** to your own Riot client session on `127.0.0.1` — the same
  local API the game's own UI uses. It never connects to remote Riot
  endpoints, never sends your data anywhere, and never runs a server.
- The crosshair overlay and display tools (ChromaDesk) **never read from or
  inject into game processes**. They are separate top-level windows and
  system-level display calls, nothing more.
- Everything (settings, cache, logs) stays on your disk, under your user.

## Supported versions

Only the latest tagged release (and `main`) is supported. The app is in
active development; there are no LTS branches.

## Reporting a vulnerability

If you find a security-relevant issue — e.g. something that makes Sightware
talk to a remote host, expose credentials, write outside its own data
directories, or execute code it shouldn't:

1. **Do not open a public issue** for anything that could be exploited.
2. Use GitHub's ["Report a vulnerability"](https://github.com/ayoItzzseb/Sightware/security/advisories/new)
   (private security advisory) so the details stay confidential.
3. Include: affected version, steps to reproduce, and what you believe the
   impact is.

You'll get a response within a few days. Fixes are released promptly and
credited in the changelog unless you'd rather stay anonymous.

## Scope notes

- Reports about Riot Games' own client, servers, or API are out of scope —
  those belong to [Riot's HackerOne program](https://hackerone.com/riot).
- Sightware is an independent project and is **not affiliated with, endorsed
  by, or sponsored by Riot Games**. It is a read-only companion tool that
  uses your own local client session.
