# -*- coding: utf-8 -*-

'''
Billing calculators

Created on  2020-12-16

@author: Aaron Kitzmiller <akitzmiller@g.harvard.edu>
@copyright: 2020 The Presidents and Fellows of Harvard College.
All rights reserved.
@license: GPL v2.0
'''
import logging
import json
from decimal import Decimal
from importlib import import_module
from django.db import transaction
from django.db.models import Q
from django.conf import settings
from django.utils import timezone
from ifxuser.models import Organization
from ifxbilling.models import OrganizationRate, Rate, BillingRecord, Transaction, BillingRecordState, ProductUsageProcessing, ProductUsage, Product, Facility


logger = logging.getLogger('ifxbilling')
INITIAL_STATE = 'PENDING_LAB_APPROVAL'

def getClassFromName(dotted_path):
    """
    Utility that will return the class object for a fully qualified
    classname
    """
    try:
        module_path, class_name = dotted_path.rsplit('.', 1)
        logging.debug(module_path)
        logging.debug(class_name)
    except ValueError as e:
        msg = f"{dotted_path} doesn't look like a module path"
        raise ImportError(msg) from e

    module = import_module(module_path)

    try:
        return getattr(module, class_name)
    except AttributeError as e:
        msg = f'Module "{module_path}" does not define a "{class_name}" attribute/class'
        raise ImportError(msg) from e


def calculateBillingMonth(month, year, facility, recalculate=False, verbose=False, product_names=None):
    '''
    Calculate a months worth of billing records and return the number of successes and list of error messages
    '''
    successes = 0
    errors = []
    # only billable usages will be billed
    product_usages = ProductUsage.objects.filter(month=month, year=year, product__facility=facility, product__billable=True)

    # Filter by product if needed
    products = []
    if product_names is not None:
        for product_name in product_names:
            try:
                products.append(Product.objects.get(product_name=product_name))
            except Product.DoesNotExist:
                # pylint: disable=raise-missing-from
                raise Exception(f'Cannot filter by {product_name}: Product does not exist.')
        if products:
            product_usages = product_usages.filter(product__in=products)

    calculators = {
        'ifxbilling.calculator.BasicBillingCalculator': BasicBillingCalculator()
    }
    usage_data = {}
    for product_usage in product_usages:
        if BillingRecord.objects.filter(product_usage=product_usage).exists():
            if recalculate:
                BillingRecord.objects.filter(product_usage=product_usage).delete()
            else:
                continue
        try:
            billing_calculator_name = product_usage.product.billing_calculator
            if billing_calculator_name not in calculators:
                billing_calculator_class = getClassFromName(billing_calculator_name)
                calculators[billing_calculator_name] = billing_calculator_class()
            billing_calculator = calculators[billing_calculator_name]
            billing_calculator.createBillingRecordsForUsage(product_usage, usage_data=usage_data)
            successes += 1
        except Exception as e:
            if verbose:
                logger.exception(e)
            errors.append(f'Unable to create billing record for {product_usage}: {e}')
    for class_name, calculator in calculators.items():
        try:
            with transaction.atomic():
                calculator.finalize(month, year, facility, recalculate=False, verbose=False)
        except Exception as e:
            if verbose:
                logger.exception(e)
            errors.append(f'Finalization failed for {class_name}: {e}')
    return (successes, errors)


