import unittest

from app.state import AppState
from app.history import (
    save_history, clear_history,
    create_session, get_session, list_sessions, delete_session,
    set_active_session, get_active_session, clear_all_sessions
)


class TestHistory(unittest.TestCase):
    """Tests for history module using in-memory session storage."""

    def setUp(self):
        """Create a fresh AppState before each test."""
        self.state = AppState()

    def test_create_session(self):
        """Create a new session."""
        session = create_session(self.state, "Test Session")
        self.assertEqual(session.name, "Test Session")
        self.assertEqual(len(session.messages), 0)
        self.assertIsNotNone(session.id)

    def test_create_session_sets_active(self):
        """Creating a session makes it active."""
        session = create_session(self.state)
        active = get_active_session(self.state)
        self.assertIsNotNone(active)
        assert active is not None
        self.assertEqual(active.id, session.id)

    def test_list_sessions(self):
        """List all sessions."""
        create_session(self.state, "Session 1")
        create_session(self.state, "Session 2")
        sessions = list_sessions(self.state)
        self.assertEqual(len(sessions), 2)

    def test_delete_session(self):
        """Delete a session."""
        session = create_session(self.state)
        session_id = session.id
        self.assertTrue(delete_session(self.state, session_id))
        self.assertIsNone(get_session(self.state, session_id))

    def test_set_active_session(self):
        """Switch active session."""
        s1 = create_session(self.state, "First")
        s2 = create_session(self.state, "Second")
        active = get_active_session(self.state)
        self.assertIsNotNone(active)
        assert active is not None
        self.assertEqual(active.id, s2.id)
        
        set_active_session(self.state, s1.id)
        active = get_active_session(self.state)
        self.assertIsNotNone(active)
        assert active is not None
        self.assertEqual(active.id, s1.id)

    def test_save_and_load_history(self):
        """Save and load messages in active session."""
        create_session(self.state)
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        save_history(self.state, messages)
        session = get_active_session(self.state)
        self.assertIsNotNone(session)
        assert session is not None
        self.assertEqual(session.messages, messages)

    def test_clear_history(self):
        """Clear messages in active session."""
        create_session(self.state)
        messages = [{"role": "user", "content": "Test"}]
        save_history(self.state, messages)
        clear_history(self.state)
        session = get_active_session(self.state)
        self.assertIsNotNone(session)
        assert session is not None
        self.assertEqual(session.messages, [])

    def test_history_across_sessions(self):
        """Each session maintains its own history."""
        s1 = create_session(self.state, "Session 1")
        save_history(self.state, [{"role": "user", "content": "In session 1"}])
        
        s2 = create_session(self.state, "Session 2")
        save_history(self.state, [{"role": "user", "content": "In session 2"}])
        
        # Check session 2 (active)
        active = get_active_session(self.state)
        self.assertIsNotNone(active)
        assert active is not None
        self.assertEqual(active.messages[0]["content"], "In session 2")
        
        # Switch to session 1
        set_active_session(self.state, s1.id)
        active = get_active_session(self.state)
        self.assertIsNotNone(active)
        assert active is not None
        self.assertEqual(active.messages[0]["content"], "In session 1")


if __name__ == "__main__":
    unittest.main()
