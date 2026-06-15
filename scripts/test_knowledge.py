# foundry-template: test-knowledge v1
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import knowledge  # noqa: E402

# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------

MINIMAL_CONFIG = {
    "types": ["reference", "architecture", "guide", "decision"],
    "lifecycles": ["current", "superseded", "historical"],
    "required_fields": ["title", "description", "type"],
    "concept_globs": ["knowledge/**/*.md", "crates/*/knowledge/**/*.md"],
    "exclude_substrings": ["/node_modules/", "/.vitepress/"],
    "exclude_prefixes": ["knowledge/crates/"],
    "reserved_files": ["knowledge/index.md", "knowledge/log.md"],
    "skill_ref_prefixes": [
        "scripts/",
        "knowledge/",
        "crates/",
        "roadmap/specs/",
        ".claude/",
    ],
}


def _make_tree(root, files):
    for relpath, content in files.items():
        path = os.path.join(root, relpath)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)


def _tree_with_config(root, files, config=None):
    """Write files + a knowledge-config.json, then a fresh index.md so run_check's
    index-freshness assertion is satisfied (a real repo always has a current index)."""
    cfg = config if config is not None else MINIMAL_CONFIG
    _make_tree(
        root,
        {
            "knowledge/knowledge-config.json": json.dumps(cfg),
            **files,
        },
    )
    index_path = os.path.join(root, "knowledge", "index.md")
    with open(index_path, "w", encoding="utf-8") as handle:
        handle.write(knowledge.build_index(knowledge.curated(root, cfg), cfg))


# ---------------------------------------------------------------------------
# parse_frontmatter
# ---------------------------------------------------------------------------


class ParseFrontmatterTests(unittest.TestCase):
    def test_parses_simple_block(self):
        text = "---\ntitle: Glossary\ntype: reference\n---\n# Body\n"
        meta, ok = knowledge.parse_frontmatter(text)
        self.assertTrue(ok)
        self.assertEqual(meta["title"], "Glossary")
        self.assertEqual(meta["type"], "reference")

    def test_strips_inline_comment_and_quotes(self):
        text = '---\nlifecycle: current   # current | superseded\ntitle: "A B"\n---\n'
        meta, ok = knowledge.parse_frontmatter(text)
        self.assertTrue(ok)
        self.assertEqual(meta["lifecycle"], "current")
        self.assertEqual(meta["title"], "A B")

    def test_no_frontmatter_returns_false(self):
        meta, ok = knowledge.parse_frontmatter("# Just a heading\n")
        self.assertFalse(ok)
        self.assertEqual(meta, {})

    def test_unterminated_block_returns_false(self):
        meta, ok = knowledge.parse_frontmatter("---\ntitle: X\n# no close\n")
        self.assertFalse(ok)

    def test_quoted_value_with_hash_is_preserved(self):
        text = '---\ntitle: "tracked by #1"\n---\n'
        meta, ok = knowledge.parse_frontmatter(text)
        self.assertEqual(meta["title"], "tracked by #1")


# ---------------------------------------------------------------------------
# discover
# ---------------------------------------------------------------------------


class DiscoverTests(unittest.TestCase):
    def test_discovers_and_infers_crate(self):
        with tempfile.TemporaryDirectory() as root:
            _tree_with_config(
                root,
                {
                    "knowledge/glossary.md": "---\ntitle: G\ndescription: d\ntype: reference\n---\n",
                    "crates/lp/knowledge/architecture.md": "---\ntitle: LP\ndescription: d\ntype: architecture\n---\n",
                    "knowledge/node_modules/junk.md": "---\ntitle: no\n---\n",
                },
            )
            found = knowledge.discover(root, MINIMAL_CONFIG)
            paths = [c["path"] for c in found]
            self.assertIn("knowledge/glossary.md", paths)
            self.assertIn("crates/lp/knowledge/architecture.md", paths)
            self.assertNotIn("knowledge/node_modules/junk.md", paths)
            lp = next(c for c in found if c["crate"] == "lp")
            self.assertEqual(lp["type"], "architecture")

    def test_lifecycle_defaults_to_current(self):
        with tempfile.TemporaryDirectory() as root:
            _tree_with_config(
                root,
                {
                    "knowledge/a.md": "---\ntitle: A\ndescription: d\ntype: reference\n---\n",
                },
            )
            found = knowledge.discover(root, MINIMAL_CONFIG)
            a = next(c for c in found if c["path"] == "knowledge/a.md")
            self.assertEqual(a["lifecycle"], "current")


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------


