"""Module related to OpenAPI Schema."""

import collections
import datetime
import enum
import logging
import typing as t
import uuid

from aiohttp import hdrs, web

from aiohttp_openapi.parser import decorators, extractors

from . import struct

DEFAULT_NO_BODY_STATUS = 204
DEFAULT_WITH_BODY_STATUS = 200
DEFAULT_DESCRIPTION = ""
DEFAULT_NO_BODY_DESCRITPTION = "OK"


def make_schema(app: web.Application, title: str, version: str):
    """
    Build swagger schema for application in internal format OpenAPIObject.
    """
    return SchemaMaker(app).make_schema(title, version)


class SchemaMaker:
    def __init__(self, app):
        self.app = app
        self.used_schemas = {}

    def make_schema(self, title: str, version: str, include_head=False):
        schema_obj = struct.OpenAPIObject(
            openapi=self.OPENAPI_VERSION,
            info=struct.InfoObject(title=title, version=version),
            paths=self._build_paths_object(self.app, include_head),
            components=self._build_components_object(),
        )
        return schema_obj

    def _build_paths_object(
        self, app: web.Application, include_head: bool
    ) -> struct.PathsObject:
        paths_obj = struct.PathsObject()
        if app is None:
            return paths_obj

        resources = collections.defaultdict(list)
        for route in app.router.routes():
            path = route.resource.canonical
            if include_head or route.method != hdrs.METH_HEAD:
                resources[path].append(route)

        for path, routes in resources.items():
            path_item = self._build_path_item_object(routes)
            paths_obj[path] = path_item

        return paths_obj

    def _build_path_item_object(
        self, routes: t.List[web.AbstractRoute]
    ) -> struct.PathItemObject:
        path_item = struct.PathItemObject()
        for route in routes:
            for method, route_info in decorators.gen_routes_info(route):
                operation_obj = self._build_operation_object(route_info)
                setattr(path_item, method.lower(), operation_obj)
        return path_item

    def _build_operation_object(
        self, route_info: decorators.RouteInfo
    ) -> struct.OperationObject:
        operation_parameters = []
        request_body = None
        for param_name, extractor in route_info.extractors.items():
            if isinstance(extractor, extractors.Body):
                schema = self._make_schema_for_body(extractor)
                request_body = struct.RequestBodyObject(
                    content={extractor._content_: struct.MediaTypeObject(schema=schema)}
                )
            else:
                operation_parameters.append(
                    struct.SimpleParameterObject(
                        name=extractor.alias or param_name,
                        in_=struct.InEnum[extractor._in_.name],
                        required=extractor.required,
                        schema_=self._make_schema_for_param(extractor),
                        **extractor.extra,
                    )
                )

        inspect_info = route_info.inspect_info
        responses = self._build_responses_object(
            route_info.meta, inspect_info.return_type
        )
        if inspect_info.docstring:
            summary_description = inspect_info.docstring.split("\n\n", 1)
            texts = dict(
                zip(("summary", "description"), map(str.strip, summary_description))
            )
        else:
            texts = dict()
        operation_obj = struct.OperationObject(
            responses=responses, parameters=operation_parameters, **texts
        )
        if tags := route_info.meta.tags:
            operation_obj.tags = tags
        if deprecated := route_info.meta.deprecated:
            operation_obj.deprecated = deprecated
        if request_body:
            operation_obj.requestBody = request_body
        return operation_obj

    def _build_responses_object(
        self, response_meta, return_type
    ) -> struct.ResponseObject:
        response_status = response_meta.response_status
        description = response_meta.response_description
        if response_status is None:
            if return_type is not None:
                response_status = DEFAULT_WITH_BODY_STATUS
            else:
                response_status = DEFAULT_NO_BODY_STATUS
                description = DEFAULT_NO_BODY_DESCRITPTION
        if description is None:
            description = DEFAULT_DESCRIPTION

        response_object = struct.ResponseObject(description=description)
        contentless_responses = struct.ResponsesObject.parse_obj(
            {str(response_status): response_object}
        )
        if return_type in (None, web.Response):
            return contentless_responses
        schema = self._get_schema_for_pydantic(
            return_type
        ) or self._get_schema_for_generic(return_type)
        if schema is None:
            logger.warning(
                f"Can not determine schema for return annotation: {return_type}."
                "Response schema will not be generated in OpenAPI Schema."
            )
            return contentless_responses
        response_object.content = {
            response_meta.content_type.value: struct.MediaTypeObject(schema=schema)
        }
        return struct.ResponsesObject.parse_obj({str(response_status): response_object})

    def _build_components_object(self) -> t.Optional[struct.ComponentsObject]:
        if self.used_schemas:
            return struct.ComponentsObject(schemas=self.used_schemas)

    def _make_schema_for_param(self, extractor):
        schema = self._get_schema_for_enum(extractor.parser)
        if schema is not None:
            if extractor.has_schema_default:
                schema["default"] = extractor.default.value
        else:
            schema = self._make_schema_for_primitive(extractor.parser)
            if extractor.has_schema_default:
                schema["default"] = extractor.default
        extra = {
            k: extractor.extra[k]
            for k in extractor.extra
            if k
            not in struct.SimpleParameterObject.get_common_fields_with_schema_object()
        }
        schema.update(extra)
        schema_obj = struct.SchemaObject.parse_obj(schema)
        return schema_obj.dict()

    def _make_schema_for_body(self, extractor):
        return (
            self._get_schema_for_multipart(extractor)
            or self._get_schema_for_pydantic(extractor.parser)
            or self._make_schema_for_primitive(extractor.parser)
        )

    def _get_schema_for_multipart(self, multi_extractor: extractors.MultiPartReader):
        if not multi_extractor.is_multipart:
            return None
        return {
            "type": "object",
            "properties": {
                part_extractor.alias
                or part_name: self._make_schema_for_body(part_extractor)
                for part_name, part_extractor in multi_extractor.extractors.items()
            },
        }

    def _get_schema_for_pydantic(self, cls):
        if not extractors._is_pydantic_model(cls):
            return None
        schema = dict(cls.schema(ref_template=self._REF_TEMPLATE))
        self.used_schemas.update(schema.pop("definitions", {}))
        model_name = schema.get("title", cls.__name__)
        if model_name not in self.used_schemas:
            self.used_schemas[model_name] = schema
        return {"$ref": self._REF_TEMPLATE.format(model=model_name)}

    def _get_schema_for_generic(self, cls):
        generic_type = t.get_origin(cls)
        if generic_type is not list:
            return None
        args = t.get_args(cls)
        if len(args) != 1:
            return None
        item_type = args[0]
        schema = self._get_schema_for_pydantic(
            item_type
        ) or self._get_schema_for_generic(item_type)
        if not schema:
            return None
        return {"type": "array", "items": schema}

    def _get_schema_for_enum(self, cls):
        if not isinstance(cls, enum.EnumMeta):
            return None
        values = [m.value for m in cls]
        if not values:
            logger.warning(
                f"Enumeration '{cls}' have no members and will be "
                "described as plain string id OpenAPI Schema."
            )
        value_type = type(values[0])
        schema = {"enum": values}
        value_schema = self._make_schema_for_primitive(value_type)
        schema["type"] = value_schema["type"]
        schema["format"] = value_schema.get("format")
        return schema

    def _make_schema_for_primitive(self, cls):
        type_, format_ = self._PYTHON_TYPE_TO_SWAGGER.get(cls, (None, None))
        if type_ is None:
            logger.warning(
                f"Class '{cls}' have no known schema and will be "
                "described as plain string id OpenAPI Schema."
            )
            type_, format_ = "string", None
        schema = {"type": type_}
        if format_ is not None:
            schema["format"] = format_
        return schema

    _REF_TEMPLATE = "#/components/schemas/{model}"

    _PYTHON_TYPE_TO_SWAGGER = {
        dict: ("object", None),
        bytes: ("string", "binary"),
        bytearray: ("string", "binary"),
        str: ("string", None),
        bool: ("boolean", None),
        int: ("integer", None),
        float: ("number", None),
        datetime.date: ("string", "date"),
        datetime.datetime: ("string", "date-time"),
        uuid.UUID: ("string", "uuid"),
    }

    OPENAPI_VERSION = "3.0.0"


logger = logging.getLogger(__name__)
