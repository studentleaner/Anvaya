import re

from anvaya_api.ids import new_id


def test_format_and_prefix():
    assert re.fullmatch(r"conv_[0-9A-HJKMNP-TV-Z]{26}", new_id("conv"))
    assert new_id("act").startswith("act_")


def test_sortable_by_time_and_unique():
    a, b = new_id("msg", now_ms=1_000), new_id("msg", now_ms=2_000)
    assert a < b
    assert new_id("msg", now_ms=5) != new_id("msg", now_ms=5)
