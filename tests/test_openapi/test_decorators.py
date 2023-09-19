import datetime
import json
import logging
import sys
import uuid
from typing import List, Optional

import pytest
from aiohttp import web
from pydantic import BaseModel

from aiohttp_openapi import exceptions
from aiohttp_openapi.parser.decorators import openapi_view
from aiohttp_openapi.parser.extractors import Extractor, Json, Param, Text
from aiohttp_openapi.parser.func_inspector import make_extractors_for_handler


async def get_json(resp, expected_status=200):
    if resp.status != expected_status:
        logger.error(await resp.text())
    return await resp.json()


class Note(BaseModel):
    id: uuid.UUID
    title: str
    content: Optional[str]
    owner_id: int
    created: datetime.datetime


class NoteList(BaseModel):
    __root__: List[Note]


@openapi_view
async def int_view(note_id=Param(int), note=Json(Note)):
    return web.json_response({"note_id": note_id, "note": json.loads(note.json())})


@openapi_view
async def one_view(note_id=Param(43)):
    return web.json_response({"note_id": note_id})


@openapi_view
async def one_default_view(note_id=Param(default=43)):
    return note_id


@openapi_view
async def undefined_view(note_id=Param(str)):
    return note_id


@openapi_view
async def mixed_query_params(note_id=Param(int, default=43)):
    return note_id


@openapi_view
async def body_view(note=Json(Note)):
    return note


@openapi_view
async def int_view_simple(note_id: int, note: Note):
    return web.json_response({"note_id": note_id, "note": note.dict()})


@openapi_view
async def one_view_simple(note_id=43):
    return web.json_response({"note_id": note_id})


@openapi_view
async def one_default_view_simple(note_id=43):
    return note_id


@openapi_view
async def undefined_view_simple(note_id: str):
    return note_id


@openapi_view
async def mixed_query_params_simple(note_id: int = 43):
    return note_id


@openapi_view
async def body_view_simple(note: Note):
    return note


@openapi_view
async def post_many_view(notes: NoteList):
    return web.json_response(text=notes.json())


@pytest.mark.parametrize("declaration_type", ["full", "simple"])
@pytest.mark.parametrize(
    "func_to_expected_params",
    [
        (int_view, {"note_id": [int, Param], "note": [Note, Json]}),
        (one_view, {"note_id": [int, Param, 43]}),
        (one_default_view, {"note_id": [int, Param, 43]}),
        (undefined_view, {"note_id": [str, Param]}),
        (mixed_query_params, {"note_id": [int, Param, 43]}),
        (body_view, {"note": [Note, Json]}),
    ],
)
def test_parse_arguments(func_to_expected_params, declaration_type):
    view, expected = func_to_expected_params
    if declaration_type == "simple":
        this = sys.modules[__name__]
        view = getattr(this, view.__name__ + "_simple", None)
        if not view:
            pytest.skip("Not implemented")
    params, unmatched, _ = make_extractors_for_handler(view)

    assert not unmatched
    undefined = object()
    for name, parser_and_default in expected.items():
        parser, extractor_cls, *_default = parser_and_default + [undefined]
        default = _default[0]
        param = params[name]
        assert isinstance(param, Extractor)
        assert param.parser is parser
        assert getattr(param, "default", undefined) == default


@pytest.fixture
async def client(aiohttp_client):
    app = web.Application()
    r = app.router
    r.add_get("/one_view", one_view)
    r.add_get("/int_view", int_view)
    r.add_post("/create_many", post_many_view)
    client = await aiohttp_client(app)
    try:
        yield client
    finally:
        await client.close()


@pytest.mark.parametrize("query_resp", [("", 43), ("?note_id=13", 13)])
async def test_extract_params(client, query_resp):
    query, number = query_resp
    resp = await client.get("/one_view" + query)
    data = await get_json(resp)
    assert data == {"note_id": number}


async def test_extract_body_dict(client):
    now = datetime.datetime.now()
    note_data = {
        "id": str(uuid.uuid4()),
        "title": "test_title",
        "owner_id": 2,
        "created": now.isoformat(),
    }
    resp = await client.get("/int_view?note_id=13", json=note_data)
    data = await get_json(resp)
    assert data["note_id"] == 13
    for k in note_data:
        assert data["note"][k] == note_data[k]
    assert data["note"]["content"] is None


