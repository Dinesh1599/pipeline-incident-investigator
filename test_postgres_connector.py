"""Test Postgres connector against pipeline_db."""

from dotenv import load_dotenv
load_dotenv(".env.local")

from agent.connectors.postgres_connector import PostgresConnector


def test_postgres_connector():
    pc = PostgresConnector()

    # Table existence
    print("── Table Existence ──")
    print(f"bronze.sales exists: {pc.check_table_exists('sales', 'bronze')}")
    print(f"bronze.customers exists: {pc.check_table_exists('customers', 'bronze')}")
    print(f"silver.silver_sales exists: {pc.check_table_exists('silver_sales', 'silver')}")
    print(f"gold.fct_sales exists: {pc.check_table_exists('fct_sales', 'gold')}")
    print(f"fake.table exists: {pc.check_table_exists('fake_table', 'public')}")
    print()

    # Column metadata
    print("── bronze.sales Columns ──")
    result = pc.get_table_columns("sales", "bronze")
    for row in result["rows"]:
        print(f"  {row['column_name']:15s} {row['data_type']:10s} nullable={row['is_nullable']}")
    print()

    # Constraints
    print("── gold.fct_sales Constraints ──")
    result = pc.get_table_constraints("fct_sales", "gold")
    if result["rows"]:
        for row in result["rows"]:
            print(f"  {row['constraint_name']} ({row['constraint_type']}) on {row['column_name']}")
    else:
        print("  No constraints found")
    print()

    # All tables per schema
    for schema in ["bronze", "silver", "gold"]:
        result = pc.get_all_tables(schema)
        tables = [r["table_name"] for r in result["rows"]]
        print(f"── {schema} tables: {tables}")

    # Full metadata collection
    print("\n── Full Metadata: bronze.sales ──")
    metadata = pc.collect_metadata("sales", "bronze")
    print(f"  exists: {metadata['exists']}")
    print(f"  columns: {metadata['columns']['row_count']}")
    print()

    print("All Postgres connector tests passed.")


if __name__ == "__main__":
    test_postgres_connector()
