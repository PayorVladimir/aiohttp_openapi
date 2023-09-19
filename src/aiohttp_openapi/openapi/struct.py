"""Contains classes for OpenAPI objects."""

import enum
from typing import Any, Dict, List
from typing import Optional as O  # noqa: E741
from typing import Union as U

from pydantic import BaseModel, Field


class BaseObject(BaseModel):
    def dict(self, **kw):
        kw["by_alias"] = True
        kw["exclude_none"] = True
        kw["exclude_unset"] = True
        return super().dict(**kw)

    class Config:
        allow_population_by_field_name = True


class BaseMapObject(BaseObject):
    def __setitem__(self, key, value):
        if not self.__root__:
            self.__root__ = dict()
        self.__root__[key] = value


class ReferenceObject(BaseObject):
    ref_: str = Field(alias="$ref")


class SequrityRequirementObject(BaseMapObject):
    __root__: Dict[str, List[str]] = dict()


class ServerVariableObject(BaseObject):
    enum: O[List[str]]
    default: str
    description: O[str]


class ServerObject(BaseObject):
    url: str
    description: O[str]
    variables: O[Dict[str, ServerVariableObject]]


class ExampleObject(BaseObject):
    summary: O[str]
    description: O[str]
    value: O[Any]
    externalValue: O[str]


class XMLObject(BaseObject):
    name: O[str]
    namespace: O[str]
    prefix: O[str]
    attribute: O[bool]
    wrapped: O[bool]


class DiscriminatorObject(BaseObject):
    propertyName: str
    mapping: O[Dict[str, str]]


class ExternalDocumentationObject(BaseObject):
    description: O[str]
    url: str


SchemaOrRef = U[ReferenceObject, "SchemaObject"]


class SchemaObject(BaseObject):
    title: O[str]
    multipleOf: O[str]
    maximum: O[Any]
    exclusiveMaximum: O[str]
    minimum: O[Any]
    exclusiveMinimum: O[str]
    maxLength: O[str]
    minLength: O[str]
    pattern: O[str]
    maxItems: O[str]
    minItems: O[str]
    uniqueItems: O[str]
    maxProperties: O[str]
    minProperties: O[str]
    required: O[List[str]]
    enum: O[List["str"]]

    type: O[str]
    allOf: O[List[SchemaOrRef]]
    oneOf: O[List[SchemaOrRef]]
    anyOf: O[List[SchemaOrRef]]
    not_: O[List[SchemaOrRef]] = Field(alias="not")
    items: O[SchemaOrRef]
    properties: O[Dict[str, SchemaOrRef]]
    additionalProperties: O[U[bool, "SchemaObject"]]
    description: O[str]
    format: O[str]
    default: O[Any]

    nullable: O[bool]
    discriminator: O[DiscriminatorObject]
    readOnly: O[bool]
    writeOnly: O[bool]
    xml: O[XMLObject]
    externalDocs: O[ExternalDocumentationObject]
    example: O[Any]
    deprecated: O[bool]


SchemaObject.update_forward_refs()


class PahlessInEnum(str, enum.Enum):
    query = "query"
    header = "header"
    cookie = "cookie"


class InEnum(str, enum.Enum):
    query = "query"
    header = "header"
    cookie = "cookie"
    path = "path"


class BaseHeaderObject(BaseObject):
    description: O[str]
    required: O[bool]
    deprecated: O[bool]
    allow_empty_value: O[bool] = Field(alias="allowEmptyValue")


class BaseParameterObject(BaseHeaderObject):
    name: str
    in_: InEnum = Field(alias="in")

    def dict(self, **kw):
        result = super().dict(**kw)
        result["in"] = result["in"].value
        return result


class SimpleParameterOrHeader(BaseObject):
    style: O[str]
    explode: O[bool]
    allowReserved: O[bool]
    schema_: SchemaObject = Field(alias="schema")
    example: O[Any]
    examples: O[Dict[str, U[ExampleObject, ReferenceObject]]]


class SimpleHeaderObject(BaseHeaderObject, SimpleParameterOrHeader):
    pass


class SimpleParameterObject(BaseParameterObject, SimpleParameterOrHeader):
    @classmethod
    def get_common_fields_with_schema_object(cls):
        return set(cls.__fields__).intersection(set(SchemaObject.__fields__))


class ComplexParameterOrHeader(BaseObject):
    content: Dict[str, "MediaTypeObject"]


class ComplexHeaderObject(BaseHeaderObject, ComplexParameterOrHeader):
    pass


class ComplexParameterObject(BaseParameterObject, ComplexParameterOrHeader):
    pass


HeaderObject = U[SimpleHeaderObject, ComplexHeaderObject]
ParameterObject = U[SimpleParameterObject, ComplexParameterObject]


class EncodingObject(BaseObject):
    contentType: O[str]
    headers: O[Dict[str, U[HeaderObject, ReferenceObject]]]
    style: O[str]
    explode: O[bool]
    allowReserved: O[bool]


