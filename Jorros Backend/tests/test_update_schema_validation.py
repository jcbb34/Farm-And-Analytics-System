import unittest

from pydantic import ValidationError

from app.schemas.crops import CropUpdate
from app.schemas.inventory import InventoryUpdate
from app.schemas.livestock import LivestockUpdate
from app.schemas.roles import RoleUpdate
from app.schemas.users import UserProfileUpdate, UserUpdate


class UpdateSchemaValidationTests(unittest.TestCase):
    def assert_rejects_null(self, schema, field):
        with self.assertRaises(ValidationError):
            schema.model_validate({field: None})

    def test_user_required_update_fields_reject_explicit_null(self):
        self.assert_rejects_null(UserUpdate, "username")
        self.assert_rejects_null(UserProfileUpdate, "username")

    def test_profile_email_can_be_cleared_for_employee_accounts(self):
        self.assertIsNone(UserProfileUpdate.model_validate({"email": None}).email)

    def test_role_sensitive_fields_reject_explicit_null(self):
        self.assert_rejects_null(RoleUpdate, "is_active")
        self.assert_rejects_null(RoleUpdate, "permissions")

    def test_crop_required_fields_reject_explicit_null(self):
        self.assert_rejects_null(CropUpdate, "planting_date")
        self.assert_rejects_null(CropUpdate, "area_hectares")

    def test_inventory_required_fields_reject_explicit_null(self):
        self.assert_rejects_null(InventoryUpdate, "unit")
        self.assert_rejects_null(InventoryUpdate, "date_acquired")

    def test_livestock_required_fields_reject_explicit_null(self):
        self.assert_rejects_null(LivestockUpdate, "quantity")
        self.assert_rejects_null(LivestockUpdate, "growth_status")

    def test_nullable_note_fields_can_still_be_cleared(self):
        self.assertIsNone(InventoryUpdate.model_validate({"notes": None}).notes)
        self.assertIsNone(LivestockUpdate.model_validate({"health_notes": None}).health_notes)


if __name__ == "__main__":
    unittest.main()
