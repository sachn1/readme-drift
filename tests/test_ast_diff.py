"""Tests for ast_diff module."""

from readme_check.ast_diff import diff_apis, extract_public_api
from readme_check.models import ChangeType

OLD_SOURCE = """
class Client:
    def connect(self, host, port):
        pass

    def disconnect(self):
        pass

    def _private(self):
        pass

def helper(x, y):
    pass
"""

NEW_SOURCE = """
class Client:
    def connect(self, url):
        pass

    def reconnect(self, url):
        pass

    def _private(self):
        pass

def helper(x, y):
    pass

def new_function(z):
    pass
"""


def test_extract_public_api_functions():
    api = extract_public_api(OLD_SOURCE)
    assert "helper" in api.functions
    assert "_private" not in api.functions


def test_extract_public_api_classes():
    api = extract_public_api(OLD_SOURCE)
    assert "Client" in api.classes
    assert "Client.connect" in api.methods
    assert "Client.disconnect" in api.methods
    assert "Client._private" not in api.methods


def test_diff_detects_signature_change():
    changes = diff_apis(OLD_SOURCE, NEW_SOURCE)
    names = [c.name for c in changes]
    types = [c.change_type for c in changes]
    assert "Client.connect" in names
    idx = names.index("Client.connect")
    assert types[idx] == ChangeType.SIGNATURE_CHANGED


def test_diff_detects_removed_method():
    changes = diff_apis(OLD_SOURCE, NEW_SOURCE)
    removed = [c for c in changes if c.change_type == ChangeType.REMOVED]
    assert any("disconnect" in c.name for c in removed)


def test_diff_detects_added_method():
    changes = diff_apis(OLD_SOURCE, NEW_SOURCE)
    added = [c for c in changes if c.change_type == ChangeType.ADDED]
    assert any("reconnect" in c.name for c in added)
    assert any("new_function" in c.name for c in added)


def test_diff_empty_old_source():
    changes = diff_apis("", NEW_SOURCE)
    types = {c.change_type for c in changes}
    assert ChangeType.ADDED in types
    assert ChangeType.REMOVED not in types


def test_diff_empty_new_source():
    changes = diff_apis(OLD_SOURCE, "")
    types = {c.change_type for c in changes}
    assert ChangeType.REMOVED in types
    assert ChangeType.ADDED not in types


def test_diff_no_changes():
    changes = diff_apis(OLD_SOURCE, OLD_SOURCE)
    assert changes == []


def test_rename_detection():
    old = "def foo(x, y):\n    pass\n"
    new = "def bar(x, y):\n    pass\n"
    changes = diff_apis(old, new)
    assert any(c.change_type == ChangeType.RENAMED for c in changes)


def test_private_methods_ignored():
    old = "class A:\n    def _hidden(self): pass\n"
    new = "class A:\n    def _hidden(self, extra): pass\n"
    changes = diff_apis(old, new)
    assert changes == []
