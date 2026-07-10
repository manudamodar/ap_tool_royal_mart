import uuid
from decimal import Decimal
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


def _normalize_percentage_value(value):
    if value is None or isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        numeric_value = float(value)
        if abs(numeric_value) <= 1:
            return numeric_value * 100
        return numeric_value

    text = str(value).strip()
    if not text:
        return value

    cleaned = text.replace('%', '').replace(' ', '')
    try:
        numeric_value = float(cleaned)
    except ValueError:
        return value

    if abs(numeric_value) <= 1 and '%' not in text:
        return numeric_value * 100
    return numeric_value

class UserRole(models.TextChoices):
    UNASSIGNED = 'UNASSIGNED', 'Unassigned'
    AP_TEAM = 'AP_TEAM', 'AP Team'
    STORE_ACCOUNTANT = 'STORE_ACCOUNTANT', 'Store Accountant'
    STORE_MANAGER = 'STORE_MANAGER', 'Store Manager'

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    account_manager = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='managed_users',
    )
    role = models.CharField(max_length=20, choices=UserRole.choices, default=UserRole.UNASSIGNED)
    
    msal_data = models.JSONField(null=True, blank=True)
    profile_photo = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"{self.user.username} - {self.role}"

class Vendor(models.Model):
    name = models.CharField(max_length=255)
    gstin = models.CharField(max_length=15, unique=True)
    bank_name = models.CharField(max_length=255)
    account_number = models.CharField(max_length=50)
    is_blacklisted = models.BooleanField(default=False)

    def __str__(self):
        return self.name

class InvoiceStatus(models.TextChoices):
    UPLOADED = 'UPLOADED', 'Uploaded'
    EXTRACTED = 'EXTRACTED', 'Extracted'
    RECONCILED = 'RECONCILED', 'Reconciled'
    PENDING_CORRECTION = 'PENDING_CORRECTION', 'Pending Correction'
    APPROVED = 'APPROVED', 'Approved'
    PAID = 'PAID', 'Paid'

