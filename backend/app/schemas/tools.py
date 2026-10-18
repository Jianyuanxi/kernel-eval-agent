"""给 Dify 调用的工具接口请求体（POST + 扁平 JSON），与 contracts/tools.openapi.yaml 一一对应"""
from pydantic import BaseModel, Field


class ProjectRef(BaseModel):
    task_id: str
    project_id: str


class ReadSourceRequest(ProjectRef):
    path: str = Field(description="相对工程根的路径")
    start_line: int = Field(1, ge=1)
    end_line: int = Field(200, ge=1, description="一次最多 200 行，超出自动截到 start_line+199")
