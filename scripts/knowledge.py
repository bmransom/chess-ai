#!/usr/bin/env python3
# foundry-template: knowledge v1
"""knowledge — list and lint the curated knowledge concepts by type + description.

Dev tooling for agents/humans navigating this repo's knowledge base. Not part of
any product CLI. Zero runtime dependencies (stdlib only).

Config: knowledge/knowledge-config.json (relative to repo root). Run without it to
see the bootstrap instructions.
"""

import argparse
import glob
import json
import os
import re
import shutil
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(REPO_ROOT, "knowledge", "knowledge-config.json")


def load_config():
    """Load knowledge/knowledge-config.json. Exits with a clear message if missing."""
    if not os.path.exists(CONFIG_PATH):
        sys.exit(
            f"knowledge: config not found at {CONFIG_PATH}\n"
            "Create it from the seed: cp plugins/foundry/templates/seeds/knowledge/knowledge-config.json knowledge/knowledge-config.json\n"
            "Then edit it for this repo."
        )
    with open(CONFIG_PATH, encoding="utf-8") as handle:
        return json.load(handle)


def parse_frontmatter(text):
    """Return (meta, ok). Parse a minimal YAML frontmatter block: a leading
    '---' line, 'key: value' lines, a closing '---'. Values are strings;
    a trailing ' #' comment and surrounding quotes are stripped. ok is False
    when there is no opening '---' or no closing '---'."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, False
    meta = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return meta, True
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in line:
            continue
        key, _, val = line.partition(":")
        # Strip a trailing ' #' comment only from unquoted values, so a quoted
        # value that legitimately contains ' #' (e.g. "tracked by #1") survives.
        if not val.strip().startswith(('"', "'")) and " #" in val:
            val = val.split(" #", 1)[0]
        meta[key.strip()] = val.strip().strip('"').strip("'")
    return {}, False


def strict_yaml_errors(text):
    """Frontmatter our lenient parser accepts but strict YAML (the VitePress
    site build) rejects: an unquoted scalar containing ': ' parses as a nested
    mapping and breaks the build. Return human-readable errors so `check` (the
    cheap gate) catches what the heavyweight site build would."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return []
    errors = []
    for line in lines[1:]:
        if line.strip() == "---":
            break
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        value = value.strip()
        if not value.startswith(('"', "'")) and ": " in value:
            errors.append(
                f"value for '{key.strip()}' contains ': ' but is unquoted "
                "(strict YAML / VitePress rejects it — wrap the value in quotes)"
            )
    return errors


def infer_crate(relpath):
    parts = relpath.split("/")
    if len(parts) >= 2 and parts[0] == "crates":
        return parts[1]
    return None


def discover(root, config):
    """Return curated concepts as dicts sorted by path. Each dict has public keys
    (path, title, description, type, crate, lifecycle) plus internal _ok/_meta."""
    concept_globs = config["concept_globs"]
    exclude_substrings = config.get("exclude_substrings", [])
    exclude_prefixes = tuple(config.get("exclude_prefixes", []))

    seen = {}
    for pattern in concept_globs:
        for abspath in glob.glob(os.path.join(root, pattern), recursive=True):
            relpath = os.path.relpath(abspath, root).replace(os.sep, "/")
            if any(s in "/" + relpath for s in exclude_substrings):
                continue
            if exclude_prefixes and relpath.startswith(exclude_prefixes):
                continue
            if relpath in seen:
                continue
            with open(abspath, encoding="utf-8") as handle:
                raw = handle.read()
            meta, ok = parse_frontmatter(raw)
            seen[relpath] = {
                "path": relpath,
                "title": meta.get("title", ""),
                "description": meta.get("description", ""),
                "type": meta.get("type", ""),
                "crate": meta.get("crate") or infer_crate(relpath),
                "lifecycle": meta.get("lifecycle", "current") if ok else "",
                "_ok": ok,
                "_meta": meta,
                "_strict": strict_yaml_errors(raw),
            }
    return [seen[k] for k in sorted(seen)]


def validate(concept, config):
    """Return a list of human-readable errors for a discovered concept ([] = clean)."""
    types = config["types"]
    lifecycles = config.get("lifecycles", ["current", "superseded", "historical"])
    required = config.get("required_fields", ["title", "description", "type"])

    if not concept["_ok"]:
        return ["missing frontmatter block"]
    meta = concept["_meta"]
    errors = []
    for field in required:
        if not meta.get(field):
            errors.append(f"missing required field '{field}'")
    if meta.get("type") and meta["type"] not in types:
        errors.append(f"invalid type '{meta['type']}' (expected one of {types})")
    if meta.get("lifecycle") and meta["lifecycle"] not in lifecycles:
        errors.append(
            f"invalid lifecycle '{meta['lifecycle']}' (expected one of {lifecycles})"
        )
    errors.extend(concept.get("_strict", []))
    return errors


