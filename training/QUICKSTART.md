# Handbook Whitelabel Kit — Quickstart

A reusable cross-training handbook for a QuickSight-backed
reconciliation tool. The source is written in a generic codename
("Sasquatch National Bank" / "SNB"); `publish.py` substitutes
those for your organization's names at publish time.

## Steps

1. Copy the mapping template:
   ```
   cp mapping.yaml.example mapping.yaml
   ```
2. Edit `mapping.yaml` to fill in your real-program names. The
   template enumerates every SNB string that is eligible for
   substitution. Leave a value blank to keep the SNB text as-is —
   useful when you want to rebrand the real-program context but
   keep demo references intact.
3. Dry run to preview substitution counts per file:
   ```
   ./publish.py --dry-run
   ```
4. Publish for real. Output lands in `./.publish/`:
   ```
   ./publish.py
   ```
5. The script warns if any SNB-signature strings remain in the
   output. Either update your mapping or accept (some references
   to the demo environment itself are intentional).
6. Upload `.publish/handbook/` to your wiki / docs host.

Requires Python 3 (stdlib only). No `pip install` needed.
