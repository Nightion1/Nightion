import unittest
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from main import app

class TestWebSocket(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_websocket_chat_flow(self):
        with self.client.websocket_connect("/ws/chat") as websocket:
            websocket.send_json({"message": "test socket flow", "use_rag": False})
            
            # The immediate processing token
            data1 = websocket.receive_json()
            self.assertEqual(data1["type"], "token")
            self.assertTrue("Processing [Trace:" in data1["content"])
            
            # The execution stream token
            data2 = websocket.receive_json()
            self.assertEqual(data2["type"], "token")
            
            # The finalization payload
            data3 = websocket.receive_json()
            self.assertEqual(data3["type"], "done")
            self.assertFalse(data3["rag_used"])

    def test_health_includes_model_ready(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("model_ready", data)
        self.assertIn("ollama_ready", data)
        self.assertIn("status", data)

    def test_greeting_returns_friendly_response(self):
        with self.client.websocket_connect("/ws/chat") as websocket:
            websocket.send_json({"message": "hi", "use_rag": False, "session_id": "test_session"})
            
            # 1. Processing token
            data1 = websocket.receive_json()
            self.assertEqual(data1["type"], "token")
            
            # 2. Response token
            data2 = websocket.receive_json()
            self.assertEqual(data2["type"], "token")
            self.assertIn("Hello! How can I help you today?", data2["content"])
            
            # 3. Done
            data3 = websocket.receive_json()
            self.assertEqual(data3["type"], "done")

if __name__ == '__main__':
    unittest.main()
