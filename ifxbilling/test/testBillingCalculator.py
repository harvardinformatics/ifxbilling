# -*- coding: utf-8 -*-

'''
Test BasicBillingCalculator

Created on  2021-05-06

@author: Aaron Kitzmiller <aaron_kitzmiller@harvard.edu>
@copyright: 2021 The Presidents and Fellows of Harvard College.
All rights reserved.
@license: GPL v2.0
'''
from rest_framework.test import APITestCase
from rest_framework.authtoken.models import Token
from rest_framework.reverse import reverse
from rest_framework import status
from django.contrib.auth import get_user_model
from django.utils import timezone
from ifxbilling.test import data
from ifxbilling.calculator import BasicBillingCalculator
from ifxbilling import models

class TestCalculator(APITestCase):
    '''
    Test BasicBillingCalculator
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
        Ensure that a simple ProductUsage can be converted to a BillingRecord specifying only the product_usage.
        '''
        data.init(types=['Account', 'Product', 'ProductUsage', 'UserAccount'])
        product_usage_data = data.PRODUCT_USAGES[0]
        product_usage = models.ProductUsage.objects.get(
            product__product_name=product_usage_data['product'],
            product_user__full_name=product_usage_data['product_user'],
            quantity=product_usage_data['quantity']
        )

        bbc = BasicBillingCalculator()
        brs = bbc.createBillingRecordsForUsage(product_usage)
        self.assertTrue(len(brs) == 1, f'Incorrect number of billing records returned {brs}')

        br = brs[0]
        expected_charge = 100
        self.assertTrue(br.charge == expected_charge, f'Incorrect charge {br}')

        price = product_usage.product.rate_set.first().price
        units = product_usage.product.rate_set.first().units
        self.assertTrue(br.rate == f'{price} {units}', f'Incorrect billing record rate {br.rate}')

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

        bbc = BasicBillingCalculator()
        brs = bbc.createBillingRecordsForUsage(product_usage)
        self.assertTrue(len(brs) == 2, f'Incorrect number of billing records returned {brs}')

        for charge in [25, 75]:
            try:
                models.BillingRecord.objects.get(product_usage=product_usage, charge=charge)
            except models.BillingRecord.DoesNotExist:
                self.assertTrue(False, f'Unable to find billing record with charge {charge}\n{brs}')
