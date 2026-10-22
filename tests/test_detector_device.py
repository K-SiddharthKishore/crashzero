from types import SimpleNamespace
import sys
import pytest
from src.detector import resolve_device


@pytest.mark.parametrize('cuda,mps,expected', [
    (True, True, 'cuda:0'), (False, True, 'mps'), (False, False, 'cpu'),
])
def test_auto_device(monkeypatch, cuda, mps, expected):
    monkeypatch.setitem(sys.modules, 'torch', SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: cuda),
        backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: mps))))
    assert resolve_device('auto') == expected
    assert resolve_device('cpu') == 'cpu'
    assert resolve_device('mps') == 'mps'
