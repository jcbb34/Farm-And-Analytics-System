"""Validated structured details, alongside backward-compatible full_name/address."""
import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.services.location_reference import location_index

class AddressDetails(BaseModel):
    model_config = ConfigDict(extra='forbid')
    street: str | None = Field(default=None, max_length=100)
    subdivision: str | None = Field(default=None, max_length=100)
    province: str | None = Field(default=None, max_length=100)
    province_code: str | None = Field(default=None, pattern=r'^\d{10}$')
    city: str | None = Field(default=None, max_length=100)
    city_code: str | None = Field(default=None, pattern=r'^\d{10}$')
    barangay: str | None = Field(default=None, max_length=100)
    barangay_code: str | None = Field(default=None, pattern=r'^\d{10}$')
    postal_code: str | None = Field(default=None, pattern=r'^\d{4}$')

    @field_validator('*', mode='before')
    @classmethod
    def clean(cls, value):
        return (re.sub(r'\s+', ' ', value).strip() or None) if isinstance(value, str) else value

    @model_validator(mode='after')
    def validate_reference(self):
        for level, name, parent in [('provinces', 'province', None), ('cities', 'city', 'province'), ('barangays', 'barangay', 'city')]:
            code = getattr(self, name + '_code')
            if code:
                row = location_index(level).get(code)
                if row is None or (parent and row[parent + '_code'] != getattr(self, parent + '_code')):
                    raise ValueError(f'Select a valid {name} for the selected location, or use a custom entry.')
                setattr(self, name, row['name'])
        if any(getattr(self, key) for key in ('street', 'subdivision', 'province', 'city', 'barangay', 'postal_code')) and not all(getattr(self, key) for key in ('province', 'city', 'barangay')):
            raise ValueError('Provide province, city/municipality and barangay when entering an address. Custom entries are allowed.')
        if len(self.formatted) > 255:
            raise ValueError('The complete address must be at most 255 characters.')
        return self

    @property
    def formatted(self):
        return ', '.join(str(value) for value in (self.street, self.subdivision, self.barangay, self.city, self.province, self.postal_code) if value)

class PersonalDetails(BaseModel):
    model_config = ConfigDict(extra='forbid')
    first_name: str | None = Field(default=None, max_length=60)
    middle_name: str | None = Field(default=None, max_length=60)
    surname: str | None = Field(default=None, max_length=60)
    suffix: Literal['Jr.', 'Sr.', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X'] | None = None
    address: AddressDetails | None = None

    @field_validator('first_name', 'middle_name', 'surname', 'suffix', mode='before')
    @classmethod
    def clean(cls, value):
        return (re.sub(r'\s+', ' ', value).strip() or None) if isinstance(value, str) else value

    @model_validator(mode='after')
    def validate_name(self):
        if any((self.first_name, self.middle_name, self.surname, self.suffix)) and not (self.first_name and self.surname):
            raise ValueError('First name and surname are required when entering separate name fields.')
        if self.full_name and not 2 <= len(self.full_name) <= 120:
            raise ValueError('The complete name must contain 2 to 120 characters.')
        return self

    @property
    def full_name(self):
        return ' '.join(value for value in (self.first_name, self.middle_name, self.surname, self.suffix) if value) if self.first_name and self.surname else None

class PersonalDetailsPayload(BaseModel):
    personal_details: PersonalDetails | None = None

    @model_validator(mode='before')
    @classmethod
    def derive_display_name(cls, value):
        if isinstance(value, dict) and value.get('personal_details') is not None:
            details = PersonalDetails.model_validate(value['personal_details'])
            if details.full_name:
                return {**value, 'full_name': details.full_name}
        return value

class PersonalDetailsCreationPayload(PersonalDetailsPayload):
    @model_validator(mode='after')
    def require_structured_name(self):
        if self.personal_details is not None and not self.personal_details.full_name:
            raise ValueError('First name and surname are required for a new structured personal profile.')
        return self
