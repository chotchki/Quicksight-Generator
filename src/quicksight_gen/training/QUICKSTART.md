# Handbook Whitelabel Kit — Quickstart

A reusable cross-training handbook for a QuickSight-backed
reconciliation tool. The source is written in a generic codename
("Sasquatch National Bank" / "SNB"); `quicksight-gen export training`
substitutes those for your organization's names at export time.

## Steps

1. Copy the mapping template from the installed package and fill it in:
   ```
   cp $(python -c "import quicksight_gen, pathlib; print(pathlib.Path(quicksight_gen.__file__).parent / 'training' / 'mapping.yaml.example')") mapping.yaml
   ```
   Edit `mapping.yaml` to fill in your real-program names. The template
   enumerates every SNB string that is eligible for substitution. Leave a
   value blank to keep the SNB text as-is — useful when you want to
   rebrand the real-program context but keep demo references intact.
2. Dry run to preview substitution counts per file:
   ```
   quicksight-gen export training --output ./out/handbook --mapping mapping.yaml --dry-run
   ```
3. Export for real:
   ```
   quicksight-gen export training --output ./out/handbook --mapping mapping.yaml
   ```
   The command warns if any SNB-signature strings remain in the output.
   Either update your mapping or accept (some references to the demo
   environment itself are intentional).
4. Upload `./out/handbook/` to your wiki / docs host.

To export the canonical (un-substituted) Sasquatch-named copy, omit
`--mapping`.
