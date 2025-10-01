"""Compatibility shim providing mysql.connector interface backed by psycopg."""

from . import connector  # noqa: F401

__all__ = ["connector"]
