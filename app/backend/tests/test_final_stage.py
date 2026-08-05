from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from context.conversation_context import ConversationContext
from context.pending_action_store import PendingActionStore
from context.state_repository import AgentStateRepository
from context.workflow_store import WorkflowStore
from memory.episodic_service import EpisodicMemoryService
from memory.memory_repository import MemoryRepository
from memory.memory_service import MemoryService


class FinalStagePersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "alfred.db"
        self.state = AgentStateRepository(self.db)

    def tearDown(self):
        self.temp.cleanup()

    def test_conversation_survives_new_service_instance(self):
        first = ConversationContext(self.state)
        first.add_turn(
            session_id="one",
            user_text="show my projects",
            assistant_text="I found three projects.",
            route="projects",
            response_type="projects",
        )
        second = ConversationContext(AgentStateRepository(self.db))
        self.assertEqual(second.last_route("one"), "projects")
        self.assertIn("show my projects", second.build_prompt_context("one"))

    def test_pending_action_survives_new_service_instance(self):
        first = PendingActionStore(self.state)
        first.set(
            session_id="one",
            kind="tool_confirmation",
            route="email",
            original_command="send it",
            payload={"confirmation_token": "abc"},
        )
        second = PendingActionStore(AgentStateRepository(self.db))
        action = second.get("one")
        self.assertIsNotNone(action)
        self.assertEqual(action.payload["confirmation_token"], "abc")

    def test_workflow_deduplicates_completed_tool_step(self):
        store = WorkflowStore(self.state)
        workflow = store.start(
            session_id="one",
            original_command="show weather and calendar",
        )
        args = {"location": "Atlanta"}
        result = {"response": "Sunny"}
        store.record_step(
            workflow_id=workflow.workflow_id,
            tool_name="weather",
            arguments=args,
            result=result,
        )
        self.assertEqual(
            store.completed_result(workflow.workflow_id, "weather", args),
            result,
        )

    def test_episode_survives_new_service_instance(self):
        first = EpisodicMemoryService(self.state)
        first.record(
            session_id="one",
            route="calendar",
            event_type="calendar_updated",
            summary="Moved Dentist to Friday at 3 PM.",
        )
        second = EpisodicMemoryService(AgentStateRepository(self.db))
        matches = second.search("When was Dentist moved?")
        self.assertTrue(matches)
        self.assertIn("Friday at 3 PM", matches[0]["summary"])

    def test_automatic_preference_learning(self):
        repository = MemoryRepository(self.db)
        service = MemoryService(repository)
        learned = service.maybe_learn_durable_preference(
            "I prefer React examples in TypeScript"
        )
        self.assertIsNotNone(learned)
        memory, created = learned
        self.assertTrue(created)
        self.assertEqual(memory.source, "automatic")


if __name__ == "__main__":
    unittest.main()
