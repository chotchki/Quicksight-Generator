# How do I publish docs against my L2?

The unified docs site renders against any L2 institution YAML. Pick
yours; the same source produces a different rendered handbook (vocab,
diagrams, intro prose) without touching any markdown.

## End-to-end

```bash
# 1. Extract the docs source to a working directory.
quicksight-gen export docs -o /tmp/my-docs --l2-instance run/my-l2.yaml

# 2. The CLI echoes the right env-var-prefixed mkdocs command.
QS_DOCS_L2_INSTANCE=/Users/me/run/my-l2.yaml \
    mkdocs build -f /tmp/my-docs/mkdocs.yml

# 3. Serve locally to eyeball:
QS_DOCS_L2_INSTANCE=/Users/me/run/my-l2.yaml \
    mkdocs serve -f /tmp/my-docs/mkdocs.yml
```

The rendered `site/` directory is a static site you can publish to
your wiki, GitHub Pages, S3, or any static host.

## What changes per L2 instance

Three substitution surfaces:

- **Vocab strings** (`{{ vocab.institution.name }}`,
  `{{ vocab.institution.acronym }}`, etc.) substitute throughout the
  prose. The built-in `sasquatch_pr` vocabulary carries Sasquatch
  flavor; any other instance falls back to a neutral
  "Your Institution" voice derived from the L2 description's first
  proper-noun-shaped run.
- **L2-driven diagrams** (`{{ diagram("l2_topology", kind="accounts") }}`,
  `{{ diagram("dataflow", app="l1_dashboard") }}`) regenerate from
  your L2's structural data — accounts + rails + chains laid out
  visually for your specific institution.
- **The page set** stays the same; the CONTENT of each page reflects
  your L2.

## What stays the same

- **Conceptual diagrams** (`docs/_diagrams/conceptual/*.dot`) are
  hand-authored teaching aids. They don't change per L2.
- **Reference material** describing the L1 invariants, the SPEC, and
  the Schema v6 contract are persona-blind and identical across
  renders.
- **Walkthroughs** describing per-sheet operator flows are written
  against the dashboard structure (which is the same regardless of
  L2). Body examples may still mention SNB-flavored identifiers
  (gl-1010, Bigfoot Brews) where the example is illustrative; those
  are tagged for future cleanup or replacement with vocab pulls.

## Custom built-in vocabularies

If your institution wants richer flavor than the neutral fallback —
named scenarios, regional voice, custom Investigation personas —
either:

1. Submit a PR adding your vocabulary as a built-in (the same way
   `sasquatch_pr` ships one), OR
2. Wait for the future `personas:` YAML block (audit §5 sketch)
   that will let your L2 carry the data inline.

The neutral fallback keeps your handbook readable until then.
