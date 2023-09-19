import logging

from .main import SchemaController, publish_schema
from .parser.decorators import openapi_view
from .parser.extractors import (
    Cookie,
    FileUpload,
    FileUploadReader,
    Header,
    Json,
    MultiPart,
    MultiPartReader,
    MultipleFileUpload,
    Param,
    Text,
)

__all__ = (
    "openapi_view",
    "publish_schema",
    "SchemaController",
    "VERSION",
    "logger",
    "Param",
    "Header",
    "Cookie",
    "Json",
    "Text",
    "FileUpload",
    "FileUploadReader",
    "MultipleFileUpload",
    "MultiPartReader",
    "MultiPart",
)

VERSION = "0.0.2"

logger = logging.getLogger("aiohttp_openapi")
logger.setLevel(logging.WARNING)
logger.addHandler(logging.NullHandler())