class MediaTypeObject(BaseObject):
    schema_: O[SchemaOrRef] = Field(alias="schema")
    example: O[Any]
    examples: O[Dict[str, U[ExampleObject, ReferenceObject]]]
    encoding: O[Dict[str, EncodingObject]]


ComplexParameterOrHeader.update_forward_refs()


class LinkObject(BaseObject):
    operationRef: O[str]
    operationId: O[str]
    parameters: O[Dict[str, Any]]
    requestBody: O[Any]
    description: O[str]
    server: O[ServerObject]


class ResponseObject(BaseObject):
    description: str
    headers: O[Dict[str, U[HeaderObject, ReferenceObject]]]
    content: O[Dict[str, MediaTypeObject]]
    links: O[Dict[str, U[LinkObject, ReferenceObject]]]


class ResponsesObject(BaseObject):
    __root__: Dict[str, U[ResponseObject, ReferenceObject]]


class RequestBodyObject(BaseObject):
    description: O[str]
    content: Dict[str, MediaTypeObject]
    required: O[bool]


class CallbackObject(BaseMapObject):
    __root__: Dict[str, "PathItemObject"]


class OperationObject(BaseObject):
    tags: O[List[str]]
    summary: O[str]
    description: O[str]
    exteralDocs: O[ExternalDocumentationObject]
    operationId: O[str]
    parameters: O[List[U[ParameterObject, ReferenceObject]]]
    requestBody: O[U[RequestBodyObject, ReferenceObject]]
    responses: ResponsesObject
    callbacks: O[Dict[str, U[CallbackObject, ReferenceObject]]]
    deprecated: O[bool]
    security: O[List[SequrityRequirementObject]]
    servers: O[List[ServerObject]]


class PathItemObject(BaseObject):
    ref_: O[str] = Field(alias="$ref")
    summary: O[str]
    description: O[str]

    get: O[OperationObject]
    put: O[OperationObject]
    post: O[OperationObject]
    delete: O[OperationObject]
    options: O[OperationObject]
    head: O[OperationObject]
    patch: O[OperationObject]
    trace: O[OperationObject]

    servers: O[List[ServerObject]]
    parameters: O[List[U[ParameterObject, ReferenceObject]]]


CallbackObject.update_forward_refs()


class PathsObject(BaseMapObject):
    __root__: Dict[str, U[PathItemObject]] = dict()


class OAuthFlowsObject(BaseObject):
    authorizationUrl: str
    tokenUrl: str
    refreshUrl: O[str]
    scopes: Dict[str, str]


class SecuritySchemeType(str, enum.Enum):
    api_key = "apiKey"
    http = "http"
    oauth2 = "oauth2"
    open_id_connect = "openIdConnect"


class AnySecuritySchemeObject(BaseObject):
    type: SecuritySchemeType
    description: O[str]


class ApiKeySecuritySchemeObject(AnySecuritySchemeObject):
    name: str
    in_: PahlessInEnum


class HTTPSecuritySchemeObject(AnySecuritySchemeObject):
    scheme: str
    bearerFormat: O[str]


class OAuth2SecuritySchemeObject(AnySecuritySchemeObject):
    flows: OAuthFlowsObject


class OpenIdConnectSecuritySchemeObject(AnySecuritySchemeObject):
    openIdConnectUrl: str


SecuritySchemeObject = U[
    ApiKeySecuritySchemeObject,
    HTTPSecuritySchemeObject,
    OAuth2SecuritySchemeObject,
    OpenIdConnectSecuritySchemeObject,
]


class ComponentsObject(BaseObject):
    schemas: O[Dict[str, SchemaOrRef]]
    responses: O[Dict[str, U[ResponseObject, ReferenceObject]]]
    parameters: O[Dict[str, U[ParameterObject, ReferenceObject]]]
    examples: O[Dict[str, U[ExampleObject, ReferenceObject]]]
    requestBodies: O[Dict[str, U[RequestBodyObject, ReferenceObject]]]
    headers: O[Dict[str, U[HeaderObject, ReferenceObject]]]
    securitySchemes: O[Dict[str, U[SecuritySchemeObject, ReferenceObject]]]
    links: O[Dict[str, U[LinkObject, ReferenceObject]]]
    callbacks: O[Dict[str, U[CallbackObject, ReferenceObject]]]


class TagObject(BaseObject):
    name: str
    description: O[str]
    externalDocs: O[ExternalDocumentationObject]


class LicenseObject(BaseObject):
    name: str
    url: O[str]


class ContactObject(BaseObject):
    name: O[str]
    url: O[str]
    email: O[str]


class InfoObject(BaseObject):
    title: str
    description: O[str]
    termsOfService: O[str]
    contact: O[ContactObject]
    license: O[LicenseObject]
    version: str


class OpenAPIObject(BaseObject):
    openapi: str
    info: InfoObject
    servers: O[List[ServerObject]]
    paths: PathsObject = PathsObject()
    components: O[ComponentsObject]
    security: O[List[SequrityRequirementObject]]
    tags: O[List[TagObject]]
    externalDocs: O[ExternalDocumentationObject]
