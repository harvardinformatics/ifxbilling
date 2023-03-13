# -*- coding: utf-8 -*-

'''
Admin for ifxbilling

Created on  2020-07-01

@author: Meghan Correa <mportermahoney@g.harvard.edu>
@copyright: 2020 The Presidents and Fellows of Harvard College.
All rights reserved.
@license: GPL v2.0
'''
import logging
from dateutil.relativedelta import relativedelta
from django.utils import timezone
from django.contrib import admin
from django.contrib.admin.widgets import AutocompleteSelect
from django.forms import TextInput
from django import forms
from django.db.models import CharField
from ifxbilling import models

class FacilityProductInlineAdmin(admin.TabularInline):
    '''
    List products for a Facility
    '''
    model = models.Product
    extra = 0


class FacilityAdmin(admin.ModelAdmin):
    '''
    Admin for Facilities
    '''
    fields = (
        'name',
        'application_username',
        'credit_code',
        'object_code',
        'invoice_prefix',
        'billing_record_template',
        'billing_record_calculator'
    )
    list_display = (
        'id',
        'name',
        'application_username',
        'credit_code',
        'object_code',
        'invoice_prefix',
        'billing_record_template',
        'billing_record_calculator'
    )
    ordering = ('name',)
    search_fields = (
        'name',
    )
    inlines = [FacilityProductInlineAdmin]


admin.site.register(models.Facility, FacilityAdmin)


class AccountInlineForm(forms.ModelForm):
    '''
    Just makes the account field widget larger
    '''
    class Meta:
        widgets = {
            'account': AutocompleteSelect(
                models.UserAccount._meta.get_field('account'),
                admin.site,
                attrs={'style': 'width: 500px'}
            ),
        }


class ProductAccountInlineForm(forms.ModelForm):
    '''
    Just makes the account and product field widget larger
    '''
    class Meta:
        widgets = {
            'account': AutocompleteSelect(
                models.UserProductAccount._meta.get_field('account'),
                admin.site,
                attrs={'style': 'width: 500px'}
            ),
            'product': AutocompleteSelect(
                models.UserProductAccount._meta.get_field('product'),
                admin.site,
                attrs={'style': 'width: 500px'}
            ),
        }


logger = logging.getLogger(__name__)


class UserAccountInlineAdmin(admin.TabularInline):
    '''
    Inline for user account listing.  To be used on UserAdmin
    '''
    model = models.UserAccount
    autocomplete_fields = ('user',)
    extra = 0
    form = AccountInlineForm


class AccountAdmin(admin.ModelAdmin):
    '''
    Admin for expense codes and POs
    '''
    fields = (
        'name',
        'code',
        'account_type',
        'organization',
        'root',
        'expiration_date',
        'active',
        'valid_from',
        'created',
        'updated'
    )
    list_display = (
        'id',
        'name',
        'code',
        'account_type',
        'organization',
        'root',
        'expiration_date',
        'active',
        'valid_from',
        'created',
        'updated'
    )
    ordering = ('updated',)
    search_fields = (
        'code',
        'name',
        'root',
        'organization__name',
    )
    list_filter = ('account_type', 'active', 'organization__name')
    readonly_fields = ('created', 'updated')
    inlines = (UserAccountInlineAdmin,)
    autocomplete_fields = ('organization',)
    formfield_overrides = {
        CharField: {'widget': TextInput(attrs={'size':'60'})},
    }


admin.site.register(models.Account, AccountAdmin)


class RateInlineAdmin(admin.TabularInline):
    '''
    Inline for displaying rates with a Product
    '''
    model = models.Rate
    extra = 0


class ProductAdmin(admin.ModelAdmin):
    '''
    Admin products
    '''
    fields = (
        'product_number',
        'product_name',
        'product_description',
        'facility',
        'billing_calculator',
        'reporting_group',
        'billable'
    )
    list_display = (
        'id',
        'product_number',
        'product_name',
        'product_description',
        'facility',
        'billable'
    )
    ordering = ('product_number',)
    search_fields = (
        'product_number',
        'product_name',
        'product_description',
        'billing_calculator',
        'facility',
        'reporting_group'
     )
    list_filter = ('billing_calculator', 'billable')
    inlines = (RateInlineAdmin,)
    readonly_fields = ('product_number',)


admin.site.register(models.Product, ProductAdmin)


