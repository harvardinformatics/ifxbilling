# -*- coding: utf-8 -*-

'''
Test Product

Created on  2021-02-10

@author: Aaron Kitzmiller <aaron_kitzmiller@harvard.edu>
@copyright: 2021 The Presidents and Fellows of Harvard College.
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
from ifxbilling.models import Product


class TestProduct(APITestCase):
    '''
    Test Product models and serializers
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

    def testProductInsert(self):
        '''
        Insert a minimal Product with a parent.  Fetch by parent product number.
        '''
        data.init(['Product'])
        pp_data = data.PRODUCTS[0]
        rate_count = len(pp_data['rates'])
        rate_name = pp_data['rates'][0]['name']
        parent_product = Product.objects.get(product_name=pp_data['product_name'])
        product_name = 'Helium Dewar Test'
        object_code_category = 'Laboratory Consumables'
        product_category = 'Stuff'
        product_data = {
            'product_name': product_name,
            'product_description': 'A dewar of helium',
            'facility': 'Liquid Nitrogen Service',
            'billable': True,
            'parent': {
                'product_number': parent_product.product_number
            },
            'object_code_category': object_code_category,
            'product_category': product_category,
            'product_organization': {
                'name': 'Kitzmiller Lab',
                'slug': 'Kitzmiller Lab (a Harvard Laboratory)',
                'ifxorg': 'IFXORGX00000000G',
            }
        }
        url = reverse('product-list')
        response = self.client.post(url, product_data, format='json')
        product = Product.objects.get(product_name=product_name)
        self.assertTrue(response.status_code == status.HTTP_201_CREATED, f'Incorrect response status: {response.data}')
        self.assertTrue(product.billing_calculator == 'ifxbilling.calculator.BasicBillingCalculator', f'Incorrect response data {response.data}')
        self.assertTrue(product.product_number, f'Product number not set {response.data}')
        self.assertTrue(product.object_code_category == object_code_category, f'Incorrect object code category {response.data}')
        self.assertTrue(product.product_category == product_category, f'Incorrect product category {response.data}')

        # Rates should be parent rates
        rates = product.get_active_rates()
        self.assertTrue(len(rates) == rate_count, f'Incorrect number of rates {rates}')
        self.assertTrue(rates[0].name == rate_name, f'Incorrect rate name {rates[0]}')

        # Return child product using parent number
        response = self.client.get(url, {'parent_number': parent_product.product_number}, format='json')
        self.assertTrue(response.status_code == status.HTTP_200_OK, f'Incorrect response status: {response.data}')
        self.assertTrue(len(response.data) == 1, f'Incorrect response data {response.data}')
        self.assertTrue(response.data[0]['product_name'] == product_name, f'Incorrect response data {response.data}')


    def testProductUpdate(self):
        '''
        Ensure that you can update a Product
        '''
        data.init()
        product_data = {
            'product_name': 'Helium Dewar Test',
            'product_description': 'A dewar of helium',
            'facility': 'Liquid Nitrogen Service',
            'billable': True,
        }
        url = reverse('product-list')
        response = self.client.post(url, product_data, format='json')
        product_id = response.data['id']
        self.assertTrue(response.status_code == status.HTTP_201_CREATED, f'Incorrect response status: {response.data}')

        new_description = 'new description'
        product_data = {
            'product_name': 'Helium Dewar Test',
            'product_description': new_description,
            'facility': 'Liquid Nitrogen Service',
            'billable': True,
        }
        url = reverse('product-detail', kwargs={ 'pk': product_id })
        response = self.client.put(url, product_data, format='json')

        self.assertTrue(response.data['product_description'] == new_description, f'Incorrect response data {response.data}')

    def testMissingProductName(self):
        '''
        Ensure insertion fails without product name
        '''
        data.init()
        product_data = {
            'product_description': 'A dewar of helium',
            'facility': 'Liquid Nitrogen Service',
            'billable': True,
        }
        url = reverse('product-list')
        response = self.client.post(url, product_data, format='json')
        self.assertTrue(response.status_code == status.HTTP_400_BAD_REQUEST, f'Incorrect response status: {response.data}')
        self.assertTrue('This field is required' in str(response.data['product_name']), f'Incorrect response data {response.data}')

    def testMissingProductDescription(self):
        '''
        Ensure insertion fails without product name
        '''
        data.init()
        product_data = {
            'product_name': 'Helium Dewar Test',
            'facility': 'Liquid Nitrogen Service',
            'billable': True,
        }
        url = reverse('product-list')
        response = self.client.post(url, product_data, format='json')
        self.assertTrue(response.status_code == status.HTTP_400_BAD_REQUEST, f'Incorrect response status: {response.data}')
        self.assertTrue('This field is required' in str(response.data['product_description']), f'Incorrect response data {response.data}')

    def testInsertProductWithRates(self):
        '''
        Ensure that a product can be inserted with rates
        '''
        data.init()
        product_data = {
            'product_name': 'Helium Dewar Test',
            'product_description': 'A dewar of helium',
            'facility': 'Liquid Nitrogen Service',
            'billable': True,
            'rates': [
                {
                    'name': 'Helium Dewar Internal Rate',
                    'description': 'fy99',
                    'price': 1000,
                    'units': 'Dewar',
                    'is_active': True
                },
                {
                    'name': 'Helium Dewar External Rate',
                    'price': 10000,
                    'units': 'Dewar',
                    'is_active': True
                }
            ]
        }
        url = reverse('product-list')
        response = self.client.post(url, product_data, format='json')
        self.assertTrue(response.status_code == status.HTTP_201_CREATED, f'Incorrect response status: {response.data}')

        product = Product.objects.get(id=response.data['id'])
        # Make sure the rates are saved
        self.assertTrue(len(product.rate_set.all()) == 2, f'Rates were not properly saved {product}')

    def testUpdateProductRatePrice(self):
        '''
        Ensure that a product rates cannot be updated
        '''
        data.init()
        product_data = {
            'product_name': 'Helium Dewar Test',
            'product_description': 'A dewar of helium',
            'facility': 'Liquid Nitrogen Service',
            'billable': True,
            'rates': [
                {
                    'name': 'Helium Dewar Internal Rate',
                    'decimal_price': Decimal('1000'),
                    'units': 'Dewar',
                    'is_active': True
                },
                {
                    'name': 'Helium Dewar External Rate',
                    'description': 'fy00',
                    'decimal_price': Decimal('1000'),
                    'units': 'Dewar',
                    'is_active': True
                }
            ]
        }
        url = reverse('product-list')
        response = self.client.post(url, product_data, format='json')
        self.assertTrue(response.status_code == status.HTTP_201_CREATED, f'Incorrect response status: {response.data}')

        # Fetch the existing object
        url = reverse('product-detail', kwargs={'pk': response.data['id']})
        response = self.client.get(url, format='json')
        self.assertTrue(response.data['product_name'] == 'Helium Dewar Test', f'Incorrect response {response.data}')
        product_data = response.data
        for i, rate in enumerate(product_data['rates']):
            if rate['name'] == 'Helium Dewar External Rate':
                self.assertTrue(Decimal(rate['decimal_price']) == Decimal('1000'), f'Rate was incorrectly saved {rate}')
                product_data['rates'][i]['decimal_price'] = Decimal('9999')

        # Update object
        response = self.client.put(url, product_data, format='json')
        self.assertTrue(response.status_code == status.HTTP_400_BAD_REQUEST, f'Incorrect response code {response.status_code}')

    def testUpdateProductRateIsActive(self):
        '''
        Ensure that a product rate is active flag can be updated
        '''
        data.init()
        product_data = {
            'product_name': 'Helium Dewar Test',
            'product_description': 'A dewar of helium',
            'facility': 'Liquid Nitrogen Service',
            'billable': True,
            'rates': [
                {
                    'name': 'Helium Dewar Internal Rate',
                    'price': 1000,
                    'decimal_price': Decimal('10.00'),
                    'units': 'Dewar',
                    'is_active': True
                },
                {
                    'name': 'Helium Dewar External Rate',
                    'price': 10000,
                    'decimal_price': Decimal('100.00'),
                    'units': 'Dewar',
                    'is_active': True
                }
            ]
        }
        url = reverse('product-list')
        response = self.client.post(url, product_data, format='json')
        self.assertTrue(response.status_code == status.HTTP_201_CREATED, f'Incorrect response status: {response.data}')

        # Fetch the existing object
        url = reverse('product-detail', kwargs={'pk': response.data['id']})
        response = self.client.get(url, format='json')
        self.assertTrue(response.data['product_name'] == 'Helium Dewar Test', f'Incorrect response {response.data}')
        product_data = response.data
        for i, rate in enumerate(product_data['rates']):
            if rate['name'] == 'Helium Dewar External Rate':
                self.assertTrue(rate['is_active'], f'Rate was incorrectly saved {rate}')
                product_data['rates'][i]['is_active'] = False

        # Update object
        response = self.client.put(url, product_data, format='json')
        self.assertTrue(response.status_code == status.HTTP_200_OK, f'Incorrect response code {response.status_code}')

    def testRemoveProductRate(self):
        '''
        Ensure that a product rates cannot be removed
        '''
        data.init()
        product_data = {
            'product_name': 'Helium Dewar Test',
            'product_description': 'A dewar of helium',
            'facility': 'Liquid Nitrogen Service',
            'billable': True,
            'rates': [
                {
                    'name': 'Helium Dewar Internal Rate',
                    'price': 1000,
                    'units': 'Dewar',
                    'is_active': True
                },
                {
                    'name': 'Helium Dewar External Rate',
                    'price': 10000,
                    'units': 'Dewar',
                    'is_active': True
                }
            ]
        }
        url = reverse('product-list')
        response = self.client.post(url, product_data, format='json')
        self.assertTrue(response.status_code == status.HTTP_201_CREATED, f'Incorrect response status: {response.data}')

        # Fetch the existing object
        url = reverse('product-detail', kwargs={'pk': response.data['id']})
        response = self.client.get(url, format='json')
        self.assertTrue(len(response.data['rates']) == 2, f'Incorrect response {response.data}')
        product_data = response.data
        for i, rate in enumerate(product_data['rates']):
            if rate['name'] == 'Helium Dewar External Rate':
                del product_data['rates'][i]

        # Update object
        response = self.client.put(url, product_data, format='json')
        self.assertTrue(response.status_code == status.HTTP_400_BAD_REQUEST, f'Incorrect response code {response.status_code}')
