"""Module contains decorators to be used to enable functionality for handler."""

import asyncio as aio
import functools
import inspect
import re
import typing as t
from dataclasses import dataclass

from aiohttp import hdrs, web

from aiohttp_openapi import exceptions

from . import enums, extractors, func_inspector


def openapi_view(openapi_handler=None, **meta):
    """Return function or class than can be used by aiohttp library as handler."""
    if openapi_handler is None:
        # @openapi_view(response_status=400)
        # def openapi_handler(spam: int, ham: str)
        return _AiohttpHandlerMaker(**meta)

    # @openapi_view
    # def openapi_handler(spam: int, ham: str):
    assert callable(openapi_handler), f"Expected callble, got {repr(openapi_handler)}"
    handler_maker = _AiohttpHandlerMaker()
    handler = handler_maker(openapi_handler)
    return handler


@dataclass(init=False)
class MetaInfo:
    def __init__(
        self,
        response_status=None,
        content_type=enums.ContentType.application_json,
        *,
        response_description=None,
        tag=None,
        tags=tuple(),
        deprecated=None,
    ):
        self.response_status = response_status
        self.response_description = response_description
        self.content_type = enums.ContentType(content_type)
        if tags:
            if tag is not None:
                raise exceptions.UnacceptableSignature(
                    "Cannot use both 'tag' and 'tags' attributes."
                )
            self.tags = tags
        elif tag:
            self.tags = [tag]
        else:
            self.tags = tuple()
        self.deprecated = deprecated


class _AiohttpHandlerMaker:

    _ERR_RESPONSE_STATUS = 400

    def __init__(self, **meta):
        self.meta = MetaInfo(**meta)

    def __call__(self, openapi_handler) -> t.Callable:
        if inspect.isclass(openapi_handler):
            return self.make_class_view(openapi_handler)
        else:
            return self.make_handler(openapi_handler)

    def make_handler(self, openapi_handler) -> t.Callable:
        """Make usual aiohttp handler (that accepts `request` or `self`)."""
        self.set_meta(openapi_handler)
        self.mark_openapi_handler(openapi_handler)

        @functools.wraps(openapi_handler)
        async def handler(*args):
            assert 0 < len(args) < 3
            if isinstance(args[-1], web.Request):
                request = args[-1]  # (request,) or (self, request) or (cls, request)
            else:
                request = args[0].request  # (self,)

            errors = []
            try:
                kwargs, unmatched = await _parse_arguments(request, openapi_handler)
            except exceptions.ValidationError as e:
                errors.extend(e.errors())
            if errors:
                return web.json_response(data=errors, status=self._ERR_RESPONSE_STATUS)

            result = await openapi_handler(*args[: len(unmatched)], **kwargs)
            return result

        return handler

    def make_class_view(self, cls: web.View) -> web.View:
        for method in hdrs.METH_ALL:
            if method_handler := getattr(cls, method.lower(), None):
                if self.get_openapi_handler(method_handler):
                    continue
                aiohttp_method = openapi_view(method_handler)
                setattr(cls, method.lower(), aiohttp_method)
        return cls

    def set_meta(self, func):
        func.meta = self.meta

    @staticmethod
    def get_meta(func):
        return func.meta

    @staticmethod
    def is_openapi_handler(func) -> bool:
        return getattr(func, "_is_openapi_handler", False)

    @staticmethod
    def mark_openapi_handler(openapi_handler):
        openapi_handler._is_openapi_handler = True

    @staticmethod
    def get_openapi_handler(handler):
        while wrapped := getattr(handler, "__wrapped__", None):
            if _AiohttpHandlerMaker.is_openapi_handler(wrapped):
                return wrapped


async def _parse_arguments(
    request, openapi_handler
) -> t.Tuple[t.Dict[str, t.Any], t.List[str]]:
    """
    Return map of openapi_handler parameters to its values.

    Values extracted from request.
    """
    path_param_names = set(request.match_info.keys())
    extractors, unmatched, _ = func_inspector.make_extractors_for_handler(
        openapi_handler, path_param_names
    )
    arguments = await _extract_arguments(request, extractors)
    return arguments, unmatched


async def _extract_arguments(
    request: web.Request, extractors: t.Dict[str, extractors.Extractor]
) -> t.Dict[str, t.Any]:
    param_names = list(extractors.keys())
    values = await aio.gather(
        *(extractors[param_name].extract(request) for param_name in param_names)
    )
    return dict(zip(param_names, values))


class RouteInfo(t.NamedTuple):
    """
    Result of inspecting route.

    Combination of analyzing resource path and aiohttp handler.
    """

    extractors: t.Dict[str, extractors.Extractor]
    inspect_info: func_inspector.InspectInfo
    meta: MetaInfo


def gen_routes_info(route):
    """
    Return all info from parsing openapi handler for route.
    """
    for method, openapi_handler in _gen_openapi_handlers(route):
        path_param_names = _get_path_param_names_for_resource(route.resource)
        extractors_info = func_inspector.make_extractors_for_handler(
            openapi_handler, path_param_names
        )
        route_extractors, _, inspect_info = extractors_info
        param_extractors = set(
            extractor.alias
            for extractor in route_extractors.values()
            if isinstance(extractor, extractors.Param)
        )
        for path_param_name in path_param_names:
            if path_param_name not in param_extractors:
                raise exceptions.UnacceptableSignature(
                    f"Route {route} have path parameter '{path_param_name}' "
                    f"without declared extractor like `{path_param_name}=Param(...)` "
                    f"or `ham=Param(..., name={path_param_name})`"
                )
        meta = _AiohttpHandlerMaker.get_meta(openapi_handler)
        yield method, RouteInfo(route_extractors, inspect_info, meta)


def _gen_openapi_handlers(route):
    if route.method in hdrs.METH_ALL:
        handlers = [(route.method, route.handler)]
    else:
        handlers = []
        handler_cls = route.handler
        for method in hdrs.METH_ALL:
            handler = getattr(handler_cls, method.lower(), None)
            if handler:
                handlers.append((method, handler))

    for method, handler in handlers:
        if openapi_handler := _AiohttpHandlerMaker.get_openapi_handler(handler):
            yield method, openapi_handler


def _get_path_param_names_for_resource(resource) -> t.Set[str]:
    """Return set of names of path parameters from path."""
    path = resource.canonical
    if not ("{" in path or "}" in path):
        return set()
    DYN = re.compile(r"\{(?P<var>[_a-zA-Z][_a-zA-Z0-9]*)\}")
    return set(DYN.findall(path))
