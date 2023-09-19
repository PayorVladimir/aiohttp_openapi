import datetime
import json
import typing as t
import uuid

import pydantic
from aiohttp import web

from aiohttp_openapi import openapi_view
from aiohttp_openapi.parser.extractors import Param

from . import models

routes = web.RouteTableDef()


class NoteDetailView(web.View):
    @openapi_view
    async def get(self, note_id=Param(uuid.UUID, name="id")) -> models.Note:
        note = models.database.get(note_id)
        if not note:
            return web.json_response(reason="Note not found", status=404)

        return web.json_response(text=note.json())

    async def patch(self) -> models.Note:
        new_fields = await self.request.json()
        note_id_str = self.request.match_info["id"]
        note_id = uuid.UUID(note_id_str)
        note = models.database.get(note_id)
        if not note:
            return web.json_response(reason="Note not found", status=404)

        new_fields.pop("id", None)
        patched_fields = note.dict()
        patched_fields.update(new_fields)
        patched_note = models.Note(**patched_fields)
        models.database[patched_note.id] = patched_note

        return web.json_response(text=patched_note.json())

    @staticmethod
    @openapi_view
    async def count(request):
        return web.json_response({"count": len(models.database)})


@routes.view("/notes")
@openapi_view
class NotesView(web.View):
    async def post(self, body: models.CreateNote) -> models.Note:
        try:
            note = models.Note(
                **body.dict(), id=uuid.uuid4(), created=datetime.datetime.utcnow()
            )
        except pydantic.ValidationError as e:
            return web.json_response(text=e.json(), status=400)

        if note.title in (note.title for note in models.database.values()):
            return web.json_response(
                reason="Note with the same title already exists", status=409
            )

        models.database[note.id] = note
        return web.json_response(text=note.json(), status=201)

    @openapi_view
    async def get(self) -> t.List[models.Note]:
        reason = ""
        type_ = "ValueError"
        try:
            offset = int(self.request.query["offset"])
        except KeyError as e:
            param_name = e.args[0]
            reason = 'Parameter "{}" is required in query'.format(param_name)
            type_ = "MissingValueError"
        except ValueError as e:
            reason = str(e)
            param_name = "offset"
        else:
            try:
                limit = int(self.request.query.get("limit", 25))
            except ValueError as e:
                reason = str(e)
                param_name = "limit"
        if reason:
            return web.json_response(
                [{"in": "query", "loc": [param_name], "msg": reason, "type": type_}],
                status=400,
            )

        notes = list(models.database.values())
        return web.json_response(
            [json.loads(note.json()) for note in notes[offset : offset + limit]]
        )


class HelloView:
    @openapi_view
    async def intro(self, request):
        return web.Response(text="Hello, world")

    @openapi_view
    async def hello(self, request, name: str, surname="Unfamiliar"):
        assert request.content_type.startswith("application/")
        txt = "Hello, {} {}".format(name, surname)
        return web.Response(text=txt)

    @classmethod
    @openapi_view
    async def class_greeting(cls, request):
        name = request.query.get("name", "Anonymous")
        txt = "Hello, {}".format(name)
        return web.Response(text=txt)

    @staticmethod
    @routes.get("/health")
    @openapi_view
    async def health():
        """Check server health"""
        return web.Response(status=web.HTTPNoContent.status_code)


def setup_routes(app):
    app.router.add_get("/notes/count", NoteDetailView.count)
    app.router.add_view("/notes/{id}", NoteDetailView)
    app.router.add_routes(routes)

    hello_view = HelloView()
    app.add_routes(
        [
            web.get("/intro", hello_view.intro),
            web.get("/hello/{name}", hello_view.hello),
            web.get("/greet", HelloView.class_greeting),
            web.get("/aloha", hello_view.class_greeting),
        ]
    )
