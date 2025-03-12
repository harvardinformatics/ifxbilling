# -*- coding: utf-8 -*-

'''
Test data

Created on  2021-02-10

@author: Aaron Kitzmiller <aaron_kitzmiller@harvard.edu>
@copyright: 2021 The Presidents and Fellows of Harvard College.
All rights reserved.
@license: GPL v2.0
'''
from datetime import datetime
from copy import deepcopy
from ifxuser.models import Organization, Contact, OrganizationContact
from django.utils import timezone
from django.contrib.auth import get_user_model
from fiine.client import API as FiineAPI
from ifxbilling import models


FIINE_TEST_USER = 'Slurpy Slurpiston'  # Full name of Fiine Person that is also an ifxbilling test person
FIINE_TEST_ACCOUNT = {
    'organization': 'Kitzmiller Lab (a Harvard Laboratory)',
    'name': 'Another code',
    'code': '370-99999-8100-000775-600200-0000-44075',
}
FIINE_TEST_PRODUCT = 'Test Product'

FACILITIES = [
    {
        'ifxfac': 'IFXFAC0000000002',
        'name': 'Helium Recovery Service',
        'application_username': 'hers',
        'credit_code': '370-32556-8254-018485-627247-0000-00000',
        'invoice_prefix': 'HE',
        'object_code': '6600',
        'facility_codes': [
            {
                'credit_code': '370-32556-8254-018485-627247-0000-00000',
                'debit_object_code_category': 'Laboratory Consumables',
            }
        ],
    },
    {
        'ifxfac': 'IFXFAC0000000003',
        'name': 'Liquid Nitrogen Service',
        'application_username': 'hers',
        'credit_code': '370-32556-8254-018485-627258-0000-00000',
        'invoice_prefix': 'LN2',
        'object_code': '6600',
        'facility_codes': [
            {
                'credit_code': '370-32556-8254-018485-627258-0000-00000',
                'debit_object_code_category': 'Laboratory Consumables',
            }
        ],
    },
]

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
    },
    {
        'name': 'Derpiston Lab',
        'rank': 'lab',
        'org_tree': 'Harvard',
        'contacts': [
            {
                'role': 'PI',
                'contact': {
                    'type': 'Email',
                    'detail': 'pi@ajk.com',
                }
            },
            {
                'role': 'Lab Manager',
                'contact': {
                    'type': 'Email',
                    'detail': 'lab_manager@ajk.com',
                }
            },
            {
                'role': 'Billing Record Review',
                'contact': {
                    'type': 'Email',
                    'detail': 'billing_record_review@ajk.com',
                }
            },
            {
                'role': 'Billing Record Review for Helium Recovery Service',
                'contact': {
                    'type': 'Email',
                    'detail': 'billing_record_review_for_helium_recovery_service@ajk.com',
                }
            },
            {
                'role': 'Billing Record Review for Liquid Nitrogen Service',
                'contact': {
                    'type': 'Email',
                    'detail': 'billing_record_review_for_liquid_nitrogen_service@ajk.com',
                }
            },
        ]
    },
    {
        'name': 'Aliens',
        'rank': 'company',
        'org_tree': 'Harvard'
    },
    {
        'name': 'Faculty of Arts and Sciences',
        'rank': 'school',
        'org_tree': 'Harvard',
    },
    {
        'name': 'Liquid Nitrogen Service',
        'rank': 'facility',
        'org_tree': 'Harvard',
        'contacts': [
            {
                'role': 'Facility Invoice',
                'contact': {
                    'type': 'Email',
                    'detail': 'facility_invoice_contact@ajk.com',
                }
            }
        ]
    }
]

USERS = [
    {
        'username': 'sslurpiston',
        'first_name': 'Slurpy',
        'last_name': 'Slurpiston',
        'full_name': 'Slurpy Slurpiston',
        'email': 'sslurpiston@gmail.com',
        'ifxid': 'IFXIDC00000000D',
        'primary_affiliation': 'Kitzmiller Lab',
    },
    {
        'username': 'dderpiston',
        'first_name': 'Derpy',
        'last_name': 'Derpiston',
        'full_name': 'Derpy Derpiston',
        'email': 'dderpiston@gmail.com',
        'ifxid': 'IFXIDC00000000E',
        'primary_affiliation': 'Kitzmiller Lab',
    },
    {
        'username': 'mhankin',
        'first_name': 'Markos',
        'last_name': 'Hankin',
        'full_name': 'Markos Hankin',
        'email': 'mhankin@gmail.com',
        'ifxid': 'IFXIDC00000000F',
        'is_staff': True,
        'primary_affiliation': 'Kitzmiller Lab',
    },
]

