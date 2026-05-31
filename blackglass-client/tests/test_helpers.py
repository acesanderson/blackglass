from __future__ import annotations
import json
from blackglass_client.cli._output import _emit


def test_emit_compact_default(capsys):
    _emit({"a": 1, "b": 2}, pretty=False)
    captured = capsys.readouterr()
    assert captured.out == '{"a":1,"b":2}\n'


def test_emit_pretty(capsys):
    _emit({"a": 1}, pretty=True)
    captured = capsys.readouterr()
    assert captured.out == '{\n  "a": 1\n}\n'


def test_emit_none_writes_nothing(capsys):
    _emit(None, pretty=False)
    captured = capsys.readouterr()
    assert captured.out == ""


def test_emit_list(capsys):
    _emit([1, 2, 3], pretty=False)
    captured = capsys.readouterr()
    assert captured.out == "[1,2,3]\n"


from blackglass_client.cli._payloads import (
    patch_op_append,
    patch_op_prepend,
    patch_op_set_frontmatter,
    patch_op_replace,
)


def test_patch_op_append():
    assert patch_op_append("hello") == {"op": "append", "content": "hello"}


def test_patch_op_prepend():
    assert patch_op_prepend("hi") == {"op": "prepend", "content": "hi"}


def test_patch_op_set_frontmatter():
    assert patch_op_set_frontmatter("tag", "blue") == {
        "op": "set_frontmatter",
        "key": "tag",
        "value": "blue",
    }


def test_patch_op_replace_no_all():
    assert patch_op_replace("foo", "bar", False) == {
        "op": "replace",
        "old": "foo",
        "new": "bar",
        "replace_all": False,
    }


def test_patch_op_replace_all():
    assert patch_op_replace("foo", "bar", True) == {
        "op": "replace",
        "old": "foo",
        "new": "bar",
        "replace_all": True,
    }
