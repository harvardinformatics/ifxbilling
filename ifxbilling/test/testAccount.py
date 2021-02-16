# -*- coding: utf-8 -*-

'''
Test Account

Created on  2021-02-10

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
from django.contrib.auth.models import Group
from django.conf import settings
from ifxuser.models import Organization
from ifxbilling.models import Account
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

    def testAccountInsert(self):
        '''
        Insert a minimal account.
        Default account_type 'Expense Code' should be set.
        active should be False, and valid_from should be now()
        '''
        data.init()
        account_data = {
            'code': '234-234234-32-342-4',
            'organization': 'Kitzmiller Lab (a Harvard Laboratory)',
            'name': 'mycode',
            'root': '1234'
        }
        url = reverse('account-list')
        response = self.client.post(url, account_data, format='json')
        self.assertTrue(response.status_code=status.HTTP_201_CREATED, f'Incorrect response status: {response.status_code}')