-- fct_sales.sql
-- Joins silver_sales with silver_customers, aggregates by customer and date.
-- Depends on: silver_sales, silver_customers
--
-- Scenario 1 (Null Join Key): LEFT JOIN preserves NULL customer_ids from
--   silver_sales. The model contract enforces NOT NULL on customer_id,
--   so dbt run fails with a constraint violation.
-- Scenario 3 (Missing Partition): No rows for 2026-03-04 means zero output
--   for that date. Pipeline succeeds but produces wrong results.

SELECT
    ss.customer_id,
    sc.customer_name,
    sc.region,
    ss.order_date,
    COUNT(*)                AS order_count,
    SUM(ss.total_amount)    AS daily_revenue
FROM {{ ref('silver_sales') }} ss
LEFT JOIN {{ ref('silver_customers') }} sc
    ON ss.customer_id = sc.customer_id
GROUP BY
    ss.customer_id,
    sc.customer_name,
    sc.region,
    ss.order_date