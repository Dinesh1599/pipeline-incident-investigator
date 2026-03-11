-- silver_sales.sql
-- Casts types from bronze TEXT columns, filters for valid dates.
-- Depends on: source bronze_sales
--
-- Scenario 1 (Null Join Key): NULL customer_id passes through as NULL integer.
-- Scenario 2 (Schema Drift): 'CUST-001' format fails CAST to INTEGER here.

SELECT
    CAST(order_id AS INTEGER)           AS order_id,
    CAST(customer_id AS INTEGER)        AS customer_id,
    CAST(order_date AS DATE)            AS order_date,
    product,
    CAST(quantity AS INTEGER)           AS quantity,
    CAST(unit_price AS NUMERIC(10,2))   AS unit_price,
    CAST(quantity AS INTEGER) * CAST(unit_price AS NUMERIC(10,2)) AS total_amount
FROM {{ source('bronze', 'sales') }}
WHERE order_date IS NOT NULL