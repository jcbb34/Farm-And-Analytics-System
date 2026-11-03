from sqlalchemy.orm import Session

from app.models import Employee, User
from app.services.code_counter_service import next_record_code


def next_employee_code(db: Session) -> str:
    return next_record_code(
        db,
        namespace="employee",
        prefix="EMP",
        seed_model=Employee,
        code_column=Employee.employee_code,
    )


def next_user_code(db: Session) -> str:
    return next_record_code(
        db,
        namespace="user",
        prefix="USR",
        seed_model=User,
        code_column=User.user_code,
    )
