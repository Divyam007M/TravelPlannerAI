import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from backend import main
from Travel_Planner_Agent import SCOPE_REPLY, build_graph, estimate_budget, get_city_info, get_packing_list


class FakeLLM:
    def __init__(self):
        self.calls = []

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        self.calls.append(messages)
        humans = [m.content for m in messages if isinstance(m, HumanMessage)]
        return AIMessage(content=f"Reply {len(humans)}: {humans[-1]}")


class WanderTests(unittest.TestCase):
    def setUp(self):
        main.app.state.stateless = False
        main._sessions.clear()
        main._locks.clear()
        self.fake = FakeLLM()
        main._graph = build_graph(self.fake)
        self.client = TestClient(main.app)

    def tearDown(self):
        main._graph = None
        main.app.state.stateless = False

    def test_health_and_validation(self):
        self.assertEqual(self.client.get("/api/health").json()["status"], "ok")
        self.assertEqual(self.client.post("/api/chat", json={"message": "   "}).status_code, 422)
        self.assertEqual(self.client.post("/api/chat", json={"message": "x" * 4001}).status_code, 422)
        self.assertEqual(self.client.post("/api/clear", json={"session_id": "bad"}).status_code, 422)

    def test_context_isolation_and_clear(self):
        a = self.client.post("/api/chat", json={"message": "Goa"}).json()
        b = self.client.post("/api/chat", json={"message": "Jaipur"}).json()
        follow = self.client.post("/api/chat", json={"message": "What next?", "session_id": a["session_id"]}).json()
        self.assertEqual(follow["reply"], "Reply 2: What next?")
        self.assertNotEqual(a["session_id"], b["session_id"])
        self.assertEqual(len(main._sessions[a["session_id"]]), 4)
        self.assertEqual(len(main._sessions[b["session_id"]]), 2)
        self.assertEqual(len(self.fake.calls[-1]), 4)  # system + prior user/assistant + new user
        self.assertTrue(self.client.post("/api/clear", json={"session_id": a["session_id"]}).json()["cleared"])
        fresh = self.client.post("/api/chat", json={"message": "Goa again", "session_id": a["session_id"]}).json()
        self.assertEqual(fresh["reply"], "Reply 1: Goa again")

    def test_unrelated_questions_are_declined_without_calling_the_model(self):
        first = self.client.post("/api/chat", json={"message": "What is LCM?"})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["reply"], SCOPE_REPLY)
        self.assertEqual(self.fake.calls, [])

        travel = self.client.post("/api/chat", json={"message": "Plan a trip to Goa", "session_id": first.json()["session_id"]})
        self.assertEqual(travel.status_code, 200)
        self.assertEqual(len(self.fake.calls), 1)

        unrelated_follow_up = self.client.post("/api/chat", json={"message": "Explain photosynthesis", "session_id": first.json()["session_id"]})
        self.assertEqual(unrelated_follow_up.json()["reply"], SCOPE_REPLY)
        self.assertEqual(len(self.fake.calls), 1)

        code_request = self.client.post("/api/chat", json={"message": "Write me a Python program", "session_id": first.json()["session_id"]})
        self.assertEqual(code_request.json()["reply"], SCOPE_REPLY)
        self.assertEqual(len(self.fake.calls), 1)

        relevant_follow_up = self.client.post("/api/chat", json={"message": "What next?", "session_id": first.json()["session_id"]})
        self.assertEqual(relevant_follow_up.status_code, 200)
        self.assertEqual(len(self.fake.calls), 2)

        broader_trip = self.client.post("/api/chat", json={"message": "Plan a weekend in Paris"})
        self.assertEqual(broader_trip.status_code, 200)
        self.assertEqual(len(self.fake.calls), 3)

    def test_error_does_not_commit_history(self):
        class Failing:
            def invoke(self, *_args, **_kwargs):
                raise RuntimeError("secret internal traceback")
        main._graph = Failing()
        result = self.client.post("/api/chat", json={"message": "Goa"})
        self.assertEqual(result.status_code, 502)
        self.assertNotIn("secret", result.text)
        self.assertFalse(main._sessions)

    def test_missing_key(self):
        main._graph = None
        with patch.dict(os.environ, {"GROQ_API_KEY": ""}):
            result = self.client.post("/api/chat", json={"message": "Goa"})
        self.assertEqual(result.status_code, 503)

    def test_same_session_serializes(self):
        session = "550e8400-e29b-41d4-a716-446655440000"
        def send(i):
            return self.client.post("/api/chat", json={"message": f"Plan a trip to Goa for {i + 2} days", "session_id": session})
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(send, range(2)))
        self.assertTrue(all(r.status_code == 200 for r in results))
        self.assertEqual(len(main._sessions[session]), 4)

    def test_tools(self):
        self.assertIn("Amber Fort", get_city_info.invoke({"city": " jaipur "}))
        self.assertIn("No built-in", get_city_info.invoke({"city": "Unknown"}))
        self.assertIn("₹", estimate_budget.invoke({"city": "Goa", "days": 3, "travel_class": "mid-range"}))
        self.assertIn("Invalid day", estimate_budget.invoke({"city": "Goa", "days": -1, "travel_class": "mid"}))
        self.assertIn("Unsupported", estimate_budget.invoke({"city": "Goa", "days": 2, "travel_class": "ultra"}))
        self.assertIn("Sunscreen", get_packing_list.invoke({"destination_type": " BEACH "}))
        self.assertIn("Unsupported", get_packing_list.invoke({"destination_type": "space"}))

    def test_graph_executes_tool_and_recovers_bad_arguments(self):
        class ToolCallingLLM:
            def bind_tools(self, _tools):
                return self

            def invoke(self, messages):
                result = next((m for m in messages if isinstance(m, ToolMessage)), None)
                if result:
                    return AIMessage(content=result.content)
                return AIMessage(content="", tool_calls=[{
                    "name": "estimate_budget",
                    "args": {"city": "Goa", "days": "invalid", "travel_class": "low"},
                    "id": "call-1", "type": "tool_call"
                }])

        graph = build_graph(ToolCallingLLM())
        output = graph.invoke({"messages": [HumanMessage(content="Budget?")]})
        self.assertEqual(len(output["messages"]), 4)
        self.assertIn("Invalid tool arguments", output["messages"][-1].content)

    def test_stateless_vercel_context_and_clear(self):
        main.app.state.stateless = True
        first = self.client.post("/api/chat", json={"message": "Goa"}).json()
        history = [{"role": "user", "content": "Goa"}, {"role": "assistant", "content": first["reply"]}]
        follow = self.client.post("/api/chat", json={"message": "And then?", "session_id": first["session_id"], "history": history})
        self.assertEqual(follow.status_code, 200)
        self.assertEqual(follow.json()["reply"], "Reply 2: And then?")
        self.assertFalse(main._sessions)
        self.assertTrue(self.client.post("/api/clear", json={"session_id": first["session_id"]}).json()["cleared"])
        fresh = self.client.post("/api/chat", json={"message": "Goa again", "session_id": first["session_id"], "history": []}).json()
        self.assertEqual(fresh["reply"], "Reply 1: Goa again")

    def test_stateless_scope_preserves_trip_follow_ups(self):
        main.app.state.stateless = True
        first = self.client.post("/api/chat", json={"message": "Plan a Jaipur trip"}).json()
        history = [{"role": "user", "content": "Plan a Jaipur trip"}, {"role": "assistant", "content": first["reply"]}]
        unrelated = self.client.post("/api/chat", json={"message": "What is LCM?", "history": history})
        self.assertEqual(unrelated.json()["reply"], SCOPE_REPLY)
        self.assertEqual(len(self.fake.calls), 1)
        history.extend([{"role": "user", "content": "What is LCM?"}, {"role": "assistant", "content": SCOPE_REPLY}])
        follow = self.client.post("/api/chat", json={"message": "What next?", "history": history})
        self.assertEqual(follow.status_code, 200)
        self.assertEqual(len(self.fake.calls), 2)

    def test_stateless_history_validation(self):
        main.app.state.stateless = True
        invalid = [
            [{"role": "assistant", "content": "wrong start"}, {"role": "user", "content": "wrong end"}],
            [{"role": "user", "content": "unpaired"}],
            [{"role": "user", "content": "   "}, {"role": "assistant", "content": "reply"}],
            [{"role": "user", "content": "x"}, {"role": "assistant", "content": "y"}] * 11,
        ]
        for history in invalid:
            with self.subTest(history=history):
                self.assertEqual(self.client.post("/api/chat", json={"message": "Goa", "history": history}).status_code, 422)

    def test_vercel_entrypoint_exposes_stateless_app(self):
        import importlib
        from api import index
        app = importlib.reload(index).app
        self.assertIs(app, main.app)
        self.assertTrue(app.state.stateless)


if __name__ == "__main__":
    unittest.main()
