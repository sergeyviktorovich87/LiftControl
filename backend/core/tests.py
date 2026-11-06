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
