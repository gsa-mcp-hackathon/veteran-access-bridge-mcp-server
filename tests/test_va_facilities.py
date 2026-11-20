import httpx
import pytest

from veteran_access_bridge.adapters.va_facilities import read_health_facility


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setenv("VA_SANDBOX_ENABLED", "true")
    monkeypatch.setenv("VA_FACILITIES_READ_ENABLED", "true")
    monkeypatch.setenv("VA_FACILITIES_API_KEY", "unit-test-only")


def client(data, status=200):
    def handle(request):
        assert request.url.host == "sandbox-api.va.gov"
        assert request.url.path.endswith("/facilities/vha_688")
        assert request.headers["apikey"] == "unit-test-only"
        return httpx.Response(status, json={"data": data})

    return httpx.Client(transport=httpx.MockTransport(handle))


def test_facility_metadata_is_not_patient_assignment(enabled):
    with client(
        {
            "id": "vha_688",
            "attributes": {"name": "Test clinic", "timeZone": "America/New_York"},
        }
    ) as http:
        result = read_health_facility("vha_688", http=http)
    assert result["source_verified"] is True
    assert result["time_zone"] == "America/New_York"
    assert result["patient_assignment_verified"] is False
    assert result["booking_authority"] is False
    assert "apikey" not in result


@pytest.mark.parametrize(
    "identifier", ["../Patient", "https://example.com", "vha_688/../ids", "vha_688?x=1"]
)
def test_no_arbitrary_endpoints(enabled, identifier):
    with pytest.raises(ValueError):
        read_health_facility(identifier)


@pytest.mark.parametrize(
    "data",
    [
        {
            "id": "vha_999",
            "attributes": {"name": "Test", "timeZone": "America/New_York"},
        },
        {"id": "vha_688", "attributes": {"name": "Test", "timeZone": "invented"}},
        {"id": "vha_688", "attributes": {"name": "Test"}},
    ],
)
def test_rejects_unverified_mapping_and_zone(enabled, data):
    with client(data) as http, pytest.raises(ValueError):
        read_health_facility("vha_688", http=http)


def test_disabled_before_network(monkeypatch):
    monkeypatch.delenv("VA_FACILITIES_READ_ENABLED", raising=False)
    with pytest.raises(PermissionError):
        read_health_facility("vha_688")


@pytest.mark.parametrize("status", [302, 401, 403, 404, 429, 500])
def test_no_redirects_or_success_on_failure(enabled, status):
    with client({}, status) as http, pytest.raises(RuntimeError):
        read_health_facility("vha_688", http=http)