def filter_concepts(concepts, type_name, crate, lifecycle):
    result = concepts
    if type_name:
        result = [c for c in result if c["type"] == type_name]
    if crate:
        result = [c for c in result if c["crate"] == crate]
    if lifecycle:
        result = [c for c in result if c["lifecycle"] == lifecycle]
    return result


def public_view(concept):
    return {
        k: concept[k]
        for k in ["path", "title", "description", "type", "crate", "lifecycle"]
    }


def format_list(concepts, config):
    """Render concepts grouped by type, one line each, as a string."""
    types = config["types"]
    out = []
    for type_name in types:
        group = [c for c in concepts if c["type"] == type_name]
        if not group:
            continue
        out.append(type_name.upper() + (" (dated)" if type_name == "decision" else ""))
        for concept in group:
            bits = []
            if concept["crate"]:
                bits.append(concept["crate"])
            if type_name == "decision" and concept["_meta"].get("updated"):
                bits.append(concept["_meta"]["updated"])
            tag = f" [{' · '.join(bits)}]" if bits else ""
            out.append(f"  {concept['path']}{tag}  {concept['description']}")
    return "\n".join(out)


def curated(root, config):
    reserved = set(config.get("reserved_files", []))
    return [c for c in discover(root, config) if c["path"] not in reserved]


def _inline_code_spans(text):
    """Single-backtick spans, skipping fenced ``` code blocks (commands, not refs)."""
    spans = []
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            spans.extend(re.findall(r"`([^`]+)`", line))
    return spans


def check_skill_refs(root, config):
    """Reference-integrity for .claude/skills/code/SKILL.md: every repo path it names must
    resolve. Literal paths must exist; glob tokens must match >=1 file; '<...>'/'{...}' shapes
    are skipped. Returns a list of human-readable errors ([] = clean; [] when the skill is absent)."""
    skill_path = os.path.join(root, ".claude", "skills", "code", "SKILL.md")
    if not os.path.exists(skill_path):
        return []
    with open(skill_path, encoding="utf-8") as handle:
        raw = handle.read()
    meta, ok = parse_frontmatter(raw)
    if not ok:
        return [".claude/skills/code/SKILL.md: missing frontmatter block"]
    errors = []
    if meta.get("name") != "code":
        errors.append(".claude/skills/code/SKILL.md: frontmatter 'name' must be 'code'")
    if not meta.get("description"):
        errors.append(".claude/skills/code/SKILL.md: missing 'description'")
    skill_ref_prefixes = tuple(config.get("skill_ref_prefixes", []))
    if not skill_ref_prefixes:
        return errors
    # Split each span on whitespace so an embedded path in a compound command span
    # (e.g. `python3 scripts/knowledge.py check`) is still checked, not just bare-path spans.
    for token in (part for span in _inline_code_spans(raw) for part in span.split()):
        if not token.startswith(skill_ref_prefixes):
            continue
        if any(ch in token for ch in "<>{}"):
            continue  # a reference shape, not a literal path
        if "*" in token:
            if not glob.glob(os.path.join(root, token), recursive=True):
                errors.append(
                    f".claude/skills/code/SKILL.md: glob '{token}' matches no file"
                )
        elif not os.path.exists(os.path.join(root, token.rstrip("/"))):
            errors.append(
                f".claude/skills/code/SKILL.md: reference '{token}' does not exist"
            )
    return errors


def site_url(path):
    """Map a repo concept path to its VitePress URL (crate concepts are synced under knowledge/)."""
    trimmed = path[:-3] if path.endswith(".md") else path
    if trimmed.startswith("knowledge/"):
        return "/" + trimmed[len("knowledge/") :]
    if trimmed.startswith("crates/") and "/knowledge/" in trimmed:
        crate = trimmed.split("/")[1]
        rest = trimmed.split("/knowledge/", 1)[1]
        return f"/crates/{crate}/{rest}"
    return "/" + trimmed


