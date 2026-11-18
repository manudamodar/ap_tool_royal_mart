from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('ap_app', '0008_merge_0007_migration_branches'),
    ]

    operations = [
        migrations.AlterField(
            model_name='vendormaster',
            name='vendor_id',
            field=models.CharField(max_length=50, unique=True),
        ),
        migrations.AlterField(
            model_name='vendormaster',
            name='gst_number',
            field=models.CharField(blank=True, db_index=True, max_length=15, null=True),
        ),
    ]