class ValidateTests(unittest.TestCase):
    def _concept(self, meta, ok=True):
        return {"_meta": meta, "_ok": ok, "_strict": []}

    def test_clean_concept_has_no_errors(self):
        self.assertEqual(
            knowledge.validate(
                self._concept({"title": "T", "description": "d", "type": "reference"}),
                MINIMAL_CONFIG,
            ),
            [],
        )

    def test_missing_field_and_bad_type(self):
        errors = knowledge.validate(
            self._concept({"title": "T", "type": "bogus"}), MINIMAL_CONFIG
        )
        self.assertTrue(any("description" in e for e in errors))
        self.assertTrue(any("type" in e for e in errors))

    def test_no_frontmatter_is_error(self):
        self.assertEqual(
            knowledge.validate(self._concept({}, ok=False), MINIMAL_CONFIG),
            ["missing frontmatter block"],
        )


# ---------------------------------------------------------------------------
# format_list / filter_concepts / public_view
# ---------------------------------------------------------------------------


class ListOutputTests(unittest.TestCase):
    def _concepts(self):
        return [
            {
                "path": "knowledge/glossary.md",
                "title": "Glossary",
                "description": "the contract",
                "type": "reference",
                "crate": None,
                "lifecycle": "current",
                "_ok": True,
                "_meta": {},
            },
            {
                "path": "crates/lp/knowledge/p.md",
                "title": "pilot",
                "description": "the plan",
                "type": "decision",
                "crate": "lp",
                "lifecycle": "current",
                "_ok": True,
                "_meta": {"updated": "2026-06-05"},
            },
        ]

    def test_filter_by_type(self):
        out = knowledge.filter_concepts(
            self._concepts(), type_name="reference", crate=None, lifecycle=None
        )
        self.assertEqual([c["path"] for c in out], ["knowledge/glossary.md"])

    def test_filter_by_crate(self):
        out = knowledge.filter_concepts(
            self._concepts(), type_name=None, crate="lp", lifecycle=None
        )
        self.assertEqual([c["path"] for c in out], ["crates/lp/knowledge/p.md"])

    def test_list_output_groups_by_type(self):
        text = knowledge.format_list(self._concepts(), MINIMAL_CONFIG)
        self.assertIn("REFERENCE", text)
        self.assertIn("DECISION (dated)", text)
        self.assertIn("knowledge/glossary.md", text)
        self.assertIn("[lp · 2026-06-05]", text)

    def test_public_view_drops_internal_keys(self):
        view = knowledge.public_view(self._concepts()[0])
        self.assertEqual(
            set(view), {"path", "title", "description", "type", "crate", "lifecycle"}
        )


# ---------------------------------------------------------------------------
# build_index
# ---------------------------------------------------------------------------


class IndexTests(unittest.TestCase):
    def _concepts(self):
        return [
            {
                "path": "knowledge/glossary.md",
                "title": "Glossary",
                "description": "the contract",
                "type": "reference",
                "crate": None,
            }
        ]

    def test_index_has_no_frontmatter(self):
        out = knowledge.build_index(self._concepts(), MINIMAL_CONFIG)
        self.assertFalse(out.startswith("---"))

    def test_index_lists_entry_with_link_and_description(self):
        out = knowledge.build_index(self._concepts(), MINIMAL_CONFIG)
        self.assertIn("## Reference", out)
        self.assertIn("* [Glossary](/glossary) - the contract", out)

    def test_check_fails_when_index_stale(self):
        with tempfile.TemporaryDirectory() as root:
            _tree_with_config(
                root,
                {
                    "knowledge/a.md": "---\ntitle: A\ndescription: d\ntype: reference\n---\n",
                },
            )
            # Mutate a concept so the committed index no longer matches.
            with open(
                os.path.join(root, "knowledge", "a.md"), "w", encoding="utf-8"
            ) as handle:
                handle.write(
                    "---\ntitle: A2\ndescription: changed\ntype: reference\n---\n"
                )
            code, report = knowledge.run_check(root, MINIMAL_CONFIG)
            self.assertEqual(code, 1)
            self.assertIn("index.md is stale", report)


