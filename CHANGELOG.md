# Changelog

All notable changes to **Cortex Engine** will be documented in this file.

This project follows a SemVer-inspired versioning scheme:
- **PATCH**: bug/security fixes, small UX polish
- **MINOR**: new tools/capabilities, non-breaking enhancements
- **MAJOR**: breaking changes (plan schema/config/tool contracts)

---

## [v0.1.10] — Browser Tools (SAFE) + Public Web Support
**Release date:** 2026-03-05

### Added
- **SAFE web browsing tools**
  - `browser.fetch` — fetch URL content with strict safety controls (timeout, max bytes, content-type allowlist, redirect limit).
  - `browser.open` — open a URL in the user’s browser (SAFE; still blocked for localhost/private IP ranges).
- **URL normalization**
  - Support for inputs like `youtube.com` → normalized to `https://youtube.com`.

### Changed
- **Browser domain policy**
  - Moved toward a production-friendly model: allow public domains by default (while still blocking private/internal targets).
- **Planner behavior improvements**
  - Better mapping for “open <site>” style prompts to `browser.open` (and away from HTML fetching when not needed).

### Security
- **Network protection**
  - Blocks `localhost` and hosts resolving to private/internal IP ranges.
- **Response protection (browser.fetch)**
  - Enforced limits: `max_bytes`, `timeout_seconds`, `allowed_content_types`, `max_redirects`.

---

## [v0.1.9] — CLI UX Improvements
**Release date:** 2026-03-05

### Added
- **Secure mode banner** on `cortex run` when secure mode is enabled.
- **Risk color coding** for plan steps:
  - SAFE (green), MODIFY (yellow), CRITICAL (red)
- **Execution Summary**
  - Steps executed, succeeded, failed, final status.
- **Improved results rendering**
  - Cleaner tool output formatting.
  - Special formatting for `filesystem.list` to print clean file/dir names.

### Changed
- **Plan rendering**
  - Plan steps shown in a structured Rich table.
  - Params shown in readable pretty format.

---

## [v0.1.8.1] — Filesystem Hardening + Security Tests
**Release date:** 2026-02-27

### Added
- Windows system path denylist protections.
- Drive root protection (e.g., blocking `C:\`, `D:\`).
- Protected runtime targets (e.g., `config.yaml`, `logs/`) from modification/deletion.
- File size protection (read/write limits) to prevent memory abuse.
- Additional security tests.

### Fixed
- Improved denylist and sandbox behavior edge-cases.

---

## [v0.1.8] — Filesystem Tools + Approval Flow
**Release date:** 2026-02-26

### Added
- Filesystem tool suite:
  - `filesystem.list` (SAFE)
  - `filesystem.search` (SAFE)
  - `filesystem.read_text` (SAFE)
  - `filesystem.write_text` (MODIFY)
  - `filesystem.move` (MODIFY) *(if included in your build)*
  - `filesystem.delete` (CRITICAL)
- Execution approval flow for non-SAFE operations.

### Security
- Allowed path enforcement via sandbox guard.

---

## [v0.1.7] — Secure Mode (Password Protected)
**Release date:** 2026-02-26

### Added
- Secure mode controls:
  - `cortex secure enable`
  - `cortex secure disable`
  - `cortex secure status`
  - `cortex secure allow-path`
  - `cortex secure clear-paths`
- Password hashing + verification for secure mode.
- Secure mode enforcement: **SAFE tools only** when enabled.
- Per-user allowed paths for secure mode.

---

## [v0.1.6] — Risk Tiers + Approval Gates
**Release date:** 2026-02-22

### Added
- Tool risk tiers:
  - SAFE / MODIFY / CRITICAL
- Approval gates for non-SAFE tools.

---

## [v0.1.5] — Agent Runtime Loop
**Release date:** 2026-02-21

### Added
- Agent runtime loop:
  - session creation
  - planner call
  - plan validation
  - execution orchestration
  - result aggregation

---

## [v0.1.4] — Plan Schema + Validation
**Release date:** 2026-02-21

### Added
- Strict plan schema (Plan → Steps)
- Plan validation system in policy engine.

---

## [v0.1.3] — LLM Planner Integration (Primary + Fallback)
**Release date:** 2026-02-20

### Added
- LLM planning layer with model failover:
  - Primary: Qwen2.5
  - Fallback: Phi-3.5 mini
- Safe fallback behavior when planning fails.

---

## [v0.1.2] — Configuration System
**Release date:** 2026-02-13

### Added
- Config loader/writer
- Structured config fields for:
  - secure mode
  - allowed paths
  - LLM settings
  - GPU settings

---

## [v0.1.1] — Project Structure Initialized
**Release date:** 2026-02-13

### Added
- Initial repository structure:
  - CLI entrypoint
  - tools registry
  - runtime modules
  - security modules
  - tests skeleton

---

## [v0.1.0] — Initial Architecture Lock
**Release date:** 2026-02-11

### Added
- Cortex Engine architecture defined:
  - CLI layer
  - agent runtime
  - planner
  - tools registry
  - security + policy engine
  - audit logging

---

### Notes
- Dates reflect the implementation timeline across Phase 1.x.
- If you want exact dates per tag, you can update release dates after tagging.