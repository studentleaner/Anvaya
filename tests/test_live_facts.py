import asyncio

import httpx

from anvaya_api.config import Settings
from anvaya_api.live_facts import LiveFact, live_sources

S = Settings(ha_token="tok", radarr_api_key="rk", sonarr_api_key="sk")
NO_CREDS = Settings()  # every provider's credential is blank


def run(coro):
    return asyncio.run(coro)


def handler(*, solar_ok=True, bills=None, radarr_records=None, sonarr_records=None,
            solar_status=200, bills_status=200, radarr_status=200, sonarr_status=200,
            raise_on=()):
    bills = bills if bills is not None else []
    radarr_records = radarr_records if radarr_records is not None else []
    sonarr_records = sonarr_records if sonarr_records is not None else []

    def h(request):
        host, path = request.url.host, request.url.path
        if host in raise_on:
            raise httpx.ConnectError("down")
        if host == "homeassistant" and path.startswith("/api/states/"):
            if not solar_ok:
                return httpx.Response(solar_status)
            return httpx.Response(200, json={"state": "42", "attributes": {"unit_of_measurement": "W"}})
        if host == "finance-api" and path == "/api/bills":
            return httpx.Response(bills_status, json={"bills": bills})
        if host == "radarr-host" and path == "/api/v3/queue":
            return httpx.Response(radarr_status, json={"records": radarr_records})
        if host == "sonarr-host" and path == "/api/v3/queue":
            return httpx.Response(sonarr_status, json={"records": sonarr_records})
        return httpx.Response(404)

    return h


def settings_with_hosts(**over):
    base = dict(ha_url="http://homeassistant:8123", ha_token="tok",
                finance_api_url="http://finance-api:8200",
                radarr_url="http://radarr-host", radarr_api_key="rk",
                sonarr_url="http://sonarr-host", sonarr_api_key="sk")
    base.update(over)
    return Settings(**base)


ALL_CLASSES = {"public", "household", "finance", "health"}


def test_no_keyword_match_returns_nothing():
    facts = run(live_sources("hello there", settings_with_hosts(), ALL_CLASSES, transport=httpx.MockTransport(handler())))
    assert facts == []


def test_household_not_allowed_skips_solar_and_media():
    facts = run(live_sources("what is my solar production and any movie downloading",
                             settings_with_hosts(), {"finance"}, transport=httpx.MockTransport(handler())))
    assert facts == []


def test_finance_not_allowed_skips_bills():
    facts = run(live_sources("what bills are due", settings_with_hosts(), {"household"},
                             transport=httpx.MockTransport(handler())))
    assert facts == []


def test_solar_fact_no_token_contributes_nothing():
    s = settings_with_hosts(ha_token="")
    facts = run(live_sources("how much solar today", s, ALL_CLASSES, transport=httpx.MockTransport(handler())))
    assert facts == []


def test_solar_fact_success():
    facts = run(live_sources("what's my battery level", settings_with_hosts(), ALL_CLASSES,
                             transport=httpx.MockTransport(handler())))
    assert len(facts) == 1
    f = facts[0]
    assert f.plugin == "live.solar" and "42W" in f.text


def test_solar_fact_all_calls_fail_contributes_nothing():
    facts = run(live_sources("battery status please", settings_with_hosts(), ALL_CLASSES,
                             transport=httpx.MockTransport(handler(solar_ok=False, solar_status=500))))
    assert facts == []


def test_solar_fact_network_error_contributes_nothing():
    facts = run(live_sources("grid power now", settings_with_hosts(), ALL_CLASSES,
                             transport=httpx.MockTransport(handler(raise_on={"homeassistant"}))))
    assert facts == []


def test_bills_fact_network_error():
    facts = run(live_sources("what bills are due", settings_with_hosts(), ALL_CLASSES,
                             transport=httpx.MockTransport(handler(raise_on={"finance-api"}))))
    assert facts == []


def test_bills_fact_non_200():
    facts = run(live_sources("any payment due", settings_with_hosts(), ALL_CLASSES,
                             transport=httpx.MockTransport(handler(bills_status=500))))
    assert facts == []


