"""
This module provides function signature inspection without knowing about app.

But it knows about extractors.
"""
import inspect
import logging
import typing as t

from aiohttp_openapi import exceptions

from . import extractors


class ParamInfo(t.NamedTuple):
    """Map python param name to default and annotation."""

    annotation: t.Any
    default: t.Any


class InspectInfo(t.NamedTuple):
    """Result of inspecting Python function (aiohttp handler)."""

    params_info: t.Dict[str, ParamInfo]
    return_type: type = None
    docstring: str = None


def make_extractors_for_handler(
    openapi_handler, path_param_names=None
) -> t.Tuple[t.Dict[str, extractors.Extractor], t.List[str], InspectInfo]:
    """Return map of python parameter name to extractor and func info."""
    inspect_info = _inspect_openapi_handler(openapi_handler)
    param_extractors, unmatched = _make_extractors_from_params_info(
        inspect_info.params_info, path_param_names
    )
    if len(unmatched) > 2:
        try:
            func_name = openapi_handler.__qualname__
        except AttributeError:
            func_name = openapi_handler.__name__
        unmatched_str = ",".join(p for p in unmatched)
        raise exceptions.UnacceptableSignature(
            f"Cannot process {func_name}. More than two params without "
            f"annotation or default: {unmatched_str}"
        )
    logger.debug(f"extractors={param_extractors}")
    return param_extractors, unmatched, inspect_info


def _inspect_openapi_handler(func) -> InspectInfo:
    """
    Extract info from Python function without any processing.
    """
    annotations = dict(func.__annotations__)
    return_type = annotations.pop("return", None)

    params = inspect.signature(func).parameters.values()
    params_info = {}
    for param in params:
        default = param.default
        if default is param.empty:
            default = extractors.Extractor.Undefined
        annotation = annotations.get(param.name, extractors.Extractor.Undefined)
        params_info[param.name] = ParamInfo(annotation, default)
    inspect_info = InspectInfo(
        params_info=params_info, return_type=return_type, docstring=func.__doc__
    )
    logger.debug(f"{func.__annotations__} -> {params_info} {return_type=}")
    return inspect_info


def _make_extractors_from_params_info(
    params_info: t.Dict[str, ParamInfo], path_param_names: t.Set = None
) -> t.Tuple[t.Dict[str, extractors.Extractor], t.List[str]]:
    """
    Make extractors from default and annotation.

    raises: exceptions.UnacceptableSignature
    """
    result = {}
    unmatched_params = []
    request_seen, body_seen = None, None
    for param_name, (annotation, default) in params_info.items():
        _check_typos(param_name, annotation, default)

        if extractors.Extractor.is_request_cls(annotation):
            if request_seen:
                raise exceptions.UnacceptableSignature(
                    f"No more than one annotation 'aiohttp.web.Request'"
                    f"is allowed: {param_name}. Previous was: {request_seen}."
                )
            request_seen = param_name
            unmatched_params.append(param_name)
            continue

        extractor = _make_extractor(annotation, default)

        if extractor is None:
            if request_seen:
                raise exceptions.UnacceptableSignature(
                    f"Parameters without annotation or default are not allowed after "
                    f"parameter with 'aiohttp.web.Request' annotation: {param_name}. "
                    f"Parameter was considered as aiohttp.web.Request: {request_seen}."
                )
            unmatched_params.append(param_name)
            continue

        if isinstance(extractor, extractors.Body):
            if body_seen:
                raise exceptions.UnacceptableSignature(
                    f"More than two Body extractors are not allowed: {param_name}. "
                    f"Previous was: {body_seen}"
                )
            body_seen = param_name

        if isinstance(extractor, extractors.Param) and path_param_names is not None:
            # For Param we should define if it is Query or Path.
            # path_param_names==None is special case for testing and the best
            # that we can do without information about path parameters from app
            if (extractor.alias or param_name) in path_param_names:
                extractor_cls = extractors._Path
            else:
                extractor_cls = extractors._Query
            extractor = extractor_cls(*extractor.init_args, **extractor.init_kwargs)

        extractor.python_name = param_name
        result[param_name] = extractor
    return result, unmatched_params


def _make_extractor(annotation, default) -> extractors.Extractor:
    # ignore what serves as request in typical view - position
    # parameter with no annotations
    # def handler(request) or def handler(self)
    if annotation == extractors.Undefined == default:
        return None

    if isinstance(default, extractors.Extractor):
        # Explicit declaration, use it
        # def handler(a=Text())
        # def handler(a=Query(int, 42))
        # def handler(a: str = Query(int))
        # If user provided annotation for value (last case), just ignore it - maybe
        # it is useful for type checking or documenting.
        return default

    if annotation is not extractors.Undefined:
        if extractors._is_pydantic_model(annotation):
            # def handler(a: MyModel = default_value)
            # which is the same as
            # def handler(a: Json(MyModel, default_value))
            return extractors.Json(annotation, default)
        # def handler(a: custom_parser = default_value)
        # same as
        # def handler(a: Param(custom_parser, default_value))
        return extractors.Param(annotation, default)

    assert annotation is extractors.Undefined
    assert default is not extractors.Undefined
    # No type annotation and not default with explicit extractors.Extractor
    # What can it be? `limit=1` or `user=User(id=0)`,
    parser = type(default)
    if extractors._is_pydantic_model(parser):
        # def handler(a=MyModel(x=1, y=2))
        return extractors.Json(parser, default)
    # def handler(a=2)
    return extractors.Param(parser, default)


def _check_typos(param_name, annotation, default):
    for item in [annotation, default]:
        if inspect.isclass(item) and issubclass(item, extractors.Extractor):
            raise exceptions.UnacceptableSignature(
                f"Usage of Extractor classes itself are not allowed: {item}."
                f"Please use instances of Extractor, e.g. `spam=Param(int)`"
            )
        if isinstance(annotation, extractors.Extractor):
            cls_name = annotation.__class__.__name__
            raise exceptions.UnacceptableSignature(
                f"Please use `{param_name}={cls_name}(...)` instead of "
                f"`{param_name}: {cls_name}(...)`."
            )


logger = logging.getLogger(__name__)