def build_index(concepts, config):
    """OKF directory listing (§6): no frontmatter; a section per type;
    '* [Title](/url) - description' entries. Doubles as the VitePress home."""
    types = config["types"]
    title = config.get("index_title", "Knowledge")
    out = [f"# {title}", ""]
    for type_name in types:
        group = [c for c in concepts if c["type"] == type_name]
        if not group:
            continue
        out.append(f"## {type_name.capitalize()}")
        out.append("")
        for concept in group:
            label = concept["title"] or concept["path"]
            link = site_url(concept["path"])
            desc = concept["description"]
            entry = f"* [{label}]({link}) - {desc}" if desc else f"* [{label}]({link})"
            out.append(entry)
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def check_index_fresh(root, config):
    """The committed knowledge/index.md must match a fresh `index` generation."""
    expected = build_index(curated(root, config), config)
    index_abs = os.path.join(root, "knowledge", "index.md")
    actual = ""
    if os.path.exists(index_abs):
        with open(index_abs, encoding="utf-8") as handle:
            actual = handle.read()
    if actual != expected:
        return [
            "knowledge/index.md is stale — regenerate with "
            "`python3 scripts/knowledge.py index`"
        ]
    return []


def build_sidebar(concepts, config):
    """VitePress sidebar: one collapsible section per type, items by title."""
    types = config["types"]
    sidebar = []
    for type_name in types:
        items = [
            {"text": c["title"] or c["path"], "link": site_url(c["path"])}
            for c in concepts
            if c["type"] == type_name
        ]
        if items:
            sidebar.append(
                {
                    "text": type_name.capitalize(),
                    "collapsed": type_name == "decision",
                    "items": items,
                }
            )
    return sidebar


def sync_site(root, config):
    """Copy crate concepts into knowledge/crates/<crate>/... so VitePress can render them.
    Returns the count staged. The staged tree is gitignored and rebuilt."""
    count = 0
    for concept in curated(root, config):
        path = concept["path"]
        if path.startswith("crates/") and "/knowledge/" in path:
            crate = path.split("/")[1]
            rest = path.split("/knowledge/", 1)[1]
            dest = os.path.join(root, "knowledge", "crates", crate, rest)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copyfile(os.path.join(root, path), dest)
            count += 1
    return count


def run_check(root, config):
    """Return (exit_code, report_text). Non-zero when any curated concept is invalid."""
    concepts = curated(root, config)
    lines = []
    for concept in concepts:
        for error in validate(concept, config):
            lines.append(f"{concept['path']}: {error}")
    lines.extend(check_skill_refs(root, config))
    lines.extend(check_index_fresh(root, config))
    if lines:
        return 1, "\n".join(lines) + "\nknowledge check: FAILED"
    return 0, f"knowledge check: OK ({len(concepts)} concepts)"


def parse_headings(text):
    """Return list of (level, text, lineno) for every ATX heading in text.
    lineno is 1-based. Only ATX headings (# ... lines) are matched; setext
    headings and lines inside fenced code blocks are ignored."""
    headings = []
    in_fence = False
    for lineno, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = re.match(r"^(#{1,6})\s+(.*)", line)
        if match:
            level = len(match.group(1))
            heading_text = match.group(2).strip()
            headings.append((level, heading_text, lineno))
    return headings


def cmd_index(root, config, output=None):
    """Generate the OKF listing and write knowledge/index.md (or --output)."""
    content = build_index(curated(root, config), config)
    dest = output or os.path.join(root, "knowledge", "index.md")
    with open(dest, "w", encoding="utf-8") as handle:
        handle.write(content)
    print(f"knowledge index: wrote {os.path.relpath(dest, root)}")
    return 0


def cmd_outline(concept_path, root):
    """Print the heading tree (level, text, line number) for a concept."""
    abspath = (
        os.path.join(root, concept_path)
        if not os.path.isabs(concept_path)
        else concept_path
    )
    if not os.path.exists(abspath):
        print(f"knowledge outline: file not found: {concept_path}", file=sys.stderr)
        return 1
    with open(abspath, encoding="utf-8") as handle:
        text = handle.read()
    headings = parse_headings(text)
    if not headings:
        print(f"knowledge outline: no headings found in {concept_path}")
        return 0
    for level, heading_text, lineno in headings:
        indent = "  " * (level - 1)
        print(f"{lineno:4d}  {indent}{'#' * level} {heading_text}")
    return 0


