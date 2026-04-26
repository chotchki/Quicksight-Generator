"""Computed views over a loaded ``L2Instance`` (M.1a.4).

Holds pure-function derivations that expose values the SPEC declares
conceptually but doesn't store directly on the primitives. Today's
single citizen is ``posted_requirements_for``: the SPEC says every leg
has a PostedRequirements set composed of three sources — integrator-
declared ``posted_requirements`` on the Rail, auto-derived TransferKey
fields from any containing TransferTemplate, and ``parent_transfer_id``
when a Required-true chain entry points at the rail (directly or via
its template). Storing the resolved set on the Rail would force the
loader to compute it, baking dependency order into the type system; a
computed view keeps the input primitives clean and the derivation
testable in isolation.

Pure functions over an ``L2Instance`` — no I/O, no side effects, no
mutation.
"""

from __future__ import annotations

from .primitives import (
    Identifier,
    L2Instance,
    Rail,
    TransferTemplate,
)


# The auto-added field name for a Required-true chain child. Pinned at
# module level so tests + integrator code reference one canonical
# spelling; promoting to a SPEC literal would feel premature in v1.
PARENT_TRANSFER_ID = Identifier("parent_transfer_id")


def posted_requirements_for(
    instance: L2Instance,
    rail_name: Identifier,
) -> tuple[Identifier, ...]:
    """Return the resolved PostedRequirements set for ``rail_name``.

    Unions three sources per the SPEC's "PostedRequirements" subsection:

    1. The Rail's own ``posted_requirements`` (integrator-declared).
    2. ``TransferKey`` fields for any TransferTemplate where this rail
       appears in ``leg_rails`` (auto-derived from the template's
       grouping rule — a leg can't be Posted without naming the
       grouping values).
    3. ``parent_transfer_id`` if this rail is the child of any
       ``Required: true`` Chain entry, OR if a TransferTemplate
       containing this rail is the child of any ``Required: true``
       Chain entry.

    Output is deduped and sorted lexicographically — deterministic
    across runs, integrator-declared overlap with TransferKey
    auto-derivation collapses cleanly.

    Raises ``KeyError`` if ``rail_name`` doesn't match any declared rail.
    """
    rail = _find_rail(instance, rail_name)

    fields: set[Identifier] = set(rail.posted_requirements)

    # (2) TransferKey fields from any containing TransferTemplate.
    # A rail MAY appear in multiple templates; each contributes its keys.
    containing_templates: list[TransferTemplate] = [
        t for t in instance.transfer_templates if rail_name in t.leg_rails
    ]
    for t in containing_templates:
        fields.update(t.transfer_key)

    # (3) parent_transfer_id if any Required-true chain entry's child
    # is either this rail OR a TransferTemplate that contains this rail.
    chain_targets: set[Identifier] = {rail_name}
    chain_targets.update(t.name for t in containing_templates)
    for c in instance.chains:
        if c.required and c.child in chain_targets:
            fields.add(PARENT_TRANSFER_ID)
            break  # a single match is enough; the field is added at most once.

    return tuple(sorted(fields))


def _find_rail(instance: L2Instance, rail_name: Identifier) -> Rail:
    """Lookup helper. Raises ``KeyError`` with a friendly message on miss."""
    for r in instance.rails:
        if r.name == rail_name:
            return r
    raise KeyError(
        f"Rail {rail_name!r} not found in L2 instance "
        f"{instance.instance!r}"
    )
