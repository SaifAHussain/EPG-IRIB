"""
Tests for EPG-IRIB generate_epg.py

Covers the pure-logic functions that parse, normalize, and convert
programme data into XMLTV — no network calls involved.
"""

import json
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import pytest

from generate_epg import (
    IRAN_TZ,
    ms_to_xmltv,
    parse_radio_quran_html,
    parse_radio_quran_json,
    radio_quran_to_xmltv,
    sepehr_programmes_to_xmltv,
)

# ── Fixture paths ────────────────────────────────────────────────────────────

FIXTURES = Path(__file__).parent / "fixtures"
HTML_FIXTURE = FIXTURES / "radio_quran_page.html"
JSON_FIXTURE = FIXTURES / "radio_quran_feed.json"
FULL_HTML_FIXTURE = Path(__file__).parent.parent / "quranradiosource.txt"


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_tv() -> ET.Element:
    """Create a minimal XMLTV root element for tests."""
    return ET.Element("tv")


def _day_start(year=2026, month=2, day=19) -> datetime:
    """Return midnight of a given date in Iran TZ."""
    return datetime(year, month, day, 0, 0, 0, tzinfo=IRAN_TZ)


def _get_programmes(tv: ET.Element) -> list[ET.Element]:
    """Return all <programme> elements from the XMLTV tree."""
    return tv.findall("programme")


# ═══════════════════════════════════════════════════════════════════════════
#  ms_to_xmltv
# ═══════════════════════════════════════════════════════════════════════════


class TestMsToXmltv:
    def test_known_epoch(self):
        # 2026-02-19 00:00:00 +0330 = 2026-02-18 20:30:00 UTC
        # = 1771362600 seconds = 1771362600000 ms
        dt = datetime(2026, 2, 19, 0, 0, 0, tzinfo=IRAN_TZ)
        ms = int(dt.timestamp() * 1000)
        result = ms_to_xmltv(ms)
        assert result.startswith("20260219000000")
        assert "+0330" in result

    def test_midday(self):
        dt = datetime(2026, 2, 19, 12, 30, 0, tzinfo=IRAN_TZ)
        ms = int(dt.timestamp() * 1000)
        result = ms_to_xmltv(ms)
        assert result.startswith("20260219123000")

    def test_end_of_day(self):
        dt = datetime(2026, 2, 19, 23, 59, 59, tzinfo=IRAN_TZ)
        ms = int(dt.timestamp() * 1000)
        result = ms_to_xmltv(ms)
        assert result.startswith("20260219235959")


# ═══════════════════════════════════════════════════════════════════════════
#  parse_radio_quran_html
# ═══════════════════════════════════════════════════════════════════════════


class TestParseRadioQuranHtml:
    @pytest.fixture()
    def html_fixture(self) -> str:
        return HTML_FIXTURE.read_text(encoding="utf-8")

    def test_parses_correct_count(self, html_fixture):
        programmes = parse_radio_quran_html(html_fixture)
        assert len(programmes) == 3

    def test_first_programme_fields(self, html_fixture):
        programmes = parse_radio_quran_html(html_fixture)
        first = programmes[0]
        assert first["time"] == "00:00"
        assert first["title"] == "تیك تاك"
        assert first["duration"] == 5
        assert first["image"].startswith("https://radio.ir/")
        assert first["description"]  # non-empty

    def test_times_are_zero_padded(self, html_fixture):
        programmes = parse_radio_quran_html(html_fixture)
        for p in programmes:
            h, m = p["time"].split(":")
            assert len(h) == 2 and len(m) == 2

    def test_all_have_required_keys(self, html_fixture):
        required_keys = {"time", "title", "description", "duration", "image"}
        programmes = parse_radio_quran_html(html_fixture)
        for p in programmes:
            assert required_keys <= set(p.keys())

    def test_durations_are_positive_ints(self, html_fixture):
        programmes = parse_radio_quran_html(html_fixture)
        for p in programmes:
            assert isinstance(p["duration"], int)
            assert p["duration"] > 0

    def test_descriptions_have_no_html_tags(self, html_fixture):
        programmes = parse_radio_quran_html(html_fixture)
        for p in programmes:
            assert "<br" not in p["description"]
            assert "</" not in p["description"]

    def test_empty_html_returns_empty(self):
        assert parse_radio_quran_html("") == []

    def test_garbage_html_returns_empty(self):
        assert parse_radio_quran_html("<html><body>nothing here</body></html>") == []

    @pytest.mark.skipif(
        not FULL_HTML_FIXTURE.exists(),
        reason="Full page source quranradiosource.txt not present",
    )
    def test_full_page_source(self):
        """Smoke test against the full saved page source."""
        html = FULL_HTML_FIXTURE.read_text(encoding="utf-8")
        programmes = parse_radio_quran_html(html)
        # The full page should have many programmes (80+)
        assert len(programmes) >= 80
        # Spot-check the first one
        assert programmes[0]["time"] == "00:00"
        assert programmes[0]["title"]
        assert programmes[0]["duration"] > 0


