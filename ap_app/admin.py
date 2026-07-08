import csv
import io
from django.contrib import admin
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils.html import format_html
from .models import (
    UserProfile,
    Vendor,
    APInvoice,
    OCRBatch,
    DocumentResult,
    DueReportUpload,
    DueReportInvoiceWise,
    DueReportUnknown,
    MasterDataFile,
    PaymentMasterEntry,
    PaymentFile,
)
from import_export import resources
from import_export.admin import ImportExportModelAdmin

def _read_import_rows(uploaded_file):
    filename = getattr(uploaded_file, 'name', '') or ''
    lowered_name = filename.lower()

    if lowered_name.endswith('.csv'):
        content = uploaded_file.read().decode('utf-8-sig')
        return list(csv.DictReader(io.StringIO(content)))

    if lowered_name.endswith(('.xlsx', '.xls')) or lowered_name.endswith('.xlsm') or lowered_name.endswith('.ods'):
        import pandas as pd

        uploaded_file.seek(0)
        dataframe = pd.read_excel(uploaded_file)
        return dataframe.where(pd.notna(dataframe), None).to_dict(orient='records')

    try:
        import pandas as pd

        uploaded_file.seek(0)
        dataframe = pd.read_excel(uploaded_file)
        return dataframe.where(pd.notna(dataframe), None).to_dict(orient='records')
    except Exception as exc:
        raise ValueError('Unsupported file format. Please upload an Excel file or CSV file.') from exc

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'get_account_manager', 'get_email', 'get_first_name', 'get_last_login')
    list_filter = ('role',)
    search_fields = ('user__username', 'user__email', 'user__first_name', 'account_manager__username', 'account_manager__email')
    readonly_fields = ('msal_data', 'profile_photo')

    def get_account_manager(self, obj):
        return obj.account_manager.username if obj.account_manager else None
    get_account_manager.short_description = 'Account Manager'

    def get_email(self, obj):
        return obj.user.email
    get_email.short_description = 'Email'

    def get_first_name(self, obj):
        return obj.user.first_name
    get_first_name.short_description = 'First Name'

    def get_last_login(self, obj):
        return obj.user.last_login
    get_last_login.short_description = 'Last Login'


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ('name', 'gstin', 'bank_name', 'account_number', 'is_blacklisted')
    list_filter = ('is_blacklisted',)
    search_fields = ('name', 'gstin', 'account_number')


@admin.register(APInvoice)
class APInvoiceAdmin(admin.ModelAdmin):
    list_display = ('id', 'vendor', 'status', 'total_amount', 'uploaded_at', 'uploaded_by')
    list_filter = ('status', 'uploaded_at')
    search_fields = ('vendor__name', 'status')
    readonly_fields = ('uploaded_at',)
    
    fieldsets = (
        ('Basic Info', {
            'fields': ('vendor', 'file', 'status', 'total_amount')
        }),
        ('Audit', {
            'fields': ('uploaded_by', 'uploaded_at')
        }),
        ('Data Extraction', {
            'fields': ('raw_ocr_data', 'final_table_data'),
            'classes': ('collapse',)
        }),
    )


class DocumentResultInline(admin.StackedInline):
    model = DocumentResult
    extra = 0
    readonly_fields = ('original_filename', 'processed_at', 'extracted_text')
    can_delete = False


