import datetime
import json
import tempfile
import uuid
from pprint import pprint
from typing import Optional

import pytest
import yaml
from aiohttp import web
from pydantic import BaseModel

try:
    from openapi_spec_validator import openapi_v30_spec_validator as validator
except ImportError:
    from openapi_spec_validator import openapi_v3_spec_validator as validator

from aiohttp_openapi import exceptions
from aiohttp_openapi.main import publish_schema
from aiohttp_openapi.openapi.schema import make_schema
from aiohttp_openapi.parser.decorators import openapi_view
from aiohttp_openapi.parser.extractors import Param


class CreateNote(BaseModel):
    title: str
    content: Optional[str]
    owner_id: int


class Note(CreateNote):
    id: uuid.UUID
    created: datetime.datetime


def test_dumb_schema():
    dumb_schema = make_schema(app=None, title="Test Title", version="1.0.0")
    validator.validate(dumb_schema.dict())


async def view1(request):
    pass


async def view2(request: web.Request):
    pass


async def view3(request: web.Request) -> web.Response:
    pass


@openapi_view
async def view4(request: web.Request, note: CreateNote):
    pass


@openapi_view
async def view5(request: web.Request, note: CreateNote) -> web.Response:
    pass


@openapi_view
async def view6(request: web.Request, note: CreateNote) -> Note:
    pass


@openapi_view
async def view7(note: CreateNote) -> Note:
    pass


aiohttp_views = [view1, view2, view3]
views = [
    openapi_view(view1),  # request is an str requred param
    openapi_view(view2),  # request is an str requred param
    openapi_view(
        view3
    ),  # AttributeError: type object 'Response' has no attribute 'schema
    view4,
    view5,
    view6,  # description 'null', request is an str requred param
    view7,
]


@pytest.fixture
async def app(aiohttp_client):
    app = web.Application()
    return app


@pytest.mark.parametrize("view", aiohttp_views)
async def test_ignore_aiohttp_views(view, app):
    app.router.add_post("/note_view", view)
    schema = make_schema(app, title="Blank note view", version="0.0.1")
    schema_dict = schema.dict()
    print(yaml.dump(schema_dict))
    validator.validate(schema_dict)
    assert schema_dict == {
        "info": {"title": "Blank note view", "version": "0.0.1"},
        "openapi": "3.0.0",
        "paths": {"/note_view": {}},
    }


@pytest.mark.parametrize("note_view", views)
async def test_note_view(note_view, app):
    app.router.add_post("/note_view", note_view)
    schema = make_schema(app, title="Test note view", version="0.0.1")
    schema_dict = schema.dict()
    print(yaml.dump(schema_dict))
    validator.validate(schema_dict)
    parameters = schema_dict["paths"]["/note_view"]["post"]["parameters"]
    for param in parameters:
        assert "request" not in param.values()


@pytest.fixture
def openapi_file_name():
    fd, name = tempfile.mkstemp(suffix="gradual_transfer_openapi.json")
    return name


@pytest.fixture
async def gradual_transfer_app(openapi_file_name, loop):
    app = web.Application()
    for view in views:
        try:
            app.router.add_get("/" + view.__name__, view)
        except AttributeError:
            pass
    publish_schema(
        app,
        title="Blank API",
        version="0.0.1",
        json_path=openapi_file_name,
        url_path="/",
    )
    return app


async def test_gradual_transfer(openapi_file_name, gradual_transfer_app):
    with open(openapi_file_name) as f:
        schema_dict = json.load(f)
    pprint(schema_dict)
    for resource, route in schema_dict["paths"].items():
        parameters = route["get"]["parameters"]
        for param in parameters:
            assert param["name"] != "request"


async def test_raises_when_unmatched_path_param():
    with pytest.raises(exceptions.UnacceptableSignature):
        app = web.Application()

        @openapi_view
        async def openapi_handler(pk_param=Param(int)):
            pass

        app.router.add_get("/unmatched/{id_param}", openapi_handler)
        try:
            publish_schema(app, title="test_app", version="0.1")
        except Exception as e:
            print(repr(e))
            raise