# ═══════════════════════════════════════════════════════════════════════════
#  parse_radio_quran_json
# ═══════════════════════════════════════════════════════════════════════════


class TestParseRadioQuranJson:
    @pytest.fixture()
    def json_data(self) -> dict:
        return json.loads(JSON_FIXTURE.read_text(encoding="utf-8"))

    def test_parses_valid_entries(self, json_data):
        programmes = parse_radio_quran_json(json_data)
        # 5 valid + 1 empty (skipped) + 1 invalid time (skipped) + 1 relative image = 6
        assert len(programmes) == 6

    def test_skips_empty_title(self, json_data):
        programmes = parse_radio_quran_json(json_data)
        titles = [p["title"] for p in programmes]
        assert "" not in titles

    def test_skips_invalid_time(self, json_data):
        programmes = parse_radio_quran_json(json_data)
        titles = [p["title"] for p in programmes]
        # "باید رد شود" has time="invalid", should be skipped
        assert "باید رد شود" not in titles

    def test_zero_pads_times(self, json_data):
        programmes = parse_radio_quran_json(json_data)
        # "0:00" -> "00:00", "0:5" -> "00:05", "5:5" -> "05:05"
        times = [p["time"] for p in programmes]
        assert "00:00" in times
        assert "00:05" in times
        assert "05:05" in times

    def test_relative_image_gets_prefix(self, json_data):
        programmes = parse_radio_quran_json(json_data)
        relative_img = [p for p in programmes if p["title"] == "مسیر نسبی"]
        assert len(relative_img) == 1
        assert relative_img[0]["image"].startswith("https://radioquran.ir/")

    def test_absolute_image_unchanged(self, json_data):
        programmes = parse_radio_quran_json(json_data)
        first = programmes[0]
        assert first["image"].startswith("https://radio.ir/")

    def test_duration_is_zero(self, json_data):
        """JSON feed durations are always empty, so parsed as 0."""
        programmes = parse_radio_quran_json(json_data)
        for p in programmes:
            assert p["duration"] == 0

    def test_description_is_empty(self, json_data):
        """JSON feed has no descriptions."""
        programmes = parse_radio_quran_json(json_data)
        for p in programmes:
            assert p["description"] == ""

    def test_same_schema_as_html_parser(self, json_data):
        """Both parsers return dicts with the same keys."""
        expected_keys = {"time", "title", "description", "duration", "image"}
        programmes = parse_radio_quran_json(json_data)
        for p in programmes:
            assert set(p.keys()) == expected_keys

    def test_empty_containers(self):
        assert parse_radio_quran_json({"Containers": []}) == []

    def test_missing_containers(self):
        assert parse_radio_quran_json({}) == []

    def test_empty_boxes(self):
        assert parse_radio_quran_json({"Containers": [{"boxes": []}]}) == []


# ═══════════════════════════════════════════════════════════════════════════
#  radio_quran_to_xmltv
# ═══════════════════════════════════════════════════════════════════════════


