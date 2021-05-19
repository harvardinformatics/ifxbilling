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
from importlib import import_module
from django.db import transaction
from ifxbilling.models import BillingRecord, Transaction


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
        transactions_data = []

        percent_str = ''
        if percent < 100:
            percent_str = f'{percent}% of '
        description = f'{percent_str}{product_usage.quantity} {product_usage.units} at {rate.price} per {rate.units}'
        charge = round(rate.price * product_usage.quantity * percent / 100)
        user = product_usage.product_user

        transactions_data.append(
            {
                'charge': charge,
                'description': description,
                'author': user
            }
        )
        return transactions_data

    def getAccountPercentagesForProductUsage(self, product_usage):
        '''
        For a given ProductUsage, return an array of account (Account object) and percent that should be used.  This is only called
        by createBillingRecordForUsage if an Account is not supplied.

        UserProductAccount is tested first, followed by UserAccount.  An exception is raised if neither attempt is successful.
        '''
        account_percentages = []
        if not product_usage.product_user:
            raise Exception(f'No product user for {product_usage}')
        user_product_accounts = product_usage.product_user.userproductaccount_set.filter(product=product_usage.product, is_valid=True)
        if len(user_product_accounts) > 0:
            for user_product_account in user_product_accounts:
                account_percentages.append(
                    {
                        'account': user_product_account.account,
                        'percent': user_product_account.percent,
                    }
                )
        else:
            user_account = product_usage.product_user.useraccount_set.filter(is_valid=True).first()
            if user_account:
                account_percentages.append(
                    {
                        'account': user_account.account,
                        'percent': 100,
                    }
                )
            else:
                raise Exception(f'Unable to find a user account record for {product_usage.product_user}')
        return account_percentages

    def getBillingRecordDescription(self, product_usage, percent):
        '''
        Get the description for the BillingRecord. This is only called
        by createBillingRecordForUsage if a description is not supplied.
        '''
        percent_str = ''
        if percent < 100:
            percent_str = f'{percent}% of '
        return f'{percent_str}{product_usage.quantity} {product_usage.units} of {product_usage.product} for {product_usage.product_user} on {product_usage.created}'

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
        with transaction.atomic():
            if BillingRecord.objects.filter(product_usage=product_usage).exists():
                if recalculate:
                    BillingRecord.objects.filter(product_usage=product_usage).delete()
                else:
                    raise Exception(f'Billing record already exists for usage {product_usage}')

            if not account_percentages:
                account_percentages = self.getAccountPercentagesForProductUsage(product_usage)
            for account_percentage in account_percentages:
                account = account_percentage['account']
                percent = account_percentage['percent']
                brs.append(self.createBillingRecordForUsage(product_usage, account, percent, year, month, description, usage_data))
        return brs

    def createBillingRecordForUsage(self, product_usage, account, percent, year=None, month=None, description=None, usage_data=None):
        '''
        For the given ProductUsage, Account and the optional usage_data dictionary,
        calculate charge(s) and create a billing record.

        If year or month are not specified, the values will be obtained from the ProductUsage.

        If account is not specified, then getAccountForProductUsage will be called.  If account
        is specified, then it will override any data in product_usage.

        If description is not specified, getBillingRecordDescription will be called.
        '''
        if not year:
            year = product_usage.year
        if not month:
            month = product_usage.month
        if not description:
            description = self.getBillingRecordDescription(product_usage, percent)

        transactions_data = self.calculateCharges(product_usage, percent, usage_data)
        return self.createBillingRecord(product_usage, account, year, month, transactions_data, description)

    def createBillingRecord(self, product_usage, account, year, month, transactions_data, description=None):
        '''
        Create (and save) a BillingRecord and related Transactions.
        If an existing BillingRecord has the same product_usage and account an Exception will be thrown.
        '''
        billing_record = None
        try:
            BillingRecord.objects.get(product_usage=product_usage, account=account)
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
                    description=description
                )
                billing_record.save()
            trxn = Transaction(
                billing_record=billing_record,
                charge=transaction_data['charge'],
                description=transaction_data['description'],
                author=transaction_data['author']
            )
            trxn.save()

        return billing_record
