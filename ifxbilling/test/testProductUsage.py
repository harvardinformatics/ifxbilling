# -*- coding: utf-8 -*-

'''
Test ProductUsage

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
from django.utils import timezone
from ifxbilling.test import data
from ifxbilling.models import ProductUsage

class TestProductUsage(APITestCase):
    '''
    Test ProductUsage models and serializers
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

    def testProductUsageInsert(self):
        '''
        Insert a minimal ProductUsage.  Ensure that month and year get set.
        '''
        data.init('Product')
        year = 2021
        month = 2
        product_usage_data = {
            'product': 'Helium Dewar',
            'product_user': {
                'ifxid': data.USERS[0]['ifxid']
            },
            'quantity': 1,
            'start_date': timezone.make_aware(datetime(year, month, 1)),
            'description': 'Howdy',
        }
        url = reverse('productusage-list')
        response = self.client.post(url, product_usage_data, format='json')
        self.assertTrue(response.status_code == status.HTTP_201_CREATED, f'Incorrect response {response.data}')

        product_usage = ProductUsage.objects.get(id=response.data['id'])
        self.assertTrue(product_usage.year == year, f'Year not properly set {product_usage.year}')
        self.assertTrue(product_usage.month == month, f'Month not properly set {product_usage.year}')
        self.assertTrue(product_usage.description == 'Howdy', f'Incorrect product usage description {product_usage.description}')

    def testMissingProduct(self):
        '''
        Ensure that a ProductUsage with missing Product will fail
        '''
        data.init()
        product_usage_data = {
            'product_user': {
                'ifxid': data.USERS[0]['ifxid'],
            },
            'quantity': 1,
            'start_date': timezone.make_aware(datetime(2021, 2, 1))
        }
        url = reverse('productusage-list')
        response = self.client.post(url, product_usage_data, format='json')
        self.assertTrue(response.status_code == status.HTTP_400_BAD_REQUEST, f'Incorrect response {response.status_code}')
