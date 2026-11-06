from django.test import SimpleTestCase


class ApiSecurityTests(SimpleTestCase):
    def test_health_does_not_require_credentials(self):
        response = self.client.get("/api/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_elevator_list_requires_credentials(self):
        response = self.client.get("/api/elevators/")
        self.assertIn(response.status_code, (401, 403))

    def test_ticket_list_requires_credentials(self):
        response = self.client.get("/api/tickets/")
        self.assertIn(response.status_code, (401, 403))


from django.contrib.auth import get_user_model
from django.test import TestCase


class DashboardAccessTests(TestCase):
    def test_home_requires_admin_login(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])

    def test_regular_user_cannot_open_dashboard(self):
        regular = get_user_model().objects.create_user(username="testviewer", password="test-password-not-used")
        self.client.force_login(regular)
        self.assertEqual(self.client.get("/").status_code, 302)
        self.assertEqual(self.client.get("/api/dashboard/").status_code, 403)
        self.assertEqual(self.client.get("/api/buildings/").status_code, 403)

    def test_staff_user_can_read_dashboard(self):
        staff = get_user_model().objects.create_user(username="teststaff", password="test-password-not-used", is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/api/dashboard/").status_code, 200)
