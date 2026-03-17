"""
dbt_connector.py — Parses dbt artifacts and reads model SQL files.

Provides:
    - manifest.json parsing (model metadata, depends_on, compiled SQL)
    - run_results.json parsing (run status, timing, error messages)
    - Model SQL file reading
    - Lineage extraction from depends_on graph


"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class DbtConnector:
    """Reads and parses dbt project artifacts."""

    def __init__(self, project_dir: Optional[str] = None):
        self.project_dir = Path(
            project_dir or os.environ.get("DBT_PROJECT_DIR", "/dbt")
        )
        self.target_dir = self.project_dir / "target"

    def _read_json(self, filepath: Path) -> dict:
        """Read and parse a JSON file."""
        try:
            with open(filepath, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning("File not found: %s", filepath)
            return {}
        except json.JSONDecodeError as e:
            logger.error("Invalid JSON in %s: %s", filepath, e)
            return {}

    def get_manifest(self) -> dict:
        """Read the full dbt manifest.json."""
        return self._read_json(self.target_dir / "manifest.json")

    def get_run_results(self) -> dict:
        """Read dbt run_results.json from the last run."""
        return self._read_json(self.target_dir / "run_results.json")

    def get_model_entry(self, model_name: str) -> dict:
        """Get a specific model's entry from manifest.json.

        'Once the dbt model is identified, the agent reads its 
        entry from manifest.json.
        This provides: the target table/view, all source tables
        (depends_on), the raw SQL, the schema and database, and
        any defined tests.'

        Args:
            model_name: The dbt model name (e.g., 'fct_sales')

        Returns:
            Dict with model metadata or empty dict if not found.
        """
        manifest = self.get_manifest()
        nodes = manifest.get("nodes", {})

        for node_id, node in nodes.items():
            if node.get("name") == model_name and node.get("resource_type") == "model":
                return {
                    "unique_id": node_id,
                    "name": node.get("name"),
                    "schema": node.get("schema"),
                    "database": node.get("database"),
                    "relation_name": node.get("relation_name"),
                    "depends_on": node.get("depends_on", {}),
                    "raw_sql": node.get("raw_code", node.get("raw_sql", "")),
                    "compiled_sql": node.get("compiled_code", node.get("compiled_sql", "")),
                    "columns": node.get("columns", {}),
                    "config": node.get("config", {}),
                    "description": node.get("description", ""),
                    "path": node.get("path", ""),
                    "original_file_path": node.get("original_file_path", ""),
                }

        logger.warning("Model '%s' not found in manifest", model_name)
        return {}

    def get_model_sql(self, model_name: str) -> str:
        """Read the raw SQL file for a dbt model.

        Searches the models directory for the SQL file matching
        the model name.
        """
        models_dir = self.project_dir / "models"
        for sql_file in models_dir.rglob(f"{model_name}.sql"):
            try:
                return sql_file.read_text()
            except IOError as e:
                logger.error("Failed to read %s: %s", sql_file, e)
                return ""

        logger.warning("SQL file for model '%s' not found", model_name)
        return ""

    def get_run_result_for_model(self, model_name: str) -> dict:
        """Get the run result for a specific model from run_results.json.

        Returns timing, status, error message, and execution details.
        """
        run_results = self.get_run_results()
        for result in run_results.get("results", []):
            unique_id = result.get("unique_id", "")
            if unique_id.endswith(f".{model_name}"):
                return {
                    "unique_id": unique_id,
                    "status": result.get("status"),
                    "execution_time": result.get("execution_time"),
                    "message": result.get("message", ""),
                    "failures": result.get("failures"),
                    "adapter_response": result.get("adapter_response", {}),
                }
        return {}

    def get_upstream_models(self, model_name: str) -> list[str]:
        """Get the list of upstream model names for a given model.

        Uses the depends_on.nodes field from manifest.json.
        Only returns model dependencies, not sources or tests.
        """
        entry = self.get_model_entry(model_name)
        depends_on = entry.get("depends_on", {})
        nodes = depends_on.get("nodes", [])
        return [
            node_id.split(".")[-1]
            for node_id in nodes
            if node_id.startswith("model.")
        ]

    def get_upstream_sources(self, model_name: str) -> list[dict]:
        """Get the list of upstream source tables for a given model.

        Returns source name and table name pairs.
        """
        entry = self.get_model_entry(model_name)
        depends_on = entry.get("depends_on", {})
        nodes = depends_on.get("nodes", [])

        sources = []
        manifest = self.get_manifest()
        all_sources = manifest.get("sources", {})

        for node_id in nodes:
            if node_id.startswith("source."):
                source_entry = all_sources.get(node_id, {})
                if source_entry:
                    sources.append({
                        "source_name": source_entry.get("source_name"),
                        "table_name": source_entry.get("name"),
                        "schema": source_entry.get("schema"),
                    })
        return sources

    def get_downstream_models(self, model_name: str) -> list[str]:
        """Get models that depend on the given model.

        Useful for understanding blast radius of a failure.
        """
        manifest = self.get_manifest()
        child_map = manifest.get("child_map", {})

        model_key = None
        for node_id in manifest.get("nodes", {}):
            if node_id.endswith(f".{model_name}"):
                model_key = node_id
                break

        if not model_key:
            return []

        children = child_map.get(model_key, [])
        return [
            child_id.split(".")[-1]
            for child_id in children
            if child_id.startswith("model.")
        ]

    def build_lineage(self, model_name: str) -> dict:
        """Build the full lineage context for a model.

        Returns upstream models, upstream sources, downstream models,
        and the dependency chain. This is used by the Lineage Tracer
        node (Node 8).
        """
        return {
            "model": model_name,
            "upstream_models": self.get_upstream_models(model_name),
            "upstream_sources": self.get_upstream_sources(model_name),
            "downstream_models": self.get_downstream_models(model_name),
        }

    def collect_context(self, model_name: str) -> dict:
        """Collect all dbt context for an investigation.

        Main method called by the Context Collector node.
        """
        model_entry = self.get_model_entry(model_name)
        model_sql = self.get_model_sql(model_name)
        run_result = self.get_run_result_for_model(model_name)
        lineage = self.build_lineage(model_name)

        return {
            "dbt_manifest_entry": model_entry,
            "model_sql": model_sql,
            "run_result": run_result,
            "lineage_context": lineage,
            "dbt_available": bool(model_entry),
        }
