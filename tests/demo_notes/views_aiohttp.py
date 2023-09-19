import datetime
import json
import os
import uuid
from pathlib import Path

import pydantic
from aiohttp import web

from . import models


async def create_note(request):
    try:
        body = await request.json()
    except Exception as e:
        return web.json_response(
            [
                {
                    "in": "body (json)",
                    "loc": ["__root__"],
                    "msg": str(e),
                    "type": type(e).__name__,
                }
            ],
            status=400,
        )

    try:
        note = models.Note(**body, id=uuid.uuid4(), created=datetime.datetime.utcnow())
    except pydantic.ValidationError as e:
        return web.json_response(text=e.json(), status=400)

    if note.title in (note.title for note in models.database.values()):
        return web.json_response(
            reason="Note with the same title already exists", status=409
        )

    models.database[note.id] = note
    return web.json_response(text=note.json(), status=201)


async def get_note(request: web.Request):
    note_id_str = request.match_info["id"]
    note_id = uuid.UUID(note_id_str)
    note = models.database.get(note_id)
    if not note:
        return web.json_response(reason="Note not found", status=404)

    return web.json_response(text=note.json())


async def list_notes(request):
    reason = ""
    type_ = "ValueError"
    try:
        offset = int(request.query["offset"])
    except KeyError as e:
        param_name = e.args[0]
        reason = 'Parameter "{}" is required in query'.format(param_name)
        type_ = "MissingValueError"
    except ValueError as e:
        reason = str(e)
        param_name = "offset"
    else:
        try:
            limit = int(request.query.get("limit", 25))
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


async def create_author(request):
    body = await request.json()
    try:
        author = models.Author(**body)
    except pydantic.ValidationError as e:
        return web.json_response(text=e.json(), status=400)

    models.database[author.name] = author
    return web.json_response(text=author.json(), status=201)


async def set_biography(request):
    name = request.match_info["name"]
    author = models.database[name]

    author.biography = await request.text()

    models.database[author.name] = author
    return web.json_response(text=author.json())


async def set_avatar(request):
    name = request.match_info["name"]
    author = models.database[name]
    upload_dir = Path(os.getenv("AIOHTTP_OPENAPI_DEMO_UPLOADS"))

    path = upload_dir / f"{author.name}_avatar.png"
    with open(path, "wb") as f:
        async for chunk, _ in request.content.iter_chunks():
            f.write(chunk)
    author.avatar = str(path.relative_to(upload_dir))

    models.database[author.name] = author
    return web.json_response(text=author.json())


async def set_author(request: web.Request):
    upload_dir = Path(os.getenv("AIOHTTP_OPENAPI_DEMO_UPLOADS"))
    async for part in await request.multipart():
        content_type = part.headers["content-type"]
        if part.name == "author":
            author_object = await part.json()
            try:
                author = models.Author.parse_obj(author_object)
            except pydantic.ValidationError as e:
                return web.json_response(text=e.json(), status=400)
        elif part.name == "avatar":
            filename = part.filename
            if not filename:
                return web.json_response(
                    text={"error": "Filename is mandatory"}, status=400
                )
            path = upload_dir / filename
            with open(path, "wb") as f:
                f.write(await part.read())
            author.avatar = path
        elif part.name == "biography":
            author.biography = await part.text()
        else:
            return web.json_response(
                {"error": f"Unexpected part name={part.name}: {content_type}"},
                status=400,
            )

    models.database[author.name] = author
    return web.json_response(text=author.json())


async def add_author(request):
    upload_dir = Path(os.getenv("AIOHTTP_OPENAPI_DEMO_UPLOADS"))
    request_data = {}
    async for part in await request.multipart():
        if part.name != "avatar":
            request_data[part.name] = await part.text()
            continue
        filename = part.filename
        if not filename:
            return web.json_response(
                text={"error": "Filename is mandatory"}, status=400
            )
        path = upload_dir / filename
        with open(path, "wb") as f:
            f.write(await part.read())
            request_data[part.name] = path
    author = models.Author.parse_obj(request_data)
    models.database[author.name] = author
    return web.json_response(text=author.json())


def setup_routes(app):
    app.router.add_post("/notes", create_note)
    app.router.add_get("/notes", list_notes)
    app.router.add_get("/notes/{id}", get_note)

    app.router.add_post("/authors", create_author)
    app.router.add_put("/authors/{name}/biography", set_biography)
    app.router.add_put("/authors/{name}/avatar", set_avatar)
    app.router.add_put("/authors/{name}", set_author)
    app.router.add_post("/notes/{id}/author", add_author)
