from fastapi import APIRouter, Depends

from api.task.schemas import TaskCreate, TaskId, TaskListQuery, TaskLogUpdate, TaskStatusUpdate
from api.task.service import task_service
from settings.dependencies import CommonQueryParams

router = APIRouter()


@router.post("/task/list")
def list_tasks(request_body: TaskListQuery, common: CommonQueryParams = Depends()):
    return task_service.list_tasks(request_body, common)


@router.post("/task/create")
def create_task(request_body: TaskCreate, common: CommonQueryParams = Depends()):
    return task_service.create(request_body, common)


@router.post("/task/log")
def update_task_log(request_body: TaskLogUpdate, common: CommonQueryParams = Depends()):
    return task_service.update_log(request_body, common)


@router.post("/task/status")
def update_task_status(request_body: TaskStatusUpdate, common: CommonQueryParams = Depends()):
    return task_service.set_status(request_body, common)


@router.post("/task/reevaluate")
def reevaluate_task(request_body: TaskId, common: CommonQueryParams = Depends()):
    return task_service.reevaluate(request_body, common)


@router.post("/task/complete_all")
def complete_all_tasks(common: CommonQueryParams = Depends()):
    return task_service.complete_all(common)


@router.post("/task/delete")
def delete_task(request_body: TaskId, common: CommonQueryParams = Depends()):
    return task_service.delete(request_body, common)


@router.post("/task/delete_done")
def delete_done_tasks(common: CommonQueryParams = Depends()):
    return task_service.delete_done(common)
