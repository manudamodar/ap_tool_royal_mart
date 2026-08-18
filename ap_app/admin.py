import csv
import io
from django.contrib import admin
from django.contrib import messages
from django.http import HttpResponse
from django.db.models import Case, IntegerField, Value, When
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils.html import format_html
from .models import (
    UserProfile,
    Vendor,
    APInvoice,
    OCRBatch,
    DocumentResult,
    DueReportInvoiceWise,
    MasterDataFile,
    VendorMaster,
    RoyalMartStoreMaster,
    PaymentMasterEntry,
    PaymentFile,
)
from import_export import fields, resources
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


class VendorMasterResource(resources.ModelResource):
    vendor_id = fields.Field(attribute='vendor_id', column_name='ID')
    supplier_name = fields.Field(attribute='supplier_name', column_name='Supplier name')
    gst_number = fields.Field(attribute='gst_number', column_name='GST Number')

    def before_import_row(self, row, **kwargs):
        vendor_id = row.get('ID')
        gst_number = row.get('GST Number')
        normalized_vendor_id = str(vendor_id).strip() if vendor_id not in (None, '') else None
        if normalized_vendor_id and normalized_vendor_id.endswith('.0'):
            normalized_vendor_id = normalized_vendor_id[:-2]
        row['ID'] = normalized_vendor_id
        row['GST Number'] = str(gst_number).strip().upper() if gst_number not in (None, '') else None

    def skip_row(self, instance, original, row, import_validation_errors=None):
        if not row.get('ID') or not row.get('Supplier name'):
            return True
        return super().skip_row(instance, original, row, import_validation_errors)

    class Meta:
        model = VendorMaster
        import_id_fields = ('vendor_id',)
        fields = ('vendor_id', 'supplier_name', 'gst_number')
        skip_unchanged = True


@admin.register(VendorMaster)
class VendorMasterAdmin(ImportExportModelAdmin):
    resource_class = VendorMasterResource
    list_display = ('vendor_id', 'supplier_name', 'gst_number', 'is_active', 'updated_at')
    list_filter = ('is_active',)
    search_fields = ('vendor_id', 'supplier_name', 'gst_number')


class RoyalMartStoreMasterResource(resources.ModelResource):
    serial_number = fields.Field(attribute='serial_number', column_name='SI NO')
    legal_name = fields.Field(attribute='legal_name', column_name='LEEGAL NAME')
    store_code = fields.Field(attribute='store_code', column_name='STORE CODE\u00a0')
    gst_number = fields.Field(attribute='gst_number', column_name='GST NUMBER')
    address = fields.Field(attribute='address', column_name='ADDRESS')
    email_address = fields.Field(attribute='email_address', column_name='MAIL ADDRESS')

    def before_import(self, dataset, **kwargs):
        # The supplied store workbook has a blank first Excel row and its real
        # headers on row two. Promote that row so it imports without editing.
        headers = [str(value or '').strip() for value in (dataset.headers or [])]
        if 'GST NUMBER' not in headers and dataset.height:
            candidate_headers = list(dataset[0])
            if 'GST NUMBER' in candidate_headers:
                dataset.headers = candidate_headers
                dataset.lpop()

    class Meta:
        model = RoyalMartStoreMaster
        import_id_fields = ('store_code', 'gst_number')
        fields = ('serial_number', 'legal_name', 'store_code', 'gst_number', 'address', 'email_address')
        skip_unchanged = True


