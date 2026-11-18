from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ap_app', '0013_payment_file_ap_review_flags'),
    ]

    operations = [
        migrations.AddField(
            model_name='duereportinvoicewise',
            name='payment_reference_number',
            field=models.TextField(blank=True, null=True),
        ),
    ]
