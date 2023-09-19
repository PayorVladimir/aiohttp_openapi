import datetime
import enum
import uuid
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel

database = {}


class AuthorType(str, enum.Enum):
    """Weather or not note was created by robot or a human being."""

    robot = "machine"
    human = "human"


class BaseAuthor(BaseModel):
    name: str
    nature: AuthorType


class Author(BaseAuthor):
    biography: Optional[str]
    avatar: Optional[Path]


class CreateAuthor(Author):
    avatar: bytes


class CreateNote(BaseModel):
    title: str
    content: Optional[str]
    owner_id: int


class Note(CreateNote):
    id: uuid.UUID
    created: datetime.datetime
    authors: Optional[List[Author]]


class NoteList(BaseModel):
    __root__: List[Note]