@admin.register(RoyalMartStoreMaster)
class RoyalMartStoreMasterAdmin(ImportExportModelAdmin):
    resource_class = RoyalMartStoreMasterResource
    list_display = ('store_code', 'legal_name', 'gst_number', 'email_address', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('store_code', 'legal_name', 'gst_number', 'address', 'email_address')


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
    list_display = ('batch_id', 'status', 'uploaded_by', 'processed_files', 'total_files', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('batch_id', 'uploaded_by__username', 'uploaded_by__email')
    readonly_fields = ('batch_id', 'created_at', 'uploaded_by', 'total_files', 'processed_files')
    inlines = [DocumentResultInline]
    
    fieldsets = (
        ('Batch Details', {
            'fields': ('batch_id', 'status', 'uploaded_by', 'created_at')
        }),
        ('Progress', {
            'fields': ('processed_files', 'total_files')
        }),
    )


@admin.register(DocumentResult)
class DocumentResultAdmin(admin.ModelAdmin):
    list_display = ('id', 'original_filename', 'get_batch_id', 'reconciliation_status', 'processed_at')
    list_filter = ('reconciliation_status', 'processed_at')
    search_fields = ('original_filename', 'batch__batch_id', 'extracted_text')
    readonly_fields = (
        'batch', 'original_filename', 'processed_at', 'extracted_text',
        'invoice_number_matches', 'payable_amount_matches', 'goods_value_matches',
        'tax_amount_matches', 'tax_type_matches', 'vendor_gst_matches',
        'vendor_master_verified', 'store_gst_matches', 'store_master_verified',
    )
    
    def get_batch_id(self, obj):
        return obj.batch.batch_id
    get_batch_id.short_description = 'Batch ID'


class DueReportRowAdmin(admin.ModelAdmin):
    list_display = (
        'invoice_no',
        'gst_number',
        'supplier_name',
        'status',
        'created_at',
    )
    list_filter = ('status', 'created_at')
    search_fields = (
        'invoice_no',
        'gst_number',
        'supplier_name',
        'ref_no',
    )
    readonly_fields = (
        'status',
        'tran_year',
        'branch_code',
        'location_name',
        'voucher_no',
        'supplier_name',
        'party_code',
        'gst_number',
        'invoice_no',
        'ref_no',
        'bill_voucher_date',
        'bill_date',
        'invoice_date',
        'bill_amount',
        'payable',
        'expense_ledger',
        'goods_value',
        'tax_amount',
        'tax_code',
        'tax_type',
        'tds_amount',
        'tds_section',
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
        'party_contact',
        'pay_mode',
        'other_charges',
        'payment_status',
        'transaction_link',
        'email_id',
        'bill_unique_id',
        'created_at',
    )


@admin.register(DueReportInvoiceWise)
class DueReportInvoiceWiseAdmin(DueReportRowAdmin):
    change_list_template = 'admin/ap_app/duereportinvoicewise/change_list.html'
    change_form_template = 'admin/ap_app/duereportinvoicewise/change_form.html'
    list_display = (
        'invoice_no',
        'gst_number',
        'supplier_name',
        'workflow_status',
        'created_at',
        'is_acknowledged',
        'invoice_scanned',
        'invoice_reconciliation_status',
        'invoice_number_matches',
        'payable_amount_matches',
        'goods_value_matches',
        'tax_amount_matches',
        'tax_type_matches',
        'vendor_gst_matches',
        'vendor_master_verified',
        'store_gst_matches',
        'store_master_verified',
        'is_payment_file_created',
        'manager_rejected',
        'manager_rejected_by',
    )
    list_filter = ('invoice_scanned', 'invoice_reconciliation_status', 'created_at')
    exclude = ('status',)
    readonly_fields = tuple(
        field for field in DueReportRowAdmin.readonly_fields if field != 'status'
    ) + (
        'is_acknowledged',
        'invoice_scanned',
        'invoice_reconciliation_status',
        'invoice_number_matches',
        'payable_amount_matches',
        'goods_value_matches',
        'tax_amount_matches',
        'tax_type_matches',
        'vendor_gst_matches',
        'vendor_master_verified',
        'store_gst_matches',
        'store_master_verified',
        'reconciliation_details',
        'is_payment_file_created',
        'manager_rejected',
        'manager_rejected_by',
        'manager_rejection_reason',
        'manager_rejected_at',
    )

    @admin.display(description='Status', ordering='invoice_reconciliation_status')
    def workflow_status(self, obj):
        if not obj.invoice_scanned:
            return 'Not Scanned'
        return obj.get_invoice_reconciliation_status_display()

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            workflow_priority=Case(
                When(invoice_scanned=True, invoice_reconciliation_status='VERIFIED', then=Value(0)),
                When(invoice_scanned=True, invoice_reconciliation_status='MANUALLY_VERIFIED', then=Value(1)),
                When(invoice_scanned=True, then=Value(2)),
                default=Value(3),
                output_field=IntegerField(),
            )
        ).order_by('workflow_priority', '-created_at', '-id')

    def get_urls(self):
        custom_urls = [
            path(
                '<int:object_id>/reset-processing-data/',
                self.admin_site.admin_view(self.reset_single_bill_processing_data),
                name='ap_app_duereportinvoicewise_reset_single_processing_data',
            ),
            path(
                'reset-processing-data/',
                self.admin_site.admin_view(self.reset_processing_data),
                name='ap_app_duereportinvoicewise_reset_processing_data',
            ),
        ]
        return custom_urls + super().get_urls()

    @staticmethod
    def _processing_reset_values():
        return {
            'is_acknowledged': False,
            'invoice_scanned': False,
            'invoice_reconciliation_status': 'UNVERIFIED',
            'invoice_number_matches': None,
            'payable_amount_matches': None,
            'goods_value_matches': None,
            'tax_amount_matches': None,
            'tax_type_matches': None,
            'vendor_gst_matches': None,
            'vendor_master_verified': None,
            'store_gst_matches': None,
            'store_master_verified': None,
            'reconciliation_details': {},
            'is_payment_file_created': False,
            'manager_rejected': False,
            'manager_rejection_reason': None,
            'manager_rejected_at': None,
            'manager_rejected_by': None,
        }

    def reset_processing_data(self, request):
        if not self.has_change_permission(request):
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied

        if request.method == 'POST':
            reset_count = DueReportInvoiceWise.objects.update(**self._processing_reset_values())
            self.message_user(
                request,
                f'Reset processing and reconciliation data for {reset_count} bills. GoFrugal bill fields and payment-file history were preserved.',
                level=messages.SUCCESS,
            )
            return redirect('admin:ap_app_duereportinvoicewise_changelist')

        context = {
            **self.admin_site.each_context(request),
            'title': 'Reset bill processing data',
            'opts': self.model._meta,
            'bill_count': DueReportInvoiceWise.objects.count(),
        }
        return render(request, 'admin/ap_app/duereportinvoicewise/reset_processing_data.html', context)

    def reset_single_bill_processing_data(self, request, object_id):
        if not self.has_change_permission(request):
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied

        bill = self.get_object(request, object_id)
        if bill is None:
            from django.http import Http404
            raise Http404('Bill not found')

        if request.method == 'POST':
            DueReportInvoiceWise.objects.filter(pk=bill.pk).update(**self._processing_reset_values())
            self.message_user(
                request,
                f'Reset processing and reconciliation data for invoice {bill.invoice_no}. GoFrugal fields were preserved.',
                level=messages.SUCCESS,
            )
            return redirect('admin:ap_app_duereportinvoicewise_change', bill.pk)

        context = {
            **self.admin_site.each_context(request),
            'title': 'Reset this bill',
            'opts': self.model._meta,
            'bill': bill,
        }
        return render(request, 'admin/ap_app/duereportinvoicewise/reset_single_processing_data.html', context)


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
        "processed_files",
        "total_files",
        "created_by",
        "modified_by",
        "created_at",
    )
    list_filter = ("status", "created_at", "created_by", "modified_by")
    search_fields = ("id", "unique_id", "created_by__username", "modified_by__username")
    readonly_fields = ("id", "unique_id", "created_by", "modified_by", "created_at", "updated_at", "download_link", "line_item_overrides", "rejected_due_report_row_ids")
    ordering = ("-created_at",)

    fieldsets = (
        ("Payment File", {
            "fields": ("id", "unique_id", "status", "total_files", "processed_files", "download_link", "line_item_overrides", "rejected_due_report_row_ids")
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