class TestRadioQuranToXmltv:
    @pytest.fixture()
    def sample_programmes(self) -> list[dict]:
        return [
            {
                "time": "00:00",
                "title": "تیك تاك",
                "description": "اعلام ساعت",
                "duration": 5,
                "image": "https://radio.ir/img1.jpg",
            },
            {
                "time": "00:05",
                "title": "تلاوت",
                "description": "تلاوت قرآن كریم",
                "duration": 15,
                "image": "https://radio.ir/img2.jpg",
            },
            {
                "time": "00:20",
                "title": "میان برنامه",
                "description": "",
                "duration": 0,
                "image": "",
            },
        ]

    def test_returns_correct_count(self, sample_programmes):
        tv = _make_tv()
        count = radio_quran_to_xmltv(tv, sample_programmes, "RadioQuran", _day_start())
        assert count == 3

    def test_programme_elements_added(self, sample_programmes):
        tv = _make_tv()
        radio_quran_to_xmltv(tv, sample_programmes, "RadioQuran", _day_start())
        progs = _get_programmes(tv)
        assert len(progs) == 3

    def test_start_time_format(self, sample_programmes):
        tv = _make_tv()
        radio_quran_to_xmltv(tv, sample_programmes, "RadioQuran", _day_start())
        progs = _get_programmes(tv)
        # First programme starts at 00:00
        assert progs[0].get("start").startswith("20260219000000")
        assert "+0330" in progs[0].get("start")

    def test_stop_from_duration(self, sample_programmes):
        tv = _make_tv()
        radio_quran_to_xmltv(tv, sample_programmes, "RadioQuran", _day_start())
        progs = _get_programmes(tv)
        # First programme: 00:00 + 5min = 00:05
        assert progs[0].get("stop").startswith("20260219000500")
        # Second programme: 00:05 + 15min = 00:20
        assert progs[1].get("stop").startswith("20260219002000")

    def test_stop_inferred_from_next_when_no_duration(self):
        """When duration is 0, stop is inferred from the next programme."""
        programmes = [
            {
                "time": "10:00",
                "title": "A",
                "description": "",
                "duration": 0,
                "image": "",
            },
            {
                "time": "10:30",
                "title": "B",
                "description": "",
                "duration": 0,
                "image": "",
            },
        ]
        tv = _make_tv()
        radio_quran_to_xmltv(tv, programmes, "RadioQuran", _day_start())
        progs = _get_programmes(tv)
        # First should infer stop from second's start
        assert progs[0].get("stop").startswith("20260219103000")
        # Last programme has no stop (no duration, no next programme)
        assert progs[1].get("stop") is None

    def test_duration_preferred_over_next_start(self):
        """When duration is set, it takes priority over next programme start."""
        programmes = [
            {
                "time": "10:00",
                "title": "A",
                "description": "",
                "duration": 60,
                "image": "",
            },
            {
                "time": "10:30",
                "title": "B",
                "description": "",
                "duration": 0,
                "image": "",
            },
        ]
        tv = _make_tv()
        radio_quran_to_xmltv(tv, programmes, "RadioQuran", _day_start())
        progs = _get_programmes(tv)
        # Duration says 60 min -> 11:00, even though next starts at 10:30
        assert progs[0].get("stop").startswith("20260219110000")

    def test_channel_attribute(self, sample_programmes):
        tv = _make_tv()
        radio_quran_to_xmltv(tv, sample_programmes, "MyChannel", _day_start())
        progs = _get_programmes(tv)
        for p in progs:
            assert p.get("channel") == "MyChannel"

    def test_title_element(self, sample_programmes):
        tv = _make_tv()
        radio_quran_to_xmltv(tv, sample_programmes, "RadioQuran", _day_start())
        progs = _get_programmes(tv)
        title_el = progs[0].find("title")
        assert title_el is not None
        assert title_el.text == "تیك تاك"
        assert title_el.get("lang") == "fa"

    def test_description_included_when_present(self, sample_programmes):
        tv = _make_tv()
        radio_quran_to_xmltv(tv, sample_programmes, "RadioQuran", _day_start())
        progs = _get_programmes(tv)
        desc = progs[0].find("desc")
        assert desc is not None
        assert desc.text == "اعلام ساعت"
        assert desc.get("lang") == "fa"

    def test_description_omitted_when_empty(self, sample_programmes):
        tv = _make_tv()
        radio_quran_to_xmltv(tv, sample_programmes, "RadioQuran", _day_start())
        progs = _get_programmes(tv)
        # Third programme has empty description
        desc = progs[2].find("desc")
        assert desc is None

    def test_icon_included_when_present(self, sample_programmes):
        tv = _make_tv()
        radio_quran_to_xmltv(tv, sample_programmes, "RadioQuran", _day_start())
        progs = _get_programmes(tv)
        icon = progs[0].find("icon")
        assert icon is not None
        assert icon.get("src") == "https://radio.ir/img1.jpg"

    def test_icon_omitted_when_empty(self, sample_programmes):
        tv = _make_tv()
        radio_quran_to_xmltv(tv, sample_programmes, "RadioQuran", _day_start())
        progs = _get_programmes(tv)
        icon = progs[2].find("icon")
        assert icon is None

    def test_skips_empty_title(self):
        programmes = [
            {
                "time": "10:00",
                "title": "",
                "description": "",
                "duration": 5,
                "image": "",
            },
            {
                "time": "10:05",
                "title": "   ",
                "description": "",
                "duration": 5,
                "image": "",
            },
            {
                "time": "10:10",
                "title": "Valid",
                "description": "",
                "duration": 5,
                "image": "",
            },
        ]
        tv = _make_tv()
        count = radio_quran_to_xmltv(tv, programmes, "RadioQuran", _day_start())
        assert count == 1

    def test_skips_invalid_time(self):
        programmes = [
            {
                "time": "bad",
                "title": "A",
                "description": "",
                "duration": 5,
                "image": "",
            },
            {
                "time": "10:00",
                "title": "B",
                "description": "",
                "duration": 5,
                "image": "",
            },
        ]
        tv = _make_tv()
        count = radio_quran_to_xmltv(tv, programmes, "RadioQuran", _day_start())
        assert count == 1

    def test_empty_list(self):
        tv = _make_tv()
        count = radio_quran_to_xmltv(tv, [], "RadioQuran", _day_start())
        assert count == 0
        assert _get_programmes(tv) == []