def cmd_section(concept_path, heading_query, root):
    """Print the section matching heading_query (case-insensitive substring)."""
    abspath = (
        os.path.join(root, concept_path)
        if not os.path.isabs(concept_path)
        else concept_path
    )
    if not os.path.exists(abspath):
        print(f"knowledge section: file not found: {concept_path}", file=sys.stderr)
        return 1
    with open(abspath, encoding="utf-8") as handle:
        text = handle.read()
    lines = text.splitlines(keepends=True)
    headings = parse_headings(text)
    if not headings:
        print(
            f"knowledge section: no headings found in {concept_path}", file=sys.stderr
        )
        return 1

    query_lower = heading_query.lower()
    match_index = next(
        (
            i
            for i, (_, heading_text, _) in enumerate(headings)
            if query_lower in heading_text.lower()
        ),
        None,
    )
    if match_index is None:
        available = "\n".join(f"  {heading_text}" for _, heading_text, _ in headings)
        print(
            f"knowledge section: no heading contains '{heading_query}'. Available headings:\n{available}",
            file=sys.stderr,
        )
        return 1

    start_level, _, start_lineno = headings[match_index]
    # Find end: next heading of equal-or-higher level (lower number = higher level)
    end_lineno = len(lines) + 1
    for level, _, lineno in headings[match_index + 1 :]:
        if level <= start_level:
            end_lineno = lineno
            break

    section_lines = lines[start_lineno - 1 : end_lineno - 1]
    # Strip trailing blank lines for clean output
    while section_lines and section_lines[-1].strip() == "":
        section_lines.pop()
    print("".join(section_lines), end="")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="knowledge", description=__doc__.splitlines()[0]
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="list curated concepts grouped by type")
    p_list.add_argument("--type", dest="type_name")
    p_list.add_argument("--crate")
    p_list.add_argument("--lifecycle")
    p_list.add_argument("--json", action="store_true", help="machine-readable array")
    p_list.add_argument("--paths", action="store_true", help="bare paths only")

    sub.add_parser("check", help="lint frontmatter; non-zero exit on any error")

    p_sidebar = sub.add_parser("sidebar", help="emit the VitePress sidebar JSON")
    p_sidebar.add_argument("-o", "--output", help="write here instead of stdout")
    sub.add_parser("sync", help="stage crate concepts into the site tree")

    p_index = sub.add_parser(
        "index", help="generate the OKF listing (knowledge/index.md)"
    )
    p_index.add_argument(
        "-o", "--output", help="write here instead of knowledge/index.md"
    )

    p_outline = sub.add_parser(
        "outline", help="print the heading tree of a concept file"
    )
    p_outline.add_argument(
        "concept_path", help="path to the markdown file (repo-relative or absolute)"
    )

    p_section = sub.add_parser("section", help="print one section of a concept file")
    p_section.add_argument(
        "concept_path", help="path to the markdown file (repo-relative or absolute)"
    )
    p_section.add_argument(
        "heading", help="substring to match against heading text (case-insensitive)"
    )

    args = parser.parse_args(argv)

    if args.command == "outline":
        return cmd_outline(args.concept_path, REPO_ROOT)

    if args.command == "section":
        return cmd_section(args.concept_path, args.heading, REPO_ROOT)

    # Commands below require config.
    config = load_config()
    types = config["types"]
    lifecycles = config.get("lifecycles", ["current", "superseded", "historical"])

    if args.command == "check":
        code, report = run_check(REPO_ROOT, config)
        stream = sys.stderr if code else sys.stdout
        print(report, file=stream)
        return code

    if args.command == "sidebar":
        payload = json.dumps(
            build_sidebar(curated(REPO_ROOT, config), config), indent=2
        )
        if args.output:
            with open(args.output, "w", encoding="utf-8") as handle:
                handle.write(payload + "\n")
        else:
            print(payload)
        return 0

    if args.command == "index":
        return cmd_index(REPO_ROOT, config, args.output)

    if args.command == "sync":
        print(f"knowledge sync: staged {sync_site(REPO_ROOT, config)} crate concepts")
        return 0

    # args.command == "list"
    # Validate --type / --lifecycle after loading config so choices are accurate.
    type_name = getattr(args, "type_name", None)
    lifecycle = getattr(args, "lifecycle", None)
    if type_name and type_name not in types:
        parser.error(
            f"argument --type: invalid choice: '{type_name}' (choose from {types})"
        )
    if lifecycle and lifecycle not in lifecycles:
        parser.error(
            f"argument --lifecycle: invalid choice: '{lifecycle}' (choose from {lifecycles})"
        )
    concepts = filter_concepts(
        curated(REPO_ROOT, config), type_name, getattr(args, "crate", None), lifecycle
    )
    if getattr(args, "json", False):
        print(json.dumps([public_view(c) for c in concepts], indent=2))
    elif getattr(args, "paths", False):
        print("\n".join(c["path"] for c in concepts))
    else:
        print(format_list(concepts, config))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
