# -*- coding: utf-8 -*-

'''
Test data

Created on  2021-02-10

@author: Aaron Kitzmiller <aaron_kitzmiller@harvard.edu>
@copyright: 2021 The Presidents and Fellows of Harvard College.
All rights reserved.
@license: GPL v2.0
'''
from copy import deepcopy
from ifxuser.models import Organization, UserAffiliation
from django.contrib.auth import get_user_model
from fiine.client import API as FiineAPI
from ifxbilling import models


ORGS = [
    {
        'name': 'Kitzmiller Lab',
        'rank': 'lab',
        'org_tree': 'Harvard',
    },
    {
        'name': 'Nobody Lab',
        'rank': 'lab',
        'org_tree': 'Harvard',
    }
]

USERS = [
    {
        'username': 'sslurpiston',
        'first_name': 'Slurpy',
        'last_name': 'Slurpiston',
        'full_name': 'Slurpy Slurpiston',
        'email': 'sslurpiston@gmail.com',
        'ifxid': 'IFXIDX0000000001'
    },
    {
        'username': 'dderpiston',
        'first_name': 'Derpy',
        'last_name': 'Derpiston',
        'full_name': 'Derpy Derpiston',
        'email': 'dderpiston@gmail.com',
        'ifxid': 'IFXIDX0000000002'
    },
    {
        'username': 'mhankin',
        'first_name': 'Markos',
        'last_name': 'Hankin',
        'full_name': 'Markos Hankin',
        'email': 'mhankin@gmail.com',
        'ifxid': 'IFXIDX0000000003',
        'is_staff': True,
    },
]

ACCOUNTS = [
    {
        'code': '370-31230-8100-000775-600200-0000-44075',
        'organization': 'Kitzmiller Lab (a Harvard Laboratory)',
        'name': 'mycode',
        'root': '12345',
    }
]

PRODUCTS = [
    {
        'product_number': 'IFXP0000000001',
        'product_name': 'Helium Dewar',
        'product_description': 'A dewar of helium',
        'rates': [
            {
                'name': 'Harvard Internal',
                'price': 100,
                'units': 'ea',
            }
        ]
    }
]

PRODUCT_USAGES = [
    {
        'product': 'Helium Dewar',
        'product_user': 'Slurpy Slurpiston',
        'quantity': 1,
        'units': 'ea',
    }
]

def clearTestData():
    '''
    Clear all of the data from the database.  Called during setUp
    '''
    models.BillingRecord.objects.all().delete()
    models.Account.objects.all().delete()
    models.ProductUsage.objects.all().delete()
    models.Product.objects.all().delete()

    Organization.objects.all().delete()
    for user_data in USERS:
        try:
            get_user_model().objects.get(ifxid=user_data['ifxid']).delete()
        except get_user_model().DoesNotExist:
            pass

    try:
        get_user_model().objects.filter(username='john', email='john@snow.com').delete()
    except Exception:
        pass

    # Clear stuff from fiine
    products = FiineAPI.listProducts()
    for product in products:
        FiineAPI.deleteProduct(product_number=product.product_number)




def init(types=None):
    '''
    Initialize organizations and users.  If types is set, initialize those as well.
    types will be processed in order, so child objects will need to be after parents.
    '''
    for user_data in USERS:
        get_user_model().objects.create(**user_data)
    for org_data in ORGS:
        Organization.objects.create(**org_data)
    org = Organization.objects.get(name='Kitzmiller Lab')
    for user in get_user_model().objects.all():
        if user.username in ('sslurpiston', 'dderpiston'):
            UserAffiliation.objects.create(user=user, organization=org, role='member')

    if types:
        if 'Account' in types:
            for account_data in ACCOUNTS:
                data_copy = deepcopy(account_data)
                data_copy['organization'] = Organization.objects.get(slug=account_data['organization'])
                models.Account.objects.create(**data_copy)
        if 'Product' in types:
            for product_data in PRODUCTS:
                data_copy = deepcopy(product_data)
                rates_data = data_copy.pop('rates', None)
                product = models.Product.objects.create(**data_copy)
                for rate_data in rates_data:
                    rate_data['product'] = product
                    models.Rate.objects.create(**rate_data)
        if 'ProductUsage' in types:
            for product_usage_data in PRODUCT_USAGES:
                data_copy = deepcopy(product_usage_data)
                data_copy['product'] = models.Product.objects.get(product_name=product_usage_data['product'])
                data_copy['product_user'] = get_user_model().objects.get(full_name=product_usage_data['product_user'])
                models.ProductUsage.objects.create(**data_copy)