# ═══════════════════════════════════════════════════════════════════════════
#  sepehr_programmes_to_xmltv
# ═══════════════════════════════════════════════════════════════════════════


class TestSepehrProgrammesToXmltv:
    @pytest.fixture()
    def sample_sepehr(self) -> list[dict]:
        base_ms = int(_day_start().timestamp() * 1000)
        return [
            {
                "id": 1,
                "start": base_ms,
                "duration": 30,
                "title": "برنامه صبحگاهی",
                "descSummary": "خلاصه",
                "descFull": "توضیح کامل برنامه صبحگاهی",
                "imageUrl": "https://example.com/img.jpg",
            },
            {
                "id": 2,
                "start": base_ms + 30 * 60 * 1000,
                "duration": 60,
                "title": "تلاوت قرآن",
                "descSummary": "تلاوت",
                "descFull": "",
                "imageUrl": "",
            },
            {
                "id": 3,
                "start": base_ms + 90 * 60 * 1000,
                "duration": 0,
                "title": "بدون مدت",
                "descSummary": "",
                "descFull": "",
                "imageUrl": None,
            },
        ]

    def test_returns_correct_count(self, sample_sepehr):
        tv = _make_tv()
        count = sepehr_programmes_to_xmltv(tv, sample_sepehr, "QuranTV")
        assert count == 3

    def test_start_time(self, sample_sepehr):
        tv = _make_tv()
        sepehr_programmes_to_xmltv(tv, sample_sepehr, "QuranTV")
        progs = _get_programmes(tv)
        assert progs[0].get("start").startswith("20260219000000")

    def test_stop_from_duration(self, sample_sepehr):
        tv = _make_tv()
        sepehr_programmes_to_xmltv(tv, sample_sepehr, "QuranTV")
        progs = _get_programmes(tv)
        # 00:00 + 30min = 00:30
        assert progs[0].get("stop").startswith("20260219003000")
        # 00:30 + 60min = 01:30
        assert progs[1].get("stop").startswith("20260219013000")

    def test_no_stop_when_duration_zero(self, sample_sepehr):
        tv = _make_tv()
        sepehr_programmes_to_xmltv(tv, sample_sepehr, "QuranTV")
        progs = _get_programmes(tv)
        assert progs[2].get("stop") is None

    def test_prefers_descfull_over_descsummary(self, sample_sepehr):
        tv = _make_tv()
        sepehr_programmes_to_xmltv(tv, sample_sepehr, "QuranTV")
        progs = _get_programmes(tv)
        desc = progs[0].find("desc")
        assert desc is not None
        assert desc.text == "توضیح کامل برنامه صبحگاهی"

    def test_falls_back_to_descsummary(self, sample_sepehr):
        tv = _make_tv()
        sepehr_programmes_to_xmltv(tv, sample_sepehr, "QuranTV")
        progs = _get_programmes(tv)
        desc = progs[1].find("desc")
        assert desc is not None
        assert desc.text == "تلاوت"

    def test_no_desc_when_both_empty(self, sample_sepehr):
        tv = _make_tv()
        sepehr_programmes_to_xmltv(tv, sample_sepehr, "QuranTV")
        progs = _get_programmes(tv)
        desc = progs[2].find("desc")
        assert desc is None

    def test_icon_included(self, sample_sepehr):
        tv = _make_tv()
        sepehr_programmes_to_xmltv(tv, sample_sepehr, "QuranTV")
        progs = _get_programmes(tv)
        icon = progs[0].find("icon")
        assert icon is not None
        assert icon.get("src") == "https://example.com/img.jpg"

    def test_no_icon_when_empty(self, sample_sepehr):
        tv = _make_tv()
        sepehr_programmes_to_xmltv(tv, sample_sepehr, "QuranTV")
        progs = _get_programmes(tv)
        assert progs[1].find("icon") is None

    def test_no_icon_when_none(self, sample_sepehr):
        tv = _make_tv()
        sepehr_programmes_to_xmltv(tv, sample_sepehr, "QuranTV")
        progs = _get_programmes(tv)
        assert progs[2].find("icon") is None

    def test_channel_attribute(self, sample_sepehr):
        tv = _make_tv()
        sepehr_programmes_to_xmltv(tv, sample_sepehr, "MyChannelID")
        progs = _get_programmes(tv)
        for p in progs:
            assert p.get("channel") == "MyChannelID"

    def test_skips_missing_start(self):
        programmes = [{"title": "No start", "duration": 10}]
        tv = _make_tv()
        count = sepehr_programmes_to_xmltv(tv, programmes, "QuranTV")
        assert count == 0

    def test_skips_missing_title(self):
        programmes = [{"start": 1000000, "duration": 10, "title": ""}]
        tv = _make_tv()
        count = sepehr_programmes_to_xmltv(tv, programmes, "QuranTV")
        assert count == 0

    def test_skips_whitespace_only_title(self):
        programmes = [{"start": 1000000, "duration": 10, "title": "   "}]
        tv = _make_tv()
        count = sepehr_programmes_to_xmltv(tv, programmes, "QuranTV")
        assert count == 0

    def test_empty_list(self):
        tv = _make_tv()
        count = sepehr_programmes_to_xmltv(tv, [], "QuranTV")
        assert count == 0


