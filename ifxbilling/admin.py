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


class AccountAdmin(admin.ModelAdmin):
    '''
    Admin for expense codes and POs
    '''
    fields = (
        'code',
        'name',
        'account_type',
        'root',
        'expiration_date',
        'active',
        'valid_from',
        'created',
        'updated'
    )
    list_display = (
        'id',
        'code',
        'account_type',
        'name',
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
        'root'
    )
    list_filter = ('account_type', 'active')
    readonly_fields = ('created', 'updated')


admin.site.register(models.Account, AccountAdmin)


class UserAccountInlineAdmin(admin.TabularInline):
    '''
    Inline for user account listing.  To be used on UserAdmin
    '''
    model = models.UserAccount
    autocomplete_fields = ('user', 'account')
    extra = 0
