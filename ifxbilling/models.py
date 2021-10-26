# -*- coding: utf-8 -*-

'''
Billing model for ifx applications

Created on  2020-05-12

@author: Meghan Correa <mportermahoney@g.harvard.edu>
@copyright: 2020 The Presidents and Fellows of Harvard College.
All rights reserved.
@license: GPL v2.0
'''
import re
import logging
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import models
from django.conf import settings
from django.core.validators import RegexValidator
from django.db.models.signals import post_save, post_delete
from django.db.models import ProtectedError
from django.dispatch import receiver
from author.decorators import with_author
from ifxuser.models import Organization


logger = logging.getLogger('__name__')

EXPENSE_CODE_RE = re.compile(r'\d{3}-\d{5}-\d{4}-\d{6}-\d{6}-\d{4}-\d{5}')
EXPENSE_CODE_SANS_OBJECT_RE = re.compile(r'\d{3}-\d{5}-\d{6}-\d{6}-\d{4}-\d{5}')

def thisDate():
    '''
    Callable for setting date
    '''
    return timezone.now().date()

def thisYear():
    '''
    Callable for setting default year
    '''
    return timezone.now().year


def thisMonth():
    '''
    Callable for setting default month
    '''
    return timezone.now().month


def reset_billing_record_charge(billing_record):
    '''
    For a given billing record, update the charge based on the billing record
    transactions
    '''
    billing_record_charge = 0
    transactions = billing_record.transaction_set.all()
    for trx in sorted(transactions, key=lambda transaction: transaction.created):
        billing_record_charge += trx.charge
    billing_record.charge = billing_record_charge
    billing_record.description = str(billing_record)
    billing_record.save()


class Facility(models.Model):
    '''
    Facility, roughly equivalent to an application
    '''
    class Meta:
        db_table = 'facility'
        verbose_name_plural = 'facilities'

    name = models.CharField(
        max_length=200,
        unique=True,
        help_text='Name of the facility (e.g. Helium Recovery Service)'
    )
    application_username = models.CharField(
        max_length=50,
        help_text='Username that permits logging in to the facility application (e.g. nice)'
    )
    credit_code = models.CharField(
        max_length=50,
        help_text='Credit code to receive funds from billing for product usages.',
    )
    invoice_prefix = models.CharField(
        max_length=50,
        help_text='Prefix used in the invoice names for the facility.',
    )
    def __str__(self):
        return self.name

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
    root = models.CharField(
        max_length=5,
        blank=True,
        null=True,
        default=None,
        help_text='If it is an expense code, the last 5 digits',
        validators=[
            RegexValidator('^[0-9]{5}$',
            message='Root must be 5 digits.'),
        ]
    )
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    active = models.BooleanField(default=False)
    valid_from = models.DateField(default=thisDate, blank=True)
    expiration_date = models.DateField(
        blank=True,
        null=True
    )
    slug = models.CharField(max_length=100, unique=True, help_text='EC or PO + institution')
    funding_category = models.CharField(
        blank=True,
        null=True,
        max_length=100
    )

    def __str__(self):
        return '%s (%s) an %s %s' % (self.code, self.name, 'active' if self.active else 'inactive', self.account_type)

    def save(self, *args, **kwargs):
        '''
        Set the slug
        '''
        if self.account_type == 'Expense Code':
            if self.name:
                self.slug = f'{self.code} ({self.name})'
            else:
                self.slug = self.code
        else:
            self.slug = 'PO %s (%s)' % (self.code, self.organization.name)
        super().save(*args, **kwargs)


