import datetime as dt

from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.models.calendar import DailyTask
from app.models.enums import CommandSource, CommandType, DailyTaskStatus, StudySessionStatus, TaskKind, TimeSegmentKind
from app.models.session import StudySession, TimeSegment
from app.schemas.commands import CommandRequest, CommandResult, StudySessionRead
from app.schemas.calendar import DailyTaskRead


ACTIVE_SESSION_STATUSES = {StudySessionStatus.ACTIVE, StudySessionStatus.PAUSED}
STARTABLE_TASK_STATUSES = {DailyTaskStatus.PENDING, DailyTaskStatus.REMINDING}
DEFAULT_EXTENSION_MINUTES = 10


def _now(request: CommandRequest) -> dt.datetime:
    return request.timestamp or dt.datetime.now(dt.timezone.utc)


def _touch_task(task: DailyTask, when: dt.datetime) -> None:
    task.updated_at = when


def _get_task(session: Session, task_id: int) -> DailyTask:
    task = session.get(DailyTask, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="daily task not found")
    return task


def _select_next_task(session: Session, target_date: dt.date | None) -> DailyTask | None:
    statement = select(DailyTask).where(DailyTask.status.in_(STARTABLE_TASK_STATUSES))
    if target_date:
        statement = statement.where(DailyTask.date == target_date)
    statement = statement.order_by(DailyTask.current_start_at, DailyTask.sort_order, DailyTask.id)
    return session.exec(statement).first()


def _select_next_break_task(session: Session, task: DailyTask) -> DailyTask | None:
    statement = (
        select(DailyTask)
        .where(
            DailyTask.date == task.date,
            DailyTask.student_id == task.student_id,
            DailyTask.task_kind == TaskKind.BREAK,
            DailyTask.status.in_(STARTABLE_TASK_STATUSES),
            DailyTask.sort_order > task.sort_order,
        )
        .order_by(DailyTask.sort_order, DailyTask.current_start_at, DailyTask.id)
    )
    return session.exec(statement).first()


def _active_session(session: Session, task_id: int | None = None) -> StudySession | None:
    statement = select(StudySession).where(StudySession.status.in_(ACTIVE_SESSION_STATUSES))
    if task_id is not None:
        statement = statement.where(StudySession.daily_task_id == task_id)
    statement = statement.order_by(StudySession.started_at.desc(), StudySession.id.desc())
    return session.exec(statement).first()


def _running_session(session: Session, task_id: int | None = None) -> StudySession | None:
    statement = select(StudySession).where(StudySession.status == StudySessionStatus.ACTIVE)
    if task_id is not None:
        statement = statement.where(StudySession.daily_task_id == task_id)
    statement = statement.order_by(StudySession.started_at.desc(), StudySession.id.desc())
    return session.exec(statement).first()


def _open_segment(session: Session, study_session_id: int) -> TimeSegment | None:
    statement = select(TimeSegment).where(
        TimeSegment.study_session_id == study_session_id,
        TimeSegment.ended_at.is_(None),
    )
    return session.exec(statement).first()


def _close_open_segment(session: Session, study_session: StudySession, when: dt.datetime) -> None:
    segment = _open_segment(session, study_session.id)
    if not segment:
        return

    segment.ended_at = when
    segment.duration_seconds = max(0, int((when - segment.started_at).total_seconds()))
    segment.updated_at = when
    if segment.segment_kind == TimeSegmentKind.STUDY:
        study_session.effective_seconds += segment.duration_seconds


def _start_segment(session: Session, study_session: StudySession, kind: TimeSegmentKind, when: dt.datetime) -> None:
    segment = TimeSegment(
        study_session_id=study_session.id,
        daily_task_id=study_session.daily_task_id,
        segment_kind=kind,
        started_at=when,
    )
    session.add(segment)


def _segment_kind_for_task(task: DailyTask) -> TimeSegmentKind:
    if task.task_kind == TaskKind.BREAK:
        return TimeSegmentKind.BREAK
    return TimeSegmentKind.STUDY


def _extension_minutes(request: CommandRequest) -> int:
    raw_minutes = request.payload.get("minutes", DEFAULT_EXTENSION_MINUTES)
    try:
        minutes = int(raw_minutes)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="extension minutes must be an integer") from exc
    if minutes <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="extension minutes must be positive")
    return minutes


