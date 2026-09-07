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
    def test_renders_advice_when_present(self):
        advice = {
            "read_only": True,
            "advisory_only": True,
            "target_gameweek": 4,
            "hours_to_deadline": 20,
            "deadline_time_local": "2026-09-12T05:30:00-07:00",
            "deterministic_summary": "Make the stated move.",
            "recommendation": {
                "headline": "Make 1 transfer(s): Old → New",
                "hit_cost_points": 0,
                "bank_after_millions": 0.5,
                "transfers_out": [{"player_name": "Old"}],
                "transfers_in": [{"player_name": "New"}],
                "starting_xi": [{"player_name": f"Starter {index}", "position": "MID"} for index in range(1, 12)],
                "captain": {"player_name": "Starter 1"},
                "vice_captain": {"player_name": "Starter 2"},
                "bench": [{"player_name": f"Bench {index}", "position": "DEF"} for index in range(1, 5)],
                "chip_advice": {
                    "recommendation": "Save all chips",
                    "tentative_schedule": [
                        {"chip": "triple_captain", "gameweek": 7},
                    ],
                    "chip_period": {"start_gameweek": 1, "end_gameweek": 19},
                },
            },
            "assumptions": {
                "free_transfers_assumed": 1,
                "public_squad_warning": "Locked squad only.",
                "free_transfer_warning": "Free transfers unknown.",
                "selling_price_warning": "Current prices used.",
            },
        }
        summary = {"used_ai": True, "summary": "AI summary from fixed facts."}
        subject, text_body, html_body = emailer.render_email(sample_status(), advice, summary)
        self.assertEqual(subject, "[FPL] GW4 recommendations — 20h to deadline")
        self.assertIn("Old → New", text_body)
        self.assertIn("expires at the GW19 deadline", text_body)
        self.assertIn("Triple Captain GW7", text_body)
        self.assertIn("AI commentary", html_body)
        self.assertIn("Advisory only", html_body)

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
