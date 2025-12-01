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
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import models, transaction
from django.conf import settings
from django.core.validators import RegexValidator
from django.db.models.signals import post_save, post_delete
from django.db.models import ProtectedError
from django.dispatch import receiver
from author.decorators import with_author
from natural_keys import NaturalKeyModel
from ifxec import ExpenseCodeFields
from ifxuser.models import Organization


logger = logging.getLogger('__name__')

EXPENSE_CODE_RE = re.compile(r'\d{3}-\d{5}-\d{4}-\d{6}-\d{6}-\d{4}-\d{5}')
EXPENSE_CODE_SANS_OBJECT_RE = re.compile(r'\d{3}-\d{5}-\d{6}-\d{6}-\d{4}-\d{5}')
HUMAN_TIME_FORMAT = '%-m/%d/%Y %-I:%M %p'

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
    billing_record_decimal_charge = Decimal('0.0000')
    transactions = billing_record.transaction_set.all()
    description_lines = []
    for trx in sorted(transactions, key=lambda transaction: transaction.created):
        billing_record_charge += trx.charge
        if trx.decimal_charge is not None:
            billing_record_decimal_charge += trx.decimal_charge
        description_lines.append(trx.description)
    billing_record.charge = billing_record_charge
    billing_record.decimal_charge = billing_record_decimal_charge
    billing_record.description = '\n'.join(description_lines)
    post_save.disconnect(billing_record_post_save, sender=BillingRecord)
    billing_record.save()
    post_save.connect(billing_record_post_save, sender=BillingRecord)


class Facility(NaturalKeyModel):
    '''
    Facility, roughly equivalent to an application
    '''
    class Meta:
        db_table = 'facility'
        verbose_name_plural = 'facilities'
        constraints = [
            models.UniqueConstraint(
                fields=('name',),
                name='facility_natural_key',
            )
        ]

    ifxfac = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        default=None,
        help_text='IFXFAC',
    )

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
    object_code = models.CharField(
        help_text='Object code for this facility',
        max_length=4,
        default='8250'
    )
    billing_record_template = models.CharField(
        max_length=100,
        null=False,
        blank=True,
        default='billing_record_summary_base.html',
        help_text='template for billing record summary which gets emailed to lab admins'
    )
    billing_record_calculator = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text='The name of the class that selects product usages and creates billing records using the calculator class'
    )
    def __str__(self):
        return str(self.name)


class FacilityCodes(NaturalKeyModel):
    '''
    Credit codes for facilities along with the corresponding debit object code
    '''
    class Meta:
        db_table = 'facility_codes'
        verbose_name_plural = 'facility codes'

    facility = models.ForeignKey(
        Facility,
        on_delete=models.CASCADE
    )
    credit_code = models.CharField(
        max_length=50,
        help_text='Credit code to receive funds from billing for product usages.',
    )
    debit_object_code_category = models.CharField(
        choices=(
            ('Laboratory Consumables', 'Laboratory Consumables'),
            ('Technical Services', 'Technical Services'),
            ('Animal Per Diem Charges', 'Animal Per Diem Charges'),
        ),
        max_length=100,
        default='Technical Services',
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        help_text='Organization responsible for the account.',
        blank=True,
        null=True,
    )


class Account(NaturalKeyModel):
    """
    Model for accounts, including both expense codes and POs
    """
    class Meta:
        db_table = "account"
        unique_together = ('code', 'organization')

    ifxacct = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        default=None,
        help_text='IFXACCT',
    )

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
        active_str = 'active' if self.active else 'inactive'
        return f'{self.code} ({self.name}) an {active_str} {self.account_type}'

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
            self.slug = f'PO {self.code} ({self.organization.name})'
        super().save(*args, **kwargs)

    @property
    def object_code(self):
        '''
        Return the object code for this account
        '''
        if self.account_type == 'PO':
            return None
        return ExpenseCodeFields.get_object_code(self.code)

    def replaceObjectCode(self, object_code):
        '''
        Return a string with the object code replaced
        '''
        ECFIELDS = ExpenseCodeFields()
        return ECFIELDS.replace_field(self.code, ECFIELDS.OBJECT_CODE, object_code)

    def user_has_authorization(self, user, product=None, date=None):
        '''
        Check if a user has an authorization for this account.
        If product is provided, check if the user has an authorization for the product or product parent or general authorization for the account.
        If date is provided, check if the account is valid on that date.
        '''
        if date:
            if self.expiration_date and self.expiration_date < date:
                return False
            if self.valid_from > date:
                return False

        if self.useraccount_set.filter(user=user, is_valid=True).exists():
            return True

        if product:
            return self.userproductaccount_set.filter(user=user, is_valid=True, product=product).exists() or \
                (product.parent and self.userproductaccount_set.filter(user=user, is_valid=True, product=product.parent).exists())

        return False


class UserAccount(NaturalKeyModel):
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


