import logging
import os
import tempfile
from pathlib import Path

from aiohttp import web

import aiohttp_openapi

from . import ViewImplementation


async def create_app(view_impl=ViewImplementation.extractors, run_for_user=True):
    """
    Create application that is useful as demo and for tests.

    If `run_for_user` is False, app updates schemas in git, useful for tests.
    """
    if env_view := os.getenv("view"):
        view_impl = ViewImplementation[env_view]

    if view_impl == ViewImplementation.aiohttp:
        from . import views_aiohttp as views
    elif view_impl == ViewImplementation.annotations:
        from . import views_anotations as views
    elif view_impl == ViewImplementation.extractors:
        from . import views_extractors as views
    elif view_impl == ViewImplementation.classes:
        from . import views_classes as views
    else:
        assert False, f'"{view_impl}" not supported'

    app = web.Application()
    app["view_impl"] = view_impl
    views.setup_routes(app)

    if run_for_user:
        tmp_dir = Path(tempfile.mkdtemp(prefix="aiohttp-openapi-demo"))
        json_path = tmp_dir / "openapi.json"
        yaml_path = tmp_dir / "openapi.yaml"
        aiohttp_openapi.logger.addHandler(logging.StreamHandler())
    else:
        classes = "_classes" if view_impl == ViewImplementation.classes else ""
        json_path = f"tests/demo_notes/conf/openapi{classes}.json"
        yaml_path = f"tests/demo_notes/conf/openapi{classes}.yaml"
    aiohttp_openapi.publish_schema(
        app,
        title="Notes API",
        version="0.0.1",
        json_path=json_path,
        yaml_path=yaml_path,
        url_path="/",
    )
    return app


def main():
    app = create_app()
    web.run_app(app)


if __name__ == "__main__":
    main()
