# -*- coding: utf-8 -*-

'''
Test RateTiers

Created on  2024-03-18

@author: Aaron Kitzmiller <aaron_kitzmiller@harvard.edu>
@copyright: 2024 The Presidents and Fellows of Harvard College.
All rights reserved.
@license: GPL v2.0
'''
from decimal import Decimal
from rest_framework.test import APITestCase
from rest_framework.authtoken.models import Token
from rest_framework.reverse import reverse
from rest_framework import status
from django.contrib.auth import get_user_model
from ifxbilling.test import data
from ifxbilling import models


class TestRateTiers(APITestCase):
    '''
    Test RateTier models and serializers
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
        data.clearFiineProducts()

    def tearDown(self):
        data.clearFiineProducts()

    def testCreateEmptyRateTier(self):
        '''
        Test create rate tier with no rates
        '''
        name = 'Test Rate Tier'
        url = reverse('rate-tier-list')
        data = {
            'name': name,
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(models.RateTier.objects.filter(name=name).count(), 1, 'RateTier not created')

    def testCreateRateTier(self):
        '''
        Test create rate tier with rates
        '''
        name = 'Test Rate Tier'
        url = reverse('rate-tier-list')
        data = {
            'name': name,
            'rates': [
                {
                    'name': 'Helium Dewar Internal Rate',
                    'description': 'fy99',
                    'decimal_price': Decimal('1000'),
                    'units': 'Dewar',
                    'is_active': True
                },
                {
                    'name': 'Helium Dewar External Rate',
                    'decimal_price': Decimal('10000'),
                    'units': 'Dewar',
                    'is_active': True
                }
            ]
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(models.RateTier.objects.filter(name=name).count(), 1, 'RateTier not created')
        self.assertEqual(models.RateTier.objects.get(name=name).rate_set.count(), 2, 'Rates not created')
