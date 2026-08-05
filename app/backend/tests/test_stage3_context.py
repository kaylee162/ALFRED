from __future__ import annotations

import unittest
from datetime import timedelta

from context.confirmation_executor import confirmation_choice, execute_pending_action
from context.context_models import PendingAction, utc_now
from context.conversation_context import ConversationContext
from context.pending_action_store import PendingActionStore
from memory.memory_repository import MemoryRepository
from memory.memory_service import MemoryService


class ConversationContextTests(unittest.TestCase):
    def test_recent_turns_and_route(self):
        context = ConversationContext(max_turns=3, ttl_minutes=30)
        context.add_turn(
            session_id="test",
            user_text="show my downloads",
            assistant_text="I found three files.",
            route="files",
            response_type="folder",
        )
        self.assertEqual(context.last_route("test"), "files")
        self.assertIn("show my downloads", context.build_prompt_context("test"))

    def test_contextual_follow_up(self):
        context = ConversationContext()
        self.assertTrue(context.is_contextual_follow_up("open the second one"))
        self.assertTrue(context.is_contextual_follow_up("move it to Friday"))
        self.assertFalse(context.is_contextual_follow_up("explain recursion"))

    def test_clear(self):
        context = ConversationContext()
        context.add_turn(
            session_id="test",
            user_text="hello",
            assistant_text="Hello.",
            route="chat",
            response_type="chat",
        )
        self.assertEqual(context.clear("test"), 1)
        self.assertEqual(context.recent("test"), [])


class PendingActionTests(unittest.TestCase):
    def test_choice_parser(self):
        self.assertIs(confirmation_choice("Yes"), True)
        self.assertIs(confirmation_choice("go ahead"), True)
        self.assertIs(confirmation_choice("No"), False)
        self.assertIsNone(confirmation_choice("maybe"))

    def test_expiration(self):
        store = PendingActionStore(ttl_minutes=15)
        action = store.set(
            session_id="test",
            kind="tool_confirmation",
            route="calendar",
            original_command="delete dentist",
        )
        action.expires_at = utc_now() - timedelta(seconds=1)
        self.assertIsNone(store.get("test"))

    def test_capture(self):
        store = PendingActionStore()
        action = store.capture_from_result(
            session_id="test",
            original_command="send it",
            route="email",
            result={
                "response": "Confirm send?",
                "requires_confirmation": True,
                "confirmation": {"token": "abc123"},
            },
        )
        self.assertIsNotNone(action)
        self.assertEqual(action.payload["confirmation_token"], "abc123")


class MemoryClearConfirmationTests(unittest.TestCase):
    def test_cancel_memory_clear(self):
        action = PendingAction(
            kind="memory_clear",
            route="memory",
            original_command="clear all memories",
        )
        result = execute_pending_action(action, confirmed=False)
        self.assertEqual(result["memory_action"], "cancelled")


if __name__ == "__main__":
    unittest.main()
