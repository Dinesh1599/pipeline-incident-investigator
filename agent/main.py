"""
main.py — Entry point for the investigator-api container.

Serves a simple HTTP API that accepts investigation triggers
from the Airflow failure callback and returns results.

Endpoints:
    POST /investigate  — Trigger a new investigation
    GET  /health       — Health check
    GET  /incidents    — List recent incidents

This is what the investigator-api Docker container runs.
"""

import json
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler

from agent.graph import compile_graph
from agent.memory.incident_store import get_all_incidents

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

PORT = 8000
app = None  # Compiled graph, initialized on startup


class InvestigatorHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the investigator API."""

    def do_GET(self):
        if self.path == "/health":
            self._respond(200, {"status": "healthy"})

        elif self.path == "/incidents":
            try:
                incidents = get_all_incidents()
                summaries = [
                    {
                        "incident_id": inc.get("incident_id"),
                        "failure_class": inc.get("failure_class"),
                        "confidence": inc.get("confidence"),
                        "issue_summary": inc.get("issue_summary", "")[:200],
                        "created_at": str(inc.get("created_at", "")),
                    }
                    for inc in incidents[:20]
                ]
                self._respond(200, {"incidents": summaries, "count": len(summaries)})
            except Exception as e:
                self._respond(500, {"error": str(e)})

        else:
            self._respond(404, {"error": "Not found"})

    def do_POST(self):
        if self.path == "/investigate":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length)
                trigger = json.loads(body)

                logger.info("Investigation triggered: %s", json.dumps(trigger, indent=2))

                result = app.invoke(trigger)
                report = result.get("final_report", {})

                self._respond(200, report)

            except json.JSONDecodeError:
                self._respond(400, {"error": "Invalid JSON"})
            except Exception as e:
                logger.error("Investigation failed: %s", e)
                self._respond(500, {"error": str(e)})

        else:
            self._respond(404, {"error": "Not found"})

    def _respond(self, status: int, data: dict):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, default=str).encode())

    def log_message(self, format, *args):
        """Suppress default request logging — we use our own logger."""
        pass


def main():
    global app

    logger.info("Compiling investigation graph...")
    app = compile_graph()
    logger.info("Graph compiled successfully")

    server = HTTPServer(("0.0.0.0", PORT), InvestigatorHandler)
    logger.info("Investigator API running on port %d", PORT)
    logger.info("Endpoints: POST /investigate, GET /health, GET /incidents")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        server.server_close()


if __name__ == "__main__":
    main()