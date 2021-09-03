# -*- coding: utf-8 -*-

'''
Test Unauthorized view

Created on  2021-08-25

@author: Aaron Kitzmiller <aaron_kitzmiller@harvard.edu>
@copyright: 2021 The Presidents and Fellows of Harvard College.
All rights reserved.
@license: GPL v2.0
'''
from datetime import datetime
from rest_framework.test import APITestCase
from rest_framework.authtoken.models import Token
from rest_framework.reverse import reverse
from rest_framework import status
from django.contrib.auth import get_user_model
from django.utils import timezone
from ifxbilling.test import data
from ifxbilling.models import UserAccount, Account

class TestUnauthorized(APITestCase):
    '''
    Test Unauthorized view
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

    def testUnauthorized(self):
        '''
        Ensure that user with a product usage and no authorized accounts is returned.
        '''
        data.init(['Account', 'UserAccount', 'Product'])

        ifxid_with_user_account = 'IFXID000000000D'
        ifxid_without_user_account = 'IFXID000000000E'
        for ifxid in [ifxid_with_user_account, ifxid_without_user_account]:
            product_usage_data = {
                'product': 'Helium Dewar',
                'product_user': {
                    'ifxid': ifxid
                },
                'quantity': 1,
                'start_date': timezone.make_aware(datetime(2021, 2, 1)),
                'description': 'Howdy',
            }
            url = reverse('productusage-list')
            response = self.client.post(url, product_usage_data, format='json')
            self.assertTrue(response.status_code == status.HTTP_201_CREATED, f'Incorrect response {response.status_code}')

        url = reverse('unauthorized')
        response = self.client.get(url)
        unauthorized = response.data
        self.assertTrue(len(unauthorized) == 1, f'Incorrect number of unauthorized users {unauthorized}')
        self.assertTrue(unauthorized[0]['user']['ifxid'] == ifxid_without_user_account, f'Incorrect user returned {unauthorized}')

    def testProductAuthorization(self):
        '''
        Ensure that user with a user product account is considered authorized.
        '''
        data.init(['Account', 'Product', 'UserProductAccount'])

        ifxid_with_user_account = 'IFXID000000000D'
        ifxid_without_user_account = 'IFXID000000000E'
        for ifxid in [ifxid_with_user_account, ifxid_without_user_account]:
            product_usage_data = {
                'product': 'Helium Dewar',
                'product_user': {
                    'ifxid': ifxid
                },
                'quantity': 1,
                'start_date': timezone.make_aware(datetime(2021, 2, 1)),
                'description': 'Howdy',
            }
            url = reverse('productusage-list')
            response = self.client.post(url, product_usage_data, format='json')
            self.assertTrue(response.status_code == status.HTTP_201_CREATED, f'Incorrect response {response.data}')

        # Double check to make sure user doesn't have a default account
        self.assertFalse(UserAccount.objects.filter(user__ifxid=ifxid_with_user_account).exists(), f'User should not have a UserAccount, just a UserProductAccount')

        url = reverse('unauthorized')
        response = self.client.get(url)
        unauthorized = response.data
        self.assertTrue(len(unauthorized) == 1, f'Incorrect number of unauthorized users {unauthorized}')
        self.assertTrue(unauthorized[0]['user']['ifxid'] == ifxid_without_user_account, f'Incorrect user returned {unauthorized}')

    def testWrongProductAuthorization(self):
        '''
        Ensure that user with a user product account for a different product is not considered authorized
        '''
        data.init(['Account', 'Product', 'UserProductAccount'])

        ifxid_with_user_account = 'IFXID000000000D'
        ifxid_without_user_account = 'IFXID000000000E'
        for ifxid in [ifxid_with_user_account, ifxid_without_user_account]:
            product_usage_data = {
                'product': 'Helium Balloon',
                'product_user': {
                    'ifxid': ifxid
                },
                'quantity': 1,
                'start_date': timezone.make_aware(datetime(2021, 2, 1)),
                'description': 'Howdy',
            }
            url = reverse('productusage-list')
            response = self.client.post(url, product_usage_data, format='json')
            self.assertTrue(response.status_code == status.HTTP_201_CREATED, f'Incorrect response {response.status_code}')

        # Double check to make sure user doesn't have a default account
        self.assertFalse(UserAccount.objects.filter(user__ifxid=ifxid_with_user_account).exists(), f'User should not have a UserAccount, just a UserProductAccount')

        url = reverse('unauthorized')
        response = self.client.get(url)
        unauthorized = response.data
        self.assertTrue(len(unauthorized) == 2, f'Incorrect number of unauthorized users {unauthorized}')

    def testInactiveExpenseCode(self):
        '''
        Ensure that user with a valid user account, but inactive expense code is returned
        '''
        data.init(['Account', 'Product', 'UserAccount'])

        ifxid_with_user_account = 'IFXID000000000D'
        ifxid_without_user_account = 'IFXID000000000E'
        for ifxid in [ifxid_with_user_account, ifxid_without_user_account]:
            product_usage_data = {
                'product': 'Helium Dewar',
                'product_user': {
                    'ifxid': ifxid
                },
                'quantity': 1,
                'start_date': timezone.make_aware(datetime(2021, 2, 1)),
                'description': 'Howdy',
            }
            url = reverse('productusage-list')
            response = self.client.post(url, product_usage_data, format='json')
            self.assertTrue(response.status_code == status.HTTP_201_CREATED, f'Incorrect response {response.status_code}')

        # Set accounts invalid
        Account.objects.all().update(active=False)

        url = reverse('unauthorized')
        response = self.client.get(url)
        unauthorized = response.data
        self.assertTrue(len(unauthorized) == 2, f'Incorrect number of unauthorized users {unauthorized}')
