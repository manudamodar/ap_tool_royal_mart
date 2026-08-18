from django.core.management.base import BaseCommand

from ap_app.models import DocumentResult, DueReportInvoiceWise
from ap_app.reconciliation_service import apply_reconciliation, build_bill_lookup, match_bill
from ap_app.tasks import invoice_row_to_bill


class Command(BaseCommand):
    help = 'Re-run reconciliation and populate due-report flags for previously scanned invoices.'

    def handle(self, *args, **options):
        bills = [invoice_row_to_bill(row) for row in DueReportInvoiceWise.objects.all()]
        bill_lookup = build_bill_lookup(bills)
        documents = DocumentResult.objects.select_related('batch').order_by('id')

        processed = 0
        matched = 0
        for document in documents.iterator(chunk_size=200):
            parsed_data = document.parsed_data or {}
            matched_bill = match_bill(parsed_data, bill_lookup)
            if matched_bill is None and document.matched_bill_data:
                matched_bill = document.matched_bill_data
            apply_reconciliation(document, parsed_data, matched_bill)
            processed += 1
            if matched_bill is not None:
                matched += 1

        self.stdout.write(self.style.SUCCESS(
            f'Backfilled reconciliation flags for {processed} documents; {matched} matched due-report rows.'
        ))