class TransactionInlineAdmin(admin.TabularInline):
    '''
    For displaying transactions with BillingRecords
    '''
    model = models.Transaction
    extra = 0
    autocomplete_fields = ('author', )
    def formfield_for_dbfield(self, db_field, **kwargs):
        formfield = super().formfield_for_dbfield(db_field, **kwargs)
        if db_field.name == 'comment':
            formfield.widget = forms.Textarea(attrs={'cols': 20, 'rows': 3})
        return formfield


class BillingRecordStateInlineAdmin(admin.TabularInline):
    '''
    For displaying billing record states with BillingRecords
    '''
    model = models.BillingRecordState
    autocomplete_fields = ('billing_record', 'approvers', 'user')
    extra = 0

class BillingRecordAdmin(admin.ModelAdmin):
    '''
    Admin for BillingRecords
    '''
    fields = (
        'product_usage',
        'account',
        'charge',
        'decimal_charge',
        'decimal_quantity',
        'description',
        'year',
        'month',
        'current_state',
        'created',
        'updated',
        'percent',
        'rate',
        'rate_obj',
        'product_usage_link_text',
        'product_usage_url',
        'start_date',
        'end_date',
    )
    list_display = (
        'id',
        'product_usage',
        'account',
        'decimal_charge',
        'percent',
        'month',
        'year',
        'current_state',
        'description',
        'rate_obj',
        'start_date',
        'end_date',
    )
    ordering = ('year', 'month', 'product_usage__id')
    search_fields = (
        'account__name',
        'account__code',
        'product_usage__product__product_name',
        'description',
        'id',
     )
    list_filter = ('year', 'month', 'account__root', 'product_usage__product__product_name', 'account__name')
    readonly_fields = ('created', 'updated',)
    inlines = (TransactionInlineAdmin, BillingRecordStateInlineAdmin)
    autocomplete_fields = ('account', 'product_usage')

admin.site.register(models.BillingRecord, BillingRecordAdmin)


class ProductUsageAdmin(admin.ModelAdmin):
    '''
    Admin for ProductUsages
    '''
    fields = (
        'product',
        'product_user',
        'organization',
        'logged_by',
        'description',
        'year',
        'month',
        'quantity',
        'decimal_quantity',
        'units',
        'created',
        'updated',
        'start_date',
        'end_date'
    )
    list_display = (
        'id',
        'product',
        'product_user',
        'organization',
        'logged_by',
        'quantity',
        'decimal_quantity',
        'units',
        'month',
        'year',
        'description',
        'start_date',
        'end_date'
    )
    ordering = ('year', 'month')
    search_fields = (
        'product__product_name',
        'product__product_number',
        'product_user__full_name',
     )
    list_filter = ('year', 'month', 'product', 'product_user')
    readonly_fields = ('created', 'updated')
    autocomplete_fields = ('product_user', )


admin.site.register(models.ProductUsage, ProductUsageAdmin)


class UserProductAccountInlineAdmin(admin.TabularInline):
    '''
    Inline for UserProductAccounts
    '''
    model = models.UserProductAccount
    extra = 0
    form = ProductAccountInlineForm


class ProductUsageInlineAdmin(admin.TabularInline):
    '''
    Inline for ProductUsage
    '''
    model = models.ProductUsage
    fk_name = 'product_user'
    autocomplete_fields = ('product',)
    extra = 0
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        two_months_ago = timezone.now() + relativedelta(months=-2)
        return qs.filter(start_date__gte=two_months_ago)


class AccountUserAdmin(admin.ModelAdmin):
    '''
    Show accounts associated with users
    '''
    fields = (
        'ifxid',
        'username',
        'first_name',
        'last_name',
        'full_name',
        'primary_affiliation',
        'is_active',
    )
    list_display = (
        'ifxid',
        'username',
        'first_name',
        'last_name',
        'full_name',
        'primary_affiliation',
        'is_active',
    )
    search_fields = (
        'full_name',
        'username',
        'ifxid',
        'primary_affiliation__name',
    )
    list_filter = ('primary_affiliation', )
    inlines = (UserAccountInlineAdmin, UserProductAccountInlineAdmin, ProductUsageInlineAdmin)


admin.site.register(models.AccountUser, AccountUserAdmin)

class ProductUsageProcessingAdmin(admin.ModelAdmin):
    '''
    ProductUsageProcessing
    '''
    fields = (
        'product_usage',
        'error_message',
        'resolved',
    )
    list_display = (
        'id',
        'product_usage',
        'error_message',
        'resolved',
        'created',
        'updated',
    )
    search_fields = (
        'product_usage',
        'error_message',
    )
    list_filter = ('resolved', )


admin.site.register(models.ProductUsageProcessing, ProductUsageProcessingAdmin)
