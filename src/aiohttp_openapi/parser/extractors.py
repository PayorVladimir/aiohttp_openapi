"""Module contains Extractors - classes that can extract value from request."""

import abc
import json
from collections import namedtuple

import aiohttp
import pydantic
from aiohttp import web

from aiohttp_openapi import exceptions

from .enums import Locations


class Undefined:
    pass


class Extractor(abc.ABC):
    """
    Base class to define extractors.

    Extractor is and object that can get value from request
    according to specification (type, default value). Class of extractor is responsible
    to where it finds data, e.g. Query extractor gets values from request.query
    and Json extracts from request body.

    Attributes:
        parser (type): callable that turn string into value (e.g. int).
        default (object): Value if field not in request. If parser is not given
            explicitly, parser is set to type(default).
    """

    _in_ = None

    Undefined = Undefined

    def __init__(self, parser_or_default=Undefined, default=Undefined, **extra):
        if parser_or_default == self.Undefined == default:
            # not accept Extractor()
            signature_str = "parser_or_default=Undefined, default=Undefined"
            raise exceptions.UnacceptableSignature(
                f"At least one argument needed for"
                f"{self.__class__.__name__}.__init__({signature_str})"
            )

        self.required = True
        if default is not self.Undefined:
            # Extractor(int, 42)
            self.default, self.required = default, False
        if parser_or_default is self.Undefined:
            # Extractor(default=42)
            self.parser = type(self.default)
        elif callable(parser_or_default):
            # Extractor(int)
            self.parser = parser_or_default
        else:
            # Extractor(42)
            self.default, self.required = parser_or_default, False
            self.parser = type(parser_or_default)

        self._alias = extra.pop("name", None)
        self._python_name = None
        self.extra = extra

    def __repr__(self):
        return "{}({})".format(
            self.__class__.__name__, ", ".join(map(repr, self.init_args))
        )

    @property
    def alias(self):
        """
        Name of the parameter that will be used during request parsing and in schema.

        See also: `python_name`.
        """
        return self._alias or self._python_name

    @property
    def python_name(self):
        """
        Name of the parameter in python code.

        E.g. if developer writes note=Json(NoteModel) library will set
        python_name to 'note' in the object created by Json(NoteModel).
        It will be used to determine name of the field during request parsing and
        schema generation if it was not set explicitly (self._alias).
        For example, it allows to use snake_case notation in python code while
        providing camelCase variables in API.
        """
        return self._python_name

    @python_name.setter
    def python_name(self, value):
        self._python_name = value

    @property
    def has_schema_default(self):
        return not self.required and self.default is not None

    @property
    def init_args(self) -> tuple:
        args = [self.parser]
        if not self.required:
            args.append(self.default)
        return tuple(args)

    @property
    def init_kwargs(self) -> tuple:
        kwargs = dict(self.extra)
        if self._alias is not None:
            kwargs["name"] = self._alias
        return kwargs

    @abc.abstractmethod
    async def extract(self, request: web.Request):
        raise NotImplementedError

    @staticmethod
    def is_request_cls(request):
        return issubclass(request, web.Request)


class Param(Extractor):
    """
    Path or Query parameter.
    """

    async def extract(self, request: web.Request):
        raise NotImplementedError


class _Query(Param):

    _in_ = Locations.query

    async def extract(self, request: web.Request):
        raw_value = request.query.get(self.alias, self.Undefined)
        if raw_value is self.Undefined:
            if not self.required:
                return self.default
            else:
                raise exceptions.MissingValueError(self.alias, self._in_)
        try:
            value = self.parser(raw_value)
        except ValueError as e:
            raise exceptions.WrongValueError(self.alias, self._in_, e)
        return value


class _Path(Param):
    _in_ = Locations.path

    async def extract(self, request: web.Request):
        raw_value = request.match_info[self.alias]
        try:
            value = self.parser(raw_value)
        except ValueError as e:
            raise exceptions.WrongValueError(self.alias, self._in_, e)
        return value


class Header(Param):
    _in_ = Locations.header


class Cookie(Param):
    _in_ = Locations.cookie


class Body(Extractor):
    _content_ = None

    @property
    def is_multipart(self):
        return isinstance(self, MultiPartReader)


