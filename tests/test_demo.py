import datetime
import json
import logging
import tempfile
import uuid
from pathlib import Path
from pprint import pprint

import aiohttp
import pytest

from aiohttp_openapi.main import SchemaController

from .demo_notes import ViewImplementation, models
from .demo_notes.main import create_app

logger = logging.getLogger(__name__)


async def get_json(resp, expected_status=200):
    if resp.status != expected_status:
        logger.error(await resp.text())
        assert resp.status == expected_status
    return await resp.json()


async def get_singe_error(resp, expected_status=400):
    if resp.status != expected_status:
        logger.error(await resp.text())
    assert resp.status == expected_status
    resp_data = await resp.json()
    assert isinstance(resp_data, list)
    assert len(resp_data) == 1
    err_dict = resp_data[0]
    return err_dict


@pytest.fixture
async def make_client(aiohttp_client):
    _client = None

    async def _make_client(view_impl):
        nonlocal _client
        app = await create_app(view_impl, run_for_user=False)
        client = await aiohttp_client(app)
        client._view_impl = view_impl
        _client = client
        return client

    try:
        yield _make_client
    finally:
        models.database = {}
        if _client is not None:
            await _client.close()


@pytest.fixture(
    params=[
        ViewImplementation.aiohttp,
        ViewImplementation.extractors,
        ViewImplementation.classes,
        ViewImplementation.annotations,
    ]
)
async def demo_client(request, make_client):
    return await make_client(request.param)


@pytest.fixture
def note():
    return models.Note(
        id=uuid.uuid4(),
        created=datetime.datetime.utcnow(),
        title="existing note",
        owner_id=1,
    )


@pytest.fixture(params=["with_content", "no_content"])
def add_note_dict(request):
    content = {"title": "my new note", "owner_id": 2}
    if request.param == "with_content":
        content.update(content="Note text")
    return content


@pytest.fixture
def saved_note(monkeypatch, note):
    monkeypatch.setitem(models.database, note.id, note)
    return note


async def test_double_apply(make_client):
    client = await make_client(ViewImplementation.extractors)
    controller = SchemaController(client.app)
    kw = dict(title="Blank note view", version="0.0.1")
    assert controller.make_schema(**kw) == controller.make_schema(**kw)
    await client.close()


class TestNotePost:
    async def test_201(self, demo_client, add_note_dict):
        resp = await demo_client.post("/notes", json=add_note_dict)
        resp_data = await get_json(resp, 201)
        assert resp_data["id"]
        assert resp_data["created"]
        for key in add_note_dict:
            assert resp_data[key] == add_note_dict[key]
            assert add_note_dict.get("content") == resp_data.get("content")

    async def test_409(self, demo_client, saved_note):
        req_data = {"title": saved_note.title, "owner_id": 3}
        resp = await demo_client.post("/notes", json=req_data)
        assert resp.status == 409
        assert resp.reason.endswith("exists")

    @pytest.mark.parametrize("missing_field", ["owner_id", "title"])
    async def test_400_missing(self, demo_client, add_note_dict, missing_field):
        add_note_dict.pop(missing_field)
        resp = await demo_client.post("/notes", json=add_note_dict)
        err_dict = await get_singe_error(resp, 400)
        assert err_dict["loc"] == [missing_field]
        assert err_dict["msg"] == "field required"
        assert err_dict["type"].endswith(".missing")
        if demo_client._view_impl != ViewImplementation.aiohttp:
            assert err_dict["in"] == "body (json)"

    @pytest.mark.parametrize(
        "wrong_type_item", [("owner_id", "string"), ("title", ["arrray"])]
    )
    async def test_400_wrong_type(self, demo_client, add_note_dict, wrong_type_item):
        field, wrong_value = wrong_type_item
        add_note_dict[field] = wrong_value
        resp = await demo_client.post("/notes", json=add_note_dict)
        err_dict = await get_singe_error(resp, 400)
        pprint(err_dict)
        assert err_dict["loc"] == [field]
        assert err_dict["type"].startswith("type_error")

    async def test_400_unreadable_body(self, make_client, demo_client):
        content = {"title": "my new note", "owner_id": 2}
        invalid_json = json.dumps(content)[:-1]
        resp = await demo_client.post(
            "/notes", data=invalid_json, headers={"Content-Type": "application/json"}
        )
        err_dict = await get_singe_error(resp, 400)
        pprint(err_dict)
        assert err_dict["type"] == "JSONDecodeError"
        assert err_dict["loc"] == ["__root__"]


