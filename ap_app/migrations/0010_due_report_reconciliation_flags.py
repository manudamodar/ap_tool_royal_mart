from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('ap_app', '0009_allow_vendor_master_blank_gst'),
    ]

    operations = [
        migrations.AddField(
            model_name='duereportinvoicewise',
            name=name,
            field=models.BooleanField(blank=True, null=True),
        )
        for name in (
            'invoice_number_matches', 'payable_amount_matches', 'goods_value_matches',
            'tax_amount_matches', 'tax_type_matches', 'vendor_gst_matches',
            'vendor_master_verified', 'store_gst_matches', 'store_master_verified',
        )
    ]
