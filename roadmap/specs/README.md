---
title: Spec format
description: How specs are written — requirements, design, and tasks per feature.
---

<!-- foundry-seed: specs-readme v1 -->

# Specs

A feature's spec is `roadmap/specs/<feature>/` with three files:

- `requirements.md` — user stories with EARS acceptance criteria.
- `design.md` — decisions, architecture, rationale.
- `tasks.md` — the implementation plan, ordered in waves.

## Status header

Every spec file opens with a status header that points to the board:

> **Status:** Ready (2026-01-15) — tracked on the [board](../ROADMAP.md).

When a spec and the board disagree, the board wins.

Use the board's status taxonomy.

## EARS acceptance criteria

Write each criterion in EARS form — `WHEN <trigger>, THE SYSTEM SHALL <response>` —
one testable behavior per criterion:

> AC-1.1 WHEN an import completes, THE SYSTEM SHALL report the count of rows
> imported and rows rejected.

## Tasks in waves

Order `tasks.md` as waves: tasks within a wave are independent and can land in
parallel; each wave builds on the last. Every task names the gate that proves it.

## Review before approval

Dispatch the `spec-reviewer` agent on the changed spec files and apply its
findings before presenting `design.md` for approval.
