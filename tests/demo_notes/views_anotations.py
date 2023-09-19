import datetime
import json
import uuid

import pydantic
from aiohttp import web

from aiohttp_openapi.parser.decorators import openapi_view

from . import models


@openapi_view
async def create_note(body: models.CreateNote) -> models.Note:
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
async def get_note(id: uuid.UUID) -> models.Note:
    note_id = id
    note = models.database.get(note_id)
    if not note:
        return web.json_response(reason="Note not found", status=404)

    return web.json_response(text=note.json())


@openapi_view
async def list_notes(
    offset: int,
    author_type: models.AuthorType = None,
    limit=25,
    sort_string: str = None,
) -> models.NoteList:
    if author_type is not None:
        assert isinstance(author_type, models.AuthorType)
    if sort_string is not None:
        assert isinstance(sort_string, str)
    notes = list(models.database.values())
    return web.json_response(
        [json.loads(note.json()) for note in notes[offset : offset + limit]]
    )


def setup_routes(app):
    app.router.add_post("/notes", create_note)
    app.router.add_get("/notes", list_notes)
    app.router.add_get("/notes/{id}", get_note)
