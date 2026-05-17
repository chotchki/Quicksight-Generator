mkdocs-macros include_dir
=========================

This directory is registered in mkdocs.yml as the
plugins.macros.include_dir. Markdown pages can pull in Jinja
fragments stored here using mkdocs-macros's include directive.

mkdocs-macros requires this directory to exist even when empty;
without it, mkdocs build fails at config time. This README is what
makes setuptools include the directory in the built wheel — the
package_data globs do not pick up directories whose only contents
are dotfiles like .gitkeep.

NOTE: mkdocs-macros parses every file in this directory as a Jinja
template, so this README intentionally avoids the open-curly-brace
template syntax in its prose.