class Json(Body):
    _content_ = "application/json"
    _in_ = Locations.json

    async def extract(self, request: web.Request):
        try:
            request_data = await request.json()
            if issubclass(self.parser, pydantic.BaseModel):
                value = self.parser.parse_obj(request_data)
            else:
                value = self.parser(request_data)
        except (
            json.JSONDecodeError,
            UnicodeDecodeError,
            pydantic.ValidationError,
        ) as e:
            raise exceptions.WrongValueError("__root__", self._in_, e)
        return value


class Text(Body):
    _content_ = "text/plain"
    _in_ = Locations.text

    def __init__(self, parser_or_default=Undefined, default=Undefined, **extra):
        if parser_or_default == default == Undefined:
            parser_or_default = str
        super().__init__(parser_or_default, default, **extra)

    async def extract(self, request: web.Request):
        try:
            request_data = await request.text()
            value = self.parser(request_data)
        except UnicodeDecodeError as e:
            raise exceptions.WrongValueError("__root__", self._in_, e)
        return value


class FileUpload(Body):
    _content_ = "application/octet-stream"
    _in_ = Locations.binary

    def __init__(self, parser_or_default=Undefined, default=Undefined, **extra):
        if parser_or_default == default == Undefined:
            parser_or_default = bytes
        super().__init__(parser_or_default, default, **extra)

    async def extract(self, request: web.Request):
        try:
            request_data = await request.read()
            value = self.parser(request_data)
        except UnicodeDecodeError as e:
            raise exceptions.WrongValueError("__root__", self._in_, e)
        return value


class FileUploadReader(FileUpload):
    async def extract(self, request: web.Request) -> aiohttp.streams.StreamReader:
        return request.content


class MultipleFileUpload(Body):
    _content_ = "multipart/form-data"
    _in_ = Locations.multipart

    async def extract(self, request):
        request_data = {}
        async for part in await request.multipart():
            _raise_if_not_part_name(part, self._in_)
            part_python_type = _guess_python_type(part.headers.get("Content-Type"))
            try:
                if part_python_type is str:
                    part_value = await part.text()
                elif part_python_type is bytes:
                    part_value = await part.read()
                elif part_python_type is dict:
                    part_value = await part.json()
            except ValueError as e:
                raise exceptions.WrongValueError(part.name, self._in_, e)
            request_data[part.name] = part_value

        try:
            if issubclass(self.parser, pydantic.BaseModel):
                value = self.parser.parse_obj(request_data)
            else:
                value = self.parser(request_data)
        except (ValueError, pydantic.ValidationError) as e:
            raise exceptions.WrongValueError("__root__", self._in_, e)
        return value


class MultiPartReader(Body):
    _content_ = "multipart/mixed"
    _in_ = Locations.multipart

    def __init__(self, *_, **parts_extractors):
        self.extractors = parts_extractors
        self.required = True
        self.parser = bytes
        self._alias_to_extractor = {}
        for python_name, extractor in self.extractors.items():
            extractor.python_name = python_name
            self._alias_to_extractor[extractor.alias] = extractor

    async def extract(self, request: web.Request):
        return self._reader(request)

    async def _reader(self, request):
        async for part in await request.multipart():
            _raise_if_not_part_name(part, self._in_)
            part_extractor = self._alias_to_extractor.get(part.name)
            yield part, part_extractor


class MultiPart(MultiPartReader):
    async def extract(self, request: web.Request):
        values = {}
        reader = await super().extract(request)
        async for part, part_extractor in reader:
            values[part_extractor.python_name] = await part_extractor.extract(part)
        MultipartValues = namedtuple("MultipartValues", list(self.extractors.keys()))
        return MultipartValues(**values)


def _raise_if_not_part_name(part, location):
    if not part.name:
        raise web.HTTPBadRequest(
            headers={"Content-type": "application/json"},
            body=json.dumps(
                {
                    "msg": (
                        "Name is required in Content-Disposition header, "
                        "got {}".format(part.headers["Content-Disposition"])
                    ),
                    "in": location,
                    "type": "MissingValueError",
                }
            ),
        )


def _is_pydantic_model(cls):
    return type(cls) is pydantic.main.ModelMetaclass


def _guess_python_type(content_type: str):
    if content_type.startswith("text/plain"):
        return str
    return _CONTENT_TYPE_TO_PYTHON_TYPE.get(content_type, bytes)


_CONTENT_TYPE_TO_PYTHON_TYPE = {
    "text/plain": str,
    "application/octet-stream": bytes,
    "application/json": dict,
}
