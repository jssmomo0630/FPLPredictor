import unittest
from unittest import mock

import send_fpl_email as emailer


def sample_status():
    return {
        "read_only": True,
        "gameweek": {
            "next": {"id": 4},
            "deadline_time_local": "2026-09-12T05:30:00-07:00",
        },
        "squad": {
            "source_event_id": 3,
            "player_count": 2,
            "players": [
                {"position": "GK", "player_name": "Safe", "team": "Alpha", "availability": "available"},
                {
                    "position": "MID",
                    "player_name": "Risk & Co",
                    "team": "Beta",
                    "availability": "doubtful",
                    "news": "Knock <25%>",
                },
            ],
        },
        "decision": {"action": "no_action", "reason": "Monitoring."},
    }


class EmailRenderTests(unittest.TestCase):
    def test_render_includes_source_warning_and_escapes_html(self):
        subject, text_body, html_body = emailer.render_email(sample_status())
        self.assertEqual(subject, "[FPL] Email delivery test — GW4")
        self.assertIn("locked at the GW3 deadline", text_body)
        self.assertIn("Risk &amp; Co", html_body)
        self.assertIn("Knock &lt;25%&gt;", html_body)

    def test_rejects_payload_without_read_only_marker(self):
        with self.assertRaisesRegex(ValueError, "read_only"):
            emailer.render_email({"read_only": False})

    def test_builds_multipart_message(self):
        subject, text_body, html_body = emailer.render_email(sample_status())
        message = emailer.build_message(subject, text_body, html_body, "sender@example.com", ["to@example.com"])
        self.assertEqual(message["To"], "to@example.com")
        self.assertTrue(message.is_multipart())
        self.assertEqual(len(message.get_payload()), 2)

    @mock.patch("send_fpl_email.smtplib.SMTP_SSL")
    def test_smtp_uses_tls_login_and_send(self, smtp_ssl):
        smtp = smtp_ssl.return_value.__enter__.return_value
        message = emailer.build_message("Subject", "Text", "<p>HTML</p>", "sender@example.com", ["to@example.com"])
        emailer.send_message(message, "sender@example.com", "app-password")
        smtp.login.assert_called_once_with("sender@example.com", "app-password")
        smtp.send_message.assert_called_once_with(message)


if __name__ == "__main__":
    unittest.main()