ACCOUNTS = [
    {
        'ifxacct': 'IFXACCT9900000001',
        'code': '370-11111-6600-000775-600200-0000-44075',
        'organization': 'Kitzmiller Lab (a Harvard Laboratory)',
        'name': 'Alternate code',
        'root': '44075',
        'active': True,
        'valid_from': '2000-01-01',
        'ifxacct': 'IFXACCT9900000001',
        'expiration_date': '2100-01-01',
    },
    {
        'ifxacct': 'IFXACCT9900000002',
        'code': '370-31230-6600-000775-600200-0000-44075',
        'organization': 'Kitzmiller Lab (a Harvard Laboratory)',
        'name': 'mycode',
        'root': '12345',
        'active': True,
        'valid_from': '2000-01-01',
        'ifxacct': 'IFXACCT9900000002',
        'expiration_date': '2100-01-01',
    },
    {
        'ifxacct': 'IFXACCT9900000004',
        'code': '370-99999-6600-000775-600200-0000-44075',
        'organization': 'Kitzmiller Lab (a Harvard Laboratory)',
        'name': 'Another code',
        'root': '44075',
        'active': True,
        'valid_from': '2000-01-01',
        'ifxacct': 'IFXACCT9900000004',
        'expiration_date': '2100-01-01',
    },
    {
        'ifxacct': 'IFXACCT9900000003',
        'code': '370-11111-6600-000775-600200-0000-33333',
        'organization': 'Nobody Lab (a Harvard Laboratory)',
        'name': 'Nobody lab code',
        'root': '33333',
        'active': True,
        'valid_from': '2000-01-01',
        'ifxacct': 'IFXACCT9900000003',
        'expiration_date': '2100-01-01',
    },
    {
        'code': '370-11111-6600-000775-600200-0000-99999',
        'organization': 'Nobody Lab (a Harvard Laboratory)',
        'name': 'inactive code',
        'root': '99999',
        'active': False,
        'valid_from': '2000-01-01',
        'ifxacct': 'IFXACCT9990000001',
        'expiration_date': '2100-01-01',
    },
    {
        'code': 'XFC1298w4r',
        'organization': 'Aliens (a Harvard Company)',
        'name': 'Alien PO',
        'active': True,
        'valid_from': '2000-01-01',
        'expiration_date': '2100-01-01',
        'account_type': 'PO',
    },
]

USER_ACCOUNTS = [
    {
        'user': 'Slurpy Slurpiston',
        'account': 'mycode',
        'is_valid': True,
    }
]

USER_PRODUCT_ACCOUNTS = [
    {
        'user': 'Slurpy Slurpiston',
        'account': 'Alternate code',
        'product': 'Dev Helium Dewar',
        'percent': 25,
        'is_valid': True,
    },
    {
        'user': 'Slurpy Slurpiston',
        'account': 'Another code',
        'product': 'Dev Helium Dewar',
        'percent': 75,
        'is_valid': True,
    },
    {
        'user': 'Markos Hankin',
        'account': 'Alternate code',
        'product': 'Dev Helium Dewar',
        'percent': 50,
        'is_valid': True,
    },
    {
        'user': 'Markos Hankin',
        'account': 'mycode',
        'product': 'Dev Helium Dewar',
        'percent': 50,
        'is_valid': True,
    },
    {
        'user': 'Markos Hankin',
        'account': 'mycode',
        'product': 'Dev Helium Balloon',
        'percent': 100,
        'is_valid': True,
    },
]

PRODUCTS = [
    {
        'product_number': 'IFXPX000000001',
        'product_name': 'Dev Helium Dewar',
        'product_description': 'A dewar of helium',
        'rates': [
            {
                'name': 'Harvard Internal',
                'price': 100,
                'decimal_price': 100.00,
                'units': 'ea',
            }
        ],
        'facility': 'Helium Recovery Service',
        'object_code_category': 'Laboratory Consumables',
    },
    {
        'product_number': 'IFXPX000000002',
        'product_name': 'Dev Helium Balloon',
        'product_description': 'A balloon of helium',
        'rates': [
            {
                'name': 'Harvard Internal',
                'price': 100,
                'decimal_price': 100.00,
                'units': 'ea',
            }
        ],
        'facility': 'Helium Recovery Service',
        'object_code_category': 'Laboratory Consumables',
    }
]

