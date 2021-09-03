# -*- coding: utf-8 -*-

'''
Test updateUserAccounts

Created on  2021-05-06

@author: Aaron Kitzmiller <aaron_kitzmiller@harvard.edu>
@copyright: 2021 The Presidents and Fellows of Harvard College.
All rights reserved.
@license: GPL v2.0
'''
from copy import deepcopy
from rest_framework.test import APITestCase
from rest_framework.authtoken.models import Token
from rest_framework.reverse import reverse
from rest_framework import status
from django.contrib.auth import get_user_model
from django.utils import timezone
from ifxuser.models import Organization
from ifxbilling.test import data
from ifxbilling.fiine import updateUserAccounts, updateProducts
from ifxbilling import models


class TestUpdateUserAccounts(APITestCase):
    '''
    Test updateUserAccounts
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

    def testUpdateUserAccounts(self):
        '''
        Ensure that UserAccounts can be updated from fiine, including creation of new Account
        '''
        data.init(types=['User', 'Account', 'Organization'])
        updateProducts()

        user = get_user_model().objects.get(full_name=data.FIINE_TEST_USER)
        updated_user = updateUserAccounts(user)
        user_accounts = updated_user.useraccount_set.all()
        self.assertTrue(len(user_accounts) == 1, f'Incorrect number of user_accounts {len(user_accounts)}')

    def testUpdateUserAccountView(self):
        '''
        Ensure that UserAccounts can be updated from fiine, including creation of new Account, via view
        '''
        data.init(types=['User', 'Account', 'Organization'])
        updateProducts()

        user = get_user_model().objects.get(full_name=data.FIINE_TEST_USER)
        url = reverse('update-user-accounts')
        response = self.client.post(url, data={'ifxids': [user.ifxid]}, format='json')
        self.assertTrue(response.status_code == status.HTTP_200_OK, f'Incorrect response from view {response}')

        user = get_user_model().objects.get(full_name=data.FIINE_TEST_USER)
        user_accounts = user.useraccount_set.all()

        self.assertTrue(len(user_accounts) == 1, f'Incorrect number of user_accounts {len(user_accounts)}')

    def testUpdateAllUserAccountView(self):
        '''
        Ensure that all UserAccounts can be updated from fiine, including creation of new Account, via view
        '''
        data.init(types=['User', 'Account', 'Organization'])
        updateProducts()

        url = reverse('update-user-accounts')
        response = self.client.post(url, data={}, format='json')

        # There are several users in ifxbilling test database that are not in Fiine
        # self.assertTrue(response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR, f'Incorrect response from view {response}')
        self.assertTrue(response.data['successes'] == 3, f'Incorrect response from view {response.data}')

        user = get_user_model().objects.get(full_name=data.FIINE_TEST_USER)
        user_accounts = user.useraccount_set.all()

        self.assertTrue(len(user_accounts) == 1, f'Incorrect number of user_accounts {len(user_accounts)}')

    def testUpdateUserAccountIsValid(self):
        '''
        Ensure that existing UserAccount can have is_valid flag changed when fiine updates
        '''
        data.init(types=['User', 'Organization'])
        updateProducts()
        user = get_user_model().objects.get(full_name=data.FIINE_TEST_USER)
        updateUserAccounts(user)

        account = models.Account.objects.get(name=data.FIINE_TEST_ACCOUNT['name'])

        user_account, created = models.UserAccount.objects.get_or_create(account=account, user=user)
        user_account.is_valid = False
        user_account.save()

        updated_user = updateUserAccounts(user)
        user_accounts = updated_user.useraccount_set.all()
        self.assertTrue(len(user_accounts) == 1, f'Incorrect number of user_accounts {len(user_accounts)}')
        self.assertTrue(user_accounts[0].is_valid, f'is_valid flag not overridden {user_accounts}')

    def testUpdateUserProductAccount(self):
        '''
        Ensure that a UserProductAccount can be updated from Fiine
        '''
        data.init(types=['User', 'Organization'])
        user = get_user_model().objects.get(full_name=data.FIINE_TEST_USER)

        # test_account_data = deepcopy(data.FIINE_TEST_ACCOUNT)
        # test_account_data['organization'] = Organization.objects.get(slug=test_account_data['organization'])
        # account = models.Account.objects.create(**test_account_data)

        # Get products from Fiine
        updateProducts()

        # Update user accounts
        updated_user = updateUserAccounts(user)
        user_product_accounts = updated_user.userproductaccount_set.all()
        self.assertTrue(len(user_product_accounts) == 2, f'Incorrect number of user_product_accounts {len(user_product_accounts)}')
