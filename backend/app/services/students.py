from sqlmodel import Session, select

from app.models.student import Student


def get_or_create_default_student(session: Session) -> Student:
    student = session.exec(select(Student).order_by(Student.id)).first()
    if student:
        return student

    student = Student(name="默认学生")
    session.add(student)
    session.commit()
    session.refresh(student)
    return student