def test_bills_fact_none_past_due():
    bills = [{"merchant": "Netflix", "status": "active", "expected_median": "199", "next_expected": "2026-10-01"}]
    facts = run(live_sources("bills due this month", settings_with_hosts(), ALL_CLASSES,
                             transport=httpx.MockTransport(handler(bills=bills))))
    assert len(facts) == 1 and "nothing currently past due" in facts[0].text


def test_bills_fact_past_due_and_due_soon():
    bills = [
        {"merchant": "Electricity", "status": "past_due", "expected_median": "2500", "next_expected": "2026-09-20T00:00:00"},
        {"merchant": "Internet", "status": "due_soon", "expected_median": "999", "next_expected": "2026-10-01T00:00:00"},
        {"merchant": "Gym", "status": "active", "expected_median": "500", "next_expected": "2026-10-05"},
    ]
    facts = run(live_sources("what bills are due", settings_with_hosts(), ALL_CLASSES,
                             transport=httpx.MockTransport(handler(bills=bills))))
    assert len(facts) == 1
    assert "Electricity" in facts[0].text and "Internet" in facts[0].text and "Gym" not in facts[0].text
    assert facts[0].plugin == "live.finance" and facts[0].uri == "/finance/"


def test_media_fact_no_api_keys_contributes_nothing():
    s = settings_with_hosts(radarr_api_key="", sonarr_api_key="")
    facts = run(live_sources("is my movie downloading", s, ALL_CLASSES, transport=httpx.MockTransport(handler())))
    assert len(facts) == 1 and "nothing is currently downloading" in facts[0].text


def test_media_fact_network_error_treated_as_nothing():
    facts = run(live_sources("any torrent active", settings_with_hosts(), ALL_CLASSES,
                             transport=httpx.MockTransport(handler(raise_on={"radarr-host", "sonarr-host"}))))
    assert len(facts) == 1 and "nothing is currently downloading" in facts[0].text


def test_media_fact_non_200_treated_as_nothing():
    facts = run(live_sources("new episode release", settings_with_hosts(), ALL_CLASSES,
                             transport=httpx.MockTransport(handler(radarr_status=500, sonarr_status=500))))
    assert len(facts) == 1 and "nothing is currently downloading" in facts[0].text


def test_media_fact_movies_downloading():
    records = [{"title": "Some.Movie.2026", "trackedDownloadState": "downloading"}]
    facts = run(live_sources("is that movie downloading", settings_with_hosts(), ALL_CLASSES,
                             transport=httpx.MockTransport(handler(radarr_records=records))))
    assert len(facts) == 1
    assert "Movies downloading now" in facts[0].text and "Some.Movie.2026" in facts[0].text
    assert facts[0].plugin == "live.media"


def test_media_fact_episodes_downloading():
    records = [{"title": "Some.Show.S01E01", "status": "warning"}]
    facts = run(live_sources("new episode", settings_with_hosts(), ALL_CLASSES,
                             transport=httpx.MockTransport(handler(sonarr_records=records))))
    assert len(facts) == 1 and "Episodes downloading now" in facts[0].text


def test_media_fact_both_movies_and_episodes():
    facts = run(live_sources("torrent movie and series status", settings_with_hosts(), ALL_CLASSES,
                             transport=httpx.MockTransport(handler(
                                 radarr_records=[{"title": "M", "trackedDownloadState": "downloading"}],
                                 sonarr_records=[{"title": "S", "trackedDownloadState": "downloading"}]))))
    assert len(facts) == 1 and " | " in facts[0].text


def test_all_three_providers_together():
    bills = [{"merchant": "Water", "status": "past_due", "expected_median": "300", "next_expected": "2026-09-01"}]
    facts = run(live_sources("solar battery, bills due, and any movie downloading",
                             settings_with_hosts(), ALL_CLASSES,
                             transport=httpx.MockTransport(handler(bills=bills,
                                                                    radarr_records=[{"title": "M"}]))))
    plugins = [f.plugin for f in facts]
    assert plugins == ["live.solar", "live.finance", "live.media"]


def test_live_fact_is_a_plain_namedtuple():
    f = LiveFact("live.solar", "title", "/uri", "text")
    assert f.plugin == "live.solar" and f.title == "title" and f.uri == "/uri" and f.text == "text"
