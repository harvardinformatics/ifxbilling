# -*- coding: utf-8 -*-

'''
Test BillingRecord

Created on  2021-02-10

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
from ifxbilling import models

class TestBillingRecord(APITestCase):
    '''
    Test BillingRecord models and serializers
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

    def testMinimalBillingRecordInsert(self):
        '''
        Insert a minimal BillingRecord.  Ensure that month and year get set.  Ensure that the charge is the sum of the transactions.
        '''
        data.init(types=['Account', 'Product', 'ProductUsage'])

        # Create a billing record
        product_usage = models.ProductUsage.objects.filter(product__product_name='Helium Dewar').first()
        account = models.Account.objects.first()

        billing_record_data = {
            'account': account.slug,
            'product_usage': {
                'id': product_usage.id
            },
            'charge': 999,  # This will be overwritten
            'description': 'Dewar charge',
            'transactions': [
                {
                    'charge': 100,
                    'description': 'Dewar charge'
                },
                {
                    'charge': -10,
                    'description': '10%% off coupon'
                }
            ]
        }
        url = reverse('billing-record-list')
        response = self.client.post(url, billing_record_data, format='json')
        self.assertTrue(response.status_code == status.HTTP_201_CREATED, f'Failed to post {response}')

        # Check that the charge is properly calculated
        expected_charge = 0
        for trx in billing_record_data['transactions']:
            expected_charge += trx['charge']

        self.assertTrue(response.data['charge'] == expected_charge, f'BillingRecord charge is incorrect {response.data["charge"]}')

        # Check that the year and month are set
        self.assertTrue(response.data['year'] == timezone.now().year, f'Incorrect year setting {response.data}')
        self.assertTrue(response.data['month'] == timezone.now().month, f'Incorrect month setting {response.data}')

    def testNoTransactions(self):
        '''
        Ensure that a BillingRecord without transactions is a failure.
        '''
        data.init(types=['Account', 'Product', 'ProductUsage'])

        # Create a billing record
        product_usage = models.ProductUsage.objects.filter(product__product_name='Helium Dewar').first()
        account = models.Account.objects.first()

        billing_record_data = {
            'account': account.slug,
            'product_usage': {
                'id': product_usage.id
            },
            'charge': 999,  # This will be overwritten
            'description': 'Dewar charge',
        }
        url = reverse('billing-record-list')
        response = self.client.post(url, billing_record_data, format='json')
        self.assertTrue(response.status_code == status.HTTP_400_BAD_REQUEST, f'Incorrect status {response.data}')
        self.assertTrue('Billing record must have at least one transaction' in str(response.data['transactions']), f'Incorrect response {response.data}')

    def testFilterBillingRecords(self):
        '''
        Ensure that billing records can be filtered by year, month, organization, root
        '''
        data.init(types=['Account', 'Product', 'ProductUsage', 'UserProductAccount'])

        # Create a billing record
        product_usage = models.ProductUsage.objects.filter(product__product_name='Helium Dewar').first()
        account = models.Account.objects.first()

        billing_record_data = {
            'account': account.slug,
            'product_usage': {
                'id': product_usage.id
            },
            'charge': 999,  # This will be overwritten
            'description': 'Dewar charge',
            'transactions': [
                {
                    'charge': 100,
                    'description': 'Dewar charge'
                },
                {
                    'charge': -10,
                    'description': '10%% off coupon'
                }
            ]
        }
        url = reverse('billing-record-list')
        response = self.client.post(url, billing_record_data, format='json')
        self.assertTrue(response.status_code == status.HTTP_201_CREATED, f'Failed to post {response}')

        # Check that the charge is properly calculated
        expected_charge = 0
        for trx in billing_record_data['transactions']:
            expected_charge += trx['charge']

        self.assertTrue(response.data['charge'] == expected_charge, f'BillingRecord charge is incorrect {response.data["charge"]}')

        # Check that the year and month are set
        self.assertTrue(response.data['year'] == timezone.now().year, f'Incorrect year setting {response.data}')
        self.assertTrue(response.data['month'] == timezone.now().month, f'Incorrect month setting {response.data}')
