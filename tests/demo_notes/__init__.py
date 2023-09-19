from enum import Enum, auto


class ViewImplementation(Enum):
    aiohttp = auto()
    annotations = auto()
    extractors = auto()
    classes = auto()
