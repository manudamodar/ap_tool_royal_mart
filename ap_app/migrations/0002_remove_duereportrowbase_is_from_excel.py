from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('ap_app', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(model_name='ocrbatch', name='due_report'),
        migrations.RemoveField(model_name='paymentfile', name='due_report'),
        migrations.RemoveField(
            model_name='duereportinvoicewise',
            name='is_from_excel',
        ),
        migrations.RemoveField(model_name='duereportinvoicewise', name='due_report'),
        migrations.RemoveField(model_name='duereportinvoicewise', name='uploaded_by'),
        migrations.RemoveField(model_name='duereportinvoicewise', name='is_from_api'),
        migrations.RemoveIndex(
            model_name='duereportinvoicewise',
            name='ap_app_duer_due_rep_e2bbe1_idx',
        ),
        migrations.AddIndex(
            model_name='duereportinvoicewise',
            index=models.Index(
                fields=['invoice_no', 'gst_number'],
                name='ap_app_due_invoice_416127_idx',
            ),
        ),
        migrations.AddField(model_name='duereportinvoicewise', name='tran_year', field=models.TextField(blank=True, null=True)),
        migrations.AddField(model_name='duereportinvoicewise', name='branch_code', field=models.BigIntegerField(blank=True, null=True)),
        migrations.AddField(model_name='duereportinvoicewise', name='voucher_no', field=models.TextField(blank=True, null=True)),
        migrations.AddField(model_name='duereportinvoicewise', name='party_code', field=models.BigIntegerField(blank=True, null=True)),
        migrations.AddField(model_name='duereportinvoicewise', name='bill_date', field=models.TextField(blank=True, null=True)),
        migrations.AddField(model_name='duereportinvoicewise', name='payable', field=models.TextField(blank=True, null=True)),
        migrations.AddField(model_name='duereportinvoicewise', name='expense_ledger', field=models.TextField(blank=True, null=True)),
        migrations.AddField(model_name='duereportinvoicewise', name='goods_value', field=models.TextField(blank=True, null=True)),
        migrations.AddField(model_name='duereportinvoicewise', name='tax_amount', field=models.TextField(blank=True, null=True)),
        migrations.AddField(model_name='duereportinvoicewise', name='tax_code', field=models.TextField(blank=True, null=True)),
        migrations.AddField(model_name='duereportinvoicewise', name='tax_type', field=models.TextField(blank=True, null=True)),
        migrations.AddField(model_name='duereportinvoicewise', name='tds_amount', field=models.TextField(blank=True, null=True)),
        migrations.AddField(model_name='duereportinvoicewise', name='tds_section', field=models.TextField(blank=True, null=True)),
        migrations.AddField(model_name='duereportinvoicewise', name='party_contact', field=models.TextField(blank=True, null=True)),
        migrations.AddField(model_name='duereportinvoicewise', name='pay_mode', field=models.TextField(blank=True, null=True)),
        migrations.AddField(model_name='duereportinvoicewise', name='other_charges', field=models.TextField(blank=True, null=True)),
        migrations.AddField(model_name='duereportinvoicewise', name='payment_status', field=models.TextField(blank=True, null=True)),
        migrations.AddField(model_name='duereportinvoicewise', name='transaction_link', field=models.TextField(blank=True, null=True)),
        migrations.AddField(model_name='duereportinvoicewise', name='email_id', field=models.TextField(blank=True, null=True)),
        migrations.AddField(model_name='duereportinvoicewise', name='bill_unique_id', field=models.TextField(blank=True, null=True)),
        migrations.DeleteModel(name='DueReportUnknown'),
        migrations.DeleteModel(name='DueReportUpload'),
    ]
