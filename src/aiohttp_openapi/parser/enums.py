"""Enumerations used by the package."""

from enum import Enum


class Locations(Enum):
    path = "path"
    query = "query"
    header = "header"
    cookie = "cookie"
    json = "body (json)"
    multipart = "body (multipart)"
    text = "body (text)"
    binary = "body (binary)"


class ContentType(Enum):
    application_json = "application/json"
    application_zip = "application/zip"