# ---------------------------------------------------------------------------
# run_check
# ---------------------------------------------------------------------------


class CheckTests(unittest.TestCase):
    def test_check_passes_on_clean_tree(self):
        with tempfile.TemporaryDirectory() as root:
            _tree_with_config(
                root,
                {
                    "knowledge/a.md": "---\ntitle: A\ndescription: d\ntype: reference\n---\n",
                },
            )
            code, report = knowledge.run_check(root, MINIMAL_CONFIG)
            self.assertEqual(code, 0, report)

    def test_check_fails_on_missing_description(self):
        with tempfile.TemporaryDirectory() as root:
            _tree_with_config(
                root,
                {
                    "knowledge/a.md": "---\ntitle: A\ntype: reference\n---\n",
                },
            )
            code, report = knowledge.run_check(root, MINIMAL_CONFIG)
            self.assertEqual(code, 1)
            self.assertIn("description", report)

    def test_check_ignores_reserved_files(self):
        with tempfile.TemporaryDirectory() as root:
            _tree_with_config(
                root,
                {
                    "knowledge/log.md": "# Knowledge log\n\nno frontmatter here\n",
                    "knowledge/a.md": "---\ntitle: A\ndescription: d\ntype: reference\n---\n",
                },
            )
            code, report = knowledge.run_check(root, MINIMAL_CONFIG)
            self.assertEqual(code, 0, report)

    def test_check_fails_on_unquoted_colon_value(self):
        with tempfile.TemporaryDirectory() as root:
            _tree_with_config(
                root,
                {
                    "knowledge/a.md": "---\ntitle: System overview: crates\ndescription: d\ntype: reference\n---\n",
                },
            )
            code, report = knowledge.run_check(root, MINIMAL_CONFIG)
            self.assertEqual(code, 1)
            self.assertIn("unquoted", report)

    def test_check_passes_on_quoted_colon_value(self):
        with tempfile.TemporaryDirectory() as root:
            _tree_with_config(
                root,
                {
                    "knowledge/a.md": '---\ntitle: "System overview: crates"\ndescription: d\ntype: reference\n---\n',
                },
            )
            code, report = knowledge.run_check(root, MINIMAL_CONFIG)
            self.assertEqual(code, 0, report)


# ---------------------------------------------------------------------------
# site_url / build_sidebar / sync_site
# ---------------------------------------------------------------------------


class SiteGenTests(unittest.TestCase):
    def test_site_url_strips_knowledge_prefix_and_md(self):
        self.assertEqual(
            knowledge.site_url("knowledge/architecture/solver-architecture.md"),
            "/architecture/solver-architecture",
        )

    def test_site_url_maps_crate_concepts(self):
        self.assertEqual(
            knowledge.site_url("crates/lp/knowledge/architecture.md"),
            "/crates/lp/architecture",
        )

    def test_build_sidebar_groups_by_type(self):
        concepts = [
            {
                "path": "knowledge/glossary.md",
                "title": "Glossary",
                "type": "reference",
                "crate": None,
            },
            {
                "path": "crates/lp/knowledge/p.md",
                "title": "pilot",
                "type": "decision",
                "crate": "lp",
            },
        ]
        sidebar = knowledge.build_sidebar(concepts, MINIMAL_CONFIG)
        texts = [section["text"] for section in sidebar]
        self.assertIn("Reference", texts)
        self.assertIn("Decision", texts)
        ref = next(s for s in sidebar if s["text"] == "Reference")
        self.assertEqual(ref["items"][0], {"text": "Glossary", "link": "/glossary"})
        self.assertFalse(ref["collapsed"])
        dec = next(s for s in sidebar if s["text"] == "Decision")
        self.assertTrue(dec["collapsed"])

    def test_sync_copies_crate_concepts_into_site(self):
        with tempfile.TemporaryDirectory() as root:
            _tree_with_config(
                root,
                {
                    "crates/lp/knowledge/architecture.md": "---\ntitle: LP\ndescription: d\ntype: architecture\n---\nbody\n",
                    "knowledge/glossary.md": "---\ntitle: G\ndescription: d\ntype: reference\n---\nbody\n",
                },
            )
            count = knowledge.sync_site(root, MINIMAL_CONFIG)
            self.assertEqual(count, 1)
            staged = os.path.join(root, "knowledge", "crates", "lp", "architecture.md")
            self.assertTrue(os.path.exists(staged))
            # the staged copy must not re-enter discovery (no double-count)
            self.assertEqual(len(knowledge.curated(root, MINIMAL_CONFIG)), 2)


