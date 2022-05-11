# -*- coding: utf-8 -*-

'''
ifxbilling initDev

Initializes development data for a system, include some
dev users and application tokens.

Created on  2019-12-23

@author: Aaron Kitzmiller <aaron_kitzmiller@harvard.edu>
@copyright: 2019 The Presidents and Fellows of Harvard College.
All rights reserved.
@license: GPL v2.0
'''
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
from ifxuser.models import Organization
from ifxbilling.init import main as init_production
from ifxbilling.init import USER_APP_MODEL
from ifxbilling.models import Product, Facility
from ifxuser.models import Organization, Contact, OrganizationContact



def main():
    '''
    Run dev data initialization
    '''
    modelsForFixture = init_production()
    modelsForFixture[USER_APP_MODEL].extend(initUsers())
    modelsForFixture['authtoken.Token'] = initTokens()
    modelsForFixture['ifxbilling.Facility'] = initFacilities()
    modelsForFixture['ifxbilling.Product'] = initProducts()
    modelsForFixture['ifxuser.Organization'] = initOrganizations()
    modelsForFixture['ifxuser.Contact'] = initContacts()
    modelsForFixture['ifxuser.OrganizationContact'] = initOrganizationContacts()
    return modelsForFixture

def initUsers():
    '''
    Setup veradmin and application user tokens
    '''
    pks = []
    users = [
        {
            'username': 'veradmin',
            'first_name': 'Vera D.',
            'last_name': 'Min',
            'is_active': True,
            'is_superuser': True,
            'is_staff': True,
            'ifxid': 'IFXID0000000001'
        },
    ]
    for userdata in users:
        (obj, created) = get_user_model().objects.get_or_create(**userdata)
        pks.append(obj.pk)

    return pks


def initTokens():
    '''
    Set tokens to common values
    '''
    pks = []
    tokens = [
        {
            'username': 'veradmin',
            'token': 'd30404ee8abec2fd9268b86c36ac23637649b0e9',
        },
    ]
    for tokendata in tokens:
        user = get_user_model().objects.get(username=tokendata['username'])
        (obj, created) = Token.objects.get_or_create(user=user)
        Token.objects.filter(user=user).update(key=tokendata['token'])
        pks.append(obj.pk)

    return pks

def initFacilities():
    '''
    Create some dummy facilites
    '''
    pks = []
    facilities = [
        {
            'name': 'Liquid Nitrogen Service',
            'application_username': 'hers',
            'credit_code': '370-32556-8254-018485-627258-0000-00000',
            'invoice_prefix': 'LN2'
        },
        {
            'name': 'Helium Recovery Service',
            'application_username': 'hers',
            'credit_code': '370-32556-8254-018485-627247-0000-00000',
            'invoice_prefix': 'HE'
        },
        {
            'name': 'Research Computing Storage',
            'application_username': 'coldfront',
            'credit_code': '370-32760-8254-018541-629404-0000-00000',
            'invoice_prefix': 'RC'
        },
    ]
    for facility in facilities:
        (obj, created) = Facility.objects.get_or_create(**facility)
        pks.append(obj.pk)
    return pks

def initProducts():
    '''
    This is really just for an ifxbilling test
    '''
    pks = []
    products = [
        # {
        #     'product_name': 'Test Product',
        #     'product_number': 'IFXP0000000001',
        #     'product_description': 'Test Product',
        #     'facility': 'Liquid Nitrogen Service'
        # }
    ]
    for product_data in products:
        product_data['facility'] = Facility.objects.get(name=product_data.pop('facility'))
        (obj, created) = Product.objects.get_or_create(**product_data)
        pks.append(obj.pk)
    return pks

def initOrganizations():
    '''
    This is really just for an expense code request test
    '''
    pks = []
    orgs = [
        {
            'name': 'Derpiston Lab',
            'rank': 'lab',
            'org_tree': 'Test',
            'ifxorg': 'IFXORG0000000001'
        },
        {
            'name': 'Kitzmiller Lab',
            'rank': 'lab',
            'org_tree': 'Harvard',
            'ifxorg': 'IFXORGX000000002'
        },
        {
            'name': 'Nobody Lab',
            'rank': 'lab',
            'org_tree': 'Harvard',
            'ifxorg': 'IFXORGX000000003'
        },
    ]
    for org_data in orgs:
        (obj, created) = Organization.objects.get_or_create(**org_data)
        pks.append(obj.pk)
    return pks

def initContacts():
    '''
    Setup veradmin as a contact
    '''
    pks = []
    contacts = [
        {
            'name': 'Vera D. Min',
            'ifxcon': 'IFXC0000000001',
            'is_valid': True,
            'type': 'Email',
            'detail': 'ifx@fas.harvard.edu',
        },
    ]
    for contactdata in contacts:
        (obj, created) = Contact.objects.get_or_create(**contactdata)
        pks.append(obj.pk)

    return pks

def initOrganizationContacts():
    '''
    Setup veradmin labadmin for Derpiston
    '''
    pks = []
    contact = Contact.objects.get(name='Vera D. Min')
    org = Organization.objects.get(name='Derpiston Lab')
    org_contacts = [
        {
            'contact': contact,
            'role': 'Lab Admin',
            'organization': org
        },
    ]
    for org_contactdata in org_contacts:
        (obj, created) = OrganizationContact.objects.get_or_create(**org_contactdata)
        pks.append(obj.pk)

    return pks
