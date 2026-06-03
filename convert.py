"""zkm-ner — filesystem-discovery shim; delegates to the zkm_ner package.

Loaded by core when the plugin is filesystem-discovered (dev-symlink workflow).
Core's _inject_plugin_venv (SB2) adds plugins/zkm-ner/src/ to sys.path before
loading this file, making zkm_ner importable here.
"""

from zkm_ner.convert import convert, scrub  # noqa: F401
