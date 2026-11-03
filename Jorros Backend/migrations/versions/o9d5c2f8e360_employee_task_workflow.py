"""Employee task workflow, review, care plans, attendance and linked usage.

Revision ID: o9d5c2f8e360
Revises: l6e3c9b2a750
"""

from alembic import op
import sqlalchemy as sa
import json

revision = "o9d5c2f8e360"
down_revision = "l6e3c9b2a750"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    # Add the new built-in workforce roles to existing databases.  Built-in
    # permissions remain app-defined by leaving permissions_json NULL.
    existing_roles = {
        row[0]
        for row in bind.execute(sa.text("SELECT name FROM roles WHERE name IN ('Manager','Employee')")).all()
    }
    if "Manager" not in existing_roles:
        bind.execute(sa.text(
            "INSERT INTO roles (name, description, permissions_json, is_active) "
            "VALUES ('Manager', 'Manages farm operations, employee tasks, reviews, attendance, and records.', NULL, 1)"
        ))
    if "Employee" not in existing_roles:
        bind.execute(sa.text(
            "INSERT INTO roles (name, description, permissions_json, is_active) "
            "VALUES ('Employee', 'Uses My Tasks and submits assigned farm work for review.', NULL, 1)"
        ))

    # Existing Farm Staff accounts become limited employee-workflow accounts.
    employee_permissions = json.dumps([
        "activities:view", "workforce:view", "workforce:submit",
        "weather:view", "settings:view", "settings:profile", "notifications:view",
    ])
    bind.execute(
        sa.text("UPDATE roles SET permissions_json=:p WHERE name='Farm Staff'"),
        {"p": employee_permissions},
    )

    # Employee profiles can exist without a login account.
    op.create_table(
        "employees",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("employee_code", sa.String(length=30), nullable=False),
        sa.Column("full_name", sa.String(length=120), nullable=False),
        sa.Column("contact_number", sa.String(length=20), nullable=True),
        sa.Column("position", sa.String(length=100), nullable=True),
        sa.Column("employment_status", sa.String(length=30), server_default=sa.text("'Active'"), nullable=False),
        sa.Column("login_user_id", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_archived", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["login_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_employees_employee_code", "employees", ["employee_code"], unique=True)
    op.create_index("ix_employees_full_name", "employees", ["full_name"], unique=False)
    op.create_index("ix_employees_status", "employees", ["employment_status"], unique=False)
    op.create_index("ix_employees_archived", "employees", ["is_archived"], unique=False)
    op.create_index(
        "ix_employees_login_user",
        "employees",
        ["login_user_id"],
        unique=True,
        mssql_where=sa.text("login_user_id IS NOT NULL"),
        sqlite_where=sa.text("login_user_id IS NOT NULL"),
    )

    op.create_table(
        "care_templates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("template_code", sa.String(length=30), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("module", sa.String(length=20), nullable=False),
        sa.Column("target_type", sa.String(length=100), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_care_templates_code", "care_templates", ["template_code"], unique=True)
    op.create_index("ix_care_templates_name", "care_templates", ["name"], unique=False)
    op.create_index("ix_care_templates_module", "care_templates", ["module"], unique=False)
    op.create_index("ix_care_templates_target", "care_templates", ["target_type"], unique=False)
    op.create_index("ix_care_templates_active", "care_templates", ["is_active"], unique=False)

    op.create_table(
        "care_template_steps",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=150), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("offset_days", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("priority", sa.String(length=20), server_default=sa.text("'Medium'"), nullable=False),
        sa.Column("requires_review", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("requires_evidence", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("planned_quantity", sa.Numeric(12, 3), nullable=True),
        sa.Column("planned_unit", sa.String(length=40), nullable=True),
        sa.Column("inventory_item_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["template_id"], ["care_templates.id"]),
        sa.ForeignKeyConstraint(["inventory_item_id"], ["inventory_items.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("template_id", "sequence_number", name="uq_care_template_step_sequence"),
    )
    op.create_index("ix_care_steps_template", "care_template_steps", ["template_id"], unique=False)
    op.create_index("ix_care_steps_inventory", "care_template_steps", ["inventory_item_id"], unique=False)

    # Existing modules gain optional employee/care plan references.
    op.add_column("farm_activities", sa.Column("assigned_employee_id", sa.Integer(), nullable=True))
    op.add_column("farm_activities", sa.Column("instructions", sa.Text(), nullable=True))
    op.add_column("farm_activities", sa.Column("requires_review", sa.Boolean(), server_default=sa.text("0"), nullable=False))
    op.add_column("farm_activities", sa.Column("requires_evidence", sa.Boolean(), server_default=sa.text("0"), nullable=False))
    op.add_column("farm_activities", sa.Column("planned_quantity", sa.Float(), nullable=True))
    op.add_column("farm_activities", sa.Column("planned_unit", sa.String(length=40), nullable=True))
    op.add_column("farm_activities", sa.Column("recurring_rule", sa.String(length=255), nullable=True))
    op.add_column("farm_activities", sa.Column("recurring_series_key", sa.String(length=120), nullable=True))
    op.add_column("farm_activities", sa.Column("problem_report", sa.Text(), nullable=True))
    op.add_column("farm_activities", sa.Column("needs_reassignment", sa.Boolean(), server_default=sa.text("0"), nullable=False))
    op.create_foreign_key("fk_activity_employee", "farm_activities", "employees", ["assigned_employee_id"], ["id"])
    op.create_index("ix_activity_employee", "farm_activities", ["assigned_employee_id"], unique=False)
    op.create_index("ix_activity_review", "farm_activities", ["requires_review"], unique=False)
    op.create_index("ix_activity_recurring", "farm_activities", ["recurring_series_key"], unique=False)
    op.create_index("ix_activity_reassignment", "farm_activities", ["needs_reassignment"], unique=False)

    op.add_column("crops", sa.Column("assigned_employee_id", sa.Integer(), nullable=True))
    op.add_column("crops", sa.Column("care_template_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_crop_employee", "crops", "employees", ["assigned_employee_id"], ["id"])
    op.create_foreign_key("fk_crop_care_template", "crops", "care_templates", ["care_template_id"], ["id"])
    op.create_index("ix_crop_employee", "crops", ["assigned_employee_id"], unique=False)
    op.create_index("ix_crop_care_template", "crops", ["care_template_id"], unique=False)

    op.add_column("livestock", sa.Column("age_is_estimated", sa.Boolean(), server_default=sa.text("0"), nullable=False))
    op.add_column("livestock", sa.Column("estimated_age_days", sa.Integer(), nullable=True))
    op.add_column("livestock", sa.Column("feeding_plan_name", sa.String(length=150), nullable=True))
    op.add_column("livestock", sa.Column("assigned_employee_id", sa.Integer(), nullable=True))
    op.add_column("livestock", sa.Column("care_template_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_livestock_employee", "livestock", "employees", ["assigned_employee_id"], ["id"])
    op.create_foreign_key("fk_livestock_care_template", "livestock", "care_templates", ["care_template_id"], ["id"])
    op.create_index("ix_livestock_employee", "livestock", ["assigned_employee_id"], unique=False)
    op.create_index("ix_livestock_care_template", "livestock", ["care_template_id"], unique=False)

    op.create_table(
        "task_submissions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("activity_id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("recorded_by_user_id", sa.Integer(), nullable=True),
        sa.Column("attempt_number", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("actual_quantity", sa.Numeric(12, 3), nullable=True),
        sa.Column("actual_unit", sa.String(length=40), nullable=True),
        sa.Column("evidence_url", sa.String(length=500), nullable=True),
        sa.Column("worker_notes", sa.Text(), nullable=True),
        sa.Column("problem_report", sa.Text(), nullable=True),
        sa.Column("review_status", sa.String(length=30), server_default=sa.text("'Submitted'"), nullable=False),
        sa.Column("review_feedback", sa.Text(), nullable=True),
        sa.Column("reviewed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["activity_id"], ["farm_activities.id"]),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"]),
        sa.ForeignKeyConstraint(["recorded_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("activity_id", "attempt_number", name="uq_task_submission_attempt"),
    )
    op.create_index("ix_task_submission_activity", "task_submissions", ["activity_id"], unique=False)
    op.create_index("ix_task_submission_employee", "task_submissions", ["employee_id"], unique=False)
    op.create_index("ix_task_submission_review", "task_submissions", ["review_status"], unique=False)

    op.create_table(
        "staff_attendance",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("attendance_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("recorded_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"]),
        sa.ForeignKeyConstraint(["recorded_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("employee_id", "attendance_date", name="uq_employee_attendance_date"),
    )
    op.create_index("ix_attendance_employee", "staff_attendance", ["employee_id"], unique=False)
    op.create_index("ix_attendance_date", "staff_attendance", ["attendance_date"], unique=False)
    op.create_index("ix_attendance_status", "staff_attendance", ["status"], unique=False)

    op.create_table(
        "staff_leave",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("leave_type", sa.String(length=40), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=30), server_default=sa.text("'Approved'"), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("recorded_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"]),
        sa.ForeignKeyConstraint(["recorded_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_leave_employee", "staff_leave", ["employee_id"], unique=False)
    op.create_index("ix_leave_start", "staff_leave", ["start_date"], unique=False)
    op.create_index("ix_leave_end", "staff_leave", ["end_date"], unique=False)
    op.create_index("ix_leave_status", "staff_leave", ["status"], unique=False)

    # Feeding submissions record actual usage to three decimal places.
    op.alter_column(
        "resource_usages",
        "quantity",
        existing_type=sa.Numeric(12, 2),
        type_=sa.Numeric(12, 3),
        existing_nullable=False,
    )

    op.add_column("resource_usages", sa.Column("activity_id", sa.Integer(), nullable=True))
    op.add_column("resource_usages", sa.Column("task_submission_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_resource_usage_activity", "resource_usages", "farm_activities", ["activity_id"], ["id"])
    op.create_foreign_key("fk_resource_usage_submission", "resource_usages", "task_submissions", ["task_submission_id"], ["id"])
    op.create_index("ix_resource_usage_activity", "resource_usages", ["activity_id"], unique=False)
    op.create_index(
        "ix_resource_usage_submission",
        "resource_usages",
        ["task_submission_id"],
        unique=True,
        mssql_where=sa.text("task_submission_id IS NOT NULL"),
        sqlite_where=sa.text("task_submission_id IS NOT NULL"),
    )

    # Employee accounts may omit email. Keep uniqueness for non-null emails.
    op.drop_index("ix_users_email", table_name="users")
    op.alter_column("users", "email", existing_type=sa.String(length=120), nullable=True)
    op.create_index(
        "ix_users_email_not_null",
        "users",
        ["email"],
        unique=True,
        mssql_where=sa.text("email IS NOT NULL"),
        sqlite_where=sa.text("email IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_users_email_not_null", table_name="users")
    op.alter_column("users", "email", existing_type=sa.String(length=120), nullable=False)
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.alter_column(
        "resource_usages",
        "quantity",
        existing_type=sa.Numeric(12, 3),
        type_=sa.Numeric(12, 2),
        existing_nullable=False,
    )

    op.drop_index("ix_resource_usage_submission", table_name="resource_usages")
    op.drop_index("ix_resource_usage_activity", table_name="resource_usages")
    op.drop_constraint("fk_resource_usage_submission", "resource_usages", type_="foreignkey")
    op.drop_constraint("fk_resource_usage_activity", "resource_usages", type_="foreignkey")
    op.drop_column("resource_usages", "task_submission_id")
    op.drop_column("resource_usages", "activity_id")

    op.drop_table("staff_leave")
    op.drop_table("staff_attendance")
    op.drop_table("task_submissions")

    op.drop_index("ix_livestock_care_template", table_name="livestock")
    op.drop_index("ix_livestock_employee", table_name="livestock")
    op.drop_constraint("fk_livestock_care_template", "livestock", type_="foreignkey")
    op.drop_constraint("fk_livestock_employee", "livestock", type_="foreignkey")
    op.drop_column("livestock", "care_template_id")
    op.drop_column("livestock", "assigned_employee_id")
    op.drop_column("livestock", "feeding_plan_name")
    op.drop_column("livestock", "estimated_age_days")
    op.drop_column("livestock", "age_is_estimated")

    op.drop_index("ix_crop_care_template", table_name="crops")
    op.drop_index("ix_crop_employee", table_name="crops")
    op.drop_constraint("fk_crop_care_template", "crops", type_="foreignkey")
    op.drop_constraint("fk_crop_employee", "crops", type_="foreignkey")
    op.drop_column("crops", "care_template_id")
    op.drop_column("crops", "assigned_employee_id")

    for index in ("ix_activity_reassignment", "ix_activity_recurring", "ix_activity_review", "ix_activity_employee"):
        op.drop_index(index, table_name="farm_activities")
    op.drop_constraint("fk_activity_employee", "farm_activities", type_="foreignkey")
    for column in (
        "needs_reassignment", "problem_report", "recurring_series_key", "recurring_rule",
        "planned_unit", "planned_quantity", "requires_evidence", "requires_review",
        "instructions", "assigned_employee_id",
    ):
        op.drop_column("farm_activities", column)

    op.drop_table("care_template_steps")
    op.drop_table("care_templates")
    op.drop_table("employees")
