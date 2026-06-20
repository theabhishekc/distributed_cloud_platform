import unittest
import json
import io
import logging
from shared.logger import get_logger, JSONFormatter

class TestStructuredLogger(unittest.TestCase):
    def test_json_logging_output(self):
        """
        Verify that our structured logger produces valid JSON with all core fields.
        JSON format is activated by setting LOG_FORMAT=json.
        """
        logger_adapter = get_logger("test_comp", node_id="test_node")
        logger = logger_adapter.logger

        # Replace handlers with a StringIO stream to capture output
        logger.handlers.clear()
        log_buffer = io.StringIO()
        handler = logging.StreamHandler(log_buffer)
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)

        # Log a structured message
        logger_adapter.info(
            "Test message",
            extra={"event": "test_event", "custom_key": "custom_val", "cpu": 45.2}
        )

        output_str = log_buffer.getvalue().strip()
        self.assertTrue(output_str, "Logger output should not be empty")

        # Parse output as JSON
        log_json = json.loads(output_str)

        # Verify core fields
        self.assertIn("timestamp", log_json)
        self.assertEqual(log_json["level"],     "INFO")
        self.assertEqual(log_json["node_id"],   "test_node")
        self.assertEqual(log_json["component"], "test_comp")
        self.assertEqual(log_json["event"],     "test_event")
        self.assertEqual(log_json["message"],   "Test message")

        # Verify extra data is nested under "extra"
        self.assertIn("extra", log_json)
        self.assertEqual(log_json["extra"]["custom_key"], "custom_val")
        self.assertEqual(log_json["extra"]["cpu"], 45.2)

    def test_default_event(self):
        """
        Verify that if no event is specified, it defaults to 'generic'.
        """
        logger_adapter = get_logger("test_comp_default", node_id="test_node")
        logger = logger_adapter.logger
        
        logger.handlers.clear()
        log_buffer = io.StringIO()
        handler = logging.StreamHandler(log_buffer)
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
        
        logger_adapter.info("Message without event")
        
        log_json = json.loads(log_buffer.getvalue().strip())
        self.assertEqual(log_json["event"], "generic")
