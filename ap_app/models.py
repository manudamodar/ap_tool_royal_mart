import uuid
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class UserRole(models.TextChoices):
    UNASSIGNED = 'UNASSIGNED', 'Unassigned'
    AP_TEAM = 'AP_TEAM', 'AP Team'
    STORE_ACCOUNTANT = 'STORE_ACCOUNTANT', 'Store Accountant'
    STORE_MANAGER = 'STORE_MANAGER', 'Store Manager'

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=UserRole.choices, default=UserRole.UNASSIGNED)
    
    # Store the full claims payload from MSAL if needed for reference
    msal_data = models.JSONField(null=True, blank=True)
    
    # Store the user's profile photo as a base64 string
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
    MANUAL_REVIEW = 'MANUAL_REVIEW', 'Manual Review Needed' # Added MANUAL_REVIEW status

class ReconciliationStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending Reconciliation'
    VERIFIED = 'VERIFIED', 'Verified'
    MANUAL_REVIEW = 'MANUAL_REVIEW', 'Manual Review'
    NO_MATCH = 'NO_MATCH', 'No Match Found'

def generate_batch_id():
    """Generates a human-readable batch ID like AP_YYYYMMDD_UUID"""
    date_str = timezone.now().strftime('%Y%m%d')
    short_uuid = str(uuid.uuid4())[:8].upper()
    return f"AP_{date_str}_{short_uuid}"

class OCRBatch(models.Model):
    # Changed from UUIDField to CharField to support custom string IDs
    batch_id = models.CharField(max_length=50, primary_key=True, default=generate_batch_id, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    status = models.CharField(max_length=40, choices=BatchStatus.choices, default=BatchStatus.PENDING)
    total_files = models.IntegerField(default=0)
    processed_files = models.IntegerField(default=0)

    def __str__(self):
        return f"Batch {self.batch_id} - {self.status}"

class DocumentResult(models.Model):
    batch = models.ForeignKey(OCRBatch, on_delete=models.CASCADE, related_name='documents')
    original_filename = models.CharField(max_length=500)
    processed_at = models.DateTimeField(auto_now_add=True)
    extracted_text = models.TextField(null=True, blank=True)
    parsed_data = models.JSONField(null=True, blank=True)
    
    # New fields for reconciliation
    reconciliation_status = models.CharField(
        max_length=20,
        choices=ReconciliationStatus.choices,
        default=ReconciliationStatus.PENDING
    )
    matched_bill_data = models.JSONField(null=True, blank=True) # Stores the matching bill data from the API
    reconciliation_details = models.JSONField(null=True, blank=True) # Stores reasons for manual review/discrepancies

    def __str__(self):
        return f"Doc {self.id} from Batch {self.batch.batch_id} - {self.reconciliation_status}"
