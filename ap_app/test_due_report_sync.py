from unittest.mock import patch

from django.conf import settings
from django.test import TestCase

from .models import DueReportInvoiceWise
from .tasks import sync_bills_from_gofrugal


class DueReportSynchronizationTests(TestCase):
    @patch('ap_app.tasks.call_getbills_api')
    def test_real_time_snapshot_updates_rows_and_preserves_workflow_state(self, getbills):
        existing = DueReportInvoiceWise.objects.create(
            tran_year='2026_2027',
            invoice_no='INV-1',
            gst_number='29ABCDE1234F1Z5',
            bill_amount='100',
            is_acknowledged=True,
            payment_reference_number='HO-123',
        )
        stale_same_year = DueReportInvoiceWise.objects.create(
            tran_year='2026_2027',
            invoice_no='STALE-1',
            gst_number='29ABCDE1234F1Z5',
        )
        other_year = DueReportInvoiceWise.objects.create(
            tran_year='2025_2026',
            invoice_no='OLD-1',
            gst_number='29ABCDE1234F1Z5',
        )
        payload = {
            'status': 'success',
            'data': [{
                'tranYear': '2026_2027',
                'invoiceNo': 'INV-1',
                'partyGSTNo': '29ABCDE1234F1Z5',
                'voucherAmount': 250,
            }],
        }
        getbills.return_value = (payload, payload['data'])

        response, row_count = sync_bills_from_gofrugal('2026_2027')

        existing.refresh_from_db()
        self.assertEqual(response, payload)
        self.assertEqual(row_count, 1)
        self.assertEqual(existing.bill_amount, '250')
        self.assertTrue(existing.is_acknowledged)
        self.assertEqual(existing.payment_reference_number, 'HO-123')
        self.assertFalse(DueReportInvoiceWise.objects.filter(pk=stale_same_year.pk).exists())
        self.assertTrue(DueReportInvoiceWise.objects.filter(pk=other_year.pk).exists())

    def test_beat_schedule_uses_environment_backed_interval(self):
        schedule = settings.CELERY_BEAT_SCHEDULE['sync-due-reports']
        self.assertEqual(schedule['task'], 'ap_app.tasks.sync_due_reports_task')
        self.assertEqual(schedule['schedule'], settings.DUE_REPORT_SYNC_INTERVAL_SECONDS)
