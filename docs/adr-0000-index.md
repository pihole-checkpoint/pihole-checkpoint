# ADR-0000: Architecture Decision Records Index

This document serves as the index for all Architecture Decision Records (ADRs) in the Pi-hole Checkpoint project.

---

## ADR Status Definitions

| Status | Description |
|--------|-------------|
| **Proposed** | Under discussion, not yet accepted |
| **Accepted** | Decision has been accepted but not yet implemented |
| **Implemented** | Decision has been accepted and fully implemented |
| **Deprecated** | Decision is no longer relevant or has been superseded |
| **Superseded** | Replaced by a newer ADR |

---

## ADR Index

| ADR | Title | Status | Date |
|-----|-------|--------|------|
| [ADR-001](adr-001-pihole-backup-architecture.md) | Pi-hole v6 Backup Application Architecture | Accepted | 2026-01-18 |
| [ADR-002](adr-002-offline-static-assets.md) | Offline Static Assets (Remove CDN Dependencies) | Accepted | 2026-01-18 |
| [ADR-003](adr-003-single-container-architecture.md) | Single Container Architecture | Implemented | 2026-01-18 |
| [ADR-004](adr-004-manual-backup-ui-refresh.md) | Manual Backup Trigger with UI Refresh on Completion | Proposed | 2026-01-18 |
| [ADR-005](adr-005-testing-strategy.md) | Testing Strategy and Workflow | Proposed | 2026-01-18 |
| [ADR-006](adr-006-github-docker-publish.md) | GitHub Actions Docker Image Publishing | Proposed | 2026-01-18 |
| [ADR-007](adr-007-github-test-workflow.md) | GitHub Actions Test Workflow Integration | Proposed | 2026-01-18 |

---

## Summary by Status

### Implemented (1)
- ADR-003: Single Container Architecture

### Accepted (2)
- ADR-001: Pi-hole v6 Backup Application Architecture
- ADR-002: Offline Static Assets (Remove CDN Dependencies)

### Proposed (4)
- ADR-004: Manual Backup Trigger with UI Refresh on Completion
- ADR-005: Testing Strategy and Workflow
- ADR-006: GitHub Actions Docker Image Publishing
- ADR-007: GitHub Actions Test Workflow Integration

---

## Creating New ADRs

When creating a new ADR:
1. Use the next sequential number (e.g., `adr-008-*.md`)
2. Follow the established format with Status, Date, and Deciders
3. Update this index file with the new entry
