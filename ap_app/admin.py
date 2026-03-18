from django.contrib import admin
from .models import UserProfile, Vendor, APInvoice

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'get_date_joined', 'get_last_login')
    list_filter = ('role',)
    search_fields = ('user__username', 'user__email')
    # Adding msal_data to readonly fields so it can be seen but not accidentally edited
    readonly_fields = ('msal_data',)

    def get_date_joined(self, obj):
        return obj.user.date_joined
    get_date_joined.short_description = 'Created At'

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
