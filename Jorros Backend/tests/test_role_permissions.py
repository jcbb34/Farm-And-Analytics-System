import unittest

from app.services.permissions import (
    DEFAULT_ROLE_PERMISSIONS,
    default_permissions_for_role,
    normalize_permissions,
)


class RolePermissionTests(unittest.TestCase):
    def test_system_administrator_has_wildcard(self):
        self.assertIn("*", default_permissions_for_role("System Administrator"))

    def test_farm_staff_is_scoped_to_employee_workflow(self):
        permissions = default_permissions_for_role("Farm Staff")
        self.assertEqual(permissions, ["workforce:submit"])
        self.assertNotIn("crops:update", permissions)
        self.assertNotIn("livestock:update", permissions)
        self.assertNotIn("production_sales:update", permissions)
        self.assertNotIn("*", permissions)


    def test_report_and_export_permissions_exclude_employee_accounts(self):
        employee = default_permissions_for_role("Employee")
        manager = default_permissions_for_role("Manager")
        self.assertNotIn("reports:view", employee)
        self.assertNotIn("reports:export", employee)
        self.assertIn("reports:view", manager)
        self.assertIn("reports:export", manager)

    def test_permissions_are_normalized_and_deduplicated(self):
        self.assertEqual(
            normalize_permissions(["crops:view", "crops:update", "crops:view", ""]),
            ["crops:update", "crops:view"],
        )

    def test_known_roles_are_defined(self):
        self.assertIn("Viewer", DEFAULT_ROLE_PERMISSIONS)
        self.assertIn("Farm Staff", DEFAULT_ROLE_PERMISSIONS)

    def test_viewer_can_view_but_not_edit_production_sales(self):
        permissions = default_permissions_for_role("Viewer")
        self.assertIn("production_sales:view", permissions)
        self.assertNotIn("production_sales:update", permissions)


if __name__ == "__main__":
    unittest.main()
