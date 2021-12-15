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
import traceback
import json
from importlib import import_module
from django.db import transaction
from ifxbilling.models import BillingRecord, Transaction, BillingRecordState, ProductUsageProcessing, ProductUsage


logger = logging.getLogger('ifxbilling')
initial_state = 'PENDING LAB APPROVAL'

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
        msg = "%s doesn't look like a module path" % dotted_path
        raise ImportError(msg) from e

    module = import_module(module_path)

    try:
        return getattr(module, class_name)
    except AttributeError as e:
        msg = 'Module "%s" does not define a "%s" attribute/class' % (
            module_path, class_name)
        raise ImportError(msg) from e


def calculateBillingMonth(month, year, facility, recalculate=False, verbose=False):
    '''
    Calculate a months worth of billing records and return the number of successes and list of error messages
    '''
    successes = 0
    errors = []
    product_usages = ProductUsage.objects.filter(month=month, year=year, product__facility=facility)
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
                # self.update_product_usage_processing(product_usage, {'resolved': False, 'error_message': msg})
                raise Exception(msg)
        try: # errors are captured in the product_usage_processing table
            with transaction.atomic():
                if not account_percentages:
                    account_percentages = self.getAccountPercentagesForProductUsage(product_usage)
                logger.debug('Creating %d billing records for product_usage %s', len(account_percentages), str(product_usage))
                for account_percentage in account_percentages:
                    account = account_percentage['account']
                    percent = account_percentage['percent']
                    brs.append(self.createBillingRecordForUsage(product_usage, account, percent, year, month, description, usage_data))
                # processing complete update any product_usage_processing as resolved
                self.update_product_usage_processing(product_usage, {'resolved': True}, update_only_unresolved=True)
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
        rate = self.getRateDescriptionFromTransactions(transactions_data)
        return self.createBillingRecord(product_usage, account, year, month, transactions_data, percent, rate, description)

    def update_product_usage_processing(self, product_usage, attrs, update_only_unresolved=False):
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
                    current_state=initial_state,
                    percent=percent,
                    rate=rate,
                )
                billing_record.save()
                billing_record_state = BillingRecordState(
                    billing_record=billing_record,
                    name=initial_state,
                    user=product_usage.product_user,
                    #TODO: add approvers
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
        pass