class APInvoice(models.Model):
    vendor = models.ForeignKey(Vendor, on_delete=models.SET_NULL, null=True, blank=True)
    file = models.FileField(upload_to='invoices/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    status = models.CharField(max_length=20, choices=InvoiceStatus.choices, default=InvoiceStatus.UPLOADED)
    raw_ocr_data = models.JSONField(null=True, blank=True)
    final_table_data = models.JSONField(null=True, blank=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    def __str__(self):
        return f"Invoice {self.id} - {self.status}"

# --- OCR Processing Models ---

class BatchStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    PROCESSING = 'INVOICES_SCANNING_IN_PROCESS', 'Invoices Scanning in Process'
    COMPLETED = 'INVOICES_SCANNED', 'Invoices Scanned'
    FAILED = 'FAILED', 'Failed'
    MANUAL_REVIEW = 'MANUAL_REVIEW', 'Manual Review Needed'
    REJECTED = 'REJECTED', 'Rejected'

class ReconciliationStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending Reconciliation'
    VERIFIED = 'VERIFIED', 'Verified'
    MANUAL_REVIEW = 'MANUAL_REVIEW', 'Manual Review'
    NO_MATCH = 'NO_MATCH', 'No Match Found'
    MANUALLY_VERIFIED = 'MANUALLY_VERIFIED', 'Manually Verified' # Added for post-correction status

def generate_batch_id():
    """Generates a human-readable batch ID like AP_YYYYMMDD_UUID"""
    date_str = timezone.now().strftime('%Y%m%d')
    short_uuid = str(uuid.uuid4())[:8].upper()
    return f"AP_{date_str}_{short_uuid}"


def generate_unique_id():
    """Generates a human-readable batch ID like AP_YYYYMMDD_UUID"""
    date_str = timezone.now().strftime('%Y%m%d')
    short_uuid = str(uuid.uuid4())[:8].upper()
    return f"AP_{date_str}_{short_uuid}"


class OCRBatch(models.Model):
    batch_id = models.CharField(max_length=50, primary_key=True, default=generate_batch_id, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    due_report = models.ForeignKey('DueReportUpload', on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=40, choices=BatchStatus.choices, default=BatchStatus.PENDING)
    total_files = models.IntegerField(default=0)
    processed_files = models.IntegerField(default=0)

    def __str__(self):
        return f"Batch {self.batch_id} - {self.status}"

class DueReportUpload(models.Model):
    original_filename = models.CharField(max_length=500)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    row_count = models.IntegerField(default=0)
    data = models.JSONField(default=list, blank=True)

    def __str__(self):
        return f"Due Report {self.original_filename} ({self.row_count} rows)"


class DueReportRowStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    READY = 'READY', 'Ready'
    MANUAL_REVIEW = 'MANUAL_REVIEW', 'Manual Review'


class DueReportInvoiceReconciliationStatus(models.TextChoices):
    VERIFIED = 'VERIFIED', 'Verified'
    UNVERIFIED = 'UNVERIFIED', 'Unverified'
    MANUALLY_VERIFIED = 'MANUALLY_VERIFIED', 'Manually Verified'


class DueReportRowBase(models.Model):
    due_report = models.ForeignKey(DueReportUpload, on_delete=models.CASCADE)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=30, choices=DueReportRowStatus.choices, default=DueReportRowStatus.PENDING)
    is_from_excel = models.BooleanField(default=True)
    is_from_api = models.BooleanField(default=False)
    location_name = models.TextField(blank=True, null=True)
    supplier_name = models.TextField(blank=True, null=True)
    gst_number = models.CharField(max_length=15, blank=True, null=True)
    invoice_no = models.TextField(blank=True, null=True)
    ref_no = models.TextField(blank=True, null=True)
    bill_voucher_date = models.TextField(blank=True, null=True)
    invoice_date = models.TextField(blank=True, null=True)
    bill_amount = models.TextField(blank=True, null=True)
    disc_amount = models.TextField(blank=True, null=True)
    amount_adjusted = models.TextField(blank=True, null=True)
    balance_amount = models.TextField(blank=True, null=True)
    pending_adj_amt = models.TextField(blank=True, null=True)
    net_balance = models.TextField(blank=True, null=True)
    no_of_days = models.TextField(blank=True, null=True)
    due_date = models.TextField(blank=True, null=True)
    over_due_days = models.TextField(blank=True, null=True)
    prior_date = models.TextField(blank=True, null=True)
    group_name = models.TextField(blank=True, null=True)
    voucher_type = models.TextField(blank=True, null=True)
    msme_type = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True


class DueReportInvoiceWise(DueReportRowBase):
    is_acknowledged = models.BooleanField(default=False)
    invoice_scanned = models.BooleanField(default=False)
    invoice_reconciliation_status = models.CharField(
        max_length=20,
        choices=DueReportInvoiceReconciliationStatus.choices,
        default=DueReportInvoiceReconciliationStatus.UNVERIFIED,
    )
    is_payment_file_created = models.BooleanField(default=False)
    manager_rejected = models.BooleanField(default=False)
    manager_rejection_reason = models.TextField(null=True, blank=True)
    manager_rejected_at = models.DateTimeField(null=True, blank=True)
    manager_rejected_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='manager_rejected_invoice_rows')

    class Meta:
        verbose_name = 'Due Report Invoice Wise'
        verbose_name_plural = 'Due Report Invoice Wise'
        constraints = [
            models.UniqueConstraint(fields=['invoice_no', 'gst_number'], name='unique_invoice_gst_number')
        ]
        indexes = [
            models.Index(fields=['due_report', 'invoice_no', 'gst_number']),
        ]
        ordering = ('-created_at',)

    def __str__(self):
        return f"{self.invoice_no} - {self.gst_number}"


class DueReportUnknown(DueReportRowBase):
    class Meta:
        verbose_name = 'Due Report Unknown'
        verbose_name_plural = 'Due Report Unknown'
        indexes = [
            models.Index(fields=['due_report']),
            models.Index(fields=['gst_number']),
        ]
        ordering = ('-created_at',)

    def __str__(self):
        return self.invoice_no or self.supplier_name or f"Unknown Due Report Row {self.id}"


class MasterDataFile(models.Model):
    document_name = models.CharField(max_length=255, unique=True, help_text="Friendly name to identify this master file")
    file = models.FileField(upload_to='master_files/%Y/%m/%d/', blank=True, null=True)
    file_type = models.CharField(max_length=20, default='EXCEL', choices=[('EXCEL', 'Excel'), ('CSV', 'CSV')])
    parsed_data = models.JSONField(default=list, blank=True, help_text="Parsed rows for quick lookups in code")
    row_count = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True, help_text="Only active master files should be used for lookups")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    description = models.TextField(blank=True, null=True)

    def save(self, *args, **kwargs):
        if self.file and not self.parsed_data:
            self._populate_from_file()
        super().save(*args, **kwargs)

    def _populate_from_file(self):
        if not self.file:
            return

        import io
        import pandas as pd

        try:
            if hasattr(self.file, 'seek'):
                self.file.seek(0)
            if hasattr(self.file, 'read'):
                content = self.file.read()
                if not content and hasattr(self.file, 'file') and hasattr(self.file.file, 'read'):
                    self.file.file.seek(0)
                    content = self.file.file.read()
                if content:
                    if self.file_type == 'CSV':
                        df = pd.read_csv(io.BytesIO(content))
                    else:
                        df = pd.read_excel(io.BytesIO(content))
                else:
                    file_path = self.file.path if hasattr(self.file, 'path') else None
                    if not file_path:
                        return
                    df = pd.read_excel(file_path)
            else:
                file_path = self.file.path if hasattr(self.file, 'path') else None
                if not file_path:
                    return
                df = pd.read_excel(file_path)

            df = df.dropna(how='all')
            rows = []
            for _, row in df.iterrows():
                record = {}
                for column, value in row.items():
                    if pd.isna(value):
                        record[str(column)] = None
                    else:
                        raw_value = value.item() if hasattr(value, 'item') else value
                        if str(column).lower() in {'cash discount', 'cash_discount', 'discount', 'discount %'}:
                            record[str(column)] = _normalize_percentage_value(raw_value)
                        else:
                            record[str(column)] = raw_value
                rows.append(record)
            self.parsed_data = rows
            self.row_count = len(rows)
        except Exception:
            self.parsed_data = []
            self.row_count = 0
            self.row_count = 0

    class Meta:
        verbose_name = 'Master Data File'
        verbose_name_plural = 'Master Data Files'
        ordering = ('-uploaded_at',)

    def __str__(self):
        status = 'Active' if self.is_active else 'Inactive'
        return f"{self.document_name} ({status})"


