# Changelog

## 0.6.0 — 2026-08-02
- Index rebuild is now atomic; a crashed build no longer leaves a half-written index
- `sparkfile serve` binds to localhost by default

## 0.5.2 — 2026-06-19
- Fix: notes with a BOM were silently skipped

## 0.5.1 — 2026-05-30
- Fix: `--out` now accepts a relative path
