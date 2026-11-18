from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('ap_app', '0010_due_report_reconciliation_flags'),
    ]

    operations = [
        migrations.AddField(
            model_name='duereportinvoicewise',
            name='reconciliation_details',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name='duereportinvoicewise',
            name='invoice_reconciliation_status',
            field=models.CharField(
                choices=[
                    ('VERIFIED', 'Verified'),
                    ('UNVERIFIED', 'Unverified'),
                    ('MANUAL_REVIEW', 'Manual Review'),
                    ('NO_MATCH', 'No Match Found'),
                    ('MANUALLY_VERIFIED', 'Manually Verified'),
                ],
                default='UNVERIFIED',
                max_length=20,
            ),
        ),
    ]