class BasicBillingCalculator():
    '''
    Looks at ProductUsages for the current month,
    picks up a single active Rate for the product,
    and applies to each usage to create a BillingRecord
    with a Transaction.

    If the recalculate flag is set, existing BillingRecords
    and Transactions will be removed and new ones will be
    created.  Otherwise, ProductUsages with existing
    BillingRecords will be skipped.
    '''
    def getRateDescription(self, rate):
        '''
        Text description of rate for use in txn rate and description.
        Empty string is returned if rate.price or rate.units is None.
        '''
        desc = ''
        if rate.price is not None and rate.units is not None:
            if rate.units == 'ea':
                desc = f'{rate.price} {rate.units}'
            else:
                desc = f'{rate.price} per {rate.units}'
        return desc

    def getRateDescriptionFromTransactions(self, transactions_data):
        '''
        Get the rate description for the BillingRecord from the transactions_data.
        Basically just picking the first one.  If there are no transactions an exception is raised.
        '''
        if not transactions_data:
            raise Exception('No transactions.  Cannot set a rate on the billing record.')
        return transactions_data[0]['rate']

    def calculateCharges(self, product_usage, percent, usage_data=None):
        '''
        Calculates one or more charges that will be used to create transactions
        using a product_usage and an optional usage_data dictionary.

        Returns an array of transaction data dictionaries that will include a
        charge, a user, and a description at least.

        Charges are in pennies so fractions are rounded.
        '''
        product = product_usage.product
        rate = product.rate_set.get(is_active=True)
        if rate.units != product_usage.units:
            raise Exception(f'Units for product usage do not match the active rate for {product}')
        rate_desc = self.getRateDescription(rate)

        transactions_data = []

        percent_str = ''
        if percent < 100:
            percent_str = f'{percent}% of '
        description = f'{percent_str}{product_usage.quantity} {product_usage.units} at {rate_desc}'
        charge = round(rate.price * product_usage.quantity * percent / 100)
        user = product_usage.product_user

        transactions_data.append(
            {
                'charge': charge,
                'description': description,
                'author': user,
                'rate': rate_desc,
            }
        )
        return transactions_data

    def getOrganizationForProductUsage(self, product_usage):
        '''
        Return the Organization associated with a ProductUsage.  This is needed to ensure that the correct Account is used for billing.
        As a default, the user primary_affiliation is returned, but this should probably evolve to a field on ProductUsage
        '''
        return product_usage.product_user.primary_affiliation

    def getAccountPercentagesForProductUsage(self, product_usage):
        '''
        For a given ProductUsage, return an array of account (Account object) and percent that should be used.  This is only called
        by createBillingRecordForUsage if an Account is not supplied.

        UserProductAccount is tested first, followed by UserAccount.  An exception is raised if neither attempt is successful.
        '''
        account_percentages = []
        if not product_usage.product_user:
            raise Exception(f'No product user for {product_usage}')

        # Get the organization associated with the ProductUsage to use for Account selection
        organization = self.getOrganizationForProductUsage(product_usage)
        if not organization:
            raise Exception(f'Unable to get an organization for {product_usage}')

        user_product_accounts = product_usage.product_user.userproductaccount_set.filter(
            product=product_usage.product,
            account__organization=organization,
            account__active=True,
            is_valid=True
        )
        if len(user_product_accounts) > 0:
            # Use them all.  If there is more than one ensure that percents add to 100.
            pct_total = 0
            for user_product_account in user_product_accounts:
                account_percentages.append(
                    {
                        'account': user_product_account.account,
                        'percent': user_product_account.percent,
                    }
                )
                pct_total += user_product_account.percent

            if pct_total != 100:
                raise Exception(f'User product account percents add up to {pct_total} instead of 100')
        else:
            # Only get the first one
            user_account = product_usage.product_user.useraccount_set.filter(
                account__organization=organization,
                account__active=True,
                is_valid=True).first()
            if user_account:
                account_percentages.append(
                    {
                        'account': user_account.account,
                        'percent': 100,
                    }
                )
            else:
                raise Exception(f'Unable to find an active user account record for {product_usage.product_user} with organization {organization.name}')
        if product_usage and account_percentages:
            logger.debug('Account percentages for %s: %s', str(product_usage), str(account_percentages))
        return account_percentages

    def createBillingRecordsForUsage(self, product_usage, account_percentages=None, year=None, month=None, description=None, usage_data=None, recalculate=False):
        '''
        Determine the number of BillingRecords to create for this usage and then creates each one.  If recalculate is True, existing records are removed.
        Throws an Exception if a BillingRecord already exists for the product_usage
        account_percentages should be a list of dicts consisting of an Account object and a numerical percent, a'la
        [
            {
                'account': AccountObj,
                'percent': 100
            }
        ]
        List of new BillingRecords is returned.
        '''
        brs = []
        if BillingRecord.objects.filter(product_usage=product_usage).exists():
            if recalculate:
                BillingRecord.objects.filter(product_usage=product_usage).delete()
            else:
                msg = f'Billing record already exists for usage {product_usage}'
                raise Exception(msg)
        try: # errors are captured in the product_usage_processing table
            with transaction.atomic():
                if not account_percentages:
                    account_percentages = self.getAccountPercentagesForProductUsage(product_usage)
                logger.debug('Creating %d billing records for product_usage %s', len(account_percentages), str(product_usage))
                for account_percentage in account_percentages:
                    account = account_percentage['account']
                    percent = account_percentage['percent']
                    br = self.createBillingRecordForUsage(product_usage, account, percent, year, month, description, usage_data)
                    if br: # can be none
                        brs.append(br)
                # processing complete update any product_usage_processing as resolved
                self.update_product_usage_processing(product_usage, {'resolved': True}, update_only_unresolved=False)
        except Exception as e:
            message = str(e)[-2000:] # limit to db column max_length
            # check for previous processing errors, only keep the latest
            if not self.update_product_usage_processing(product_usage, {'error_message': message, 'resolved': False}):
                # nothing to update, create new
                product_usage_processing = ProductUsageProcessing(
                    product_usage=product_usage,
                    error_message=message
                )
                product_usage_processing.save()
            raise e
        return brs

    def createBillingRecordForUsage(self, product_usage, account, percent, year=None, month=None, description=None, usage_data=None):
        '''
        For the given ProductUsage, Account and the optional usage_data dictionary,
        calculate charge(s) and create a billing record.

        If year or month are not specified, the values will be obtained from the ProductUsage.

        If account is not specified, then getAccountForProductUsage will be called.  If account
        is specified, then it will override any data in product_usage.

        '''
        if not year:
            year = product_usage.year
        if not month:
            month = product_usage.month
        transactions_data = self.calculateCharges(product_usage, percent, usage_data)
        if not transactions_data:
            return None
        rate = self.getRateDescriptionFromTransactions(transactions_data)
        return self.createBillingRecord(product_usage, account, year, month, transactions_data, percent, rate, description)

    def update_product_usage_processing(self, product_usage, attrs, update_only_unresolved=False):
        '''
        Update PUP
        '''
        try:
            # if exists then update
            crit = {'product_usage': product_usage}
            if update_only_unresolved: # only return unresolved
                crit['resolved'] = False
            processing = ProductUsageProcessing.objects.get(**crit)
            logger.info(f'Found previous ProductUsageProcessing {processing.id} will update it with {json.dumps(attrs)}.')
            for k, v in attrs.items():
                setattr(processing, k, v)
            processing.save()
            return True
        except ProductUsageProcessing.DoesNotExist:
            # nothing to update
            return False

    def createBillingRecord(self, product_usage, account, year, month, transactions_data, percent, rate, description=None):
        '''
        Create (and save) a BillingRecord and related Transactions.
        If an existing BillingRecord has the same product_usage and account an Exception will be thrown.
        '''
        billing_record = None
        try:
            BillingRecord.objects.get(product_usage=product_usage, account=account, percent=percent)
            raise Exception(f'Billing record for product usage {product_usage} and account {account} already exists.')
        except BillingRecord.DoesNotExist:
            pass

        for transaction_data in transactions_data:
            if not billing_record:
                billing_record = BillingRecord(
                    product_usage=product_usage,
                    account=account,
                    year=year,
                    month=month,
                    description=description,
                    current_state=INITIAL_STATE,
                    percent=percent,
                    rate=rate,
                )
                billing_record.save()
                billing_record_state = BillingRecordState(
                    billing_record=billing_record,
                    name=INITIAL_STATE,
                    user=product_usage.product_user,
                    comment='created by billing calculator'
                )
                billing_record_state.save()
            trxn = Transaction(
                billing_record=billing_record,
                charge=transaction_data['charge'],
                description=transaction_data['description'],
                author=transaction_data['author'],
                rate=transaction_data['rate'],
            )
            trxn.save()

        return billing_record

    def finalize(self, month, year, facility, recalculate=False, verbose=False):
        '''
        Perform any final cleanup functions
        '''


