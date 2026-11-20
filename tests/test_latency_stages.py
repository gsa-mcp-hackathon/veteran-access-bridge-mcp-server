import logging

import pytest

from veteran_access_bridge.services.latency_timing import measured_stage


def test_failure_is_measured_without_sensitive_exception_text(caplog):
    with caplog.at_level(logging.INFO, logger="uvicorn.error.vab_timing"):
        with pytest.raises(RuntimeError):
            with measured_stage("va_token"):
                raise RuntimeError("secret-patient-credential")
    assert "stage=va_token" in caplog.text
    assert "outcome=error" in caplog.text
    assert "secret-patient-credential" not in caplog.text


def test_unknown_stage_cannot_inject_log_text(caplog):
    with pytest.raises(ValueError):
        with measured_stage("patient-name"):
            pytest.fail("Should not enter")
    assert not caplog.records