# ---------------------------------------------------------------------------
# check_skill_refs
# ---------------------------------------------------------------------------


class SkillRefsTests(unittest.TestCase):
    def _skill(self, body):
        return "---\nname: code\ndescription: d\n---\n" + body

    def test_absent_skill_is_noop(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(knowledge.check_skill_refs(root, MINIMAL_CONFIG), [])

    def test_resolving_refs_pass(self):
        with tempfile.TemporaryDirectory() as root:
            _make_tree(
                root,
                {
                    ".claude/skills/code/SKILL.md": self._skill(
                        "See `scripts/real.sh`, the `knowledge/glossary.md` file, "
                        "and `roadmap/specs/<feature>/{requirements,design}.md`.\n"
                    ),
                    "scripts/real.sh": "#!/bin/sh\n",
                    "knowledge/glossary.md": "# Glossary\n",
                },
            )
            self.assertEqual(knowledge.check_skill_refs(root, MINIMAL_CONFIG), [])

    def test_dead_literal_ref_fails(self):
        with tempfile.TemporaryDirectory() as root:
            _make_tree(
                root,
                {
                    ".claude/skills/code/SKILL.md": self._skill(
                        "Run `scripts/missing.sh`.\n"
                    )
                },
            )
            errors = knowledge.check_skill_refs(root, MINIMAL_CONFIG)
            self.assertTrue(any("missing.sh" in e for e in errors))

    def test_glob_with_no_match_fails(self):
        with tempfile.TemporaryDirectory() as root:
            _make_tree(
                root,
                {
                    ".claude/skills/code/SKILL.md": self._skill(
                        "The `knowledge/*.md` files.\n"
                    )
                },
            )
            errors = knowledge.check_skill_refs(root, MINIMAL_CONFIG)
            self.assertTrue(any("knowledge/*.md" in e for e in errors))

    def test_placeholder_is_skipped(self):
        with tempfile.TemporaryDirectory() as root:
            _make_tree(
                root,
                {
                    ".claude/skills/code/SKILL.md": self._skill(
                        "Write `roadmap/specs/<feature>/{requirements,design,tasks}.md`.\n"
                    )
                },
            )
            self.assertEqual(knowledge.check_skill_refs(root, MINIMAL_CONFIG), [])

    def test_bad_name_fails(self):
        with tempfile.TemporaryDirectory() as root:
            _make_tree(
                root,
                {
                    ".claude/skills/code/SKILL.md": "---\nname: wrong\ndescription: d\n---\nbody\n"
                },
            )
            errors = knowledge.check_skill_refs(root, MINIMAL_CONFIG)
            self.assertTrue(any("name" in e for e in errors))

    def test_fenced_code_block_refs_ignored(self):
        with tempfile.TemporaryDirectory() as root:
            _make_tree(
                root,
                {
                    ".claude/skills/code/SKILL.md": self._skill(
                        "```\n`scripts/dead.sh` is only an example\n```\nProse only.\n"
                    )
                },
            )
            self.assertEqual(knowledge.check_skill_refs(root, MINIMAL_CONFIG), [])

    def test_missing_description_fails(self):
        with tempfile.TemporaryDirectory() as root:
            _make_tree(
                root,
                {".claude/skills/code/SKILL.md": "---\nname: code\n---\nbody\n"},
            )
            errors = knowledge.check_skill_refs(root, MINIMAL_CONFIG)
            self.assertTrue(any("description" in e for e in errors))

    def test_embedded_path_in_compound_span_is_checked(self):
        with tempfile.TemporaryDirectory() as root:
            _make_tree(
                root,
                {
                    ".claude/skills/code/SKILL.md": self._skill(
                        "Run `python3 scripts/gone.py check`.\n"
                    )
                },
            )
            errors = knowledge.check_skill_refs(root, MINIMAL_CONFIG)
            self.assertTrue(any("scripts/gone.py" in e for e in errors))


# ---------------------------------------------------------------------------
# parse_headings
# ---------------------------------------------------------------------------


class ParseHeadingsTests(unittest.TestCase):
    def test_parses_all_levels(self):
        text = "# H1\n## H2\n### H3\n"
        headings = knowledge.parse_headings(text)
        self.assertEqual(headings, [(1, "H1", 1), (2, "H2", 2), (3, "H3", 3)])

    def test_ignores_non_heading_lines(self):
        text = "Some prose.\n## Section\nMore prose.\n"
        headings = knowledge.parse_headings(text)
        self.assertEqual(headings, [(2, "Section", 2)])

    def test_linenos_are_one_based(self):
        text = "\n\n## Third line\n"
        headings = knowledge.parse_headings(text)
        self.assertEqual(headings[0][2], 3)

    def test_empty_document_returns_empty(self):
        self.assertEqual(knowledge.parse_headings(""), [])

    def test_heading_text_is_stripped(self):
        text = "##   Spaced heading  \n"
        headings = knowledge.parse_headings(text)
        self.assertEqual(headings[0][1], "Spaced heading")

    def test_ignores_hash_inside_fenced_block(self):
        """A # line inside a fenced code block must not be treated as a heading."""
        text = "## Real heading\n\n```bash\n# not a heading\necho hello\n```\n"
        headings = knowledge.parse_headings(text)
        self.assertEqual(len(headings), 1)
        self.assertEqual(headings[0][1], "Real heading")


# ---------------------------------------------------------------------------
# cmd_outline
# ---------------------------------------------------------------------------


class OutlineTests(unittest.TestCase):
    def _run_outline(self, content, filename="concept.md"):
        with tempfile.TemporaryDirectory() as root:
            _make_tree(root, {filename: content})
            import io
            from unittest.mock import patch

            captured = io.StringIO()
            with patch("sys.stdout", captured):
                code = knowledge.cmd_outline(filename, root)
            return code, captured.getvalue()

    def test_outline_returns_zero_on_valid_concept(self):
        code, _ = self._run_outline("# Title\n## Section\n")
        self.assertEqual(code, 0)

    def test_outline_prints_headings_with_line_numbers(self):
        code, output = self._run_outline("# Title\n\n## Section\n")
        self.assertIn("Title", output)
        self.assertIn("Section", output)
        self.assertIn("1", output)
        self.assertIn("3", output)

    def test_outline_indents_nested_headings(self):
        code, output = self._run_outline("# H1\n## H2\n### H3\n")
        lines = output.strip().splitlines()
        self.assertTrue(lines[0].endswith("# H1") or "# H1" in lines[0])
        self.assertIn("## H2", lines[1])
        self.assertIn("### H3", lines[2])
        h1_indent = len(lines[0]) - len(lines[0].lstrip())
        h2_indent = len(lines[1]) - len(lines[1].lstrip())
        self.assertGreater(h2_indent, h1_indent)

    def test_outline_returns_nonzero_on_missing_file(self):
        with tempfile.TemporaryDirectory() as root:
            code = knowledge.cmd_outline("nonexistent.md", root)
            self.assertEqual(code, 1)

    def test_outline_handles_concept_with_no_headings(self):
        code, output = self._run_outline("Just prose, no headings.\n")
        self.assertEqual(code, 0)


# ---------------------------------------------------------------------------
# cmd_section
# ---------------------------------------------------------------------------


class SectionTests(unittest.TestCase):
    SAMPLE_DOC = (
        "# Title\n\n"
        "Intro paragraph.\n\n"
        "## Canonical terms\n\n"
        "| Term | Definition |\n"
        "|---|---|\n"
        "| Foo | Bar |\n\n"
        "## Another section\n\n"
        "Other content.\n"
    )

    def _run_section(self, content, heading_query, filename="concept.md"):
        with tempfile.TemporaryDirectory() as root:
            _make_tree(root, {filename: content})
            import io
            from unittest.mock import patch

            captured = io.StringIO()
            with patch("sys.stdout", captured):
                code = knowledge.cmd_section(filename, heading_query, root)
            return code, captured.getvalue()

    def _run_section_stderr(self, content, heading_query, filename="concept.md"):
        with tempfile.TemporaryDirectory() as root:
            _make_tree(root, {filename: content})
            import io
            from unittest.mock import patch

            captured_err = io.StringIO()
            with patch("sys.stderr", captured_err):
                code = knowledge.cmd_section(filename, heading_query, root)
            return code, captured_err.getvalue()

    def test_section_returns_zero_on_match(self):
        code, _ = self._run_section(self.SAMPLE_DOC, "Canonical")
        self.assertEqual(code, 0)

    def test_section_prints_matched_heading(self):
        code, output = self._run_section(self.SAMPLE_DOC, "Canonical")
        self.assertIn("## Canonical terms", output)

    def test_section_includes_body_content(self):
        code, output = self._run_section(self.SAMPLE_DOC, "Canonical")
        self.assertIn("| Foo | Bar |", output)

    def test_section_stops_at_next_equal_level_heading(self):
        code, output = self._run_section(self.SAMPLE_DOC, "Canonical")
        self.assertNotIn("Another section", output)

    def test_section_match_is_case_insensitive(self):
        code, output = self._run_section(self.SAMPLE_DOC, "canonical")
        self.assertEqual(code, 0)
        self.assertIn("## Canonical terms", output)

    def test_section_returns_nonzero_on_no_match(self):
        code, _ = self._run_section_stderr(self.SAMPLE_DOC, "Nonexistent heading")
        self.assertEqual(code, 1)

    def test_section_error_lists_available_headings(self):
        code, stderr = self._run_section_stderr(self.SAMPLE_DOC, "Nonexistent heading")
        self.assertIn("Canonical terms", stderr)
        self.assertIn("Another section", stderr)

    def test_section_returns_nonzero_on_missing_file(self):
        with tempfile.TemporaryDirectory() as root:
            code = knowledge.cmd_section("nonexistent.md", "any", root)
            self.assertEqual(code, 1)

    def test_section_child_heading_included(self):
        """A heading nested under the matched section is part of the section body."""
        doc = "## Parent\n\n### Child\n\nchild content\n\n## Sibling\n\nsibling\n"
        code, output = self._run_section(doc, "Parent")
        self.assertIn("### Child", output)
        self.assertIn("child content", output)
        self.assertNotIn("Sibling", output)

    def test_section_partial_match(self):
        """A partial substring match (e.g. 'terms' matches 'Canonical terms')."""
        code, output = self._run_section(self.SAMPLE_DOC, "terms")
        self.assertEqual(code, 0)
        self.assertIn("Canonical terms", output)

    def test_section_includes_post_fence_body(self):
        """Body text after a fenced code block (which contains a # comment) must
        appear in the section output; the next sibling heading stops extraction."""
        doc = (
            "## Target\n"
            "\n"
            "```bash\n"
            "# shell comment — not a heading\n"
            "echo done\n"
            "```\n"
            "\n"
            "post-fence body\n"
            "\n"
            "## Next\n"
            "\n"
            "should not appear\n"
        )
        code, output = self._run_section(doc, "Target")
        self.assertEqual(code, 0)
        self.assertIn("post-fence body", output)
        self.assertNotIn("should not appear", output)


# ---------------------------------------------------------------------------
# main() — lazy config loading
# ---------------------------------------------------------------------------


class MainLazyConfigTests(unittest.TestCase):
    def test_outline_via_main_succeeds_without_config(self):
        """main() must not call load_config() before it knows the command;
        outline/section must work in a repo with no knowledge/knowledge-config.json."""
        with tempfile.TemporaryDirectory() as root:
            concept_rel = "concept.md"
            _make_tree(root, {concept_rel: "# Title\n\n## Section\n"})
            original_root = knowledge.REPO_ROOT
            original_config_path = knowledge.CONFIG_PATH
            knowledge.REPO_ROOT = root
            knowledge.CONFIG_PATH = os.path.join(
                root, "knowledge", "knowledge-config.json"
            )
            try:
                import io
                from unittest.mock import patch

                captured = io.StringIO()
                with patch("sys.stdout", captured):
                    code = knowledge.main(["outline", concept_rel])
                self.assertEqual(code, 0)
                self.assertIn("Title", captured.getvalue())
            finally:
                knowledge.REPO_ROOT = original_root
                knowledge.CONFIG_PATH = original_config_path


if __name__ == "__main__":
    unittest.main()
