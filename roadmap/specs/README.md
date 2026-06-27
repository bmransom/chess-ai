---
title: Spec format
description: How specs are written — requirements, design, and tasks per feature.
---

<!-- foundry-seed: specs-readme v2 -->

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

## Metrics

`design.md` SHOULD name the metrics that tell whether the feature works — the signals
to watch and how each is measured — or state **N/A** with a one-line reason. Define them
at spec time so success is testable, not asserted; N/A is an explicit answer, not silence.

## Diagrams

`design.md` SHOULD include a Mermaid architecture or component diagram, and a class
diagram where the component has object-oriented or typed structure — a shell-only
component uses architecture plus data-flow, not a class diagram. Diagrams are reviewed
twice: by `spec-review` at design time (accuracy and glossary vocabulary) and by
`code-review`'s docs-sync at build time (the diagram matches the shipped code; drift is
a finding).

## Review before approval

Use `spec-review` in fresh context on the changed spec files and apply its findings
before presenting `design.md` for approval.
