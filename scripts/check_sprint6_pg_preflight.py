"""CLI for the guarded, read-only Sprint 6 Supabase preflight.

Use a trusted server/terminal, not the browser. Do not print credentials.
"""

from veteran_access_bridge.adapters.supabase_sprint6_preflight import main


if __name__ == "__main__":
    raise SystemExit(main())
