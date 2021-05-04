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
from django.contrib import admin
from ifxbilling import models


logger = logging.getLogger(__name__)


class UserAccountInlineAdmin(admin.TabularInline):
    '''
    Inline for user account listing.  To be used on UserAdmin
    '''
    model = models.UserAccount
    autocomplete_fields = ('user', 'account')
    extra = 0


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
        'billing_calculator',
    )
    list_display = (
        'id',
        'product_number',
        'product_name',
        'product_description',
    )
    ordering = ('product_number',)
    search_fields = (
        'product_number',
        'product_name',
        'product_description',
     )
    list_filter = ('billing_calculator', )
    inlines = (RateInlineAdmin,)


admin.site.register(models.Product, ProductAdmin)


class TransactionInlineAdmin(admin.TabularInline):
    '''
    For displaying transactions with BillingRecords
    '''
    model = models.Transaction
    extra = 0

class BillingRecordAdmin(admin.ModelAdmin):
    '''
    Admin for BillingRecords
    '''
    fields = (
        'product_usage',
        'account',
        'charge',
        'description',
        'year',
        'month',
        'created',
        'updated'
    )
    list_display = (
        'product_usage',
        'account',
        'charge',
        'description',
        'month',
        'year'
    )
    ordering = ('year', 'month')
    search_fields = (
        'account',
        'product_usage__product__name',
        'description',
     )
    list_filter = ('year', 'month', 'product_usage__product__product_name', 'account__name')
    readonly_fields = ('created', 'updated',)
    inlines = (TransactionInlineAdmin,)

admin.site.register(models.BillingRecord, BillingRecordAdmin)