def _result(command: CommandType, task: DailyTask | None, study_session: StudySession | None, message: str) -> CommandResult:
    return CommandResult(
        command=command,
        task_status=task.status if task else None,
        task=DailyTaskRead.model_validate(task) if task else None,
        study_session=StudySessionRead.model_validate(study_session) if study_session else None,
        message=message,
    )


def process_command(session: Session, request: CommandRequest) -> CommandResult:
    handlers = {
        CommandType.START_STUDY: _start_study,
        CommandType.PAUSE_STUDY: _pause_study,
        CommandType.RESUME_STUDY: _resume_study,
        CommandType.COMPLETE_STUDY: _complete_study,
        CommandType.SKIP_TASK: _skip_task,
        CommandType.QUERY_CURRENT_TASK: _query_current_task,
        CommandType.QUERY_TODAY_PLAN: _query_today_plan,
        CommandType.EXTEND_CURRENT_TASK: _extend_current_task,
        CommandType.EXTEND_BREAK: _extend_break,
    }
    handler = handlers.get(request.command)
    if not handler:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="command is not implemented yet")
    return handler(session, request)


def _start_study(session: Session, request: CommandRequest) -> CommandResult:
    when = _now(request)
    existing_session = _active_session(session)
    if existing_session:
        task = _get_task(session, existing_session.daily_task_id)
        return _result(request.command, task, existing_session, "study session already active")

    task = _get_task(session, request.daily_task_id) if request.daily_task_id else _select_next_task(session, request.target_date)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no startable daily task found")
    if task.status not in STARTABLE_TASK_STATUSES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="daily task cannot be started")

    task.status = DailyTaskStatus.STUDYING
    _touch_task(task, when)
    study_session = StudySession(
        daily_task_id=task.id,
        student_id=task.student_id,
        status=StudySessionStatus.ACTIVE,
        started_at=when,
        command_source=request.source,
    )
    session.add(study_session)
    session.commit()
    session.refresh(study_session)
    _start_segment(session, study_session, _segment_kind_for_task(task), when)
    session.commit()
    session.refresh(task)
    session.refresh(study_session)
    return _result(request.command, task, study_session, "study started")


def _pause_study(session: Session, request: CommandRequest) -> CommandResult:
    when = _now(request)
    study_session = _active_session(session, request.daily_task_id)
    if not study_session:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="no active study session to pause")
    task = _get_task(session, study_session.daily_task_id)
    if study_session.status == StudySessionStatus.PAUSED:
        return _result(request.command, task, study_session, "study already paused")

    _close_open_segment(session, study_session, when)
    study_session.status = StudySessionStatus.PAUSED
    study_session.updated_at = when
    task.status = DailyTaskStatus.PAUSED
    _touch_task(task, when)
    _start_segment(session, study_session, TimeSegmentKind.PAUSE, when)
    session.commit()
    session.refresh(task)
    session.refresh(study_session)
    return _result(request.command, task, study_session, "study paused")


def _resume_study(session: Session, request: CommandRequest) -> CommandResult:
    when = _now(request)
    study_session = _active_session(session, request.daily_task_id)
    if not study_session or study_session.status != StudySessionStatus.PAUSED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="no paused study session to resume")
    task = _get_task(session, study_session.daily_task_id)

    _close_open_segment(session, study_session, when)
    study_session.status = StudySessionStatus.ACTIVE
    study_session.updated_at = when
    task.status = DailyTaskStatus.STUDYING
    _touch_task(task, when)
    _start_segment(session, study_session, _segment_kind_for_task(task), when)
    session.commit()
    session.refresh(task)
    session.refresh(study_session)
    return _result(request.command, task, study_session, "study resumed")


def _complete_study(session: Session, request: CommandRequest) -> CommandResult:
    result = _finish_session(session, request, DailyTaskStatus.COMPLETED, StudySessionStatus.COMPLETED, "study completed")
    if result.task:
        completed_task = _get_task(session, result.task.id)
        if completed_task.task_kind != TaskKind.BREAK:
            break_task = _select_next_break_task(session, completed_task)
            if break_task:
                return _start_specific_task(session, request, break_task, "break started automatically")
    return result