# ═══════════════════════════════════════════════════════════════════════════
#  Integration: HTML fixture -> XMLTV
# ═══════════════════════════════════════════════════════════════════════════


class TestHtmlToXmltvIntegration:
    """End-to-end: parse HTML fixture then convert to XMLTV."""

    def test_html_fixture_to_xmltv(self):
        html = HTML_FIXTURE.read_text(encoding="utf-8")
        programmes = parse_radio_quran_html(html)
        assert len(programmes) > 0

        tv = _make_tv()
        count = radio_quran_to_xmltv(tv, programmes, "RadioQuran", _day_start())
        assert count == len(programmes)

        progs = _get_programmes(tv)
        # Every programme has a title
        for p in progs:
            title_el = p.find("title")
            assert title_el is not None
            assert title_el.text

        # Every programme from HTML has a description (they all had one in fixture)
        for p in progs:
            desc_el = p.find("desc")
            assert desc_el is not None

        # Every programme from HTML has a stop time (they all had durations)
        for p in progs:
            assert p.get("stop") is not None

    def test_json_fixture_to_xmltv(self):
        data = json.loads(JSON_FIXTURE.read_text(encoding="utf-8"))
        programmes = parse_radio_quran_json(data)
        assert len(programmes) > 0

        tv = _make_tv()
        count = radio_quran_to_xmltv(tv, programmes, "RadioQuran", _day_start())
        assert count == len(programmes)

        progs = _get_programmes(tv)
        # JSON programmes have no descriptions
        for p in progs:
            assert p.find("desc") is None

        # JSON programmes have no durations, so stop is inferred from next
        # (except the last one, which has no stop)
        last_prog = progs[-1]
        assert last_prog.get("stop") is None

    @pytest.mark.skipif(
        not FULL_HTML_FIXTURE.exists(),
        reason="Full page source quranradiosource.txt not present",
    )
    def test_full_page_to_xmltv(self):
        """Smoke test: full page -> parse -> XMLTV with many programmes."""
        html = FULL_HTML_FIXTURE.read_text(encoding="utf-8")
        programmes = parse_radio_quran_html(html)
        tv = _make_tv()
        count = radio_quran_to_xmltv(tv, programmes, "RadioQuran", _day_start())
        assert count >= 80

        # Serialise to XML string and verify it's well-formed
        xml_str = ET.tostring(tv, encoding="unicode")
        reparsed = ET.fromstring(xml_str)
        assert len(reparsed.findall("programme")) == count
