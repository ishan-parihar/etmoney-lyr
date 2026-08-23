"""Edge-case tests for the low-level JS/RSC extraction layer."""

import pytest

from etmoney_lyr.jsvars import (
    extract_balanced,
    extract_js_var,
    extract_rsc_payload,
    find_json_objects,
    find_key,
    find_value,
    parse_js_var,
)


class TestExtractRscPayload:
    def test_empty_html(self):
        assert extract_rsc_payload("") == ""

    def test_no_pushes(self):
        assert extract_rsc_payload("<html><body>plain</body></html>") == ""

    def test_single_chunk(self):
        html = '<script>self.__next_f.push([1,"{\\"a\\":1}"])</script>'
        assert extract_rsc_payload(html) == '{"a":1}'

    def test_multiple_chunks_join_in_order(self):
        html = 'self.__next_f.push([1,"ab"])middle textself.__next_f.push([1,"cd"])'
        assert extract_rsc_payload(html) == "abcd"

    def test_unicode_escape(self):
        html = 'self.__next_f.push([1,"\\u20b982.81"])'
        assert extract_rsc_payload(html) == "₹82.81"

    def test_escaped_quote_and_backslash(self):
        html = 'self.__next_f.push([1,"x=\\"q\\" y=\\\\z"])'
        assert extract_rsc_payload(html) == 'x="q" y=\\z'

    def test_newline_tab_escapes(self):
        html = 'self.__next_f.push([1,"a\\nb\\tc"])'
        assert extract_rsc_payload(html) == "a\nb\tc"

    def test_truncated_escape_does_not_crash(self):
        html = 'self.__next_f.push([1,"ends with backslash\\\\"])'
        assert "ends with backslash" in extract_rsc_payload(html)


class TestExtractBalanced:
    def test_flat_object(self):
        assert extract_balanced('{"a":1}', 0) == '{"a":1}'

    def test_nested(self):
        s = '{"a":{"b":[1,2]},"c":3}'
        assert extract_balanced(s, 0) == s

    def test_braces_inside_string_ignored(self):
        s = '{"a":"not } a brace","b":1}'
        assert extract_balanced(s, 0) == s

    def test_escaped_quote_inside_string(self):
        s = '{"a":"he said \\"}\\" ok"}'
        assert extract_balanced(s, 0) == s

    def test_array_value(self):
        s = '[{"k":1},{"k":2}]'
        assert extract_balanced(s, 0) == s

    def test_unbalanced_returns_none(self):
        assert extract_balanced('{"a":1', 0) is None
        assert extract_balanced("[1,2", 0) is None

    def test_mismatched_nesting_is_callers_problem(self):
        # scanner tracks only opener/closer pairs of the root value; malformed
        # spans are caught downstream by json.loads in parse_js_var/find_value
        assert extract_balanced('{"a":1', 0) is None
        raw = extract_balanced("{[}", 0)
        assert raw is not None
        with pytest.raises(ValueError):
            import json

            json.loads(raw)


class TestExtractJsVar:
    HTML = """
    <script>
    var goodDto = {"a": 1, "list": [1,2]};
    var jsLiteral = {unquoted: "value", n: 5};
    var notBrace = "string";
    </script>
    """

    def test_finds_json_var(self):
        assert parse_js_var(self.HTML, "goodDto") == {"a": 1, "list": [1, 2]}

    def test_missing_var_returns_none(self):
        assert extract_js_var(self.HTML, "absent") is None
        assert parse_js_var(self.HTML, "absent") is None

    def test_non_json_literal_raw_extract(self):
        raw = extract_js_var(self.HTML, "jsLiteral")
        assert raw is not None and "unquoted" in raw
        assert parse_js_var(self.HTML, "jsLiteral") is None  # invalid JSON → None

    def test_string_var_skipped(self):
        # var assigned a string literal (no brace) must not match
        assert extract_js_var(self.HTML, "notBrace") is None

    def test_regex_special_chars_in_name_safe(self):
        assert extract_js_var("<script>var a.b+ = {};</script>", "a.b+") == "{}"


class TestFindValue:
    def test_extracts_array_value(self):
        payload = '{"meta":{"x":1},"stockList":[{"id":1},{"id":2}],"tail":2}'
        vals = find_value(payload, "stockList", limit=1)
        assert vals == [[{"id": 1}, {"id": 2}]]

    def test_object_value(self):
        payload = '{"card":{"sharpe":0.7}}'
        assert find_value(payload, "card")[0] == {"sharpe": 0.7}

    def test_missing_key_empty(self):
        assert find_value('{"a":1}', "zzz") == []

    def test_invalid_value_skipped(self):
        payload = '{"broken": [1,2}, "ok": [3]}'
        assert find_value(payload, "ok") == [[3]]

    def test_limit_respected(self):
        payload = '{"k":[1]},{"k":[2]},{"k":[3]}'
        assert len(find_value(payload, "k", limit=2)) == 2


class TestFindJsonObjects:
    def test_containment_and_dedup(self):
        payload = '{"stockList":[{"stockId":7,"price":1}]}'
        objs = find_json_objects(payload, "stockId", limit=3)
        assert len(objs) == 1 and objs[0]["stockId"] == 7

    def test_no_match(self):
        assert find_json_objects('{"a":1}', "zzz") == []

    def test_truncated_object_ignored(self):
        payload = '"stockId":9'  # no enclosing brace
        assert find_json_objects(payload, "stockId") == []


class TestFindKey:
    def test_quoted_string_value(self):
        assert find_key('{"name": "HDFC Bank"}', "name") == "HDFC Bank"

    def test_unquoted_number(self):
        assert find_key("{navValue: 82.81}", "navValue") == "82.81"

    def test_unquoted_string_js_literal(self):
        assert find_key("{riskometer: Very High, x: 1}", "riskometer") == "Very High"

    def test_negative_float(self):
        assert find_key('{"r": -12.5}', "r") == "-12.5"

    def test_missing(self):
        assert find_key('{"a": 1}', "b") is None
