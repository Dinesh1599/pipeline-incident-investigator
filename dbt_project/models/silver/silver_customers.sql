-- silver_customers.sql
-- Deduplicates by customer_id, standardizes name fields.
-- Depends on: source bronze_customers

SELECT DISTINCT ON (CAST(customer_id AS INTEGER))
    CAST(customer_id AS INTEGER)    AS customer_id,
    INITCAP(TRIM(customer_name))    AS customer_name,
    LOWER(TRIM(email))              AS email,
    UPPER(TRIM(region))             AS region
FROM {{ source('bronze', 'customers') }}
WHERE customer_id IS NOT NULL
ORDER BY CAST(customer_id AS INTEGER)