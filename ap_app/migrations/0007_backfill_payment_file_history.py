from django.db import migrations


def backfill_history(apps, schema_editor):
    PaymentFile = apps.get_model('ap_app', 'PaymentFile')
    PaymentFileInvoice = apps.get_model('ap_app', 'PaymentFileInvoice')
    PaymentFileReviewEvent = apps.get_model('ap_app', 'PaymentFileReviewEvent')

    for payment_file in PaymentFile.objects.all():
        invoice_ids = list(payment_file.due_report_rows.values_list('id', flat=True))
        PaymentFileReviewEvent.objects.get_or_create(
            payment_file=payment_file,
            event_type='CREATED',
            defaults={
                'actor': payment_file.created_by,
                'invoice_ids': invoice_ids,
                'metadata': {'backfilled': True},
            },
        )
        rejected_links = list(payment_file.invoice_links.filter(
            status__in=['MANAGER_REJECTED', 'AP_REJECTED'],
        ))
        if not rejected_links:
            continue
        ap_rejected = any(link.status == 'AP_REJECTED' for link in rejected_links)
        comments = [
            link.ap_rejection_reason or link.manager_rejection_reason
            for link in rejected_links
            if link.ap_rejection_reason or link.manager_rejection_reason
        ]
        PaymentFileReviewEvent.objects.get_or_create(
            payment_file=payment_file,
            event_type='AP_REJECTED' if ap_rejected else 'MANAGER_REJECTED',
            defaults={
                'actor': payment_file.ap_reviewed_by if ap_rejected else payment_file.modified_by,
                'comment': '; '.join(comments) or None,
                'invoice_ids': [link.invoice_id for link in rejected_links],
                'metadata': {'backfilled': True},
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ('ap_app', '0006_payment_file_lifecycle'),
    ]

    operations = [
        migrations.RunPython(backfill_history, migrations.RunPython.noop),
    ]