class Product(NaturalKeyModel):
    '''
    General name of product and product number.  Helium dewar,  ELYRA microscope, Lustre disk, Promethion sequencing could
    all be Products.  Rate sets are associated with products.  Actual usage of a product is a ProductUsage
    '''
    class Meta:
        db_table = 'product'
        constraints = [
            models.UniqueConstraint(
                fields=('product_number',),
                name='product_natural_key',
            )
        ]

    product_number = models.CharField(
        max_length=14,
        null=False,
        blank=False,
        default=None,
        unique=True,
        help_text='Product number of the form IFXP0000000000'
    )
    product_name = models.CharField(
        max_length=100,
        null=False,
        blank=False,
        default=None,
        unique=True,
        help_text='Name of the product'
    )
    product_description = models.CharField(
        max_length=4000,
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
    billable = models.BooleanField(default=True)
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        help_text='Parent product for this product'
    )
    product_category = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )
    object_code_category = models.CharField(
        choices=(
            ('Laboratory Consumables', 'Laboratory Consumables'),
            ('Technical Services', 'Technical Services'),
            ('Animal Per Diem Charges', 'Animal Per Diem Charges'),
        ),
        max_length=100,
        blank=True,
        null=True,
        default='Technical Services',
    )
    product_organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        help_text='Organization responsible for the account.',
        blank=True,
        null=True,
    )
    is_active = models.BooleanField(
        default=True,
        help_text='Is this product currently active?'
    )

    def is_billable(self):
        '''
        Return True if this product is billable or has a billable parent
        '''
        if self.billable:
            return True
        if self.parent:
            return self.parent.is_billable()
        return False

    def get_active_rates(self):
        '''
        Returns a queryset of the currently active rates.
        If self has no rates, but is billable, parent will be checked.
        If not billable, None will be returned.
        If billable, but no active rates can be found, an exception is thrown.
        '''
        if not self.billable:
            return None
        rates = self.rate_set.filter(is_active=True)
        if rates:
            return rates
        else:
            if self.parent:
                rates = self.parent.get_active_rates()
                if rates:
                    return rates
        raise Exception(f'No active rates for billable product {self}')

    def __str__(self):
        parent_str = ''
        if self.parent:
            parent_str = f' a {self.parent.product_name}'
        return f'{self.product_name}{parent_str} ({self.product_number})'


class Rate(NaturalKeyModel):
    '''
    Rates for chargeable products
    '''
    class Meta:
        db_table = 'rate'
        unique_together = ('product', 'name', 'version')
        ordering = ('sort_order', '-version')

    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    name = models.CharField(
        max_length=50,
        null=False,
        blank=False,
        default=None,
        help_text='Name for this rate'
    )
    description = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text='Description of the rate',
    )
    price = models.IntegerField(
        null=False,
        blank=False,
        default=0,
        help_text='Price in pennies'
    )
    decimal_price = models.DecimalField(
        null=True,
        blank=True,
        max_digits=19,
        decimal_places=4,
        help_text='Price in dollars and cents'
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
    version = models.IntegerField(
        null=False,
        blank=False,
        default=1,
        help_text='Version of the rate'
    )
    sort_order = models.IntegerField(
        null=False,
        blank=False,
        default=1,
        help_text='Sort order for display purposes'
    )
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        is_active_str = 'Active' if self.is_active else 'Inactive'
        units_str = 'ea' if self.units == 'ea' else f'per {self.units}'
        dollar_str = ''
        price_str = ''
        if self.decimal_price:
            dollar_str = '$' if self.decimal_price > Decimal('0') else '-$'
            # pylint: disable=no-member
            price_str = f'{abs(self.decimal_price.quantize(Decimal("0.00")))}'


        # pylint: disable=no-member
        return f'{is_active_str} rate {self.name} of {dollar_str}{price_str} {units_str}'


class OrganizationRate(NaturalKeyModel):
    '''
    Rate to be used for a particular organization
    '''
    class Meta:
        db_table = 'organization_rate'

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        help_text='The organization that gets the rate'
    )
    rate = models.ForeignKey(
        Rate,
        on_delete=models.CASCADE,
        help_text='The rate the organization gets'
    )
    start_date = models.DateField(
        help_text='Start time that this rate applies'
    )
    end_date = models.DateField(
        help_text='Time this rate stops applying',
        blank=True,
        null=True
    )


