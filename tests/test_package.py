import importlib.metadata


def test_package_version():
    version = importlib.metadata.version("kv-wiki")
    assert version == "0.1.0"
