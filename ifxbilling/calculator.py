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
from ifxbilling.models import BillingRecord, Transaction


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

    def calculateCharges(self, product_usage, usage_data=None):
        '''
        Calculates one or more charges that will be used to create transactions
        using a product_usage and an optional usage_data dictionary.

        Returns an array of transaction data dictionaries that will include a
        charge, a user, and a description at least.
        '''
        product = product_usage.product
        rate = product.rate_set.get(is_active=True)
        if rate.units != product_usage.units:
            raise Exception(f'Units for product usage do not match the active rate for {product}')
        transactions_data = []

        description = f'{product_usage.quantity} {product_usage.units} at {rate.price} per {rate.units}'
        charge = rate.price * product_usage.quantity
        user = product_usage.user

        transactions_data.append(
            {
                'charge': charge,
                'description': description,
                'user': user
            }
        )
        return transactions_data

    def getAccountForProductUsage(self, product_usage):
        '''
        For a given ProductUsage, return the Account that should be used.  This is only called
        by createBillingRecordForUsage if an Account is not supplied.
        '''
        return ''

    def getBillingRecordDescription(self, product_usage):
        '''
        Get the description for the BillingRecord. This is only called
        by createBillingRecordForUsage if a description is not supplied.
        '''
        return ''

    def createBillingRecordForUsage(self, product_usage, account=None, year=None, month=None, description=None, usage_data=None, recalculate=False):
        '''
        For the given ProductUsage, Account and the optional usage_data dictionary,
        calculate charge(s) and create a billing record.

        If year or month are not specified, the values will be obtained from the ProductUsage.

        If account is not specified, then getAccountForProductUsage will be called.  If account
        is specified, then it will override any data in product_usage.

        If description is not specified, getBillingRecordDescription will be called.
        '''
        if BillingRecord.objects.filter(product_usage=product_usage).exists():
            raise Exception(f'Billing record already exists for usage {product_usage}')
        if not account:
            account = self.getAccountForProductUsage(product_usage)
        if not year:
            year = product_usage.year
        if not month:
            month = product_usage.month
        if not description:
            description = self.getBillingRecordDescription(product_usage)

        transactions_data = self.calculateCharges(product_usage, usage_data)
        br = self.createBillingRecord(product_usage, account, year, month, transactions_data, description, recalculate)

        return br

    def createBillingRecord(self, product_usage, account, year, month, transactions_data, description=None, recalculate=False):
        '''
        Create (and save) a BillingRecord and related Transactions.
        If an existing BillingRecord has the same product_usage and account an Exception will be thrown.
        '''
        billing_record = None
        try:
            br = BillingRecord.objects.get(product_usage=product_usage, account=account)
            if recalculate:
                br.delete()
            else:
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
            transaction = Transaction(
                billing_record=billing_record,
                charge=transaction_data['charge'],
                description=transaction_data['description'],
                author=transaction_data['author']
            )
            transaction.save()

        return billing_record
