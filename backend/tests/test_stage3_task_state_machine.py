from datetime import date, datetime, time

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import app.models  # noqa: F401
from app.models.enums import CommandSource, CommandType, DailyTaskStatus, StudySessionStatus, TaskKind, TimeSegmentKind
from app.models.session import StudySession, TimeSegment
from app.schemas.calendar import SchedulePlanCreate, ScheduleTaskItemCreate
from app.schemas.commands import CommandRequest
from app.services.calendar_plans import create_schedule_plan
from app.services.commands import handle_command
from app.services.daily_tasks import generate_daily_tasks, list_daily_tasks
from app.services.students import get_or_create_default_student
from app.services.task_state_machine import mark_due_tasks_waiting_finish_confirm


def make_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def make_daily_tasks(session: Session) -> list[int]:
    student = get_or_create_default_student(session)
    create_schedule_plan(
        session,
        student.id,
        SchedulePlanCreate(
            name="weekday evening plan",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 31),
            repeat_rule={"weekdays": [1, 2, 3, 4, 5]},
            items=[
                ScheduleTaskItemCreate(
                    sort_order=1,
                    task_kind=TaskKind.HOMEWORK,
                    subject="math",
                    title="math homework",
                    planned_start_time=time(19, 0),
                    planned_end_time=time(19, 40),
                    planned_minutes=40,
                ),
                ScheduleTaskItemCreate(
                    sort_order=2,
                    task_kind=TaskKind.BREAK,
                    title="break",
                    planned_start_time=time(19, 40),
                    planned_end_time=time(19, 50),
                    planned_minutes=10,
                )
            ],
        ),
    )
    generate_daily_tasks(session, date(2026, 7, 1))
    return [task.id for task in list_daily_tasks(session, date(2026, 7, 1))]


def make_daily_task(session: Session) -> int:
    return make_daily_tasks(session)[0]


def command(
    command_type: CommandType,
    task_id: int,
    timestamp: datetime,
    source: CommandSource = CommandSource.PARENT_WEB,
) -> CommandRequest:
    return CommandRequest(
        command=command_type,
        source=source,
        daily_task_id=task_id,
        timestamp=timestamp,
    )


def extend_command(command_type: CommandType, task_id: int, timestamp: datetime, minutes: int) -> CommandRequest:
    request = command(command_type, task_id, timestamp)
    request.payload["minutes"] = minutes
    return request


def test_start_pause_resume_complete_records_effective_study_time() -> None:
    with make_session() as session:
        task_id = make_daily_task(session)

        handle_command(session, command(CommandType.START_STUDY, task_id, datetime(2026, 7, 1, 19, 0)))
        handle_command(session, command(CommandType.PAUSE_STUDY, task_id, datetime(2026, 7, 1, 19, 10)))
        handle_command(session, command(CommandType.RESUME_STUDY, task_id, datetime(2026, 7, 1, 19, 15)))
        handle_command(session, command(CommandType.COMPLETE_STUDY, task_id, datetime(2026, 7, 1, 19, 35)))

        task = session.get(app.models.DailyTask, task_id)
        study_session = session.exec(
            select(StudySession).where(StudySession.daily_task_id == task_id)
        ).one()
        segments = list(
            session.exec(
                select(TimeSegment)
                .where(TimeSegment.study_session_id == study_session.id)
                .order_by(TimeSegment.started_at)
            )
        )

        assert task.status == DailyTaskStatus.COMPLETED
        assert study_session.effective_seconds == 30 * 60
        assert [segment.segment_kind for segment in segments] == [
            TimeSegmentKind.STUDY,
            TimeSegmentKind.PAUSE,
            TimeSegmentKind.STUDY,
        ]
        assert [segment.duration_seconds for segment in segments] == [10 * 60, 5 * 60, 20 * 60]


def test_skip_pending_task_marks_task_without_session() -> None:
    with make_session() as session:
        task_id = make_daily_task(session)

        result = handle_command(session, command(CommandType.SKIP_TASK, task_id, datetime(2026, 7, 1, 19, 0)))
        task = session.get(app.models.DailyTask, task_id)
        sessions = list(session.exec(select(StudySession)))

        assert result.task_status == DailyTaskStatus.SKIPPED
        assert task.status == DailyTaskStatus.SKIPPED
        assert sessions == []


def test_duplicate_start_returns_existing_active_session() -> None:
    with make_session() as session:
        task_id = make_daily_task(session)

        first = handle_command(session, command(CommandType.START_STUDY, task_id, datetime(2026, 7, 1, 19, 0)))
        second = handle_command(session, command(CommandType.START_STUDY, task_id, datetime(2026, 7, 1, 19, 5)))
        sessions = list(session.exec(select(StudySession)))

        assert first.study_session.id == second.study_session.id
        assert len(sessions) == 1


