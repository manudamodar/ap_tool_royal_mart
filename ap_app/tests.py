import io
import json
from types import SimpleNamespace
from decimal import Decimal
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, SimpleTestCase, TestCase
import pandas as pd

from ap_app.admin import PaymentFileAdmin, PaymentMasterEntryAdmin
from ap_app.models import UserProfile, DueReportInvoiceWise, DueReportUnknown, DueReportUpload, MasterDataFile, PaymentFile, PaymentFileInvoice, PaymentMasterEntry
from ap_app.master_data_utils import get_cash_discount_details
from ap_app.payment_file_service import create_payment_file_record
from ap_app.views import _parse_due_report_excel, _serialize_payment_file


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


class UserProfileManagerTests(TestCase):
    def test_account_manager_assignment_and_user_profile_reverse_relation(self):
        manager = User.objects.create_user(username='manager', email='manager@example.com')
        user = User.objects.create_user(username='employee', email='employee@example.com')
        profile = UserProfile.objects.create(user=user, account_manager=manager)

        self.assertEqual(profile.account_manager, manager)
        self.assertEqual(manager.managed_users.count(), 1)
        self.assertEqual(manager.managed_users.first(), profile)

        self.client.force_login(user)
        response = self.client.get('/api/auth/user/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get('account_manager', {}).get('username'), 'manager')


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
        self.assertFalse(invoice_row.is_acknowledged)
        self.assertFalse(invoice_row.is_payment_file_created)

        self.assertTrue(DueReportUnknown.objects.filter(invoice_no='INV-002', gst_number__isnull=True).exists())
        self.assertTrue(DueReportUnknown.objects.filter(invoice_no__isnull=True, gst_number='29GJPPD1953M1ZJ').exists())

    def test_upload_updates_existing_invoice_wise_row(self):
        user = User.objects.create_user(username='due-report-duplicate-user')
        self.client.force_login(user)

        original_due_report = DueReportUpload.objects.create(
            original_filename='existing_due_report.xlsx',
            uploaded_by=user,
            row_count=1,
        )
        existing_row = DueReportInvoiceWise.objects.create(
            due_report=original_due_report,
            uploaded_by=user,
            supplier_name='OLD SUPPLIER 29GJPPD1953M1ZJ',
            gst_number='29GJPPD1953M1ZJ',
            invoice_no='INV-001',
            bill_amount='1000',
        )

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
            }
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
        self.assertEqual(DueReportInvoiceWise.objects.count(), 1)

        existing_row.refresh_from_db()
        self.assertEqual(existing_row.supplier_name, '19 ENTERPRISES')
        self.assertEqual(existing_row.gst_number, '29GJPPD1953M1ZJ')
        self.assertEqual(existing_row.invoice_no, 'INV-001')
        self.assertEqual(existing_row.due_report.original_filename, 'due_report.xlsx')
        self.assertEqual(response.json()['due_report']['invoice_wise_count'], 1)

    def test_due_report_invoice_wise_default_flags(self):
        user = User.objects.create_user(username='due-report-flag-user')
        due_report = DueReportUpload.objects.create(
            original_filename='flag_report.xlsx',
            uploaded_by=user,
            row_count=1,
        )

        invoice_row = DueReportInvoiceWise.objects.create(
            due_report=due_report,
            uploaded_by=user,
            supplier_name='TEST VENDOR',
            gst_number='29GJPPD1953M1ZJ',
            invoice_no='INV-100',
        )

        self.assertFalse(invoice_row.is_acknowledged)
        self.assertFalse(invoice_row.is_payment_file_created)


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

    def test_manager_can_review_and_reject_payment_file_rows(self):
        manager = User.objects.create_user(username='manager-user')
        accountant = User.objects.create_user(username='accountant-user')
        UserProfile.objects.create(user=manager, role='STORE_MANAGER')
        UserProfile.objects.create(user=accountant, role='STORE_ACCOUNTANT', account_manager=manager)

        due_report = DueReportUpload.objects.create(
            original_filename='payment_due_report.xlsx',
            uploaded_by=accountant,
            row_count=2,
        )

        invoice_row1 = DueReportInvoiceWise.objects.create(
            due_report=due_report,
            uploaded_by=accountant,
            supplier_name='Test Vendor 1',
            gst_number='29GJPPD1953M1ZJ',
            invoice_no='INV-101',
            bill_amount='1000',
            balance_amount='1000',
            net_balance='1000',
        )
        invoice_row2 = DueReportInvoiceWise.objects.create(
            due_report=due_report,
            uploaded_by=accountant,
            supplier_name='Test Vendor 2',
            gst_number='29GJPPD1953M1ZJ',
            invoice_no='INV-102',
            bill_amount='2000',
            balance_amount='2000',
            net_balance='2000',
        )

        payment_file = PaymentFile.objects.create(
            due_report=due_report,
            payment_type='ICICI',
            status='COMPLETED',
            total_files=2,
            processed_files=2,
            created_by=accountant,
            modified_by=accountant,
        )
        payment_file.due_report_rows.add(invoice_row1, invoice_row2)

        self.client.force_login(manager)
        response = self.client.post(
            f'/api/rest/central-payment/{payment_file.id}/review/',
            data=json.dumps({
                'rejected_ids': [invoice_row2.id],
                'edits': {
                    str(invoice_row1.id): {
                        'remarks': 'Approved with correction',
                        'amount': '990.00'
                    }
                }
            }),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        payment_file.refresh_from_db()
        invoice_row2.refresh_from_db()
        self.assertTrue(invoice_row2.manager_rejected)
        self.assertEqual(invoice_row2.manager_rejected_by, manager)
        self.assertEqual(payment_file.rejected_due_report_row_ids, [invoice_row2.id])
        self.assertEqual(payment_file.line_item_overrides.get(str(invoice_row1.id))['remarks'], 'Approved with correction')

    def test_create_payment_file_record_preserves_rejected_state_for_reselected_rows(self):
        accountant = User.objects.create_user(username='accountant-user-preserve')
        due_report = DueReportUpload.objects.create(
            original_filename='payment_due_report_preserve.xlsx',
            uploaded_by=accountant,
            row_count=1,
        )
        invoice_row = DueReportInvoiceWise.objects.create(
            due_report=due_report,
            uploaded_by=accountant,
            supplier_name='Preserved Vendor',
            gst_number='29GJPPD1953M1ZJ',
            invoice_no='INV-203',
            bill_amount='1000',
            balance_amount='1000',
            net_balance='1000',
            manager_rejected=True,
        )

        create_payment_file_record(
            payment_type='ICICI',
            invoice_rows=[invoice_row],
            due_report=due_report,
            created_by=accountant,
        )

        invoice_row.refresh_from_db()
        self.assertTrue(invoice_row.manager_rejected)
        self.assertTrue(invoice_row.is_payment_file_created)

    def test_store_accountant_can_regenerate_payment_file_excluding_rejected_rows(self):
        manager = User.objects.create_user(username='manager-user2')
        accountant = User.objects.create_user(username='accountant-user2')
        UserProfile.objects.create(user=manager, role='STORE_MANAGER')
        UserProfile.objects.create(user=accountant, role='STORE_ACCOUNTANT')

        due_report = DueReportUpload.objects.create(
            original_filename='payment_due_report2.xlsx',
            uploaded_by=accountant,
            row_count=2,
        )

        invoice_row1 = DueReportInvoiceWise.objects.create(
            due_report=due_report,
            uploaded_by=accountant,
            supplier_name='Test Vendor 1',
            gst_number='29GJPPD1953M1ZJ',
            invoice_no='INV-201',
            bill_amount='1000',
            balance_amount='1000',
            net_balance='1000',
            manager_rejected=False,
        )
        invoice_row2 = DueReportInvoiceWise.objects.create(
            due_report=due_report,
            uploaded_by=accountant,
            supplier_name='Test Vendor 2',
            gst_number='29GJPPD1953M1ZJ',
            invoice_no='INV-202',
            bill_amount='2000',
            balance_amount='2000',
            net_balance='2000',
            manager_rejected=True,
            manager_rejected_by=manager,
        )

        payment_file = PaymentFile.objects.create(
            due_report=due_report,
            payment_type='ICICI',
            status='COMPLETED',
            total_files=2,
            processed_files=2,
            created_by=accountant,
            modified_by=accountant,
            rejected_due_report_row_ids=[invoice_row2.id],
        )
        payment_file.due_report_rows.add(invoice_row1, invoice_row2)

        self.client.force_login(accountant)
        response = self.client.post(
            f'/api/rest/central-payment/{payment_file.id}/regenerate/',
            data=json.dumps({}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data['payment_file']['total_files'], 1)
        self.assertEqual(len(data['payment_file']['rows']), 1)
        self.assertTrue(any(row['id'] == invoice_row1.id for row in data['payment_file']['rows']))
        self.assertFalse(any(row['id'] == invoice_row2.id for row in data['payment_file']['rows']))
        self.assertEqual(data['payment_file']['rejected_due_report_row_ids'], [invoice_row2.id])

    def test_store_manager_can_see_files_created_by_managed_accountant(self):
        manager = User.objects.create_user(username='manager-user3')
        accountant = User.objects.create_user(username='accountant-user3')
        other_accountant = User.objects.create_user(username='other-accountant-user')
        UserProfile.objects.create(user=manager, role='STORE_MANAGER')
        UserProfile.objects.create(user=accountant, role='STORE_ACCOUNTANT', account_manager=manager)
        UserProfile.objects.create(user=other_accountant, role='STORE_ACCOUNTANT')

        due_report = DueReportUpload.objects.create(
            original_filename='payment_due_report3.xlsx',
            uploaded_by=accountant,
            row_count=1,
        )

        invoice_row = DueReportInvoiceWise.objects.create(
            due_report=due_report,
            uploaded_by=accountant,
            supplier_name='Test Vendor 3',
            gst_number='29GJPPD1953M1ZJ',
            invoice_no='INV-300',
            bill_amount='1000',
            balance_amount='1000',
            net_balance='1000',
        )

        managed_payment_file = PaymentFile.objects.create(
            due_report=due_report,
            payment_type='ICICI',
            status='COMPLETED',
            total_files=1,
            processed_files=1,
            created_by=accountant,
            modified_by=accountant,
        )
        managed_payment_file.due_report_rows.add(invoice_row)

        other_due_report = DueReportUpload.objects.create(
            original_filename='payment_due_report_other.xlsx',
            uploaded_by=other_accountant,
            row_count=1,
        )
        other_invoice_row = DueReportInvoiceWise.objects.create(
            due_report=other_due_report,
            uploaded_by=other_accountant,
            supplier_name='Other Vendor',
            gst_number='29GJPPD1953M1ZJ',
            invoice_no='INV-301',
            bill_amount='1500',
            balance_amount='1500',
            net_balance='1500',
        )
        other_payment_file = PaymentFile.objects.create(
            due_report=other_due_report,
            payment_type='ICICI',
            status='COMPLETED',
            total_files=1,
            processed_files=1,
            created_by=other_accountant,
            modified_by=other_accountant,
        )
        other_payment_file.due_report_rows.add(other_invoice_row)

        self.client.force_login(manager)
        response = self.client.get('/api/rest/central-payment')
        self.assertEqual(response.status_code, 200)
        payment_files = response.json().get('payment_files', [])
        self.assertTrue(any(item['id'] == managed_payment_file.id for item in payment_files))
        self.assertFalse(any(item['id'] == other_payment_file.id for item in payment_files))

    def test_payment_file_creation_sets_approval_flags_default_false(self):
        user = User.objects.create_user(username='payment-file-approval-user')
        due_report = DueReportUpload.objects.create(
            original_filename='payment_due_report_approval.xlsx',
            uploaded_by=user,
            row_count=1,
        )
        invoice_row = DueReportInvoiceWise.objects.create(
            due_report=due_report,
            uploaded_by=user,
            supplier_name='Approval Vendor',
            gst_number='29GJPPD1953M1ZJ',
            invoice_no='INV-401',
            bill_amount='1000',
            balance_amount='1000',
            net_balance='1000',
        )

        payment_file = create_payment_file_record(
            payment_type='ICICI',
            invoice_rows=[invoice_row],
            due_report=due_report,
            created_by=user,
        )

        self.assertFalse(payment_file.is_payment_file_approved)
        self.assertFalse(payment_file.is_payment_done)

    def test_payment_file_serialization_exposes_row_review_status(self):
        user = User.objects.create_user(username='payment-file-serialization-user')
        due_report = DueReportUpload.objects.create(
            original_filename='payment_due_report_serialization.xlsx',
            uploaded_by=user,
            row_count=1,
        )
        invoice_row = DueReportInvoiceWise.objects.create(
            due_report=due_report,
            uploaded_by=user,
            supplier_name='Serialization Vendor',
            gst_number='29GJPPD1953M1ZJ',
            invoice_no='INV-501',
            bill_amount='1000',
            balance_amount='1000',
            net_balance='1000',
        )

        payment_file = create_payment_file_record(
            payment_type='ICICI',
            invoice_rows=[invoice_row],
            due_report=due_report,
            created_by=user,
        )
        link = payment_file.invoice_links.get(invoice=invoice_row)
        link.status = PaymentFileInvoice.Status.MANAGER_REJECTED
        link.manager_rejection_reason = 'Invalid bank account details'
        link.save()

        request = RequestFactory().get('/')
        payload = _serialize_payment_file(payment_file, request)

        self.assertEqual(payload['rows'][0]['review_status'], PaymentFileInvoice.Status.MANAGER_REJECTED)
        self.assertEqual(payload['rows'][0]['review_reason'], 'Invalid bank account details')
        self.assertTrue(payload['rows'][0]['is_rejected'])

    def test_central_payment_allows_new_and_rejected_rows_but_blocks_existing_unrejected_rows(self):
        user = User.objects.create_user(username='payment-file-eligibility-user')
        self.client.force_login(user)

        due_report = DueReportUpload.objects.create(
            original_filename='payment_due_report_eligibility.xlsx',
            uploaded_by=user,
            row_count=3,
        )

        new_row = DueReportInvoiceWise.objects.create(
            due_report=due_report,
            uploaded_by=user,
            supplier_name='New Vendor',
            gst_number='29GJPPD1953M1ZJ',
            invoice_no='INV-402',
            bill_amount='1000',
            balance_amount='1000',
            net_balance='1000',
        )
        rejected_row = DueReportInvoiceWise.objects.create(
            due_report=due_report,
            uploaded_by=user,
            supplier_name='Rejected Vendor',
            gst_number='29GJPPD1953M1ZJ',
            invoice_no='INV-403',
            bill_amount='1000',
            balance_amount='1000',
            net_balance='1000',
            manager_rejected=True,
            is_payment_file_created=True,
        )
        existing_row = DueReportInvoiceWise.objects.create(
            due_report=due_report,
            uploaded_by=user,
            supplier_name='Existing Vendor',
            gst_number='29GJPPD1953M1ZJ',
            invoice_no='INV-404',
            bill_amount='1000',
            balance_amount='1000',
            net_balance='1000',
            is_payment_file_created=True,
        )

        allow_response = self.client.post(
            '/api/rest/central-payment',
            data=json.dumps({
                'invoice_ids': [new_row.id, rejected_row.id],
                'payment_type': 'ICICI'
            }),
            content_type='application/json'
        )
        self.assertEqual(allow_response.status_code, 201)

        block_response = self.client.post(
            '/api/rest/central-payment',
            data=json.dumps({
                'invoice_ids': [existing_row.id],
                'payment_type': 'ICICI'
            }),
            content_type='application/json'
        )
        self.assertEqual(block_response.status_code, 400)

    def test_central_payment_creates_payment_file_for_invoice_rows(self):
        user = User.objects.create_user(username='payment-file-user')
        self.client.force_login(user)

        due_report = DueReportUpload.objects.create(
            original_filename='payment_due_report.xlsx',
            uploaded_by=user,
            row_count=1,
        )

        invoice_row = DueReportInvoiceWise.objects.create(
            due_report=due_report,
            uploaded_by=user,
            supplier_name='Test Vendor 29GJPPD1953M1ZJ',
            gst_number='29GJPPD1953M1ZJ',
            invoice_no='INV-100',
            bill_amount='1000',
            balance_amount='1000',
            net_balance='1000',
        )

        response = self.client.post(
            '/api/rest/central-payment',
            data=json.dumps({
                'invoice_ids': [invoice_row.id],
                'payment_type': 'ICICI'
            }),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertIn('payment_file', data)
        self.assertEqual(data['payment_file']['payment_type'], 'ICICI')
        self.assertEqual(data['payment_file']['total_files'], 1)
        self.assertTrue(DueReportInvoiceWise.objects.filter(id=invoice_row.id, is_payment_file_created=True).exists())

    def test_rejected_invoice_can_be_reselected_in_a_new_payment_file(self):
        user = User.objects.create_user(username='payment-file-resubmit-user')
        self.client.force_login(user)

        due_report = DueReportUpload.objects.create(
            original_filename='payment_due_report_resubmit.xlsx',
            uploaded_by=user,
            row_count=1,
        )

        invoice_row = DueReportInvoiceWise.objects.create(
            due_report=due_report,
            uploaded_by=user,
            supplier_name='Resubmission Vendor',
            gst_number='29GJPPD1953M1ZJ',
            invoice_no='INV-500',
            bill_amount='1000',
            balance_amount='1000',
            net_balance='1000',
        )

        first_payment_file = create_payment_file_record(
            payment_type='ICICI',
            invoice_rows=[invoice_row],
            due_report=due_report,
            created_by=user,
        )
        first_link = first_payment_file.invoice_links.get(invoice=invoice_row)
        first_link.status = PaymentFileInvoice.Status.MANAGER_REJECTED
        first_link.manager_rejection_reason = 'Invalid bank account details'
        first_link.save()

        response = self.client.post(
            '/api/rest/central-payment',
            data=json.dumps({
                'invoice_ids': [invoice_row.id],
                'payment_type': 'ICICI',
                'force_selected_ids': [invoice_row.id],
            }),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 201)
        second_payment_file = PaymentFile.objects.order_by('-created_at').first()
        second_link = second_payment_file.invoice_links.get(invoice=invoice_row)
        self.assertEqual(second_link.status, PaymentFileInvoice.Status.PENDING_MANAGER_REVIEW)
        self.assertTrue(second_link.force_selected)

    def test_download_payment_file_returns_xlsx(self):
        user = User.objects.create_user(username='payment-file-download-user')
        self.client.force_login(user)

        due_report = DueReportUpload.objects.create(
            original_filename='payment_due_report.xlsx',
            uploaded_by=user,
            row_count=1,
        )

        invoice_row = DueReportInvoiceWise.objects.create(
            due_report=due_report,
            uploaded_by=user,
            supplier_name='Test Vendor 29GJPPD1953M1ZJ',
            gst_number='29GJPPD1953M1ZJ',
            invoice_no='INV-200',
            bill_amount='1000',
            balance_amount='1000',
            net_balance='1000',
        )

        payment_file = PaymentFile.objects.create(
            due_report=due_report,
            payment_type='ICICI',
            status='COMPLETED',
            total_files=1,
            processed_files=1,
            created_by=user,
            modified_by=user,
        )
        payment_file.due_report_rows.add(invoice_row)

        response = self.client.get(f'/api/rest/central-payment/download/{payment_file.id}/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        self.assertIn('attachment; filename=', response['Content-Disposition'])
        self.assertTrue(response.content.startswith(b'PK'))


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