@admin.register(OCRBatch)
class OCRBatchAdmin(admin.ModelAdmin):
    list_display = ('batch_id', 'status', 'uploaded_by', 'due_report', 'processed_files', 'total_files', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('batch_id', 'uploaded_by__username', 'uploaded_by__email')
    readonly_fields = ('batch_id', 'created_at', 'uploaded_by', 'due_report', 'total_files', 'processed_files')
    inlines = [DocumentResultInline]
    
    fieldsets = (
        ('Batch Details', {
            'fields': ('batch_id', 'status', 'uploaded_by', 'due_report', 'created_at')
        }),
        ('Progress', {
            'fields': ('processed_files', 'total_files')
        }),
    )


@admin.register(DocumentResult)
class DocumentResultAdmin(admin.ModelAdmin):
    list_display = ('id', 'original_filename', 'get_batch_id', 'processed_at')
    list_filter = ('processed_at',)
    search_fields = ('original_filename', 'batch__batch_id', 'extracted_text')
    readonly_fields = ('batch', 'original_filename', 'processed_at', 'extracted_text')
    
    def get_batch_id(self, obj):
        return obj.batch.batch_id
    get_batch_id.short_description = 'Batch ID'


@admin.register(DueReportUpload)
class DueReportUploadAdmin(admin.ModelAdmin):
    list_display = ('id', 'original_filename', 'row_count', 'uploaded_by', 'uploaded_at')
    list_filter = ('uploaded_at',)
    search_fields = ('original_filename', 'uploaded_by__username', 'uploaded_by__email')
    readonly_fields = ('original_filename', 'uploaded_at', 'uploaded_by', 'row_count', 'data')


class DueReportRowAdmin(admin.ModelAdmin):
    list_display = (
        'invoice_no',
        'gst_number',
        'supplier_name',
        'due_report',
        'uploaded_by',
        'status',
        'is_from_excel',
        'is_from_api',
        'created_at',
    )
    list_filter = ('status', 'is_from_excel', 'is_from_api', 'created_at')
    search_fields = (
        'invoice_no',
        'gst_number',
        'supplier_name',
        'ref_no',
        'due_report__original_filename',
        'uploaded_by__username',
        'uploaded_by__email',
    )
    readonly_fields = (
        'due_report',
        'uploaded_by',
        'status',
        'is_from_excel',
        'is_from_api',
        'location_name',
        'supplier_name',
        'gst_number',
        'invoice_no',
        'ref_no',
        'bill_voucher_date',
        'invoice_date',
        'bill_amount',
        'disc_amount',
        'amount_adjusted',
        'balance_amount',
        'pending_adj_amt',
        'net_balance',
        'no_of_days',
        'due_date',
        'over_due_days',
        'prior_date',
        'group_name',
        'voucher_type',
        'msme_type',
        'created_at',
    )


@admin.register(DueReportInvoiceWise)
class DueReportInvoiceWiseAdmin(DueReportRowAdmin):
    list_display = DueReportRowAdmin.list_display + ('is_acknowledged', 'is_payment_file_created', 'manager_rejected', 'manager_rejected_by')
    readonly_fields = DueReportRowAdmin.readonly_fields + ('is_acknowledged', 'is_payment_file_created', 'manager_rejected', 'manager_rejected_by', 'manager_rejection_reason', 'manager_rejected_at')


@admin.register(DueReportUnknown)
class DueReportUnknownAdmin(DueReportRowAdmin):
    pass


@admin.register(MasterDataFile)
class MasterDataFileAdmin(admin.ModelAdmin):
    list_display = ('document_name', 'file_type', 'is_active', 'row_count', 'uploaded_by', 'uploaded_at')
    list_filter = ('is_active', 'file_type', 'uploaded_at')
    search_fields = ('document_name', 'description', 'uploaded_by__username')
    readonly_fields = ('uploaded_at', 'row_count')
    fieldsets = (
        ('Basic Info', {
            'fields': ('document_name', 'file', 'file_type', 'description', 'is_active')
        }),
        ('Upload Details', {
            'fields': ('uploaded_by', 'uploaded_at', 'row_count', 'parsed_data')
        }),
    )


class PaymentMasterEntryResource(resources.ModelResource):
    class Meta:
        model = PaymentMasterEntry
        skip_unchanged = True
        report_skipped = True


@admin.register(PaymentMasterEntry)
class PaymentMasterEntryAdmin(ImportExportModelAdmin):
    resource_class = PaymentMasterEntryResource

    list_display = (
        "voucher_no",
        "voucher_date",
        "party_name",
        "invoice_no",
        "debit",
        "credit",
        "bank_ref_no",
        "created_by",
        "modified_by",
        "created_at",
    )

    list_filter = (
        "voucher_date",
        "voucher_type",
        "created_at",
        "created_by",
        "modified_by",
    )

    search_fields = (
        "voucher_no",
        "invoice_no",
        "party_name",
        "bill_ref_no",
        "bank_ref_no",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
        "created_by",
        "modified_by",
    )

    ordering = ("-created_at",)

    list_per_page = 50

    fieldsets = (
        ("Payment Details", {
            "fields": (
                "location_name",
                "counter",
                "voucher_date",
                "particulars",
                "voucher_no",
                "voucher_type",
                "invoice_no",
                "debit",
                "credit",
                "party_name",
                "cheque_no",
                "cheque_date",
                "remarks",
                "bill_ref_no",
                "attachments",
                "bank_ref_no",
            )
        }),
        ("Audit", {
            "fields": ("created_by", "modified_by", "created_at", "updated_at")
        }),
    )

    def save_model(self, request, obj, form, change):
        if not change and not obj.created_by_id:
            obj.created_by = request.user
        obj.modified_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(PaymentFile)
class PaymentFileAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "unique_id",
        "status",
        "due_report",
        "processed_files",
        "total_files",
        "created_by",
        "modified_by",
        "created_at",
    )
    list_filter = ("status", "created_at", "created_by", "modified_by")
    search_fields = ("id", "unique_id", "due_report__original_filename", "created_by__username", "modified_by__username")
    readonly_fields = ("id", "unique_id", "created_by", "modified_by", "created_at", "updated_at", "download_link", "line_item_overrides", "rejected_due_report_row_ids")
    ordering = ("-created_at",)

    fieldsets = (
        ("Payment File", {
            "fields": ("id", "unique_id", "due_report", "status", "total_files", "processed_files", "download_link", "line_item_overrides", "rejected_due_report_row_ids")
        }),
        ("Audit", {
            "fields": ("created_by", "modified_by", "created_at", "updated_at")
        }),
    )

    def download_link(self, obj):
        if not obj.pk:
            return "-"
        url = reverse('download_payment_file', args=[obj.pk])
        return format_html('<a href="{}" target="_blank">Download XLSX</a>', url)
    download_link.short_description = "Download"

    def save_model(self, request, obj, form, change):
        if not change and not obj.created_by_id:
            obj.created_by = request.user
        obj.modified_by = request.user
        super().save_model(request, obj, form, change)