def test_extend_current_task_updates_end_time_and_modify_count() -> None:
    with make_session() as session:
        task_id = make_daily_task(session)

        handle_command(session, command(CommandType.START_STUDY, task_id, datetime(2026, 7, 1, 19, 0)))
        result = handle_command(
            session,
            extend_command(CommandType.EXTEND_CURRENT_TASK, task_id, datetime(2026, 7, 1, 19, 20), 15),
        )
        task = session.get(app.models.DailyTask, task_id)

        assert result.message == "current task extended"
        assert task.current_end_at == datetime(2026, 7, 1, 19, 55)
        assert task.modify_count == 1


def test_complete_study_auto_starts_next_break_without_effective_study_time() -> None:
    with make_session() as session:
        study_task_id, break_task_id = make_daily_tasks(session)

        handle_command(session, command(CommandType.START_STUDY, study_task_id, datetime(2026, 7, 1, 19, 0)))
        result = handle_command(session, command(CommandType.COMPLETE_STUDY, study_task_id, datetime(2026, 7, 1, 19, 35)))
        break_task = session.get(app.models.DailyTask, break_task_id)
        break_session = session.exec(
            select(StudySession).where(StudySession.daily_task_id == break_task_id)
        ).one()
        break_segment = session.exec(
            select(TimeSegment).where(TimeSegment.study_session_id == break_session.id)
        ).one()

        assert result.message == "break started automatically"
        assert result.task.id == break_task_id
        assert break_task.status == DailyTaskStatus.STUDYING
        assert break_session.effective_seconds == 0
        assert break_segment.segment_kind == TimeSegmentKind.BREAK


def test_extend_break_updates_break_end_time() -> None:
    with make_session() as session:
        study_task_id, break_task_id = make_daily_tasks(session)

        handle_command(session, command(CommandType.START_STUDY, study_task_id, datetime(2026, 7, 1, 19, 0)))
        handle_command(session, command(CommandType.COMPLETE_STUDY, study_task_id, datetime(2026, 7, 1, 19, 35)))
        result = handle_command(
            session,
            extend_command(CommandType.EXTEND_BREAK, break_task_id, datetime(2026, 7, 1, 19, 45), 5),
        )
        break_task = session.get(app.models.DailyTask, break_task_id)

        assert result.message == "break extended"
        assert break_task.current_end_at == datetime(2026, 7, 1, 19, 55)
        assert break_task.modify_count == 1


def test_due_studying_task_waits_for_finish_confirmation_without_completion() -> None:
    with make_session() as session:
        task_id = make_daily_task(session)

        handle_command(session, command(CommandType.START_STUDY, task_id, datetime(2026, 7, 1, 19, 0)))
        changed = mark_due_tasks_waiting_finish_confirm(session, datetime(2026, 7, 1, 19, 40))
        task = session.get(app.models.DailyTask, task_id)
        study_session = session.exec(select(StudySession)).first()

        assert [task.id for task in changed] == [task_id]
        assert task.status == DailyTaskStatus.WAITING_FINISH_CONFIRM
        assert study_session.effective_seconds == 0
        assert study_session.status == StudySessionStatus.ACTIVE
        assert study_session.ended_at is None


def test_waiting_finish_confirm_keeps_counting_until_complete_command() -> None:
    with make_session() as session:
        task_id = make_daily_task(session)

        handle_command(session, command(CommandType.START_STUDY, task_id, datetime(2026, 7, 1, 19, 0)))
        mark_due_tasks_waiting_finish_confirm(session, datetime(2026, 7, 1, 19, 40))
        handle_command(session, command(CommandType.COMPLETE_STUDY, task_id, datetime(2026, 7, 1, 19, 50)))
        task = session.get(app.models.DailyTask, task_id)
        study_session = session.exec(
            select(StudySession).where(StudySession.daily_task_id == task_id)
        ).one()

        assert task.status == DailyTaskStatus.COMPLETED
        assert study_session.effective_seconds == 50 * 60


def test_command_can_complete_from_virtual_device_source() -> None:
    with make_session() as session:
        task_id = make_daily_task(session)

        handle_command(
            session,
            command(
                CommandType.START_STUDY,
                task_id,
                datetime(2026, 7, 1, 19, 0),
                source=CommandSource.VIRTUAL_DEVICE,
            ),
        )
        handle_command(
            session,
            command(
                CommandType.COMPLETE_STUDY,
                task_id,
                datetime(2026, 7, 1, 19, 30),
                source=CommandSource.VIRTUAL_DEVICE,
            ),
        )
        study_session = session.exec(
            select(StudySession).where(StudySession.daily_task_id == task_id)
        ).one()
        task = session.get(app.models.DailyTask, task_id)

        assert task.status == DailyTaskStatus.COMPLETED
        assert study_session.command_source == CommandSource.VIRTUAL_DEVICE
