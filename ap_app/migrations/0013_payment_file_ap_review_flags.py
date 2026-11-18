from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ap_app', '0012_alter_documentresult_reconciliation_status_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='paymentfile',
            name='is_ap_approved',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='paymentfile',
            name='is_ap_rejected',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='paymentfileinvoice',
            name='is_ap_approved',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='paymentfileinvoice',
            name='is_ap_rejected',
            field=models.BooleanField(default=False),
        ),
    ]
