# -*- coding: utf-8 -*-

'''
Billing model for ifx applications

Created on  2020-05-12

@author: Meghan Correa <mportermahoney@g.harvard.edu>
@copyright: 2020 The Presidents and Fellows of Harvard College.
All rights reserved.
@license: GPL v2.0
'''
import logging
from datetime import datetime
from django.db import models
from django.core.validators import RegexValidator
from django.db.models.signals import post_save
from django.dispatch import receiver
from author.decorators import with_author


logger = logging.getLogger('__name__')


class Account(models.Model):
    """
    Model for accounts, including both expense codes and POs
    """
    class Meta:
        db_table = "account"
        unique_together = ('code', 'institution')

    code = models.CharField(
        max_length=50,
        blank=False,
        null=False,
        default=None,
        help_text='Account code (e.g. expense code or PO number)',
    )
    institution = models.CharField(
        max_length=100,
        blank=False,
        null=False,
        default='Harvard',
        help_text='Institution that issues the code'
    )
    account_type = models.CharField(
        max_length=10,
        blank=False,
        null=False,
        default='Expense Code',
        choices=('Expense Code', 'PO'),
        help_text='Expense Code or PO',
    )
    name = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text='Short, human readable name for this code'
    )
    root = models.IntegerField(
        blank=True,
        null=True,
        default=None,
        help_text='If it is an expense code, the last 4 digits',
        validators=[
            RegexValidator('^[0-9]{4}$',
            message='Root must be 4 digits.'),
        ]
    )
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    active = models.BooleanField(default=False)
    valid_from = models.DateTimeField(default=datetime.now(), blank=True)
    expiration_date = models.DateTimeField(
        blank=True,
        null=True
    )
    def __str__(self):
        return '%s (%s) an %s %s' % (self.code, self.name, 'active' if self.active else 'inactive', self.account_type)


class Product(models.Model):
    '''
    Mixin model for anything that can be charged for.
    This is a mixin (and BillingRecord points to product_number as foreign key)
    because things like "DewarRequest" that inherit from Request may be the product
    '''
    class Meta:
        db_table = 'product'

    product_number = models.CharField(
        max_length=14,
        null=False,
        blank=False,
        default=None,
        unique=True,
        help_text='Product number of the form IFXP0000000000'
    )
    product_name = models.CharField(
        max_length=50,
        null=False,
        blank=False,
        default=None,
        help_text='Name of the product'
    )
    product_description = models.CharField(
        max_length=200,
        null=False,
        blank=False,
        default=None,
        help_text='Product description'
    )


class Rate(models.Model):
    '''
    Rates for chargeable products
    '''
    class Meta:
        db_table = 'rate'

    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    name = models.CharField(
        max_length=50,
        null=False,
        blank=False,
        default=None,
        help_text='Name for this rate'
    )
    price = models.IntegerField(
        null=False,
        blank=False,
        default=0,
        help_text='Price in pennies'
    )
    unit = models.CharField(
        null=False,
        blank=False,
        default=None,
        help_text='Unit for price (e.g. ea)'
    )


class BillingRecord(models.Model):
    '''
    Summary charge for a thing to an account.
    Combination of transactions should add up to the charge on
    this record.
    This will eventually be a line item in an invoice.
    '''
    class Meta:
        db_table = 'billing_record'

    account = models.ForeignKey(Account, on_delete=models.PROTECT)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    charge = models.IntegerField(
        null=False,
        blank=False,
        default=0,
        help_text='Sum of charge records in pennies'
    )
    quantity = models.IntegerField(
        null=False,
        blank=False,
        default=1,
        help_text='Quantity of product'
    )
    units = models.CharField(
        null=False,
        blank=False,
        default='ea',
        help_text='Units of quantity'
    )
    description = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        help_text='Description of the billing record.'
    )
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)


@with_author
class Transaction(models.Model):
    '''
    Individual transaction used to compose a BillingRecord
    '''
    class Meta:
        db_table = 'transaction'

    billing_record = models.ForeignKey(BillingRecord, on_delete=models.CASCADE)
    charge = models.IntegerField(
        null=False,
        blank=False,
        default=0,
        help_text='Positive or negative charge in pennies'
    )
    description = models.CharField(
        max_length=200,
        blank=False,
        null=False,
        default=None,
        help_text='Reason for this charge.'
    )
    created = models.DateTimeField(auto_now_add=True)


@receiver(post_save, sender=Transaction)
def transaction_post_save(sender, instance, **kwargs):
    """
    Recalculate the BillingRecord charge
    """
    billing_record_charge = 0
    transactions = instance.billing_record.transactions
    for trx in sorted(transactions, key=lambda transaction: transaction.created):
        billing_record_charge += trx.charge
    instance.billing_record.charge = billing_record_charge
    instance.billing_record.save()
