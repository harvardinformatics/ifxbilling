# -*- coding: utf-8 -*-

'''
Test Account

Created on  2021-02-10

@author: Aaron Kitzmiller <aaron_kitzmiller@harvard.edu>
@copyright: 2021 The Presidents and Fellows of Harvard College.
All rights reserved.
@license: GPL v2.0
'''
from functools import reduce
from rest_framework.test import APITestCase
from rest_framework.authtoken.models import Token
from rest_framework.reverse import reverse
from rest_framework import status
from django.contrib.auth import get_user_model
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
        self.assertTrue(response.data['active'] is False, f'Incorrect value in "active" {response.data}')
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

    def testUserProductAccount(self):
        '''
        Ensure that user accounts and user product accounts are fetched with an account.
        '''
        data.init(['Account', 'Product', 'UserProductAccount', 'UserAccount'])

        url = reverse('account-list')
        response = self.client.get(url, { 'name': 'mycode' }, format='json')
        account = response.data[0]
        self.assertTrue(len(account['user_accounts']) == 1, f'Account has incorrect number of user_accounts {account}')
        self.assertTrue(len(account['user_product_accounts']) == 2, f'Account has incorrect number of user_product_accounts {account}')
        upa = account['user_product_accounts'][0]
        self.assertTrue(upa['product'] == 'Dev Helium Dewar', f'Incorrect product on user product account {account}')

    def testFilterActive(self):
        '''
        Ensure that only active accounts can be returned when 'active' filter is applied.
        '''
        data.init(['Account'])

        url = reverse('account-list')
        response = self.client.get(url, { 'active': 'true' }, format='json')
        accounts = response.data
        self.assertTrue(len(accounts) == len(data.ACCOUNTS) - 1, 'active filter for account list did not work')

    def testFilterPO(self):
        '''
        Ensure that only POs are returned when account_type is set to PO.
        '''
        data.init(['Account'])
        expected_number_of_accts = reduce(lambda x,y: x + 1 if y.get('account_type') == 'PO' else x, data.ACCOUNTS, 0)
        expected_po_name = 'Alien PO'

        url = reverse('account-list')
        response = self.client.get(url, { 'account_type': 'PO' }, format='json')
        self.assertTrue(len(response.data) == expected_number_of_accts, f'Incorrect number of POs returned {response.data}')
        po_account = response.data[0]
        self.assertTrue(po_account['name'] == expected_po_name, f'Incorrect PO returned {po_account}')

    def testFilterExpenseCode(self):
        '''
        Ensure that only expense codes are returned when account_type is set to Expense Code.
        '''
        data.init(['Account'])
        expected_number_of_accts = reduce(lambda x,y: x + 1 if y.get('account_type') != 'PO' else x, data.ACCOUNTS, 0)

        url = reverse('account-list')
        response = self.client.get(url, { 'account_type': 'Expense Code' }, format='json')
        self.assertTrue(len(response.data) == expected_number_of_accts, f'Incorrect number of accts returned {response.data}')

    def testFilterByOrganizationSlug(self):
        '''
        Ensure that the correct accounts are returned using an organization slug.
        '''
        data.init(['Account'])
        organization_slug = 'Nobody Lab (a Harvard Laboratory)'
        expected_number_of_accts = reduce(lambda x,y: x + 1 if y.get('organization') == organization_slug else x, data.ACCOUNTS, 0)

        url = reverse('account-list')
        response = self.client.get(url, { 'organization': organization_slug }, format='json')
        self.assertTrue(len(response.data) == expected_number_of_accts, f'Incorrect number of accts returned {response.data}')

    def testFilterByOrganizationName(self):
        '''
        Ensure that the correct accounts are returned using an organization name.
        '''
        data.init(['Account'])
        organization_name = 'Nobody Lab'
        expected_number_of_accts = reduce(lambda x,y: x + 1 if organization_name in y.get('organization') else x, data.ACCOUNTS, 0)

        url = reverse('account-list')
        response = self.client.get(url, { 'organization': organization_name }, format='json')
        self.assertTrue(len(response.data) == expected_number_of_accts, f'Incorrect number of accts returned {response.data}')

    def testFilterByBadOrganizationName(self):
        '''
        Ensure that a 400 error is returned when a bad account name is used.
        '''
        data.init(['Account'])
        organization_name = 'Nonexistent Lab'

        url = reverse('account-list')
        response = self.client.get(url, { 'organization': organization_name }, format='json')
        self.assertTrue(response.status_code == status.HTTP_400_BAD_REQUEST, f'Incorrect response to bad org {response.status_code}')
