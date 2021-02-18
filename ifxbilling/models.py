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
from django.utils import timezone
from django.db import models
from django.conf import settings
from django.core.validators import RegexValidator
from django.db.models.signals import post_save
from django.dispatch import receiver
from author.decorators import with_author
from ifxuser.models import Organization


logger = logging.getLogger('__name__')


class Account(models.Model):
    """
    Model for accounts, including both expense codes and POs
    """
    class Meta:
        db_table = "account"
        unique_together = ('code', 'organization')

    code = models.CharField(
        max_length=50,
        blank=False,
        null=False,
        default=None,
        help_text='Account code (e.g. expense code or PO number)',
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,  # Organizations are not deleted during sync.  Organizations with accounts should not be deleted.
        help_text='Organization responsible for the account.'
    )
    account_type = models.CharField(
        max_length=20,
        blank=False,
        null=False,
        default='Expense Code',
        choices=(
            ('Expense Code', 'Expense Code'),
            ('PO', 'PO'),
        ),
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
            RegexValidator('^[0-9]{5}$',
            message='Root must be 5 digits.'),
        ]
    )
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    active = models.BooleanField(default=False)
    valid_from = models.DateTimeField(default=timezone.now(), blank=True)
    expiration_date = models.DateTimeField(
        blank=True,
        null=True
    )
    slug = models.CharField(max_length=100, unique=True, help_text='EC or PO + institution')

    def __str__(self):
        return '%s (%s) an %s %s' % (self.code, self.name, 'active' if self.active else 'inactive', self.account_type)

    def save(self, *args, **kwargs):
        '''
        Set the slug
        '''
        if self.account_type == 'Expense Code':
            self.slug = self.code
        else:
            self.slug = 'PO %s (%s)' % (self.code, self.organization.name)
        super().save(*args, **kwargs)

class Product(models.Model):
    '''
    General name of product and product number.  Helium dewar,  ELYRA microscope, Lustre disk, Promethion sequencing could
    all be Products.  Rate sets are associated with products.  Actual usage of a product is a ProductUsage
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
    billing_calculator = models.CharField(
        max_length=100,
        null=False,
        blank=False,
        default='ifxbilling.calculator.BasicBillingCalculator',
        help_text='Class to use for calculating charges for this product'
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
    units = models.CharField(
        max_length=100,
        null=False,
        blank=False,
        default=None,
        help_text='Unit for price (e.g. ea)'
    )
    is_active = models.BooleanField(
        default=True,
        help_text='Is this rate currently active?'
    )


class ProductUsage(models.Model):
    '''
    Usage of a product that can be billed for.
    Base class that should be subclassed in the lab application,
    or, if it's already a subclass, a OneToOne relationship can be set.
    '''
    class Meta:
        db_table = 'product_usage'

    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    product_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    year = models.IntegerField(
        null=False,
        blank=False,
        help_text='Calendar year in which the usage occurs',
        default=timezone.now().year
    )
    month = models.IntegerField(
        null=False,
        blank=False,
        help_text='Month in which the usage occurs',
        default=timezone.now().month
    )
    quantity = models.IntegerField(
        null=False,
        blank=False,
        default=1,
        help_text='Quantity of product'
    )
    units = models.CharField(
        max_length=100,
        null=False,
        blank=False,
        default='ea',
        help_text='Units of quantity'
    )
    created = models.DateTimeField(auto_now_add=True)


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
    product_usage = models.ForeignKey(ProductUsage, on_delete=models.PROTECT)
    charge = models.IntegerField(
        null=False,
        blank=False,
        default=0,
        help_text='Sum of charge records in pennies'
    )
    description = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        help_text='Description of the billing record.'
    )
    year = models.IntegerField(
        null=False,
        blank=False,
        help_text='Calendar year to which the billing applies',
        default=timezone.now().year
    )
    month = models.IntegerField(
        null=False,
        blank=False,
        help_text='Month in which the billing applies',
        default=timezone.now().month
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
