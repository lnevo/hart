"""Shared helpers for the repo's CPython tools: tables.xml, paths, hosts and the name map.

CPython 3.9+ only, standard library only. Jython scripts that run inside JMRI must not
import it. See tools/hartlib/README.md for the API and the rules for moving a script.
"""
__all__ = ["hosts", "names", "paths", "tables"]
