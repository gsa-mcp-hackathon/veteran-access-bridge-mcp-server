"""One server-owned dispatch name shared by issuance, worker and readiness."""

import os
import re


def voice_agent_name():
    name = os.getenv("VAB_VOICE_AGENT_NAME", "vab-avery")
    if not re.fullmatch(r"vab-avery(?:-[a-z0-9-]{1,40})?", name):
        raise ValueError("Invalid Avery dispatch name")
    return name
