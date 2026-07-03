import io
from types import SimpleNamespace
from decimal import Decimal
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase
import pandas as pd

from ap_app.admin import PaymentFileAdmin, PaymentMasterEntryAdmin
from ap_app.models import DueReportInvoiceWise, DueReportUnknown, DueReportUpload, MasterDataFile, PaymentFile, PaymentMasterEntry
from ap_app.master_data_utils import get_cash_discount_details
from ap_app.views import _parse_due_report_excel


class DueReportParserTests(SimpleTestCase):
    def test_parse_due_report_with_new_headers_and_us_dates(self):
        df = pd.DataFrame([
            {
                'Location Name': 'RMJ ROYAL MART SUPER MARKET',
                'Supplier Name': '19 ENTERPRISES 29GJPPD1953M1ZJ',
                'Invoice No': 'AKEE/25-26/4075',
                'Ref No': 'MR9830',
                'Bill/Voucher Date': '2/9/2026',
                'Invoice Date': '2/9/2026',
                'Bill Amount': '1,728.00',
                'Disc Amount': '0',
                'Amount Adjusted': '0',
                'Balance Amount': '1,728.00',
                'Pending Adj Amt': '0',
                'Net Balance': '1,728.00',
                'No of Days': '134',
                'Due Date': '2/12/2026',
                'Over Due Days': '131',
                'Prior Date': '2/12/2026',
                'Group Name': 'CREDITORS FOR PURCHASE',
                'Voucher Type': 'Purchase',
                'MSMETYPE': 'NA',
            }
        ])

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Sheet1')
        buffer.seek(0)

        rows = _parse_due_report_excel(buffer)

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row['invoiceNo'], 'AKEE/25-26/4075')
        self.assertEqual(row['payable'], 1728.0)
        self.assertEqual(row['dueDate'], '2026-02-12 00:00:00')
        self.assertEqual(row['invoiceDate'], '2026-02-09 00:00:00')
        self.assertEqual(row['voucherDate'], '2026-02-09 00:00:00')


