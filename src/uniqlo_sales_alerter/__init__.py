"""Uniqlo Sales Alerter — monitors Uniqlo sales and sends notifications."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("uniqlo-sales-alerter")
except PackageNotFoundError:
    __version__ = "0.0.0"