def _skip_task(session: Session, request: CommandRequest) -> CommandResult:
    when = _now(request)
    study_session = _active_session(session, request.daily_task_id)
    if study_session:
        return _finish_session(session, request, DailyTaskStatus.SKIPPED, StudySessionStatus.SKIPPED, "task skipped")

    task = _get_task(session, request.daily_task_id) if request.daily_task_id else _select_next_task(session, request.target_date)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no daily task found to skip")
    if task.status not in {DailyTaskStatus.PENDING, DailyTaskStatus.REMINDING, DailyTaskStatus.OVERDUE}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="daily task cannot be skipped")
    task.status = DailyTaskStatus.SKIPPED
    _touch_task(task, when)
    session.commit()
    session.refresh(task)
    return _result(request.command, task, None, "task skipped")


def _finish_session(
    session: Session,
    request: CommandRequest,
    task_status: DailyTaskStatus,
    session_status: StudySessionStatus,
    message: str,
) -> CommandResult:
    when = _now(request)
    study_session = _active_session(session, request.daily_task_id)
    if not study_session:
        study_session = _running_session(session, request.daily_task_id)
    if not study_session:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="no active study session to finish")
    task = _get_task(session, study_session.daily_task_id)
    _close_open_segment(session, study_session, when)
    study_session.status = session_status
    study_session.ended_at = when
    study_session.updated_at = when
    task.status = task_status
    _touch_task(task, when)
    session.commit()
    session.refresh(task)
    session.refresh(study_session)
    return _result(request.command, task, study_session, message)


def _start_specific_task(
    session: Session,
    request: CommandRequest,
    task: DailyTask,
    message: str,
) -> CommandResult:
    when = _now(request)
    task.status = DailyTaskStatus.STUDYING
    _touch_task(task, when)
    study_session = StudySession(
        daily_task_id=task.id,
        student_id=task.student_id,
        status=StudySessionStatus.ACTIVE,
        started_at=when,
        command_source=request.source,
    )
    session.add(study_session)
    session.commit()
    session.refresh(study_session)
    _start_segment(session, study_session, _segment_kind_for_task(task), when)
    session.commit()
    session.refresh(task)
    session.refresh(study_session)
    return _result(request.command, task, study_session, message)


def _extend_current_task(session: Session, request: CommandRequest) -> CommandResult:
    study_session = _active_session(session, request.daily_task_id)
    if not study_session:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="no active study session to extend")
    task = _get_task(session, study_session.daily_task_id)
    if task.task_kind == TaskKind.BREAK:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="use EXTEND_BREAK for break tasks")
    return _extend_task(session, request, task, study_session, "current task extended")


def _extend_break(session: Session, request: CommandRequest) -> CommandResult:
    study_session = _active_session(session, request.daily_task_id)
    if not study_session:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="no active break session to extend")
    task = _get_task(session, study_session.daily_task_id)
    if task.task_kind != TaskKind.BREAK:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="active task is not a break")
    return _extend_task(session, request, task, study_session, "break extended")


def _extend_task(
    session: Session,
    request: CommandRequest,
    task: DailyTask,
    study_session: StudySession,
    message: str,
) -> CommandResult:
    when = _now(request)
    minutes = _extension_minutes(request)
    task.current_end_at = task.current_end_at + dt.timedelta(minutes=minutes)
    task.modify_count += 1
    _touch_task(task, when)
    session.commit()
    session.refresh(task)
    session.refresh(study_session)
    return _result(request.command, task, study_session, message)


def _query_current_task(session: Session, request: CommandRequest) -> CommandResult:
    study_session = _active_session(session, request.daily_task_id)
    if not study_session:
        return _result(request.command, None, None, "no active study session")
    task = _get_task(session, study_session.daily_task_id)
    return _result(request.command, task, study_session, "current task found")


def _query_today_plan(session: Session, request: CommandRequest) -> CommandResult:
    task = _select_next_task(session, request.target_date)
    return _result(request.command, task, None, "next task found" if task else "no startable task found")


def mark_due_tasks_waiting_finish_confirm(session: Session, when: dt.datetime) -> list[DailyTask]:
    statement = select(DailyTask).where(
        DailyTask.status == DailyTaskStatus.STUDYING,
        DailyTask.current_end_at <= when,
    )
    changed: list[DailyTask] = []
    for task in session.exec(statement):
        task.status = DailyTaskStatus.WAITING_FINISH_CONFIRM
        _touch_task(task, when)
        changed.append(task)

    session.commit()
    for task in changed:
        session.refresh(task)
    return changed