class PaymentMasterEntry(models.Model):
    location_name = models.CharField(max_length=255, blank=True, null=True)
    counter = models.CharField(max_length=255, blank=True, null=True)
    voucher_date = models.DateField(blank=True, null=True)
    particulars = models.CharField(max_length=500, blank=True, null=True)
    voucher_no = models.CharField(max_length=255, unique=True, blank=True, null=True)
    voucher_type = models.CharField(max_length=255, blank=True, null=True)
    invoice_no = models.CharField(max_length=255, blank=True, null=True)
    debit = models.DecimalField(max_digits=14, decimal_places=2, default=0, blank=True, null=True)
    credit = models.DecimalField(max_digits=14, decimal_places=2, default=0, blank=True, null=True)
    party_name = models.CharField(max_length=500, blank=True, null=True)
    cheque_no = models.CharField(max_length=255, blank=True, null=True)
    cheque_date = models.DateField(blank=True, null=True)
    remarks = models.TextField(blank=True, null=True)
    bill_ref_no = models.CharField(max_length=255, blank=True, null=True)
    attachments = models.CharField(max_length=500, blank=True, null=True)
    bank_ref_no = models.CharField(max_length=255, blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_payment_master_entries')
    modified_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='modified_payment_master_entries')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Payment Master Entry'
        verbose_name_plural = 'Payment Master Entries'
        ordering = ('-voucher_date', '-created_at')

    def __str__(self):
        return self.voucher_no or f"Payment Entry {self.id}"

    @classmethod
    def import_from_rows(cls, rows):
        created_count = 0
        for row in rows:
            if not row:
                continue

            normalized_row = cls._normalize_row(row)
            voucher_no = normalized_row.get('voucher_no')
            if not voucher_no:
                voucher_no = f"AUTO-{created_count + 1}"

            defaults = {
                'location_name': normalized_row.get('location_name'),
                'counter': normalized_row.get('counter'),
                'voucher_date': normalized_row.get('voucher_date'),
                'particulars': normalized_row.get('particulars'),
                'voucher_type': normalized_row.get('voucher_type'),
                'invoice_no': normalized_row.get('invoice_no'),
                'debit': normalized_row.get('debit'),
                'credit': normalized_row.get('credit'),
                'party_name': normalized_row.get('party_name'),
                'cheque_no': normalized_row.get('cheque_no'),
                'cheque_date': normalized_row.get('cheque_date'),
                'remarks': normalized_row.get('remarks'),
                'bill_ref_no': normalized_row.get('bill_ref_no'),
                'attachments': normalized_row.get('attachments'),
                'bank_ref_no': normalized_row.get('bank_ref_no'),
            }
            entry, created = cls.objects.update_or_create(voucher_no=str(voucher_no), defaults=defaults)
            if created:
                created_count += 1
        return created_count

    @classmethod
    def _normalize_row(cls, row):
        normalized = {}
        for key, value in row.items():
            if key is None:
                continue
            normalized_key = str(key).strip().lower()
            normalized_key = normalized_key.replace(' ', '_').replace('-', '_').replace('.', '')
            if normalized_key in {'location_name', 'location', 'locationname'}:
                normalized['location_name'] = value
            elif normalized_key in {'counter', 'counterno'}:
                normalized['counter'] = value
            elif normalized_key in {'voucher_date', 'date', 'voucherdate'}:
                normalized['voucher_date'] = cls._coerce_date(value)
            elif normalized_key in {'particulars', 'particular'}:
                normalized['particulars'] = value
            elif normalized_key in {'voucher_no', 'voucherno', 'voucher_number', 'voucherno'}:
                normalized['voucher_no'] = value
            elif normalized_key in {'voucher_type', 'type'}:
                normalized['voucher_type'] = value
            elif normalized_key in {'invoiceno', 'invoice_no', 'invoice'}:
                normalized['invoice_no'] = value
            elif normalized_key in {'debit', 'debit_amount'}:
                normalized['debit'] = cls._coerce_decimal(value)
            elif normalized_key in {'credit', 'credit_amount'}:
                normalized['credit'] = cls._coerce_decimal(value)
            elif normalized_key in {'partyname', 'party_name', 'partynames', 'party'}:
                normalized['party_name'] = value
            elif normalized_key in {'chqno', 'chequeno', 'cheque_no', 'cheque'}:
                normalized['cheque_no'] = value
            elif normalized_key in {'chqdate', 'chequedate', 'cheque_date'}:
                normalized['cheque_date'] = cls._coerce_date(value)
            elif normalized_key in {'remarks', 'remark'}:
                normalized['remarks'] = value
            elif normalized_key in {'billrefno', 'bill_ref_no', 'billref'}:
                normalized['bill_ref_no'] = value
            elif normalized_key in {'attachments', 'attachment'}:
                normalized['attachments'] = value
            elif normalized_key in {'bank_refno', 'bank_ref_no', 'bankrefno', 'bankref'}:
                normalized['bank_ref_no'] = value
            else:
                normalized[normalized_key] = value
        return normalized

    @staticmethod
    def _coerce_date(value):
        if value in (None, ''):
            return None
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
        try:
            from datetime import datetime
            if isinstance(value, str):
                if 'T' in value:
                    return datetime.fromisoformat(value).date()
                for fmt in ['%Y-%m-%d', '%d-%m-%Y', '%m/%d/%Y', '%m/%d/%y', '%d/%m/%Y', '%d/%m/%y']:
                    try:
                        return datetime.strptime(value, fmt).date()
                    except ValueError:
                        continue
            return value
        except Exception:
            return None

    @staticmethod
    def _coerce_decimal(value):
        if value in (None, ''):
            return Decimal('0.00')
        if isinstance(value, (int, float)):
            return Decimal(str(value))
        if isinstance(value, str):
            text = value.strip().replace(',', '')
            if not text:
                return Decimal('0.00')
            try:
                return Decimal(text)
            except Exception:
                return Decimal('0.00')
        return Decimal('0.00')


