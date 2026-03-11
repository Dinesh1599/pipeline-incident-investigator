#!/bin/bash
# ============================================================
# trigger_failure.sh — Swap seed CSVs to trigger failure scenarios
#
# Usage:
#   ./scripts/trigger_failure.sh null_key
#   ./scripts/trigger_failure.sh schema_drift
#   ./scripts/trigger_failure.sh missing_partition
#   ./scripts/trigger_failure.sh clean
# ============================================================

set -euo pipefail

SEEDS_DIR="dbt_project/seeds"

case "${1:-}" in
    null_key)
        echo "Scenario 1: Null Join Key"
        echo "Swapping raw_sales.csv with raw_sales_nulls.csv"
        cp "$SEEDS_DIR/raw_sales_nulls.csv" "$SEEDS_DIR/raw_sales.csv"
        echo "Done. Trigger the DAG to see fct_sales fail with NOT NULL violation."
        ;;
    schema_drift)
        echo "Scenario 2: Schema Drift"
        echo "Swapping raw_customers.csv with raw_customers_schema_drift.csv"
        cp "$SEEDS_DIR/raw_customers_schema_drift.csv" "$SEEDS_DIR/raw_customers.csv"
        echo "Done. Trigger the DAG to see silver_customers fail with type cast error."
        ;;
    missing_partition)
        echo "Scenario 3: Missing Partition"
        echo "Swapping raw_sales.csv with raw_sales_missing_partition.csv"
        cp "$SEEDS_DIR/raw_sales_missing_partition.csv" "$SEEDS_DIR/raw_sales.csv"
        echo "Done. Trigger the DAG — pipeline succeeds but March 4th data is missing."
        ;;
    clean)
        echo "Restoring clean data"
        git checkout "$SEEDS_DIR/raw_sales.csv" "$SEEDS_DIR/raw_customers.csv" 2>/dev/null || {
            echo "Git restore failed. Manually replace with original clean CSVs."
            exit 1
        }
        echo "Done. Clean data restored."
        ;;
    *)
        echo "Usage: $0 {null_key|schema_drift|missing_partition|clean}"
        exit 1
        ;;
esac