class TestGetNote:
    async def test_200(self, demo_client, saved_note):
        resp = await demo_client.get(f"/notes/{saved_note.id}")
        resp_data = await get_json(resp)
        assert resp_data == json.loads(saved_note.json())

    async def test_404(self, demo_client):
        note_id = str(uuid.uuid4())
        resp = await demo_client.get(f"/notes/{note_id}")
        assert resp.status == 404
        assert resp.reason.endswith("found")


class TestListNote:
    @pytest.mark.parametrize("query", ["minimal", "extended"])
    async def test_200(self, query, demo_client, saved_note):
        if query == "minimal":
            query_string = "?offset=0"
            expected_header = "None"
        elif query == "extended":
            query_string = (
                "?offset=0&limit=1&authorType=machine"
                "&sort_string=created:dec,title:asc"
                "&extra_param=not_used_by_app"
            )
            expected_header = "machine"
        resp = await demo_client.get(f"/notes{query_string}")
        resp_data = await get_json(resp)
        pprint(resp_data)
        assert len(resp_data) == 1
        assert resp_data[0]["title"] == saved_note.title
        if demo_client.app["view_impl"] == ViewImplementation.extractors:
            assert resp.headers["author-type"] == expected_header

    async def test_400_missing(self, demo_client, saved_note):
        resp = await demo_client.get("/notes?sort=created:dec,title:asc&limit=1")
        err_dict = await get_singe_error(resp, 400)
        assert err_dict == {
            "in": "query",
            "loc": ["offset"],
            "msg": 'Parameter "offset" is required in query',
            "type": "MissingValueError",
        }

    async def test_400_wrong_type(self, demo_client, saved_note):
        resp = await demo_client.get("/notes?&offset=0&limit=str_not_int")
        err_dict = await get_singe_error(resp, 400)
        assert err_dict == {
            "in": "query",
            "loc": ["limit"],
            "msg": "invalid literal for int() with base 10: 'str_not_int'",
            "type": "ValueError",
        }


async def test_patch_note(make_client, saved_note):
    new_title = "new_title"
    client = await make_client(ViewImplementation.extractors)
    resp = await client.patch(f"/notes/{saved_note.id}", json={"title": new_title})
    resp_data = await get_json(resp)
    assert resp_data["title"] == new_title


async def test_openapi_file(make_client):
    client = await make_client(ViewImplementation.extractors)
    schema_path = Path("tests/demo_notes/conf/openapi.json")
    control_path = Path("tests/testdata/control_openapi.json")
    with open(control_path) as control_file:
        control_schema = json.loads(control_file.read())
    with open(schema_path) as schema_file:
        schema = json.loads(schema_file.read())
    assert schema == control_schema
    resp = await client.get("/")
    assert resp.status == 200
    resp_text = await resp.text()
    assert "<title> Notes API </title>" in resp_text


async def test_openapi_classes_file(make_client):
    client = await make_client(ViewImplementation.classes)
    schema_path = Path("tests/demo_notes/conf/openapi_classes.json")
    control_path = Path("tests/testdata/control_openapi_classes.json")
    with open(control_path) as control_file:
        control_schema = json.loads(control_file.read())
    with open(schema_path) as schema_file:
        schema = json.loads(schema_file.read())
    assert schema == control_schema
    resp = await client.get("/")
    assert resp.status == 200
    resp_text = await resp.text()
    assert "<title> Notes API </title>" in resp_text


class TestUsualClassesView:
    @pytest.fixture
    async def client(self, make_client):
        client = await make_client(ViewImplementation.classes)
        return client

    async def test_hello(self, client):
        name, surname = "Capitan", "Nemo"
        resp = await client.get(f"/hello/{name}?surname={surname}")
        assert resp.status == 200
        assert (await resp.text()) == f"Hello, {name} {surname}"

    @pytest.mark.parametrize("path", ["/greet", "/aloha"])
    async def test_greeting(self, path, client):
        resp = await client.get(path)
        assert resp.status == 200
        assert (await resp.text()) == "Hello, Anonymous"

    async def test_health(self, client):
        resp = await client.get("/health")
        assert resp.status == 204


