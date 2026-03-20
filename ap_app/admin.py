from django.contrib import admin
from .models import UserProfile, Vendor, APInvoice, OCRBatch, DocumentResult

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'get_email', 'get_first_name', 'get_last_login')
    list_filter = ('role',)
    search_fields = ('user__username', 'user__email', 'user__first_name')
    readonly_fields = ('msal_data', 'profile_photo')

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
    list_display = ('id', 'original_filename', 'get_batch_id', 'processed_at')
    list_filter = ('processed_at',)
    search_fields = ('original_filename', 'batch__batch_id', 'extracted_text')
    readonly_fields = ('batch', 'original_filename', 'processed_at', 'extracted_text')
    
    def get_batch_id(self, obj):
        return obj.batch.batch_id
    get_batch_id.short_description = 'Batch ID'
