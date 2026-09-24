{#-
    Overriding the schema naming.

    By default, dbt CONCATENATES the target schema and the custom schema: with
    target.schema = "analytics" and +schema: staging, the models would land in
    a schema called "analytics_staging".

    That behaviour protects shared environments (each developer works under
    their own prefix). Here we want exactly the schemas created in PHASE 1:
    `staging` and `analytics`. So we override the macro.

    This is one of the most common dbt overrides - and one of the first sources
    of confusion when discovering the tool.
-#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
