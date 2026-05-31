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
