"""Package sub-directory for deterministic demo scheduling fixtures.

These JSON files are the canonical runtime source read by the synthetic source
adapters via importlib.resources. They are the same content as the files in
data/fixtures/demo/ at the repository root.

Sync contract
-------------
data/fixtures/demo/ is the human-readable, reviewer-facing canonical location.
The copies here are what gets installed into the package when a user runs
``pip install veteran-access-bridge``.

Any edit to a fixture file must be applied to BOTH locations:
  - src/veteran_access_bridge/adapters/fixtures/<file>.json  (installed artefact)
  - data/fixtures/demo/<file>.json                           (repo reference copy)

A future CI step may enforce this with a diff check.
"""
