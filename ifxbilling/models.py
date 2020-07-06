# -*- coding: utf-8 -*-

'''
Billing model for ifx applications

Created on  2020-05-12

@author: Meghan Correa <mportermahoney@g.harvard.edu>
@copyright: 2020 The Presidents and Fellows of Harvard College.
All rights reserved.
@license: GPL v2.0
'''
from django_mysql.models import JSONField
from django.contrib.auth import get_user_model
from django.db import models
from django.core.validators import RegexValidator
from model_utils.managers import InheritanceManager
from django.conf import settings
from datetime import datetime
import logging

logger = logging.getLogger('__name__')

class ExpenseCode(models.Model):
    """
    ExpenseCode model
    """
    class Meta:
        db_table = "expense_code"

    fullcode = models.CharField(
        max_length=50,
        blank=False,
        null=False,
        default=None,
        help_text='expense code, dash seperated',
        validators=[
            RegexValidator('^[0-9]{3}\-[0-9]{5}\-[0-9]{4}\-[0-9]{6}\-[0-9]{6}\-[0-9]{4}\-[0-9]{5}$',
            message='Expense code must be dash separated.'),
        ]
    )

    name = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text='short human readable name for this code'
    )

    root = models.IntegerField(
        blank=True,
        null=True,
        default=None,
        help_text='the root 4 digits of the expense code',
        validators=[
            RegexValidator('^[0-9]{4}$',
            message='Root must be 4 digits.'),
        ]
    )

    created = models.DateTimeField(auto_now_add=True)

    updated = models.DateTimeField(auto_now=True)

    active = models.BooleanField(default = False)

    valid_from = models.DateTimeField(default=datetime.now(), blank=True)

    expiration_date = models.DateTimeField(
        blank=True,
        null=True
    )

    def __str__(self):
        return 'id %s, fullcode %s, name %s' % (str(self.id), self.fullcode, self.name)
