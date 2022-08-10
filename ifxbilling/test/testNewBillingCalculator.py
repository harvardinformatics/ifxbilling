# -*- coding: utf-8 -*-

'''
Test NewBillingCalculator

Created on  2021-05-06

@author: Aaron Kitzmiller <aaron_kitzmiller@harvard.edu>
@copyright: 2021 The Presidents and Fellows of Harvard College.
All rights reserved.
@license: GPL v2.0
'''
from decimal import Decimal
from rest_framework.test import APITestCase
from rest_framework.authtoken.models import Token
from rest_framework.reverse import reverse
from rest_framework import status
from django.contrib.auth import get_user_model
from django.utils import timezone
from ifxbilling.test import data
from ifxbilling.calculator import NewBillingCalculator
from ifxbilling import models

class TestCalculator(APITestCase):
    '''
    Test NewBillingCalculator
    '''
    def setUp(self):
        '''
        setup
        '''
        data.clearTestData()
        self.superuser = get_user_model().objects.create_superuser('john', 'john@snow.com', 'johnpassword')
        self.token = Token(user=self.superuser)
        self.token.save()
        self.client.login(username='john', password='johnpassword')
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + self.token.key)

    def tearDown(self):
        data.clearTestData()

    def testCalculator(self):
        '''
        Ensure that a simple ProductUsage can be converted to a BillingRecord.
        '''
        data.init(types=['Account', 'Product', 'ProductUsage', 'UserProductAccount', 'UserAccount'])
        product_usage_data = data.PRODUCT_USAGES[0]
        product_usage = models.ProductUsage.objects.get(
            product__product_name=product_usage_data['product'],
            product_user__full_name=product_usage_data['product_user'],
            quantity=product_usage_data['quantity'],
            decimal_quantity=product_usage_data['decimal_quantity']
        )

        year = 2022
        month = 1
        bc = NewBillingCalculator()
        result = bc.calculate_billing_month(year, month, verbosity=NewBillingCalculator.LOUD)
        brs = result['Kitzmiller Lab']['successes']
        self.assertTrue(len(brs) == 2, f'Incorrect number of billing records returned {brs}')

        br = brs[0]
        expected_decimal_charge = Decimal('100.00')
        self.assertTrue(br.decimal_charge == expected_decimal_charge, f'Incorrect decimal charge {br.decimal_charge}')

        expected_charge = 100
        self.assertTrue(br.charge == expected_charge, f'Incorrect charge {br.charge}')

        decimal_price = product_usage.product.rate_set.first().decimal_price
        units = product_usage.product.rate_set.first().units
        self.assertTrue(br.rate == f'{decimal_price} {units}', f'Incorrect billing record rate {br.rate}')

    def testInactiveAccount(self):
        '''
        Ensure that BillingRecord creation will fail if the Account is inactive.
        '''
        data.init(types=['Account', 'Product', 'ProductUsage', 'UserAccount'])
        # Make "mycode" inactive
        models.Account.objects.filter(name='mycode').update(active=False)

        product_usage_data = data.PRODUCT_USAGES[0]
        product_usage = models.ProductUsage.objects.get(
            product__product_name=product_usage_data['product'],
            product_user__full_name=product_usage_data['product_user'],
            quantity=product_usage_data['quantity']
        )

        year = 2022
        month = 1
        bc = NewBillingCalculator()
        result = bc.calculate_billing_month(year, month, verbosity=NewBillingCalculator.QUIET)
        successes = result['Kitzmiller Lab']['successes']
        self.assertTrue(len(successes) == 0, f'Incorrect number of billing records returned {successes}')
        errors = result['Kitzmiller Lab']['errors']
        self.assertTrue(len(errors) == 2, f'Incorrect number of errors returned {errors}')
        for error in errors:
            self.assertTrue('Unable to find an active user account record' in error, f'Incorrect error message: {error}')

    def testUserProductAccountSplit(self):
        '''
        Ensure that a charge against a UserProductAccount with percentages creates split billing records.
        '''
        data.init(types=['Account', 'Product', 'ProductUsage', 'UserProductAccount'])
        product_usage_data = data.PRODUCT_USAGES[0]
        product_usage = models.ProductUsage.objects.get(
            product__product_name=product_usage_data['product'],
            product_user__full_name=product_usage_data['product_user'],
            quantity=product_usage_data['quantity']
        )

        year = 2021
        month = 2
        bc = NewBillingCalculator()
        result = bc.calculate_billing_month(year, month, verbosity=NewBillingCalculator.QUIET)
        successes = result['Kitzmiller Lab']['successes']
        self.assertTrue(len(successes) == 2, f'Incorrect number of successfully processed brs: {successes}')
        for charge in [Decimal('25.00'), Decimal('75.00')]:
            try:
                models.BillingRecord.objects.get(product_usage=product_usage, decimal_charge=charge)
            except models.BillingRecord.DoesNotExist:
                self.assertTrue(False, f'Unable to find billing record with charge {charge}\n{successes}')

    # def testBadUserProductAccountSplit(self):
    #     '''
    #     Ensure that a split that doesn't add to 100 fails.
    #     '''
    #     data.init(types=['Account', 'Product', 'ProductUsage', 'UserProductAccount'])
    #     product_usage_data = data.PRODUCT_USAGES[1]
    #     product_usage = models.ProductUsage.objects.get(
    #         product__product_name=product_usage_data['product'],
    #         product_user__full_name=product_usage_data['product_user'],
    #         quantity=product_usage_data['quantity'],
    #         year=product_usage_data['year']
    #     )

    #     bbc = BasicBillingCalculator()
    #     self.assertRaisesMessage(Exception, 'User product account percents add up to', bbc.createBillingRecordsForUsage, product_usage)