class NewBillingCalculator():
    '''
    New billing calculator class that iterates over organizations to
    do calculations so that organization level adjustments can be made.

    The only method that needs to remain the same in a subclass is
    :func:`~ifxbilling.calculator.NewBillingCalculator.calculate_billing_month` as this
    is the method that will be called by the `calculateBillingMonth` management command.
    Even the "process by organization" loop is not necessary as long as the return dict
    of the function keyed by organization name and has the same basic contents.

    It is also strongly encouraged to carry over the :func:`~ifxbilling.calculator.NewBillingCalculator.create_billing_record`
    function as it enforces the creation of a :class:`~ifxbilling.models.BillingRecord` via a
    combination of :class:`~ifxbilling.models.Transaction` objects.
    '''
    QUIET = 0
    CHATTY = 1
    LOUD = 2

    # if subclassing set the facility name constant in your class
    FACILITY_NAME = None

    PUP_MESSAGES = {}

    STANDARD_QUANTIZE = Decimal('0.0000')
    TWO_DIGIT_QUANTIZE = Decimal('0.00')


    def __init__(self):
        self.set_facility()
        self.verbosity = self.QUIET

    def is_flat_rate(self, rate):
        '''
        Returns True if the rate is a flat rate
        '''
        return False

    def get_decimal_charge_str(self, decimal_charge):
        '''
        String with dollar sign, two digits, and proper negative
        '''
        sign_str = ''
        if decimal_charge < 0:
            sign_str = '-'
        two_digits = abs(decimal_charge.quantize(self.TWO_DIGIT_QUANTIZE))
        return f'{sign_str}${two_digits}'

    def set_facility(self):
        '''
        return the facility name.  This function is needed if the baseclass is
        used for billing record calculation.  For subclasses self.FACILITY_NAME
        should be set as a constant in the class.
        '''
        facility_name = self.FACILITY_NAME
        if facility_name:
            try:
                self.facility = Facility.objects.get(name=facility_name)
            except Facility.DoesNotExist:
                # pylint: disable=raise-missing-from
                raise Exception(f'Facility name {facility_name} cannot be found')
        else:
            facilities = Facility.objects.all()
            if len(facilities) == 1:
                self.facility = facilities[0]
            else:
                raise Exception('Default facility can only be set if there is exactly 1 Facility record.')


    def calculate_billing_month(self, year, month, organizations=None, recalculate=False, verbosity=0):
        '''
        Calculate a month of billing for the given year and month

        Returns a dict keyed by organization name that includes a count of successfully processed
        product usages along with a list of error messages for each one that failed.

        :param year: Year that will be assigned to :class:`~ifxbilling.models.BillingRecord` objects
        :type year: int

        :param month: Month that will be assigned to :class:`~ifxbilling.models.BillingRecord` objects
        :type month: int

        :param organizations: List of specific organizations to process.  If not set, all will be processed.
        :type organizations: list, optional

        :param recalculate: If set to True, will delete existing :class:`~ifxbilling.models.BillingRecord` objects
        :type recalculate: bool, optional

        :param verbosity: Determines the amount of error reporting.  Can be set to self.QUIET (no logger output),
            self.CHATTY (use logger.error for errors), or self.LOUD (use logger.exception for errors).  Defaults to QUIET.
        :type verbosity: int, optional

        :return: dict keyed by organization name.  Value is a dict of "successes" (a list of :class:`~ifxbilling.models.BillingRecord` objects) and
            "errors" (a list of error messages)
        :rtype: dict
        '''
        self.verbosity = verbosity

        organizations_to_process = organizations
        if not organizations_to_process:
            organizations_to_process = Organization.objects.all()

        results = {}
        for organization in organizations_to_process:
            result = self.generate_billing_records_for_organization(year, month, organization, recalculate)
            results[organization.name] = result

        return results

    def generate_billing_records_for_organization(self, year, month, organization, recalculate, **kwargs):
        '''
        Create and save all of the :class:`~ifxbilling.models.BillingRecord` objects for the month for an organization.

        Iterates over :class:`~ifxbilling.models.ProductUsage` objects obtained with get_product_usages_for_organization() and calls
        generate_billing_records_for_usage().  Exceptions are captured in each loop iteration
        though mainly for reporting purposes (:class:`~ifxbilling.models.ProductUsageProcessing` will store errors except for
        attempts to process :class:`~ifxbilling.models.ProductUsage` objects with existing :class:`~ifxbilling.models.BillingRecord` objects)

        Returns a dict that includes a list of successfully created :class:`~ifxbilling.models.BillingRecord` objects
        ("successes") and a list of error messages ("errors")

        :param year: Year that will be assigned to :class:`~ifxbilling.models.BillingRecord` objects
        :type year: int

        :param month: Month that will be assigned to :class:`~ifxbilling.models.BillingRecord` objects
        :type month: int

        :param organization: The organization whose :class:`~ifxbilling.models.BillingRecord` objects should be generated
        :type organization: list

        :param recalculate: If True, will delete existing :class:`~ifxbilling.models.BillingRecord` objects if possible
        :type recalculate: bool

        :return: A dictionary with keys "successes" (a list of successfully created :class:`~ifxbilling.models.BillingRecord` objects) and
            "errors" (a list of error messages)
        :rtype: dict
        '''
        successes = []
        errors = []

        try:
            product_usages = self.get_product_usages_for_organization(year, month, organization, **kwargs)
        except Exception as e:
            logger.error(e)
            errors.append(str(e))
            return {
                'successes': successes,
                'errors': errors,
            }
        for product_usage in product_usages:
            try:
                if BillingRecord.objects.filter(product_usage=product_usage).exists():
                    if recalculate:
                        BillingRecord.objects.filter(product_usage=product_usage).delete()
                    else:
                        msg = f'Billing record already exists for usage {product_usage}'
                        raise Exception(msg)
                successes.extend(
                    self.generate_billing_records_for_usage(year, month, product_usage, **kwargs)
                )
            except Exception as e:
                errors.append(str(e))
                if self.verbosity == self.CHATTY:
                    logger.error(e)
                if self.verbosity == self.LOUD:
                    logger.exception(e)

        return {
            'successes': successes,
            'errors': errors,
        }

    def get_product_usages_for_organization(self, year, month, organization, **kwargs):
        '''
        Get a list of :class:`~ifxbilling.models.ProductUsage` object to be converted to :class:`~ifxbilling.models.BillingRecord`
        objects for the given :class:`~ifxuser.models.Organization`.  Base class just gets the
        :class:`~ifxbilling.models.ProductUsage` with matching organization, year, and month.

        :param year: Year that will be assigned to :class:`~ifxbilling.models.BillingRecord` objects
        :type year: int

        :param month: Month that will be assigned to :class:`~ifxbilling.models.BillingRecord` objects
        :type month: int

        :param organization: The organization whose :class:`~ifxbilling.models.BillingRecord` objects should be generated
        :type organization: list

        :return: QuerySet of :class:`~ifxbilling.models.ProductUsage` objects filtered by the organization, year, and month
        :rtype: :class:`~django.db.models.query.QuerySet`
        '''
        product_usages = ProductUsage.objects.filter(organization=organization, year=year, month=month, product__facility=self.facility, product__billable=True)
        if not product_usages and self.verbosity > self.CHATTY:
            logger.info(f'No product usages for: {organization.name}, {month}, {year}')
        return product_usages

    def generate_billing_records_for_usage(self, year, month, product_usage, **kwargs):
        '''
        Returns one or more billing records for a given ProductUsage.

        :class:`~ifxbilling.models.Account` percentages are fetched using
        :func:`~ifxbilling.calculator.NewBillingCalculator.get_account_percentages_for_product_usage` and
        :func:`~ifxbilling.calculator.NewBillingCalculator.create_billing_record_for_usage` is called for each
        :class:`~ifxbilling.models.Account` and percent.  If the combination of percents does not add up to 100, an Exception is thrown.

        A :class:`~ifxbilling.models.ProductUsageProcessing` instance is created for each :class:`~ifxbilling.models.ProductUsage`
        using :func:`~ifxbilling.calculator.NewBillingCalculator.update_product_usage_processing`.
        Successful :class:`~ifxbilling.models.BillingRecord` creation will result in an instance with `resolved=True`
        and 'OK' as the message.  Any Exceptions will result in `resolved=False` and the Exception error message.

        :param year: Year that will be assigned to :class:`~ifxbilling.models.BillingRecord` objects
        :type year: int

        :param month: Month that will be assigned to :class:`~ifxbilling.models.BillingRecord` objects
        :type month: int

        :param product_usage: The :class:`~ifxbilling.models.ProductUsage` used for calculating the :class:`~ifxbilling.models.BillingRecord` objects
        :type product_usage: :class:`~ifxbilling.models.ProductUsage`

        :return: list of :class:`~ifxbilling.models.BillingRecord` objects that were successfully created
        :rtype: list
        :raises Exception: Any exception thrown during :class:`~ifxbilling.models.BillingRecord` creation is
            caught and used to create :class:`~ifxbilling.models.ProductUsageProcessing` and then re-raised
        '''
        brs = []
        try: # errors are captured in the product_usage_processing table
            with transaction.atomic():
                billing_data_dicts = self.get_billing_data_dicts_for_usage(product_usage, **kwargs)
                for billing_data_dict in billing_data_dicts:
                    account = billing_data_dict.pop('account')
                    percent = billing_data_dict.pop('percent')
                    rate_obj = billing_data_dict.pop('rate_obj', None)
                    if not rate_obj:
                        raise Exception(f'No rate_obj for billing_data_dict {billing_data_dict}')
                    decimal_quantity = billing_data_dict.pop('decimal_quantity')
                    pup_message = billing_data_dict.pop('pup_message', 'OK')
                    br = self.generate_billing_record_for_usage(year, month, product_usage, account, percent, rate_obj, decimal_quantity, billing_data_dict)
                    if br: # can be none
                        brs.append(br)

                # processing complete update any product_usage_processing as resolved
                self.update_product_usage_processing(product_usage, resolved=True, message=pup_message)
        except Exception as ex:
            if self.verbosity == self.CHATTY:
                logger.error(ex)
            if self.verbosity == self.LOUD:
                logger.exception(ex)
            self.update_product_usage_processing(product_usage, resolved=False, message=str(ex))
            raise ex
        return brs

    def get_rate_for_product_usage(self, product_usage, **kwargs):
        '''
        Return the appropriate rate for a product_usage.
        Base class uses Product.get_active_rates() and takes the first one.

        kwargs from get_billing_data_dicts_for_usage are passed in.

        Exception may be thrown if Product has no active rates

        :param product_usage: The :class:`~ifxbilling.models.ProductUsage`
        :type product_usage: :class:`~ifxbilling.models.ProductUsage`

        :return: A single rate
        :rtype: :class:`~ifxbilling.models.Rate`
        '''
        rates = product_usage.product.get_active_rates()
        if not rates:
            raise Exception(f'No active rates for product {product_usage.product}')
        return rates[0]

    def get_billing_data_dicts_for_usage(self, product_usage, **kwargs):
        '''
        Return a list of dictionaries containing the data needed to create a billing record from the usage
        Each dict should be enough for a single billing record.

        This base class just returns a dict of 'rate_obj', 'decimal_quantity', 'account' and 'percent' corresponding
        to any splits along with the first active rate. The 'rate_obj' is the first active rate for the product and
        the 'decimal_quantity' is the entire value from product_usage.

        :param product_usage: The :class:`~ifxbilling.models.ProductUsage` associated with the instance
        :type product_usage: :class:`~ifxbilling.models.ProductUsage`

        :return: A list of dictionaries
        :rtype: list
        '''
        data_dicts = self.get_account_percentages_for_product_usage(product_usage)
        rate = self.get_rate_for_product_usage(product_usage, **kwargs)
        if not rate:
            raise Exception(f'Cannot find an active rate for product {product_usage.product}')

        for data_dict in data_dicts:
            data_dict['rate_obj'] = rate
            data_dict['decimal_quantity'] = product_usage.decimal_quantity
        return data_dicts

    def update_product_usage_processing(self, product_usage, resolved=True, message=None):
        '''
        Create or update a :class:`~ifxbilling.models.ProductUsageProcessing` instance.
        If `resolved=True` and `message=None` the message 'OK' is set.
        Otherwise, the message parameter is used.

        If the message matches one of the values of the PUP_MESSAGES dictionary, resolved will be
        set to True.  This is for handling "exceptions" that are actually valid non-charge situations.

        The PUP is returned, but only for debugging purposes; it is not directly used by the calling code.

        :param product_usage: The :class:`~ifxbilling.models.ProductUsage` associated with the instance
        :type product_usage: :class:`~ifxbilling.models.ProductUsage`

        :param resolved: Was a :class:`~ifxbilling.models.BillingRecord` successfully created for the :class:`~ifxbilling.models.ProductUsage`?
        :type resolved: bool, optional

        :param message: String message if not resolved
        :type message: str, optional

        :return: A ProductUsageProcessing instance
        :rtype: :class:`~ifxbilling.models.ProductUsageProcessing`
        '''
        if resolved and message is None:
            message = 'OK'

        if message in self.PUP_MESSAGES.values():
            resolved = True

        message = message[-2000:] # limit to last 2000 chars (db column max_length)

        try:
            pup = ProductUsageProcessing.objects.get(product_usage=product_usage)
            if self.verbosity > self.QUIET:
                logger.info(f'Found previous ProductUsageProcessing {pup.id} will update it with resolved={resolved} and message {message}.')

            pup.resolved = resolved
            pup.error_message = message
            pup.save()
        except ProductUsageProcessing.DoesNotExist:
            pup = ProductUsageProcessing.objects.create(
                product_usage=product_usage,
                error_message=message,
                resolved=resolved
            )
        return pup

    def generate_billing_record_for_usage(self, year, month, product_usage, account, percent, rate_obj, decimal_quantity, billing_data_dict):
        '''
        Create a single :class:`~ifxbilling.models.BillingRecord` for a :class:`~ifxbilling.models.ProductUsage`

        :func:`~ifxbilling.calculator.NewBillingCalculator.calculate_charges` is called to generate the
        necessary transaction data, :func:`~ifxbilling.calculator.NewBillingCalculator.get_billing_record_rate_description`
        is called to get rate description and then :func:`~ifxbilling.calculator.NewBillingCalculator.create_billing_record`
        actually creates the :class:`~ifxbilling.models.BillingRecord`

        :param year: Year that will be assigned to :class:`~ifxbilling.models.BillingRecord` objects
        :type year: int

        :param month: Month that will be assigned to :class:`~ifxbilling.models.BillingRecord` objects
        :type month: int

        :param product_usage: The :class:`~ifxbilling.models.ProductUsage` being processed.
        :type product_usage: :class:`~ifxbilling.models.ProductUsage`

        :param billing_data_dict: A dictionary of data needed for creating the billing record.  The should at least
            include the :class:`~ifxbilling.models.Account`.
        :type account: dict

        :return: The created billing record
        :rtype: :class:`~ifxbilling.models.BillingRecord`
        '''

        transactions_data = self.calculate_charges(product_usage, percent, rate_obj, decimal_quantity, billing_data_dict)
        if not transactions_data:
            return None
        return self.create_billing_record(year, month, product_usage, account, percent, rate_obj, decimal_quantity, transactions_data, billing_data_dict)

    def get_account_percentages_for_product_usage(self, product_usage, **kwargs):
        '''
        For the given :class:`~ifxbilling.models.ProductUsage` return
        a list of (:class:`~ifxbilling.models.Account`, percent) pairs.
        :class:`~ifxbilling.models.UserProductAccount` authorizations are checked first for
        active, matching :class:`~ifxbilling.models.Product` s.  If none are found, active
        :class:`~ifxbilling.models.UserAccount` authorizations will be checked.

        If no matches are found, an Exception is thrown

        :param product_usage: The :class:`~ifxbilling.models.ProductUsage`
        :type product_usage: :class:`~ifxbilling.models.ProductUsage`

        :raises: Exception if product_usage has no product_user, if product_usage has no organization
        :raises: Exception if set of matching :class:`~ifxbilling.models.UserProductAccount` percents do not add up to 100
        :raises: Exception if no matching active authorization can be found

        :return: list of dicts of the form { 'account': :class:`~ifxbilling.models.Account`, 'percent': percent }
        :rtype: list
        '''
        account_percentages = []
        if not product_usage.product_user:
            raise Exception(f'No product user for {product_usage}')

        # Get the organization associated with the ProductUsage to use for Account selection
        organization = product_usage.organization
        if not organization:
            raise Exception(f'Unable to get an organization for {product_usage}')

        # First try for the product_usage.product, then try the parent
        product = product_usage.product
        user_product_accounts = product_usage.product_user.userproductaccount_set.filter(
            (Q(account__expiration_date=None) | Q(account__expiration_date__gt=product_usage.start_date)),
            product=product,
            account__organization=organization,
            account__valid_from__lte=product_usage.start_date,
            is_valid=True
        )
        if not user_product_accounts:
            product = product_usage.product.parent
            user_product_accounts = product_usage.product_user.userproductaccount_set.filter(
                (Q(account__expiration_date=None) | Q(account__expiration_date__gt=product_usage.start_date)),
                product=product,
                account__organization=organization,
                account__valid_from__lte=product_usage.start_date,
                is_valid=True
            )

        if len(user_product_accounts) > 0:
            # Use them all.  If there is more than one ensure that percents add to 100.
            pct_total = 0
            for user_product_account in user_product_accounts:
                account_percentages.append(
                    {
                        'account': user_product_account.account,
                        'percent': user_product_account.percent,
                    }
                )
                pct_total += user_product_account.percent

            if pct_total != 100:
                raise Exception(f'User product account percents add up to {pct_total} instead of 100')
        else:
            # Only get the first one
            user_account = product_usage.product_user.useraccount_set.filter(
                (Q(account__expiration_date=None) | Q(account__expiration_date__gt=product_usage.start_date)),
                account__organization=organization,
                account__valid_from__lte=product_usage.start_date,
                is_valid=True).first()
            if user_account:
                account_percentages.append(
                    {
                        'account': user_account.account,
                        'percent': 100,
                    }
                )
            else:
                date_format_str = '%-I:%M %p on %-m/%d/%Y'
                start_date_str = timezone.localtime(product_usage.start_date).strftime(date_format_str)
                raise Exception(f'Unable to find an active user account record for {product_usage.product_user.full_name} with organization {organization.name}, product {product_usage.product.product_name} and start_date {start_date_str}')
        if product_usage and account_percentages:
            logger.debug('Account percentages for %s: %s', str(product_usage), str(account_percentages))
        return account_percentages


    def calculate_charges(self, product_usage, percent, rate_obj, decimal_quantity, billing_data_dict=None):
        '''
        Calculates one or more charges that will be used to create transactions
        using a product_usage and an optional usage_data dictionary.

        Returns an array of transaction data dictionaries that will include a
        charge, a user, and a description at least.

        '''
        product = product_usage.product
        if rate_obj.units != product_usage.units:
            raise Exception(f'Units for product usage do not match the active rate for {product}')
        rate_desc = self.get_rate_description(rate_obj)

        transactions_data = []

        percent_str = ''
        if percent < 100:
            percent_str = f'{percent}% of '

        plural = ''
        if decimal_quantity != Decimal('1.0'):
            if product_usage.units[-1] != 's':
                plural = 's'
        description = f'{percent_str}{decimal_quantity.quantize(self.TWO_DIGIT_QUANTIZE)} {product_usage.units}{plural} at {rate_desc}'

        if self.is_flat_rate(rate_obj):
            decimal_charge = rate_obj.decimal_price
        else:
            decimal_charge = rate_obj.decimal_price * decimal_quantity * Decimal(percent / 100)

        user = product_usage.product_user

        transactions_data.append(
            {
                'decimal_charge': decimal_charge,
                'charge': round(decimal_charge),
                'description': description,
                'author': user,
                'rate': rate_desc,
            }
        )
        return transactions_data

    def get_rate(self, product_usage=None, name=None):
        '''
        Return the rate for calculating the charge. Only rates with is_active set to true are returned.

        If only a name is provided, the named rate will be retrieved.

        If a name and product_usage are provided, the named rate for corresponding product will be returned

        If there is no name, and a rate for the product_usage.organization (via :class:`~cbsn.models.OrganizationRate`)
        where the start_date and end_date are appropriate for the usage, use that.
        Otherwise, return settings.RATES.INTERNAL_RATE_NAME
        If OrganizationRates were previously set, but currently expired, it's an error.

        :param product_usage: The :class:`~ifxbilling.models.ProductUsage` associated with the instance
        :type product_usage: :class:`~ifxbilling.models.ProductUsage`

        :param name: The name of a Rate
        :type name: str

        An exception is thrown if a Rate is not found or if more than one is retrieved.

        :return: Rate matching the criteria
        :rtype: `~ifxbilling.models.Rate`
        '''
        if not product_usage and not name:
            raise Exception('Need to specify either product_usage or name options')

        rates = Rate.objects.filter(is_active=True)
        if name:
            rates = rates.filter(name=name)
            if product_usage:
                rates = rates.filter(product=product_usage.product)
        else:
            try:
                rate_name = OrganizationRate.objects.filter(
                    Q(end_date__isnull=True) | Q(end_date__gte=product_usage.end_date)).get(
                    organization=product_usage.organization,
                    rate__product=product_usage.product,
                    start_date__lte=product_usage.start_date,
                ).rate.name
                rate = self.get_rate(name=rate_name, product_usage=product_usage)
                rates = [rate]
            except OrganizationRate.DoesNotExist:
                # If there used to be explicit OrganizationRates, but isn't currently a valid one, it's an error.
                if OrganizationRate.objects.filter(
                    organization=product_usage.organization,
                    rate__product=product_usage.product,
                    end_date__lt=product_usage.end_date
                ).count():
                    # pylint: disable=raise-missing-from
                    raise Exception(
                        f'Organization {product_usage.organization.name} has non-default rates, but they have expired.'
                    )
                # Default is INTERNAL_RATE_NAME matched to the product_usage.product
                rates = rates.filter(product=product_usage.product, name=settings.RATES.INTERNAL_RATE_NAME)
            except OrganizationRate.MultipleObjectsReturned as e:
                raise Exception(f'There are overlapping rates for {product_usage.organization}') from e

        if len(rates) != 1:
            msgs = []
            if product_usage:
                msgs.append(f'product {product_usage.product.product_name}')
            if name:
                msgs.append(f'named {name}')
            msgtxt = ', '.join(msgs)
            if not rates:
                raise Exception(f'Unable to find active rate with {msgtxt}')
            raise Exception(f'More than one active rate was found with {msgtxt}; found {len(rates)}')

        return rates[0]

    def get_rate_description(self, rate):
        '''
        Text description of rate for use in txn rate and description.
        Empty string is returned if rate.price or rate.units is None.

        Description is <price> per <units> unless units is 'ea', then it is <price> <units>

        :param rate: The :class:`~ifxbilling.models.Rate` for the :class:`~ifxbilling.models.Product`
            from the :class:`~ifxbilling.models.ProductUsage`
        :type rate: :class:`~ifxbilling.models.Rate`

        :return: Text description of the rate
        :rtype: str
        '''
        desc = ''
        if rate.decimal_price is not None and rate.units is not None:
            if rate.units == 'ea':
                desc = f'{rate.decimal_price} {rate.units}'
            else:
                desc = f'{rate.decimal_price} per {rate.units}'
        elif rate.price is not None and rate.units is not None:
            if rate.units == 'ea':
                desc = f'{rate.price} {rate.units}'
            else:
                desc = f'{rate.price} per {rate.units}'
        return desc

    def get_billing_record_rate_description(self, transactions_data, **kwargs):
        '''
        This may no longer be needed if transactions are becoming pointless

        Get the rate description for the BillingRecord from the transactions_data.
        Basically just picking the first one.  If there are no transactions an exception is raised.

        :param transactions_data: List of dicts representing data for creating :class:`~ifxbilling.models.Transaction` objects.
        :type transactions_data: list
        :return: Text of first transaction dict 'rate' value
        :rtype: str
        '''
        if not transactions_data:
            raise Exception('No transactions.  Cannot set a rate on the billing record.')
        return transactions_data[0]['rate']

    def create_billing_record(self, year, month, product_usage, account, percent, rate_obj, decimal_quantity, transactions_data, billing_data_dict):
        '''
        Create (and save) a BillingRecord and related Transactions.
        If an existing BillingRecord has the same product_usage and account an Exception will be thrown.????

        :param year: Year that will be assigned to :class:`~ifxbilling.models.BillingRecord` objects
        :type year: int

        :param month: Month that will be assigned to :class:`~ifxbilling.models.BillingRecord` objects
        :type month: int

        :param product_usage: The :class:`~ifxbilling.models.ProductUsage` being processed.
        :type product_usage: :class:`~ifxbilling.models.ProductUsage`

        :param account: The :class:`~ifxbilling.models.Account` being charged.
        :type account: :class:`~ifxbilling.models.Account`

        :param percent: Percent of total :class:`~ifxbilling.models.ProductUsage` charge
            represented by this :class:`~ifxbilling.models.BillingRecord`
        :type percent: int

        :param rate_obj: Rate object being used for calculations
        :type rate_obj: :class:`~ifxbilling.models.Rate`

        :param decimal_quantity: Quantity of usage being charged
        :type decimal_quantity: :class:`~decimal.Decimal`

        :param transactions_data: List of dicts that can be used to create :class:`~ifxbilling.models.Transaction` instances
        :type transactions_data: list

        :param billing_data_dict: Dictionary of additional information needed to create the billing record.  This function checks for
            initial_state
                The initial billing record state.  Defaults to INITIAL_STATE.
            rate_description
                Defaults to the value of get_rate_description
            billing_record_state_user
                User for the initial billing record state.  Defaults to product_usage.user
            billing_record_state_comment
                Comment to be placed on the initial billing record state.
            product_usage_link_text
                Display text for a link back to product usage.  Defaults to product_usage.id
            product_usage_url
                A url for accessing the product usage detail page
        :type transactions_data: list

        :return: The :class:`~ifxbilling.models.BillingRecord`.
        :rtype: :class:`~ifxbilling.models.BillingRecord`
        '''
        initial_state = billing_data_dict.get('initial_state', INITIAL_STATE)
        rate_description = billing_data_dict.get('rate_description', self.get_rate_description(rate_obj))
        billing_record_state_user = billing_data_dict.get('billing_record_state_user', product_usage.product_user)
        billing_record_state_comment = billing_data_dict.get('billing_record_state_comment', 'created by billing calculator')
        start_date = billing_data_dict.get('start_date', product_usage.start_date)
        end_date = billing_data_dict.get('end_date', product_usage.end_date)
        product_usage_link_text = billing_data_dict.get('product_usage_link_text', str(product_usage.id))
        product_usage_url = billing_data_dict.get('product_usage_url')
        billing_record_author = billing_data_dict.get('billing_record_author')

        billing_record = None

        try:
            BillingRecord.objects.get(product_usage=product_usage, account=account, percent=percent, rate_obj=rate_obj, decimal_quantity=decimal_quantity)
            raise Exception(f'Billing record for product usage {product_usage} and account {account} already exists with percent = {percent}, rate = {rate_obj} and decimal_quantity = {decimal_quantity}.')
        except BillingRecord.DoesNotExist:
            pass
        for transaction_data in transactions_data:
            if not billing_record:

                if not billing_record_author:
                    billing_record_author = transaction_data['author']

                billing_record = BillingRecord(
                    product_usage=product_usage,
                    account=account,
                    year=year,
                    month=month,
                    current_state=initial_state,
                    percent=percent,
                    rate=rate_description,
                    rate_obj=rate_obj,
                    decimal_quantity=decimal_quantity,
                    start_date=start_date,
                    end_date=end_date,
                    product_usage_link_text=product_usage_link_text,
                    product_usage_url=product_usage_url,
                    author=billing_record_author,
                    updated_by=billing_record_author
                )
                billing_record.save()
                billing_record_state = BillingRecordState(
                    billing_record=billing_record,
                    name=initial_state,
                    user=billing_record_state_user,
                    comment=billing_record_state_comment
                )
                billing_record_state.save()
            trxn = Transaction(
                billing_record=billing_record,
                decimal_charge=transaction_data['decimal_charge'],
                description=transaction_data['description'],
                author=transaction_data['author'],
                rate=transaction_data['rate'],
            )
            trxn.save()

        return billing_record
