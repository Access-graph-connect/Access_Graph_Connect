---
title: AccessGraph Connect
---

# AccessGraph Connect

A read-only SaaS access-discovery and connector-operations platform.

It connects to third-party SaaS services (GitHub, Slack), imports identities
and access metadata, normalizes differences between providers, keeps the
inventory synchronized, and makes connector failures visible.

**Out of scope by design:** AI security agents, risk scoring, graph
reasoning, approval workflows, revocation, suspension, and automated
remediation.

## Links

- [Source code](https://github.com/Karan2807/Access_Graph_Connect)
- [Architecture](./architecture.md)
- [Design decisions](./design-decisions.md)

## Status

| Phase | Focus | State |
| --- | --- | --- |
| 1 | Architecture, environment, schema | Done |
| 2 | GitHub connector end-to-end | Done |
| 3 | Sync engine and reconciliation | Next |
| 4 | Slack connector and webhooks | Pending |
| 5 | Credential lifecycle and failure handling | Pending |
| 6 | Operations dashboard | Pending |
| 7 | Hardening, documentation, demo | Pending |