PRODUCT_USAGES = [
    {
        'product': 'Dev Helium Dewar',
        'product_user': 'Slurpy Slurpiston',
        'quantity': 1,
        'decimal_quantity': 1.0,
        'units': 'ea',
        'year': 2021,
        'month': 2,
        'start_date': timezone.make_aware(datetime(2021, 2, 1)),
        'organization': 'Kitzmiller Lab (a Harvard Laboratory)',
        'logged_by': 'john@snow.com',
    },
    {
        'product': 'Dev Helium Dewar',
        'product_user': 'Markos Hankin',
        'quantity': 1,
        'decimal_quantity': 1.0,
        'units': 'ea',
        'year': 1900,
        'month': 1,
        'start_date': timezone.make_aware(datetime(1900, 1, 1)),
        'organization': 'Kitzmiller Lab (a Harvard Laboratory)',
        'logged_by': 'john@snow.com',
    },
    {
        'product': 'Dev Helium Dewar',
        'product_user': 'Markos Hankin',
        'quantity': 1,
        'decimal_quantity': 1.0,
        'units': 'ea',
        'year': 2020,
        'month': 2,
        'start_date': timezone.make_aware(datetime(2020, 2, 1)),
        'organization': 'Kitzmiller Lab (a Harvard Laboratory)',
        'logged_by': 'john@snow.com',
    },
    {
        'product': 'Dev Helium Dewar',
        'product_user': 'Markos Hankin',
        'quantity': 1,
        'decimal_quantity': 1.0,
        'units': 'ea',
        'year': 2021,
        'month': 3,
        'start_date': timezone.make_aware(datetime(2020, 3, 1)),
        'organization': 'Kitzmiller Lab (a Harvard Laboratory)',
        'logged_by': 'john@snow.com',
    },
    {
        'product': 'Dev Helium Balloon',
        'product_user': 'Markos Hankin',
        'quantity': 1,
        'decimal_quantity': 1.0,
        'units': 'ea',
        'year': 2022,
        'month': 1,
        'start_date': timezone.make_aware(datetime(2020, 3, 1)),
        'organization': 'Kitzmiller Lab (a Harvard Laboratory)',
        'logged_by': 'john@snow.com',
    },
    {
        'product': 'Dev Helium Balloon',
        'product_user': 'Markos Hankin',
        'quantity': 1,
        'decimal_quantity': 1.0,
        'units': 'ea',
        'year': 2022,
        'month': 1,
        'start_date': timezone.make_aware(datetime(2020, 3, 2)),
        'organization': 'Kitzmiller Lab (a Harvard Laboratory)',
        'logged_by': 'john@snow.com',
    },
]

def clearTestData():
    '''
    Clear all of the data from the database.  Called during setUp
    '''
    models.BillingRecord.objects.all().delete()
    models.Account.objects.all().delete()
    models.ProductUsage.objects.all().delete()
    models.Product.objects.all().delete()
    models.Facility.objects.all().delete()

    for user_data in USERS:
        try:
            get_user_model().objects.get(ifxid=user_data['ifxid']).delete()
        except get_user_model().DoesNotExist:
            pass
    Contact.objects.all().delete()
    Organization.objects.all().delete()

    try:
        get_user_model().objects.filter(email='john@snow.com').delete()
    except Exception:
        pass


def clearFiineProducts():
    '''
    Clear stuff from fiine
    '''
    products = FiineAPI.listProducts()
    for product in products:
        if product.product_name == 'Helium Dewar Test':
            FiineAPI.deleteProduct(product_number=product.product_number)


def init(types=None):
    '''
    Initialize organizations and users.  If types is set, initialize those as well.
    types will be processed in order, so child objects will need to be after parents.
    '''

    for org_data in ORGS:
        org_data_copy = deepcopy(org_data)
        org_contacts_data = org_data_copy.pop('contacts', [])
        org = Organization.objects.create(**org_data_copy)
        for org_contact_data in org_contacts_data:
            contact_data = org_contact_data.pop('contact')
            contact = Contact.objects.create(**contact_data)
            OrganizationContact.objects.create(organization=org, contact=contact, role=org_contact_data['role'])
    for original_user_data in USERS:
        user_data = deepcopy(original_user_data)
        user_data['primary_affiliation'] = Organization.objects.get(name=user_data.pop('primary_affiliation'))
        get_user_model().objects.create(**user_data)
    for facility_data in FACILITIES:
        facility_data_copy = deepcopy(facility_data)
        facility_codes_data = facility_data_copy.pop('facility_codes')
        facility = models.Facility.objects.create(**facility_data_copy)
        for facility_code_data in facility_codes_data:
            facility_code_data['facility'] = facility
            models.FacilityCodes.objects.create(**facility_code_data)

    if types:
        if 'Account' in types:
            for account_data in ACCOUNTS:
                data_copy = deepcopy(account_data)
                data_copy['organization'] = Organization.objects.get(slug=account_data['organization'])
                models.Account.objects.create(**data_copy)
        if 'Product' in types:
            for product_data in PRODUCTS:
                data_copy = deepcopy(product_data)
                data_copy['facility'] = models.Facility.objects.get(name=data_copy.pop('facility'))
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
                data_copy['organization'] = Organization.objects.get(slug=data_copy.pop('organization'))
                data_copy['logged_by'] = get_user_model().objects.get(email=data_copy.pop('logged_by'))
                models.ProductUsage.objects.create(**data_copy)
        if 'UserAccount' in types:
            init_user_accounts()
        if 'UserProductAccount' in types:
            for user_product_account_data in USER_PRODUCT_ACCOUNTS:
                account = models.Account.objects.get(name=user_product_account_data['account'])
                user = get_user_model().objects.get(full_name=user_product_account_data['user'])
                product = models.Product.objects.get(product_name=user_product_account_data['product'])
                models.UserProductAccount.objects.create(
                    product=product,
                    account=account,
                    user=user,
                    is_valid=user_product_account_data['is_valid'],
                    percent=user_product_account_data['percent']
                )

def init_user_accounts():
    '''
    Initialize user accounts
    '''
    for user_account_data in USER_ACCOUNTS:
        account = models.Account.objects.get(name=user_account_data['account'])
        user = get_user_model().objects.get(full_name=user_account_data['user'])
        models.UserAccount.objects.create(account=account, user=user, is_valid=user_account_data['is_valid'])
