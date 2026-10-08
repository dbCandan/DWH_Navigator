"""The process's search index, created by the application factory and kept on ``app.state``."""

from fastapi import Request

from app.services.search_index import SearchIndex


def get_search_index(request: Request) -> SearchIndex:
    index: SearchIndex = request.app.state.search_index
    return index
