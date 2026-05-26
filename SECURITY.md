# Security Policy

## Reporting a vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

Report them privately via one of these channels:

- **GitHub private disclosure** — use the [Report a vulnerability](../../security/advisories/new) button on the Security tab of this repository.
- **Email** — [sachnandmenon@gmail.com](mailto:sachnandmenon@gmail.com)

Include as much detail as you can: steps to reproduce, impact, and any suggested fix if you have one.

**Response time:** I aim to acknowledge reports within 72 hours and resolve confirmed vulnerabilities within 14 days. You will be credited in the fix unless you prefer to remain anonymous.

---

## Scope

This tool runs locally as a pre-commit hook or in CI. It reads files from the repository it is run against and calls `git`. It does not make network requests, handle untrusted input from external sources, or store credentials.

Realistic security concerns include:

- **Malicious repository content** causing unexpected behaviour when parsed (e.g. crafted YAML/JSON/TOML triggering a parser vulnerability in a dependency).
- **Path traversal** if the tool ever follows symlinks outside the repository root.
- **Dependency vulnerabilities** in `pyyaml` or other runtime dependencies.

Out of scope: issues in the user's own project that readme-drift happens to scan.