class UserAccount(models.Model):
    '''
    Provide default accounts for a user
    '''
    class Meta:
        db_table = 'user_account'
        unique_together = ('account', 'user')

    account = models.ForeignKey(
        Account,
        on_delete=models.CASCADE
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )
    is_valid = models.BooleanField(
        null=False,
        blank=False,
        default=True
    )
    def __str__(self):
        valid_str = 'Validated' if self.is_valid else 'Invalid'
        return f'{valid_str} authorization of {self.account} for {self.user}'


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
        unique=True,
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
        blank=True,
        default='ifxbilling.calculator.BasicBillingCalculator',
        help_text='Class to use for calculating charges for this product'
    )
    facility = models.ForeignKey(
        Facility,
        on_delete=models.CASCADE
    )
    reporting_group = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    def __str__(self):
        return f'{self.product_name} ({self.product_number})'


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
    max_qty = models.IntegerField(
        null=True,
        blank=True,
        help_text='Price applys to this number or units or less'
    )
    is_active = models.BooleanField(
        default=True,
        help_text='Is this rate currently active?'
    )


class UserProductAccount(models.Model):
    '''
    Provide accounts specific for a particular product
    '''
    class Meta:
        db_table = 'user_product_account'

    account = models.ForeignKey(
        Account,
        on_delete=models.CASCADE
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE
    )
    percent = models.IntegerField(
        help_text='Percent of charge that should be applied to this account for the user product',
        null=False,
        blank=False,
        default=100,
    )
    is_valid = models.BooleanField(
        null=False,
        blank=False,
        default=True
    )


class AbstractProductUsage(models.Model):
    '''
    Abstract base class for any Product usage representing
    a usage of a product that can be billed for.
    '''
    class Meta:
        abstract = True
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    product_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    year = models.IntegerField(
        null=False,
        blank=False,
        help_text='Calendar year in which the usage occurs',
    )
    month = models.IntegerField(
        null=False,
        blank=False,
        help_text='Month in which the usage occurs',
    )
    quantity = models.BigIntegerField(
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
    description = models.CharField(
        max_length=2000,
        null=True,
        blank=True,
        help_text='Description of usage'
    )
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField(null=True, blank=True)


class ProductUsage(AbstractProductUsage):
    '''
    Concrete subclass of AbstractProductUsage
    '''
    class Meta:
        db_table = 'product_usage'

    def save(self, *args, **kwargs):
        if not self.description:
            self.description = f'{self.quantity} {self.units} of {self.product} for {self.product_user} on {self.start_date}'
        if not self.month:
            self.month = self.start_date.month
        if not self.year:
            self.year = self.start_date.year
        super().save(*args, **kwargs)

    def __str__(self):
        return self.description




@with_author
class BillingRecord(models.Model):
    '''
    Summary charge for a thing to an account.
    Combination of transactions should add up to the charge on
    this record.
    This will eventually be a line item in an invoice.
    '''

    class Meta:
        db_table = 'billing_record'

    product_usage = models.ForeignKey(ProductUsage, on_delete=models.PROTECT)
    account = models.ForeignKey(Account, on_delete=models.CASCADE)
    charge = models.IntegerField(
        null=False,
        blank=False,
        default=0,
        help_text='Sum of charge records in pennies'
    )
    percent = models.IntegerField(
        help_text='Percent of total product usage cost that this charge represents, defaults to 100%',
        null=False,
        blank=False,
        default=100,
    )
    description = models.CharField(
        max_length=1000,
        blank=True,
        null=True,
        default='',
        help_text='Description of the billing record.'
    )
    year = models.IntegerField(
        null=False,
        blank=False,
        help_text='Calendar year to which the billing applies',
        default=thisYear
    )
    month = models.IntegerField(
        null=False,
        blank=False,
        help_text='Month in which the billing applies',
        default=thisMonth
    )
    current_state = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text='Name of the most recent BillingRecordState'
    )
    rate = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text='Text description of the rate used to calculate the charge'
    )
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    def setState(self, name, user, approvers=None, comment=None):
        '''
        Creates a billing record state and sets the current_state value
        '''
        logger.info(f'Setting state {name} for billing record {self} with approvers {approvers}')
        user_obj = get_user_model().objects.get(username=user)
        rs = BillingRecordState(name=name, user=user_obj, billing_record=self, comment=comment)
        rs.save()
        # Set approvers if needed
        if approvers is not None:
            if not isinstance(approvers, list):
                approvers = [approvers]
            for approver in approvers:
                rs.approvers.add(approver)

        self.current_state = name
        self.save()

    def getCurrentBillingRecordState(self):
        """
        Returns the most recent BillingRecordState
        """
        rs = BillingRecordState.objects.filter(billing_record=self, name=self.current_state).order_by('-created')[0]
        return rs

    def canApprove(self, user):
        """
        Return true if the user can provide approval for the current billing
        record state.

        Default behavior is to match the latest request state approver, or be an admin
        """
        rs = self.getCurrentBillingRecordState()
        # Is user SuperUser, or an explicit approver on the request
        return user.is_superuser or rs.approvers.filter(ifxid=user.ifxid).exists()

    def approve(self, user, newstate, approvers=None, comment=None):
        """
        If the user can approve this, set state to approved.
        """
        if self.canApprove(user):
            self.setState(newstate, user, approvers, comment)
        else:
            raise Exception('User %s cannot approve this billing record.' % str(user))

    def delete(self):
        """
        Prevent delete of BillingRecord
        """
        if self.current_state and self.current_state not in ['INIT', 'PENDING_LAB_APPROVAL']:
            raise ProtectedError('Billing Records can not be deleted.', self)

    def __str__(self):
        return f'Charge of {self.charge} against {self.account} for the use of {self.product_usage} on {self.month}/{self.year}'