class DocumentResult(models.Model):
    batch = models.ForeignKey(OCRBatch, on_delete=models.CASCADE, related_name='documents')
    original_filename = models.CharField(max_length=500)
    processed_at = models.DateTimeField(auto_now_add=True)
    extracted_text = models.TextField(null=True, blank=True)
    parsed_data = models.JSONField(null=True, blank=True)
    
    reconciliation_status = models.CharField(
        max_length=20,
        choices=ReconciliationStatus.choices,
        default=ReconciliationStatus.PENDING
    )
    matched_bill_data = models.JSONField(null=True, blank=True)
    reconciliation_details = models.JSONField(null=True, blank=True) 
    
    # Audit log for tracking changes over the document's lifecycle
    # Format: [{"timestamp": "...", "action": "Scanned", "user": "System", "details": "..."}, ...]
    audit_trail = models.JSONField(default=list, blank=True)

    def __str__(self):
        return f"Doc {self.id} from Batch {self.batch.batch_id} - {self.reconciliation_status}"


class PaymentType(models.TextChoices):
    ICICI = 'ICICI', 'ICICI'
    SBI = 'SBI', 'SBI'


class PaymentFile(models.Model):
    id = models.CharField(max_length=50, primary_key=True, default=generate_batch_id, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    due_report = models.ForeignKey('DueReportUpload', on_delete=models.SET_NULL, null=True, blank=True)
    payment_type = models.CharField(max_length=20, choices=PaymentType.choices, default=PaymentType.ICICI)
    file = models.FileField(upload_to='payment_files/%Y/%m/%d/', blank=True, null=True)
    due_report_rows = models.ManyToManyField('DueReportInvoiceWise', blank=True, related_name='payment_files')
    status = models.CharField(max_length=40, choices=BatchStatus.choices, default=BatchStatus.PENDING)
    unique_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    total_files = models.IntegerField(default=0)
    processed_files = models.IntegerField(default=0)
    line_item_overrides = models.JSONField(default=dict, blank=True)
    rejected_due_report_row_ids = models.JSONField(default=list, blank=True)
    is_payment_file_approved = models.BooleanField(default=False)
    is_payment_done = models.BooleanField(default=False)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_payment_files')
    modified_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='modified_payment_files')

    def __str__(self):
        return f"Payment File {self.id} - {self.status}"

    def save(self, *args, **kwargs):
        if not self.unique_id:
            self.unique_id = generate_batch_id()

        super().save(*args, **kwargs)


class PaymentFileInvoice(models.Model):
    class Status(models.TextChoices):
        PENDING_MANAGER_REVIEW = 'PENDING_MANAGER_REVIEW', 'Pending Manager Review'
        MANAGER_APPROVED = 'MANAGER_APPROVED', 'Manager Approved'
        MANAGER_REJECTED = 'MANAGER_REJECTED', 'Manager Rejected'
        PAID = 'PAID', 'Paid'

    payment_file = models.ForeignKey(PaymentFile, on_delete=models.CASCADE, related_name='invoice_links')
    invoice = models.ForeignKey('DueReportInvoiceWise', on_delete=models.CASCADE, related_name='payment_file_links')
    status = models.CharField(max_length=50, choices=Status.choices, default=Status.PENDING_MANAGER_REVIEW)
    manager_rejection_reason = models.TextField(null=True, blank=True)
    force_selected = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['payment_file', 'invoice'], name='unique_payment_file_invoice')
        ]
        ordering = ('created_at',)

    def __str__(self):
        return f"{self.payment_file_id} -> {self.invoice_id} ({self.status})"
    
