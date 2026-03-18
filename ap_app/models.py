from django.db import models
from django.contrib.auth.models import User

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
