{#-
    Home-grown generic tests.

    dbt ships four basic tests: unique, not_null, accepted_values,
    relationships. Everything else you write yourself.

    A dbt test is a SQL query that must return ZERO rows. Every row returned is
    a violation. That is the whole mental model: you describe what MUST NOT
    exist.
-#}

{% test positive_values(model, column_name) %}
    -- Fails if the column holds a value <= 0.
    select {{ column_name }}
    from {{ model }}
    where {{ column_name }} <= 0
{% endtest %}


{% test non_negative_values(model, column_name) %}
    -- Fails if the column holds a strictly negative value.
    select {{ column_name }}
    from {{ model }}
    where {{ column_name }} < 0
{% endtest %}


{% test valid_email(model, column_name) %}
    -- Fails if a non-null value does not look like an email address.
    -- NULLs are accepted: the transformation deliberately clears invalid
    -- emails rather than dropping the customer.
    select {{ column_name }}
    from {{ model }}
    where {{ column_name }} is not null
      and {{ column_name }} !~ '^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$'
{% endtest %}
