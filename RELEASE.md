# Cortex Engine — Release Process

This document describes how to cut a release for **Cortex Engine**:

- update versions and docs
- run quality checks
- tag and push
- publish release notes (GitHub Releases)

The goal is consistent, repeatable releases with strong safety defaults.

---

## 1) Versioning Policy

We follow a SemVer-inspired scheme:

- **PATCH (x.y.Z)**: bug fixes, security fixes, small UX polish
- **MINOR (x.Y.z)**: new tools/capabilities, non-breaking enhancements
- **MAJOR (X.y.z)**: breaking changes (plan schema/config/tool contracts)

Pre-1.0 guidance:

- Prefer keeping plan/config/tool contracts stable.
- If breaking changes are unavoidable, bump **MINOR** and document migrations clearly.

---

## 2) Pre-Release Checklist (Required)

Run these **before tagging**:

### 2.1 Tests

```bash
pytest -q
```

### 2.2 CLI sanity checks

```bash
cortex tools list
cortex permissions show
cortex run --dry-run "list current folder"
cortex run --execute "list current folder"
```

### 2.3 Secure mode sanity checks

```bash
cortex secure status
# (optional) enable/disable during testing
# cortex secure enable
# cortex secure disable
```

### 2.4 Browser tool sanity checks (if present)

```bash
cortex run --execute "open example.com"
cortex run --execute "fetch https://example.com"
```
