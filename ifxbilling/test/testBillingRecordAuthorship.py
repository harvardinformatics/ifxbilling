# -*- coding: utf-8 -*-

'''
Test BillingRecord authorship

Ensure that a user other than fiine cannot set transaction or state authors

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
from django.contrib.auth.models import Group
from django.utils import timezone
from django.conf import settings
from ifxbilling.test import data
from ifxbilling import models

class TestBillingRecordAuthorship(APITestCase):
    '''
    Ensure that a user other than fiine cannot set transaction or state authors
    '''
    def setUp(self):
        '''
        setup
        '''
        data.clearTestData()

        # This needs to be fiine for the author tests to work
        self.superuser = get_user_model().objects.create_superuser('john', 'john@snow.com', 'johnpassword')
        self.superuser.ifxid = 'IFXIDX999999999'
        self.superuser.full_name = 'John Snow'
        self.superuser.save()

        admin_group, created = Group.objects.get_or_create(name=settings.GROUPS.ADMIN_GROUP_NAME)
        self.superuser.groups.add(admin_group)

        self.token = Token(user=self.superuser)
        self.token.save()
        self.client.login(username='john', password='johnpassword')
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + self.token.key)

    def testDifferentAuthor(self):
        '''
        Ensure that when real_user_ifxid is set insert fails for non-fiine user
        '''
        data.init(types=['Account', 'Product', 'ProductUsage'])

        # Get the author
        author = get_user_model().objects.get(username=data.USERS[0]['username']) # sslurpiston

        # Create a billing record
        product_usage = models.ProductUsage.objects.filter(product__product_name='Helium Dewar').first()
        account = models.Account.objects.first()

        billing_record_data = {
            'account': {
                'id': account.id,
            },
            'product_usage': {
                'id': product_usage.id
            },
            'charge': 999,  # This will be overwritten
            'description': 'Dewar charge',
            'transactions': [
                {
                    'charge': 100,
                    'description': 'Dewar charge',
                },
                {
                    'charge': -10,
                    'description': '10%% off coupon',
                }
            ],
            'real_user_ifxid': author.ifxid
        }
        url = reverse('billing-record-list')
        response = self.client.post(url, billing_record_data, format='json')
        self.assertTrue(response.status_code == status.HTTP_400_BAD_REQUEST, f'Failed to post {response}')

    def testDifferentAuthorSetState(self):
        '''
        Ensure that an attempt to set state author to a different user fails
        '''
        data.init(types=['Account', 'Product', 'ProductUsage'])

        # Create a billing record
        product_usage = models.ProductUsage.objects.filter(product__product_name='Helium Dewar').first()
        account = models.Account.objects.first()

        billing_record_data = {
            'account': {
                'id': account.id,
            },
            'product_usage': {
                'id': product_usage.id
            },
            'charge': 999,  # This will be overwritten
            'description': 'Dewar charge',
            'transactions': [
                {
                    'charge': 100,
                    'description': 'Dewar charge',
                },
                {
                    'charge': -10,
                    'description': '10%% off coupon',
                }
            ],
            'billing_record_states': [
                {
                    'name': 'INIT',
                    'user': data.USERS[0]['username'] # sslurpiston
                },
                {
                    'name': 'FINAL',
                }
            ]
        }
        url = reverse('billing-record-list')
        response = self.client.post(url, billing_record_data, format='json')
        self.assertTrue(response.status_code == status.HTTP_400_BAD_REQUEST, f'Incorrect response {response}')

    def testDifferentAuthorTransaction(self):
        '''
        Ensure that insert fails with different transaction author
        '''
        data.init(types=['Account', 'Product', 'ProductUsage'])

        # Get the author
        author = get_user_model().objects.get(username=data.USERS[0]['username']) # sslurpiston

        # Create a billing record
        product_usage = models.ProductUsage.objects.filter(product__product_name='Helium Dewar').first()
        account = models.Account.objects.first()

        billing_record_data = {
            'account': {
                'id': account.id,
            },
            'product_usage': {
                'id': product_usage.id
            },
            'charge': 999,  # This will be overwritten
            'description': 'Dewar charge',
            'transactions': [
                {
                    'charge': 100,
                    'description': 'Dewar charge',
                    'author': {
                        'ifxid': author.ifxid
                    }
                },
            ],
        }
        url = reverse('billing-record-list')
        response = self.client.post(url, billing_record_data, format='json')
        self.assertTrue(response.status_code == status.HTTP_400_BAD_REQUEST, f'Incorrect response {response}')
