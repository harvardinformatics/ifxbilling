# -*- coding: utf-8 -*-

'''
Test calculateBillingMonth

Created on  2022-02-15

@author: Aaron Kitzmiller <aaron_kitzmiller@harvard.edu>
@copyright: 2022 The Presidents and Fellows of Harvard College.
All rights reserved.
@license: GPL v2.0
'''
from rest_framework.test import APITestCase
from rest_framework.authtoken.models import Token
from django.contrib.auth import get_user_model
from ifxbilling.test import data
from ifxbilling.calculator import calculateBillingMonth
from ifxbilling import models

class TestCalculateBillingMonth(APITestCase):
    '''
    Test calculateBillingMonth
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

    def testCalculateSpecificProduct(self):
        '''
        Ensure that calculation of billing records can be limited to a specific product
        '''
        data.init(types=['Account', 'Product', 'ProductUsage', 'UserProductAccount'])

        facility = models.Facility.objects.get(name='Helium Recovery Service')

        # Values on Helium Balloon
        year = 2022
        month = 1
        (successes, errors) = calculateBillingMonth(month, year, facility, product_names=['Dev Helium Balloon'])
        self.assertTrue(successes == 2, f'Incorrect result {successes} {errors}')
        self.assertTrue(len(errors) == 0, f'Errors returned! {errors}')

        year = 2021
        month = 3
        (successes, errors) = calculateBillingMonth(month, year, facility, product_names=['Dev Helium Dewar'])
        self.assertTrue(successes == 1, f'Incorrect result {successes} {errors}')
        self.assertTrue(len(errors) == 0, f'Errors returned! {errors}')

    def testBadProduct(self):
        '''
        Ensure that calculation of billing records for a bad product will fail
        '''
        data.init(types=['Account', 'Product', 'ProductUsage', 'UserProductAccount'])

        facility = models.Facility.objects.get(name='Helium Recovery Service')

        # Values on Helium Balloon
        year = 2022
        month = 1
        self.assertRaisesMessage(Exception, 'Product does not exist', calculateBillingMonth, month, year, facility, product_names=['Not a product'])