class UserProductAccount(NaturalKeyModel):
    '''
    Provide accounts specific for a particular product
    '''
    class Meta:
        db_table = 'user_product_account'
        constraints = [
            models.UniqueConstraint(
                fields=('account', 'user', 'product'),
                name='user_product_account_natural_key',
            )
        ]

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
    logged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        help_text='User that logged the usage (may be different than user)',
        on_delete=models.PROTECT,
        related_name='product_usage_logger'
    )
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
    decimal_quantity = models.DecimalField(
        max_digits=19,
        decimal_places=4,
        null=True,
        blank=True,
        help_text='Decimal quantity of the Product.  Intended to replace the quantity field.'
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
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        help_text='Organization responsible for the account.'
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
            # pylint: disable=no-member
            self.month = self.start_date.month
        if not self.year:
            # pylint: disable=no-member
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

    # pylint: disable=too-many-arguments
    # pylint: disable=too-many-locals
    @classmethod
    def createBillingRecord(
        cls,
        account,
        decimal_charge,
        description,
        year,
        month,
        rate_obj,
        author,
        rate_description=None,
        product_usage=None,
        percent=100,
        initial_state='PENDING_LAB_APPROVAL',
        transaction_description=None,
        transaction_author=None
    ):
        '''
        Create a billing record with a single transaction and initial state
        If txn_description is not set, description will be used
        Percent defaults to 100
        If initial_state is not set, PENDING_LAB_APPROVAL is used
        If transaction_author is not set, author is used
        '''
        with transaction.atomic():

            # Make the billing record
            br_data = {
                'account': account,
                'decimal_charge': decimal_charge,
                'description': description,
                'year': year,
                'month': month,
                'rate_obj': rate_obj,
                'percent': percent,
                'author': author,
            }

            if rate_description:
                br_data['rate'] = rate_description
            else:
                br_data['rate'] = str(rate_obj)

            if product_usage:
                br_data['product_usage'] = product_usage

            br = cls.objects.create(**br_data)

            # Make the transaction
            txn_data = {
                'billing_record': br,
                'decimal_charge': decimal_charge,
                'rate': rate_description if rate_description else str(rate_obj),
            }
            txn_data['description'] = transaction_description if transaction_description else description
            txn_data['author'] = transaction_author if transaction_author else author
            Transaction.objects.create(**txn_data)

            # Set the state
            br.setState(initial_state, author.username)

            return br

    product_usage = models.ForeignKey(ProductUsage, on_delete=models.PROTECT, null=True)
    account = models.ForeignKey(Account, on_delete=models.CASCADE)
    charge = models.IntegerField(
        null=False,
        blank=False,
        default=0,
        help_text='Sum of charge records in pennies'
    )
    decimal_charge = models.DecimalField(
        null=True,
        blank=True,
        max_digits=19,
        decimal_places=4,
        help_text='Decimal version of the charge in dollars and cents.  Intended to replace "charge" field.'
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
    product_usage_link_text = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text='Display text for link to associated ProductUsage',
    )
    product_usage_url = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text='URL link for product usage display.  Should be a full URL so that it works in both facility applications and fiine',
    )
    rate_obj = models.ForeignKey(
        Rate,
        on_delete=models.PROTECT,
        help_text='The rate used to calculate this charge',
        null=True,
    )
    decimal_quantity = models.DecimalField(
        max_digits=19,
        decimal_places=4,
        null=True,
        blank=True,
        help_text='Decimal quantity of the Product used for this billing record'
    )
    start_date = models.DateTimeField(
        help_text='Start date for time span billed.',
        null=True,
        blank=True,
    )
    end_date = models.DateTimeField(
        help_text='End date for the time span billed.',
        null=True,
        blank=True,
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
            raise Exception(f'User {user} cannot approve this billing record.')

    def delete(self):
        """
        Prevent delete of BillingRecord
        """
        if self.current_state and self.current_state not in ['INIT', 'PENDING_LAB_APPROVAL', 'LAB_APPROVED']:
            raise ProtectedError('Billing Records can not be deleted.', self)

        super().delete()


    def addTransaction(self, charge, rate, description, author):
        '''
        Add a transaction to this billing record
        '''
        txn = Transaction.objects.create(billing_record=self, charge=charge, rate=rate, description=description, author=author)
        return txn

    def __str__(self):
        if self.decimal_charge:
            # pylint: disable=no-member
            dollar_charge = self.decimal_charge.quantize(Decimal('.01'))
        else:
            dollar_charge = Decimal(self.charge / 100).quantize(Decimal('1.00'))
        desc = f'Charge of ${dollar_charge} against {self.account} for the use of {self.product_usage.product} by {self.product_usage.product_user.full_name}'
        local_start = timezone.localtime(self.product_usage.start_date).strftime(HUMAN_TIME_FORMAT)
        if self.product_usage.end_date:
            desc += f' from {local_start} to {timezone.localtime(self.product_usage.end_date).strftime(HUMAN_TIME_FORMAT)}'
        else: # just start time
            desc += f' on {local_start}'
        return desc


@receiver(post_save, sender=BillingRecord)
def billing_record_post_save(sender, instance, **kwargs):
    """
    Add description to BillingRecord if null, reset charge on billing record
    """
    reset_billing_record_charge(instance)


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
    decimal_charge = models.DecimalField(
        null=True,
        blank=True,
        max_digits=19,
        decimal_places=4,
        help_text='Decimal version of charge.  Intended to replace "charge" field.'
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
