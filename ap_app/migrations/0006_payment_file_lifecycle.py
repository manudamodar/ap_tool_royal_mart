from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('ap_app', '0005_ap_payment_review'),
    ]

    operations = [
        migrations.AddField(
            model_name='paymentfile',
            name='source_payment_file',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='regenerated_files',
                to='ap_app.paymentfile',
            ),
        ),
        migrations.CreateModel(
            name='PaymentFileReviewEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('event_type', models.CharField(choices=[('CREATED', 'Created'), ('MANAGER_APPROVED', 'Manager Approved'), ('MANAGER_REJECTED', 'Manager Rejected'), ('BANK_FILE_COMPARED', 'Bank File Compared'), ('AP_APPROVED', 'AP Approved'), ('AP_REJECTED', 'AP Rejected'), ('REGENERATED', 'Regenerated')], max_length=40)),
                ('comment', models.TextField(blank=True, null=True)),
                ('invoice_ids', models.JSONField(blank=True, default=list)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('actor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='payment_file_review_events', to=settings.AUTH_USER_MODEL)),
                ('payment_file', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='review_events', to='ap_app.paymentfile')),
            ],
            options={'ordering': ('created_at', 'id')},
        ),
    ]
