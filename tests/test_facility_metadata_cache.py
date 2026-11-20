import httpx
import pytest

from veteran_access_bridge.adapters import va_facilities as mod


@pytest.fixture
def cache(monkeypatch):
    monkeypatch.setenv("VA_SANDBOX_ENABLED", "true")
    monkeypatch.setenv("VA_FACILITIES_READ_ENABLED", "true")
    monkeypatch.setenv("VA_FACILITIES_API_KEY", "test-only")
    monkeypatch.setenv("VAB_FACILITY_METADATA_CACHE_SECONDS", "60")
    monkeypatch.setattr(mod, "_CACHE", {})
    clock = [100.0]
    monkeypatch.setattr(mod.time, "monotonic", lambda: clock[0])
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "data": {
                    "id": request.url.path.rsplit("/", 1)[-1],
                    "attributes": {
                        "name": "Public facility",
                        "timeZone": "America/Chicago",
                    },
                }
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        yield http, calls, clock


def test_hit_is_copy_and_expiry_requires_fresh_read(cache):
    http, calls, clock = cache
    first = mod.read_health_facility("vha_589A5", http=http)
    first["name"] = "Changed by consumer"
    assert mod.read_health_facility("vha_589A5", http=http)["name"] == "Public facility"
    assert len(calls) == 1
    clock[0] += 60
    assert not mod.read_health_facility("vha_589A5", http=http)["cache_hit"]
    assert len(calls) == 2


@pytest.mark.parametrize(
    "setting,value",
    [
        ("VA_SANDBOX_ENABLED", "false"),
        ("VA_FACILITIES_READ_ENABLED", "false"),
        ("VA_FACILITIES_API_KEY", ""),
    ],
)
def test_warm_cache_cannot_bypass_configuration(cache, monkeypatch, setting, value):
    http, calls, _ = cache
    mod.read_health_facility("vha_589A5", http=http)
    monkeypatch.setenv(setting, value)
    with pytest.raises(PermissionError):
        mod.read_health_facility("vha_589A5", http=http)
    assert len(calls) == 1


def test_key_rotation_and_facility_id_cannot_reuse_entry(cache, monkeypatch):
    http, calls, _ = cache
    mod.read_health_facility("vha_589A5", http=http)
    monkeypatch.setenv("VA_FACILITIES_API_KEY", "new-test-only")
    assert not mod.read_health_facility("vha_589A5", http=http)["cache_hit"]
    assert not mod.read_health_facility("vha_589", http=http)["cache_hit"]
    assert len(calls) == 3


def test_disabled_cache_always_reads_source(cache, monkeypatch):
    http, calls, _ = cache
    monkeypatch.delenv("VAB_FACILITY_METADATA_CACHE_SECONDS")
    for _ in range(2):
        assert not mod.read_health_facility("vha_589A5", http=http)["cache_hit"]
    assert len(calls) == 2


def test_expired_cache_is_not_returned_on_source_failure(cache):
    http, _, clock = cache
    mod.read_health_facility("vha_589A5", http=http)
    clock[0] += 61
    with httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(503))
    ) as failed:
        with pytest.raises(RuntimeError):
            mod.read_health_facility("vha_589A5", http=failed)
