"""Fixed-schema SQL execution for private synthetic scheduling services.

Existing SQL literals deliberately target vab.*. For the *independently
authenticated test role only*, this helper maps those trusted SQL literals to
vab_test.*. It never accepts a schema from a user, MCP request, or HTTP header.

Database GRANTs are the final isolation boundary: the test role has no USAGE
on the operational vab schema, even if a query were routed incorrectly.
"""

from __future__ import annotations

import re

_SCHEMA_REFERENCE = re.compile(r"(?<![A-Za-z0-9_])vab\.(?=[a-z_])")


def execute_scheduling_sql(cur, schema: str, statement: str, params=None):
    """Execute repository-owned SQL with an allowlisted schema.

    Only SQL constants inside vetted scheduling services may call this helper.
    Never call it with a statement or identifier supplied by a client.
    """
    if schema not in ("vab", "vab_test"):
        raise PermissionError("Unapproved scheduling schema")
    if not isinstance(statement, str):
        raise TypeError("Scheduling SQL must be a trusted string literal")
    if schema == "vab_test":
        if "vab_test." in statement:
            raise ValueError("Mixed or prequalified test-schema SQL is denied")
        statement = _SCHEMA_REFERENCE.sub("vab_test.", statement)
        if _SCHEMA_REFERENCE.search(statement):
            raise ValueError("Operational schema reference in test SQL")
    if params is None:
        return cur.execute(statement)
    return cur.execute(statement, params)