class DueReportUploadStorageTests(TestCase):
    def test_upload_stores_valid_and_unknown_due_report_rows(self):
        user = User.objects.create_user(username='due-report-user')
        self.client.force_login(user)

        df = pd.DataFrame([
            {
                'Location Name': 'Main Branch',
                'Supplier Name': '19 ENTERPRISES 29GJPPD1953M1ZJ',
                'Invoice No': 'INV-001',
                'Ref No': 'REF-001',
                'Bill/Voucher Date': '2026-02-09',
                'Invoice Date': '2026-02-09',
                'Bill Amount': '1000',
                'Disc Amount': '10',
                'Amount Adjusted': '5',
                'Balance Amount': '985',
                'Pending Adj Amt': '0',
                'Net Balance': '985',
                'No of Days': '30',
                'Due Date': '2026-03-11',
                'Over Due Days': '0',
                'Prior Date': '2026-03-10',
                'Group Name': 'CREDITORS',
                'Voucher Type': 'Purchase',
                'MSMETYPE': 'NA',
            },
            {
                'Location Name': 'Main Branch',
                'Supplier Name': 'Vendor Without GST',
                'Invoice No': 'INV-002',
                'Ref No': 'REF-002',
            },
            {
                'Location Name': 'Main Branch',
                'Supplier Name': 'No Invoice Vendor 29GJPPD1953M1ZJ',
                'Invoice No': '',
                'Ref No': 'REF-003',
            },
        ])

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Sheet1')
        buffer.seek(0)

        upload = SimpleUploadedFile(
            'due_report.xlsx',
            buffer.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

        response = self.client.post('/api/due-report/upload/', {'file': upload})

        self.assertEqual(response.status_code, 201)
        self.assertEqual(DueReportUpload.objects.count(), 1)
        due_report = DueReportUpload.objects.get()
        self.assertEqual(due_report.row_count, 3)
        self.assertEqual(DueReportInvoiceWise.objects.count(), 1)
        self.assertEqual(DueReportUnknown.objects.count(), 2)

        invoice_row = DueReportInvoiceWise.objects.get()
        self.assertEqual(invoice_row.due_report, due_report)
        self.assertEqual(invoice_row.uploaded_by, user)
        self.assertEqual(invoice_row.invoice_no, 'INV-001')
        self.assertEqual(invoice_row.supplier_name, '19 ENTERPRISES')
        self.assertEqual(invoice_row.gst_number, '29GJPPD1953M1ZJ')
        self.assertTrue(invoice_row.is_from_excel)
        self.assertFalse(invoice_row.is_from_api)

        self.assertTrue(DueReportUnknown.objects.filter(invoice_no='INV-002', gst_number__isnull=True).exists())
        self.assertTrue(DueReportUnknown.objects.filter(invoice_no__isnull=True, gst_number='29GJPPD1953M1ZJ').exists())


class MasterDataFileTests(TestCase):
    def test_master_data_file_populates_parsed_data_on_save(self):
        df = pd.DataFrame([
            {
                'Invoice No': 'INV-1001',
                'Supplier Name': 'Acme Ltd',
                'Payable': '1250.50',
            }
        ])

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Sheet1')
        buffer.seek(0)

        master = MasterDataFile.objects.create(
            document_name='Vendor Master',
            file=ContentFile(buffer.getvalue(), name='vendor_master.xlsx'),
        )

        self.assertEqual(master.row_count, 1)
        self.assertEqual(master.parsed_data[0]['Invoice No'], 'INV-1001')
        self.assertEqual(master.parsed_data[0]['Supplier Name'], 'Acme Ltd')
        self.assertEqual(master.parsed_data[0]['Payable'], 1250.5)

    def test_master_data_file_normalizes_percentage_values(self):
        df = pd.DataFrame([
            {
                'SUPPLIER NAME': 'Acme Ltd',
                'SUPPLIER GST NUMBER': '32ABYPN2864L1ZY',
                'CASH DISCOUNT': 0.1,
            }
        ])

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Sheet1')
        buffer.seek(0)

        master = MasterDataFile.objects.create(
            document_name='Vendor_Cash_Discount_Bank_Details',
            file=ContentFile(buffer.getvalue(), name='cash_discount.xlsx'),
        )

        self.assertEqual(master.parsed_data[0]['CASH DISCOUNT'], 10.0)


class PaymentMasterEntryTests(TestCase):
    def test_import_from_rows_creates_payment_master_entries(self):
        rows = [{
            'Location Name': 'Main Branch',
            'Counter': 'C1',
            'Voucher Date': '2024-01-10',
            'Particulars': 'Rent Payment',
            'Voucher No': 'V-1001',
            'Voucher Type': 'Payment',
            'InvoiceNo': 'INV-1001',
            'Debit': '1000.00',
            'Credit': '0.00',
            'PARTYNAME': 'Acme Ltd',
            'ChqNo': '12345',
            'ChqDate': '2024-01-11',
            'Remarks': 'Monthly rent',
            'BillRefNo': 'BR-01',
            'Attachments': 'rent.pdf',
            'Bank RefNo.': 'BK-001',
        }]

        created_count = PaymentMasterEntry.import_from_rows(rows)

        self.assertEqual(created_count, 1)
        self.assertEqual(PaymentMasterEntry.objects.count(), 1)
        entry = PaymentMasterEntry.objects.get(voucher_no='V-1001')
        self.assertEqual(entry.location_name, 'Main Branch')
        self.assertEqual(entry.debit, Decimal('1000.00'))
        self.assertEqual(entry.party_name, 'Acme Ltd')

    def test_admin_save_model_sets_created_and_modified_users(self):
        creator = User.objects.create_user(username='creator')
        modifier = User.objects.create_user(username='modifier')
        admin = PaymentMasterEntryAdmin(PaymentMasterEntry, AdminSite())

        entry = PaymentMasterEntry(voucher_no='V-1002', party_name='Acme Ltd')
        admin.save_model(SimpleNamespace(user=creator), entry, form=None, change=False)
        entry.refresh_from_db()

        self.assertEqual(entry.created_by, creator)
        self.assertEqual(entry.modified_by, creator)

        entry.party_name = 'Acme Updated Ltd'
        admin.save_model(SimpleNamespace(user=modifier), entry, form=None, change=True)
        entry.refresh_from_db()

        self.assertEqual(entry.created_by, creator)
        self.assertEqual(entry.modified_by, modifier)


class PaymentFileTests(TestCase):
    def test_admin_save_model_sets_created_and_modified_users(self):
        creator = User.objects.create_user(username='payment-file-creator')
        modifier = User.objects.create_user(username='payment-file-modifier')
        admin = PaymentFileAdmin(PaymentFile, AdminSite())

        payment_file = PaymentFile(total_files=3)
        admin.save_model(SimpleNamespace(user=creator), payment_file, form=None, change=False)
        payment_file.refresh_from_db()

        self.assertEqual(payment_file.created_by, creator)
        self.assertEqual(payment_file.modified_by, creator)

        payment_file.processed_files = 1
        admin.save_model(SimpleNamespace(user=modifier), payment_file, form=None, change=True)
        payment_file.refresh_from_db()

        self.assertEqual(payment_file.created_by, creator)
        self.assertEqual(payment_file.modified_by, modifier)


class CashDiscountLookupTests(TestCase):
    def test_get_cash_discount_details_uses_supplier_name_match(self):
        MasterDataFile.objects.create(
            document_name='Vendor_Cash_Discount_Bank_Details',
            parsed_data=[{
                'SUPPLIER NAME': 'A K R CASHEW TRADERS 32ABYPN2864L1ZY',
                'SUPPLIER GST NUMBER': '32ABYPN2864L1ZY',
                'CASH DISCOUNT': '2.5%'
            }],
            row_count=1,
            is_active=True,
        )

        details = get_cash_discount_details(
            parsed_data={'vendor_gst_number': '32ABYPN2864L1ZY', 'total_amount': 1000.0},
            matched_bill_data={'partyName': 'A K R CASHEW TRADERS 32ABYPN2864L1ZY'}
        )

        self.assertEqual(details['cash_discount_percentage'], 2.5)
        self.assertEqual(details['amount_after_discount'], 975.0)
        self.assertTrue(details['match_found'])

    def test_get_cash_discount_details_reports_no_match_when_gst_is_missing(self):
        MasterDataFile.objects.create(
            document_name='Vendor_Cash_Discount_Bank_Details',
            parsed_data=[{
                'SUPPLIER NAME': 'A K R CASHEW TRADERS 32ABYPN2864L1ZY',
                'SUPPLIER GST NUMBER': '32ABYPN2864L1ZY',
                'CASH DISCOUNT': '2.5%'
            }],
            row_count=1,
            is_active=True,
        )

        details = get_cash_discount_details(
            parsed_data={'vendor_gst_number': '33ZZZZ9999Z1ZZ', 'total_amount': 1000.0},
            matched_bill_data={'partyName': 'A K R CASHEW TRADERS 32ABYPN2864L1ZY'}
        )

        self.assertIsNone(details['cash_discount_percentage'])
        self.assertIsNone(details['amount_after_discount'])
        self.assertFalse(details['match_found'])

    def test_get_cash_discount_details_normalizes_fractional_percentages(self):
        MasterDataFile.objects.create(
            document_name='Vendor_Cash_Discount_Bank_Details',
            parsed_data=[{
                'SUPPLIER NAME': 'A K R CASHEW TRADERS 32ABYPN2864L1ZY',
                'SUPPLIER GST NUMBER': '32ABYPN2864L1ZY',
                'CASH DISCOUNT': 0.1,
            }],
            row_count=1,
            is_active=True,
        )

        details = get_cash_discount_details(
            parsed_data={'vendor_gst_number': '32ABYPN2864L1ZY', 'total_amount': 1000.0},
            matched_bill_data={'partyName': 'A K R CASHEW TRADERS 32ABYPN2864L1ZY'}
        )

        self.assertEqual(details['cash_discount_percentage'], 10.0)
        self.assertEqual(details['amount_after_discount'], 900.0)
