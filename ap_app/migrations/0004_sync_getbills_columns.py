from django.db import migrations


GETBILLS_COLUMNS = (
    ('tran_year', 'text'), ('branch_code', 'bigint'), ('voucher_no', 'text'),
    ('party_code', 'bigint'), ('bill_date', 'text'), ('payable', 'text'),
    ('expense_ledger', 'text'), ('goods_value', 'text'), ('tax_amount', 'text'),
    ('tax_code', 'text'), ('tax_type', 'text'), ('tds_amount', 'text'),
    ('tds_section', 'text'), ('party_contact', 'text'), ('pay_mode', 'text'),
    ('other_charges', 'text'), ('payment_status', 'text'),
    ('transaction_link', 'text'), ('email_id', 'text'), ('bill_unique_id', 'text'),
)


def add_missing_columns(apps, schema_editor):
    table = 'ap_app_duereportinvoicewise'
    with schema_editor.connection.cursor() as cursor:
        existing = {
            column.name
            for column in schema_editor.connection.introspection.get_table_description(cursor, table)
        }
    for column_name, column_type in GETBILLS_COLUMNS:
        if column_name not in existing:
            schema_editor.execute(
                f'ALTER TABLE {schema_editor.quote_name(table)} '
                f'ADD COLUMN {schema_editor.quote_name(column_name)} {column_type} NULL'
            )


class Migration(migrations.Migration):
    dependencies = [
        ('ap_app', '0003_rename_ap_app_due_invoice_416127_idx_ap_app_duer_invoice_8ab7dd_idx'),
    ]
    operations = [
        migrations.RunPython(add_missing_columns, migrations.RunPython.noop),
    ]
