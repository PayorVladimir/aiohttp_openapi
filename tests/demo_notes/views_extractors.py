import datetime
import json
import os
import typing as t
import uuid
from pathlib import Path

import pydantic
from aiohttp import web

from aiohttp_openapi.parser.decorators import openapi_view
from aiohttp_openapi.parser.extractors import (
    FileUpload,
    FileUploadReader,
    Json,
    MultiPart,
    MultiPartReader,
    MultipleFileUpload,
    Param,
    Text,
)

from . import models


@openapi_view(response_status=201, response_description="Object created.", tag="Notes")
async def create_note(body=Json(models.CreateNote)) -> models.Note:
    """Create a note."""
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


@openapi_view(response_description="Note's detail.", tag="Notes")
async def get_note(id=Param(uuid.UUID)) -> models.Note:
    """Read full note object."""
    note = models.database.get(id)
    if not note:
        return web.json_response(reason="Note not found", status=404)
    return web.json_response(text=note.json())


@openapi_view(response_description="Update note with fields from object.", tag="Notes")
async def patch_note(
    note_id=Param(uuid.UUID, name="id"), new_fields=Json(dict)
) -> models.Note:
    """Change some fields in Note."""
    note = models.database.get(note_id)
    if not note:
        return web.json_response(reason="Note not found", status=404)

    new_fields.pop("id", None)
    patched_fields = note.dict()
    patched_fields.update(new_fields)
    patched_note = models.Note(**patched_fields)
    models.database[patched_note.id] = patched_note

    return web.json_response(text=patched_note.json())


@openapi_view(response_description="List of notes.", tag="Notes")
async def list_notes(
    offset=Param(int, minimum=0, example=10),
    limit=Param(
        25,
        examples={
            "low": {"summary": "Small portions", "value": 10},
            "high": {"summary": "Large portions", "value": 20},
        },
    ),
    author_type=Param(
        models.AuthorType,
        None,
        name="authorType",
        description="Is publisher alive",
        deprecated=True,
        allow_empty_value=True,
    ),
    sort_string=Param(""),
) -> t.List[models.Note]:
    """List notes."""
    notes = list(models.database.values())
    return web.json_response(
        [json.loads(note.json()) for note in notes[offset : offset + limit]],
        headers={"author-type": author_type.value if author_type else "None"},
    )


@openapi_view(tag="Authors")
async def create_author(author: models.Author) -> models.Author:
    models.database[author.name] = author
    return web.json_response(text=author.json(), status=201)


@openapi_view(tag="Authors")
async def set_biography(name: str, biography=Text()) -> models.Author:
    author = models.database[name]
    author.biography = biography
    models.database[author.name] = author
    return web.json_response(text=author.json())


@openapi_view(tag="Authors")
async def set_avatar(name: str, avatar=FileUploadReader()) -> models.Author:
    author = models.database[name]
    upload_dir = Path(os.getenv("AIOHTTP_OPENAPI_DEMO_UPLOADS"))

    path = upload_dir / f"{author.name}_avatar.png"
    with open(path, "wb") as f:
        async for chunk in avatar.iter_any():
            f.write(chunk)
    author.avatar = str(path.relative_to(upload_dir))

    models.database[author.name] = author
    return web.json_response(text=author.json())


@openapi_view(
    response_description="Updated list of note's authors",
    deprecated=True,
    tag="Authors",
)
async def add_author(
    id: int, author=MultipleFileUpload(models.CreateAuthor)
) -> models.Author:
    """Add author of note."""
    upload_dir = Path(os.getenv("AIOHTTP_OPENAPI_DEMO_UPLOADS"))
    path = upload_dir / f"{author.name}_avatar.png"
    with open(path, "wb") as f:
        f.write(author.avatar)
    author.avatar = path

    models.database[author.name] = author
    return web.json_response(text=author.json())


@openapi_view(tag="Authors")
async def set_author(
    name: str,
    dismembermented_author=MultiPart(
        author=Json(models.BaseAuthor),
        biography=Text(),
        avatar=FileUpload(),
    ),
) -> models.Author:
    upload_dir = Path(os.getenv("AIOHTTP_OPENAPI_DEMO_UPLOADS"))
    base_author = dismembermented_author.author
    path = upload_dir / f"{base_author.name}_avatar.png"
    with open(path, "wb") as f:
        f.write(dismembermented_author.avatar)
    author = models.Author(
        biography=dismembermented_author.biography,
        avatar=path,
        **base_author.dict(),
    )

    models.database[author.name] = author
    return web.json_response(text=author.json())


@openapi_view(tag="Authors")
async def set_author_streamed(
    name: str,
    dismembermented_author=MultiPartReader(
        base_author=Json(models.BaseAuthor, name="author"),
        biography=Text(),
        avatar=FileUpload(),
    ),
) -> models.Author:
    """Create author with bit avatar file without loading it to memory."""
    upload_dir = Path(os.getenv("AIOHTTP_OPENAPI_DEMO_UPLOADS"))
    values = {}
    async for part, extractor in dismembermented_author:
        if extractor is None:
            raise web.HTTPBadRequest(f"Unexpected part: {part.name}")
        if extractor.python_name != "avatar":
            value = await extractor.extract(part)
        else:
            assert part.filename
            author_dir = upload_dir / values["base_author"].name
            author_dir.mkdir(exist_ok=True)
            path = author_dir / f"{part.filename}.png"
            with open(path, "wb") as f:
                while chunk := await part.read_chunk():
                    f.write(chunk)
            value = path
        values[extractor.python_name] = value

    author = models.Author(
        biography=values["biography"],
        avatar=values["avatar"],
        **values["base_author"].dict(),
    )

    models.database[author.name] = author
    return web.json_response(text=author.json())


def setup_routes(app):
    app.router.add_post("/notes", create_note)
    app.router.add_get("/notes", list_notes)
    app.router.add_get("/notes/{id}", get_note)
    app.router.add_patch("/notes/{id}", patch_note)

    app.router.add_post("/authors", create_author)
    app.router.add_put("/authors/{name}/biography", set_biography)
    app.router.add_put("/authors/{name}/avatar", set_avatar)
    app.router.add_put("/authors/{name}", set_author)
    app.router.add_put("/stream/authors/{name}", set_author_streamed)
    app.router.add_post("/notes/{id}/author", add_author)
