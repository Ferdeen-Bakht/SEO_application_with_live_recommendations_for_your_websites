from seo_lab import integrations as ig


def test_parse_rows_converts_ctr_and_rounds_position():
    resp = {"rows": [{"keys": ["paris travel guide"], "clicks": 12, "impressions": 340, "ctr": 0.0353, "position": 8.456}]}
    assert ig.parse_rows(resp, ["query"]) == [
        {"query": "paris travel guide", "clicks": 12, "impressions": 340, "ctr": 3.53, "position": 8.5}
    ]


def test_parse_rows_empty_response_means_no_data_not_zero_rows():
    assert ig.parse_rows({}, ["query"]) == []


def test_keyword_opportunities_only_uses_real_rows_that_meet_the_rules():
    rows = [
        {"query": "near page one", "impressions": 100, "clicks": 3, "ctr": 3.0, "position": 11.2},
        {"query": "top but ignored", "impressions": 500, "clicks": 4, "ctr": 0.8, "position": 3.0},
        {"query": "tiny", "impressions": 5, "clicks": 0, "ctr": 0.0, "position": 12.0},
        {"query": "doing fine", "impressions": 300, "clicks": 60, "ctr": 20.0, "position": 2.0},
        {"query": "too deep", "impressions": 300, "clicks": 0, "ctr": 0.0, "position": 45.0},
    ]
    found = [o["query"] for o in ig.keyword_opportunities(rows)]
    assert found == ["top but ignored", "near page one"]  # sorted by impressions; low-volume, healthy and deep queries are excluded


def test_default_range_ends_two_days_ago_and_spans_requested_days():
    from datetime import date, timedelta
    start, end = ig.default_range(28)
    assert end == (date.today() - timedelta(days=2)).isoformat()
    assert (date.fromisoformat(end) - date.fromisoformat(start)).days == 27


def test_mask_never_reveals_the_whole_secret():
    assert ig.mask("") == "not set"
    assert "abcdefghijklmnop" not in ig.mask("abcdefghijklmnop")


def test_ci_template_mentions_all_three_build_steps():
    text = ig.github_actions_template()
    assert "npm run build" in text and "dotnet build" in text and "pytest" in text
