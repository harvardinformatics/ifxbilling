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

class ExpenseCodeAdmin(admin.ModelAdmin):
    '''
    Admin for expense codes
    '''
    fields = (
        'fullcode',
        'name',
        'root',
        'expiration_date',
        'active',
        'valid_from',
        'created',
        'updated'
    )
    list_display = (
        'id',
        'fullcode',
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
        'fullcode',
        'name',
        'root'
    )
    list_filter = ('expiration_date', 'active')
    readonly_fields = ('created', 'updated')

admin.site.register(models.ExpenseCode, ExpenseCodeAdmin)
