# -*- coding: utf-8 -*-

'''
Test BillingRecordGenerator

Created on  2022-08-06

@author: Meghan Correa <mportermahoney@g.harvard.edu>
@copyright: 2022 The Presidents and Fellows of Harvard College.
All rights reserved.
@license: GPL v2.0
'''
from rest_framework.test import APITestCase
from rest_framework.authtoken.models import Token
from rest_framework.reverse import reverse
from rest_framework import status
from django.contrib.auth import get_user_model
from django.utils import timezone
from ifxbilling.test import data
from ifxbilling.billing_record_generator import BillingRecordGenerator
from ifxbilling import models

class TestCalculator(APITestCase):
    '''
    Test BillingRecordGenerator
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

    def testGenerator(self):
        '''
        Ensure that a simple ProductUsage can be selected and converted to a BillingRecord.
        '''
        data.init(types=['Account', 'Product', 'ProductUsage', 'UserAccount'])
        gen = BillingRecordGenerator('Helium Recovery Service')
        start_date = datetime.strptime('2021-02-01', gen.DATE_FORMAT)
        results = gen.generate_billing_records(start_date)
        print(results)
        self.assertTrue(len(brs) == 1, f'Incorrect number of billing records returned {brs}')

        br = brs[0]
        expected_charge = 100
        self.assertTrue(br.charge == expected_charge, f'Incorrect charge {br}')

        price = product_usage.product.rate_set.first().price
        units = product_usage.product.rate_set.first().units
        self.assertTrue(br.rate == f'{price} {units}', f'Incorrect billing record rate {br.rate}')
