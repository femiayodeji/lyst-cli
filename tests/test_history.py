import unittest

from app.history import (
    load_history, save_history, clear_history, history_summary,
    create_session, get_session, list_sessions, delete_session,
    set_active_session, get_active_session, clear_all_sessions
)


class TestHistory(unittest.TestCase):
    """Tests for history module using in-memory session storage."""

    def setUp(self):
        """Clear all sessions before each test."""
        clear_all_sessions()

    def tearDown(self):
        """Clean up after each test."""
        clear_all_sessions()

    def test_create_session(self):
        """Create a new session."""
        session = create_session("Test Session")
        self.assertEqual(session.name, "Test Session")
        self.assertEqual(len(session.messages), 0)
        self.assertIsNotNone(session.id)

    def test_create_session_sets_active(self):
        """Creating a session makes it active."""
        session = create_session()
        active = get_active_session()
        self.assertIsNotNone(active)
        self.assertEqual(active.id, session.id)

    def test_list_sessions(self):
        """List all sessions."""
        create_session("Session 1")
        create_session("Session 2")
        sessions = list_sessions()
        self.assertEqual(len(sessions), 2)

    def test_delete_session(self):
        """Delete a session."""
        session = create_session()
        session_id = session.id
        self.assertTrue(delete_session(session_id))
        self.assertIsNone(get_session(session_id))

    def test_set_active_session(self):
        """Switch active session."""
        s1 = create_session("First")
        s2 = create_session("Second")
        self.assertEqual(get_active_session().id, s2.id)
        
        set_active_session(s1.id)
        self.assertEqual(get_active_session().id, s1.id)

    def test_save_and_load_history(self):
        """Save and load messages in active session."""
        create_session()
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        save_history(messages)
        loaded = load_history()
        self.assertEqual(loaded, messages)

    def test_clear_history(self):
        """Clear messages in active session."""
        create_session()
        messages = [{"role": "user", "content": "Test"}]
        save_history(messages)
        clear_history()
        self.assertEqual(load_history(), [])

    def test_history_summary_no_session(self):
        """History summary with no active session."""
        summary = history_summary()
        self.assertEqual(summary, "No active session.")

    def test_history_summary_with_messages(self):
        """History summary shows exchange count."""
        create_session("My Session")
        messages = [
            {"role": "user", "content": "Q1"},
            {"role": "assistant", "content": "A1"},
            {"role": "user", "content": "Q2"},
            {"role": "assistant", "content": "A2"},
        ]
        save_history(messages)
        summary = history_summary()
        self.assertIn("2 exchange", summary)
        self.assertIn("My Session", summary)

    def test_history_across_sessions(self):
        """Each session maintains its own history."""
        s1 = create_session("Session 1")
        save_history([{"role": "user", "content": "In session 1"}])
        
        s2 = create_session("Session 2")
        save_history([{"role": "user", "content": "In session 2"}])
        
        # Check session 2 (active)
        self.assertEqual(load_history()[0]["content"], "In session 2")
        
        # Switch to session 1
        set_active_session(s1.id)
        self.assertEqual(load_history()[0]["content"], "In session 1")


if __name__ == "__main__":
    unittest.main()
