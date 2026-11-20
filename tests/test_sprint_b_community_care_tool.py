"""Sprint B Community Care tool never invents eligibility or booking rights."""

import pytest

from veteran_access_bridge.mcp.tools import check_community_care_eligibility


def test_community_care_read_only_unverified(monkeypatch):
    monkeypatch.setattr(
        check_community_care_eligibility,
        "assess_access_standard",
        lambda case_id: {"case_id": case_id, "signal_only": True},
    )
    result = check_community_care_eligibility.run("TEST-COMMUNITY-CARE")
    assert result["community_care_eligibility_status"] == "UNVERIFIED"
    assert result["authoritative_eligibility_checked"] is False
    assert result["authorization_granted"] is False
    assert result["appointment_created"] is False
    assert result["read_only"] is True
    assert result["review_signal"]["signal_only"] is True


@pytest.mark.parametrize("case_id", ["", " ", None])
def test_community_care_empty_case_fails_before_lookup(monkeypatch, case_id):
    def unexpected(_case_id):
        raise AssertionError("Cannot look up an invalid case")

    monkeypatch.setattr(
        check_community_care_eligibility, "assess_access_standard", unexpected
    )
    with pytest.raises(ValueError, match="Synthetic case ID"):
        check_community_care_eligibility.run(case_id)
