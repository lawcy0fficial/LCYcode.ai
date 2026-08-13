from fastapi import APIRouter, Query

from lcycode.tools import filesystem

router = APIRouter()


@router.get("/api/workspace")
async def workspace_list(path: str = "."):
    return filesystem.list_dir(path)


@router.get("/api/workspace/file")
async def workspace_file(path: str = Query(...)):
    return filesystem.read_file(path)
