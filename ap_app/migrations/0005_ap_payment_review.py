from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('ap_app', '0004_sync_getbills_columns'),
    ]
    operations = [
        migrations.AddField(model_name='paymentfile', name='bank_portal_file', field=models.FileField(blank=True, null=True, upload_to='bank_portal_files/%Y/%m/%d/')),
        migrations.AddField(model_name='paymentfile', name='bank_file_matches', field=models.BooleanField(blank=True, null=True)),
        migrations.AddField(model_name='paymentfile', name='bank_file_comparison', field=models.JSONField(blank=True, default=dict)),
        migrations.AddField(model_name='paymentfile', name='bank_file_uploaded_at', field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name='paymentfile', name='bank_file_uploaded_by', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='uploaded_bank_payment_files', to=settings.AUTH_USER_MODEL)),
        migrations.AddField(model_name='paymentfile', name='ap_reviewed_at', field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name='paymentfile', name='ap_reviewed_by', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='reviewed_payment_files', to=settings.AUTH_USER_MODEL)),
        migrations.AddField(model_name='paymentfileinvoice', name='ap_rejection_reason', field=models.TextField(blank=True, null=True)),
        migrations.AlterField(model_name='paymentfileinvoice', name='status', field=models.CharField(choices=[('PENDING_MANAGER_REVIEW', 'Pending Manager Review'), ('MANAGER_APPROVED', 'Manager Approved'), ('MANAGER_REJECTED', 'Manager Rejected'), ('AP_APPROVED', 'AP Approved'), ('AP_REJECTED', 'AP Rejected'), ('PAID', 'Paid')], default='PENDING_MANAGER_REVIEW', max_length=50)),
    ]
