# -*- coding: utf-8 -*-

'''
Test ProductUsageProcessing table is filled in correctly during billing record
generation

Created on  2021-11-13

@author: Meghan Correa <mportermahoney@g.harvard.edu>
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
from ifxbilling.models import ProductUsage, ProductUsageProcessing

class TestProductUsageProcessing(APITestCase):
    '''
    Test ProductUsageProcessing
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

    def testProductUsageProcessingCreate(self):
        '''
        Ensure that a ProductUsageProcessing row is entered when there is an error in creating a billing record from a ProductUsage
        '''
        data.init(types=['Account', 'Product', 'ProductUsage'])
        product_usage_data = data.PRODUCT_USAGES[0]
        product_usage = ProductUsage.objects.get(
            product__product_name=product_usage_data['product'],
            product_user__full_name=product_usage_data['product_user'],
            quantity=product_usage_data['quantity']
        )

        expected_error = 'Unable to find an active user account record for'
        bbc = BasicBillingCalculator()
        self.assertRaisesMessage(Exception, expected_error, bbc.createBillingRecordsForUsage, product_usage)
        processing_rows = ProductUsageProcessing.objects.filter(product_usage=product_usage)
        self.assertTrue(len(processing_rows) == 1, f'Incorrect number of product usage processing rows returned {processing_rows}')

        processing = processing_rows[0]
        self.assertTrue(processing.resolved == False, f'Incorrect resolved status {processing}')
        self.assertTrue(expected_error in processing.error_message, f'Incorrect error_message {processing.error_message}')

        # test if resolved is set to true when reprocessed
        data.init_user_accounts()
        bbc.createBillingRecordsForUsage(product_usage)
        processing_rows = ProductUsageProcessing.objects.filter(product_usage=product_usage)
        self.assertTrue(len(processing_rows) == 1, f'Incorrect number of product usage processing rows returned {processing_rows}')

        processing = processing_rows[0]
        self.assertTrue(processing.resolved == True, f'Incorrect resolved status {processing}')