@receiver(post_save, sender=BillingRecord)
def billing_record_post_save(sender, instance, **kwargs):
    """
    Add description to BillingRecord if null, reset charge on billing record
    """
    post_save.disconnect(billing_record_post_save, sender=BillingRecord)
    reset_billing_record_charge(instance)
    post_save.connect(billing_record_post_save, sender=BillingRecord)



class BillingRecordState(models.Model):
    """
    Various states of a particular billing record.  Is used to keep a history of state changes for the billing record.
    """
    class Meta:
        db_table = 'billing_record_state'
        ordering = ('-created',)

    name = models.CharField(
        max_length=100,
        blank=False,
        null=False,
        default=None,
        help_text='Name of the state'
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=False,
        null=False,
        default=None,
        help_text='User that inserted the state',
        on_delete=models.CASCADE
    )

    billing_record = models.ForeignKey(
        BillingRecord,
        on_delete=models.CASCADE
    )

    approvers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name='billing_record_state_approvers'
    )

    comment = models.CharField(
        max_length=1000,
        blank=True,
        null=True,
        help_text='Any message associated with the state'
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
        max_length=500,
        blank=False,
        null=False,
        default=None,
        help_text='Reason for this charge.'
    )
    rate = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text='Text description of the rate used to calculate the charge'
    )
    created = models.DateTimeField(auto_now_add=True)


@receiver(post_save, sender=Transaction)
def transaction_post_save(sender, instance, **kwargs):
    """
    Recalculate the BillingRecord charge
    """
    reset_billing_record_charge(instance.billing_record)


@receiver(post_delete, sender=Transaction)
def transaction_post_delete(sender, instance, **kwargs):
    """
    Recalculate the BillingRecord charge
    """
    reset_billing_record_charge(instance.billing_record)


class AccountUser(get_user_model()):
    '''
    Proxy user that supports AccountUserAdmin
    '''
    class Meta:
        '''
        It's a proxy
        '''
        proxy = True

class ProductUsageProcessing(models.Model):
    '''
    Store error messages from product usage processing into billing records
    '''
    class Meta:
        db_table = 'product_usage_processing'
    product_usage = models.ForeignKey(ProductUsage, on_delete=models.CASCADE)
    error_message = models.CharField(
        max_length=2000,
        null=True,
        blank=True,
        help_text='Error message from processing into billing record.'
    )
    resolved = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