async def test_extract_body_list(client):
    now = datetime.datetime.now
    notes = [
        {
            "id": str(uuid.uuid4()),
            "title": f"test_title_{i}",
            "owner_id": 2,
            "created": now().isoformat(),
            "content": None,
        }
        for i in range(3)
    ]
    resp = await client.post("/create_many", json=notes)
    data = await get_json(resp)
    assert data == notes


async def bad_view1(self, request, unannotated_param):
    """More than one param without annotation."""


async def bad_view2(request: web.Request, unannotated_param):
    """More than one param without annotation."""


async def bad_view3(body1=Json(dict), body2=Text()):
    """Two bodies are forbidden."""


async def bad_view4(a: Param(int)):
    """One should write `a=Param(int)`."""


async def bad_view5(a: Param):
    """One should use instance of extractor, not class"""


async def bad_view6(a=Param):
    """One should use instance of extractor, not class"""


bad_views = [bad_view1, bad_view2, bad_view3, bad_view4, bad_view5, bad_view6]


@pytest.mark.parametrize("view", bad_views)
def test_unacceptable_signature(view):
    with pytest.raises(exceptions.UnacceptableSignature):
        try:
            extractors = make_extractors_for_handler(view)
        except Exception as e:
            print(repr(e))
            raise
        else:
            print(extractors)


async def echo(request):
    print(f"{request=}")
    print(f"query={request.query}")
    return web.json_response(await request.json())


@openapi_view
async def view1(request):
    return await echo(request)


@openapi_view
async def view2(custom_named_request):
    return await echo(custom_named_request)


@openapi_view
async def view3(request: web.Request) -> web.Response:
    return await echo(request)


@openapi_view
async def view4(req: web.Request):
    return await echo(req)


@openapi_view
async def view5(request, note_id: int, note: Note):
    return web.json_response({"note": json.loads(note.json()), "note_id": note_id})


@openapi_view
async def view6(request, note_id=Param(int), note=Json(Note)):
    return web.json_response({"note": json.loads(note.json()), "note_id": note_id})


@pytest.mark.parametrize(
    "func_to_expected_params",
    [
        (view1, {}, ["request"]),
        (view2, {}, ["custom_named_request"]),
        (view3, {}, ["request"]),
        (view4, {}, ["req"]),
        (
            view5,
            {
                "note_id": [int, Param],
                "note": [Note, Json],
            },
            ["request"],
        ),
        (
            view6,
            {
                "note_id": [int, Param],
                "note": [Note, Json],
            },
            ["request"],
        ),
    ],
)
async def test_parse_request(func_to_expected_params):
    view, expected_params, expected_unmatched = func_to_expected_params

    params, unmatched, _ = make_extractors_for_handler(view)

    undefined = object()
    assert len(params) == len(expected_params)
    for name, parser_and_default in expected_params.items():
        parser, extractor_cls, *_default = parser_and_default + [undefined]
        expected_default = _default[0]
        param = params[name]
        assert isinstance(param, Extractor)
        assert param.parser is parser
        assert getattr(param, "default", undefined) == expected_default
    assert unmatched == expected_unmatched


@pytest.fixture
def make_client(aiohttp_client):
    async def _make_client(view):
        app = web.Application()
        app.router.add_get("/view", view)
        client = await aiohttp_client(app)
        return client

    return _make_client


@pytest.mark.parametrize("view", [view1, view2, view3, view4, view5, view6])
async def test_extract_request(view, make_client):
    client = await make_client(view)
    note = Note(
        id=uuid.uuid4(), title="test_note", owner_id=13, created=datetime.datetime.now()
    )
    note_dict = json.loads(note.json())
    data = {"note_id": 42, "note": note_dict}
    if view in [view5, view6]:
        resp = await client.get("/view?note_id=42", json=note_dict)
    else:
        resp = await client.get("/view", json=data)
    assert await resp.json() == data


logger = logging.getLogger(__name__)
