"""Verify numeric stage logs survive the deployed warning-only server setting."""

import os
import subprocess
import sys


def test_timing_logger_survives_server_warning_level():
    code = """
import logging
import uvicorn
from veteran_access_bridge.voice.timing import timing_log_config
uvicorn.Config("unused:app", log_level="warning", log_config=timing_log_config())
logging.getLogger("uvicorn.error.vab_timing").info("timing_probe duration_ms=1.0")
logging.getLogger("uvicorn.error").info("ordinary_info_must_stay_hidden")
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env={
            **{k: v for k, v in os.environ.items() if k != "SSLKEYLOGFILE"},
            "VAB_MCP_TRANSPORT": "stdio",
        },
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "timing_probe duration_ms=1.0" in result.stderr
    assert "ordinary_info_must_stay_hidden" not in result.stderr
