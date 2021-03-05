# -*- coding: utf-8 -*-

'''
Test Account

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
from ifxuser.models import Organization
from ifxbilling.test import data

class TestAccount(APITestCase):
    '''
    Test Account models and serializers
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

    def testDotSeparatedExpenseCodeInsertFail(self):
        '''
        Ensure that an improperly formatted expense code (containing dot separators) will fail
        '''
        data.init()
        account_data = {
            'code': '370.31230.8100.000775.600200.0000.44075',
            'organization': 'Kitzmiller Lab (a Harvard Laboratory)',
            'name': 'mycode',
            'root': '12345',
        }
        url = reverse('account-list')
        response = self.client.post(url, account_data, format='json')
        self.assertTrue(response.status_code == status.HTTP_400_BAD_REQUEST, f'Incorrect response status: {response.data}')

    def testMissingObjectCodeInsertion(self):
        '''
        Ensure that an expense code with missing object code will succeed
        '''
        data.init()
        account_data = {
            'code': '370-31230-000775-600200-0000-44075',
            'organization': 'Kitzmiller Lab (a Harvard Laboratory)',
            'name': 'mycode',
            'root': '12345',
        }
        url = reverse('account-list')
        response = self.client.post(url, account_data, format='json')
        self.assertTrue(response.status_code == status.HTTP_201_CREATED, f'Incorrect response status: {response.data}')

    def testExpenseCodeCharsFail(self):
        '''
        Ensure that an expense code with chars will fail
        '''
        data.init()
        account_data = {
            'code': '370-31230-xxxx-000775-600200-0000-44075',
            'organization': 'Kitzmiller Lab (a Harvard Laboratory)',
            'name': 'mycode',
            'root': '12345',
        }
        url = reverse('account-list')
        response = self.client.post(url, account_data, format='json')
        self.assertTrue(response.status_code == status.HTTP_400_BAD_REQUEST, f'Incorrect response status: {response.data}')

    def testAccountInsert(self):
        '''
        Insert a minimal account. Ensure default account_type 'Expense Code', default active and valid_from are set
        '''
        data.init()
        account_data = {
            'code': '370-31230-8100-000775-600200-0000-44075',
            'organization': 'Kitzmiller Lab (a Harvard Laboratory)',
            'name': 'mycode',
            'root': '12345',
        }
        url = reverse('account-list')
        response = self.client.post(url, account_data, format='json')
        self.assertTrue(response.status_code == status.HTTP_201_CREATED, f'Incorrect response status: {response.data}')
        self.assertTrue(response.data['account_type'] == 'Expense Code', f'Incorrect value in "account_type" {response.data}')
        self.assertTrue(response.data['active'] == False, f'Incorrect value in "active" {response.data}')
        self.assertTrue('valid_from' in response.data and response.data['valid_from'], f'Incorrect value in "valid_from" {response.data}')

    def testInvalidRoot(self):
        '''
        Ensure that an invalid root value fails
        '''
        data.init()
        account_data = {
            'code': '370-31230-8100-000775-600200-0000-44075',
            'organization': 'Kitzmiller Lab (a Harvard Laboratory)',
            'name': 'mycode',
            'root': '123',
        }
        url = reverse('account-list')
        response = self.client.post(url, account_data, format='json')
        self.assertTrue(response.status_code == status.HTTP_400_BAD_REQUEST, f'Incorrect response status: {response.status_code}')
        self.assertTrue('Root must be a 5 digit number' in str(response.data['root']), f'Incorrect value in "root" {response.data}')

    def testInvalidAccountType(self):
        '''
        Ensure that an invalid account_type value fails
        '''
        data.init()
        account_data = {
            'code': '370-31230-8100-000775-600200-0000-44075',
            'organization': 'Kitzmiller Lab (a Harvard Laboratory)',
            'name': 'mycode',
            'root': '12345',
            'account_type': 'invalid',
        }
        url = reverse('account-list')
        response = self.client.post(url, account_data, format='json')
        self.assertTrue(response.status_code == status.HTTP_400_BAD_REQUEST, f'Incorrect response status: {response.status_code}')
        self.assertTrue('is not a valid choice' in str(response.data['account_type']), f'Incorrect value in "account_type" error: {response.data}')

    def testDuplicateAccount(self):
        '''
        Ensure that the same code / organization combination cannot be added twice.
        '''
        data.init()
        accounts_data = [
            {
                'code': '370-31230-8100-000775-600200-0000-44075',
                'organization': 'Kitzmiller Lab (a Harvard Laboratory)',
                'name': 'mycode',
                'root': '12345',
            },
            {
                'code': '370-31230-8100-000775-600200-0000-44075',
                'organization': 'Kitzmiller Lab (a Harvard Laboratory)',
                'name': 'another name',
                'root': '12345',
            }
        ]
        url = reverse('account-list')
        response = self.client.post(url, accounts_data[0], format='json')
        self.assertTrue(response.status_code == status.HTTP_201_CREATED, f'Incorrect response status: {response.status_code}')
        response = self.client.post(url, accounts_data[1], format='json')
        self.assertTrue(response.status_code == status.HTTP_400_BAD_REQUEST, f'Incorrect response status: {response.data}')
        self.assertTrue('The fields code, organization must make a unique set' in str(response.data['non_field_errors']), f'Incorrect response data {response.data}')