@pytest.fixture
async def upload_dir(monkeypatch):
    with tempfile.TemporaryDirectory(prefix="aiohttp_openapi_demo_uploads") as tmpdir:
        monkeypatch.setenv("AIOHTTP_OPENAPI_DEMO_UPLOADS", tmpdir)
        yield Path(tmpdir)


class TestAuthors:
    @pytest.fixture(params=[ViewImplementation.aiohttp, ViewImplementation.extractors])
    async def client(self, make_client, request):
        client = await make_client(request.param)
        return client

    @pytest.fixture
    async def saved_author(self):
        author = models.Author(name="Donald", nature=models.AuthorType.human)
        models.database[author.name] = author
        return author

    @pytest.fixture
    def avatar_file(self):
        with tempfile.TemporaryDirectory(prefix="aiohttp_openapi_demo_files") as tmpdir:
            avatar_path = Path(tmpdir) / "avatar.png"
            with open(avatar_path, "wb") as f:
                f.write(b"photo")
            yield avatar_path

    async def test_set_biograpy_200(self, client, saved_author):
        # text/plain
        # b'Amazing bio'
        biography = "Amazing bio"
        resp = await client.put(
            f"/authors/{saved_author.name}/biography", data=biography
        )
        assert resp.status == 200
        resp_data = await resp.json()
        assert resp_data["biography"] == biography

    async def test_set_avatar_200(
        self,
        upload_dir,
        client,
        saved_author,
        avatar_file,
    ):
        # image/png
        # b'photo'
        with open(avatar_file, "rb") as fd:
            resp = await client.put(f"/authors/{saved_author.name}/avatar", data=fd)
        assert resp.status == 200
        resp_data = await resp.json()
        assert resp_data["avatar"]
        with open(upload_dir / resp_data["avatar"], "rb") as dst:
            with open(avatar_file, "rb") as src:
                assert dst.read() == src.read()

    @pytest.mark.parametrize(
        "view_impl_url",
        [
            (ViewImplementation.aiohttp, "/authors/{}"),
            (ViewImplementation.extractors, "/authors/{}"),
            (ViewImplementation.extractors, "/stream/authors/{}"),
        ],
    )
    async def test_set_author_200(
        self, view_impl_url, upload_dir, make_client, avatar_file
    ):
        view_impl, url = view_impl_url
        client = await make_client(view_impl)
        create_author = {
            "name": "Donald",
            "nature": "human",
        }
        biography = "Amazing bio"

        form = aiohttp.FormData()
        form.add_field(
            "author", json.dumps(create_author), content_type="application/json"
        )
        form.add_field("biography", biography)
        with open(avatar_file, "rb") as fd:
            form.add_field("avatar", fd)
            resp = await client.put(url.format(create_author["name"]), data=form)

        if not resp.status == 200:
            print(await resp.text())
        assert resp.status == 200
        resp_data = await resp.json()
        pprint(resp_data)

        assert resp_data["biography"] == biography
        with open(upload_dir / resp_data["avatar"], "rb") as dst:
            with open(avatar_file, "rb") as src:
                assert dst.read() == src.read()
        for k in create_author:
            assert create_author[k] == resp_data[k]

    async def test_add_author(self, client, upload_dir, avatar_file):
        create_author = {
            "name": "Donald",
            "nature": "human",
        }
        biography = "Amazing bio"

        form = aiohttp.FormData()
        form.add_fields(
            ("name", "Donald"),
            ("nature", "human"),
        )
        form.add_field("biography", biography)
        with open(avatar_file, "rb") as fd:
            form.add_field("avatar", fd)
            resp = await client.post("/notes/0/author", data=form)

        if not resp.status == 200:
            print(await resp.text())
        assert resp.status == 200
        resp_data = await resp.json()
        pprint(resp_data)

        assert resp_data["biography"] == biography
        with open(upload_dir / resp_data["avatar"], "rb") as dst:
            with open(avatar_file, "rb") as src:
                assert dst.read() == src.read()
        for k in create_author:
            assert create_author[k] == resp_data[k]
