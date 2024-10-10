# -*- coding: utf-8 -*-

'''
Test Billing Contacts

Created on  2024-10-10

@author: Aaron Kitzmiller <aaron_kitzmiller@harvard.edu>
@copyright: 2024 The Presidents and Fellows of Harvard College.
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
from ifxbilling import models
from ifxbilling.notification import BillingRecordEmailGenerator

class TestBillingContacts(APITestCase):
    '''
    Test Billing Contact logic
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

    def testBillingReviewContact(self):
        '''
        Ensure that Billing Record Review and facility-specific Billing Record Review contacts are returned
        '''
        data.init()
        test_facility_name = 'Liquid Nitrogen Service'
        test_org = Organization.objects.get(name='Derpiston Lab')
        facility_specific_contact_role = f'Billing Record Review for {test_facility_name}'
        facility = models.Facility.objects.get(name=test_facility_name)

        breg = BillingRecordEmailGenerator(2024, 1, facility)
        contactables = breg.get_organization_contacts(test_org)
        self.assertEqual(len(contactables), 2)
        for contactable in contactables:
            self.assertTrue(contactable['type'] == 'Billing Record Review' or contactable['type']== facility_specific_contact_role)
