from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('ap_app', '0006_payment_file_lifecycle')]

    operations = [
        migrations.CreateModel(
            name='VendorMaster',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('vendor_id', models.CharField(blank=True, max_length=50, null=True)),
                ('supplier_name', models.CharField(max_length=500)),
                ('gst_number', models.CharField(db_index=True, max_length=15, unique=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'verbose_name': 'Vendor Master', 'verbose_name_plural': 'Vendor Master', 'ordering': ('supplier_name',)},
        ),
        migrations.CreateModel(
            name='RoyalMartStoreMaster',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('serial_number', models.CharField(blank=True, max_length=50, null=True)),
                ('legal_name', models.CharField(max_length=500)),
                ('store_code', models.CharField(db_index=True, max_length=50)),
                ('gst_number', models.CharField(db_index=True, max_length=15)),
                ('address', models.TextField(blank=True, null=True)),
                ('email_address', models.EmailField(blank=True, max_length=254, null=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'verbose_name': 'Royal Mart Store Master', 'verbose_name_plural': 'Royal Mart Store Master', 'ordering': ('store_code',)},
        ),
        migrations.AddConstraint(
            model_name='royalmartstoremaster',
            constraint=models.UniqueConstraint(fields=('store_code', 'gst_number'), name='unique_store_code_gst_number'),
        ),
        *[
            migrations.AddField(
                model_name='documentresult',
                name=name,
                field=models.BooleanField(blank=True, null=True),
            )
            for name in (
                'invoice_number_matches', 'payable_amount_matches', 'goods_value_matches',
                'tax_amount_matches', 'tax_type_matches', 'vendor_gst_matches',
                'vendor_master_verified', 'store_gst_matches', 'store_master_verified',
            )
        ],
    ]
