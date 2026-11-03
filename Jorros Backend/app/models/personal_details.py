import json
from sqlalchemy import UnicodeText
from sqlalchemy.orm import Mapped, mapped_column

class PersonalDetailsMixin:
    personal_details_json: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)

    @property
    def personal_details(self):
        return json.loads(self.personal_details_json) if self.personal_details_json else None

    @personal_details.setter
    def personal_details(self, value):
        self.personal_details_json = json.dumps(value, ensure_ascii=False) if value is not None else None
