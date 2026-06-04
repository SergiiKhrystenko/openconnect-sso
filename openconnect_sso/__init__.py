import importlib.metadata as importlib_metadata

_metadata = importlib_metadata.metadata("openconnect-sso")

__version__ = _metadata["Version"]
__description__ = _metadata["Summary"]
