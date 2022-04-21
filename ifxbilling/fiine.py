# -*- coding: utf-8 -*-

'''
Functions for interacting with fiine

Created on  2021-4-5

@author: Aaron Kitzmiller <akitzmiller@g.harvard.edu>
@copyright: 2021 The Presidents and Fellows of Harvard College.
All rights reserved.
@license: GPL v2.0
'''

import logging
from copy import deepcopy
from django.db import IntegrityError
from django.contrib.auth import get_user_model
from django.conf import settings
from rest_framework import status
from rest_framework.exceptions import ValidationError, NotAuthenticated
from ifxuser.models import Organization
from fiine.client import API as FiineAPI
from fiine.client import ApiException
from ifxvalidcode.ec_functions import ExpenseCodeFields
from ifxbilling import models


logger = logging.getLogger(__name__)

def replaceObjectCodeInFiineAccount(acct_data, object_code):
    '''
    Replace object code and return dictionary version of FiineAPI account
    Expense code should be in acct_data.account.code (it should be an account from FiineAPI)
    '''
    acct_data.account.code = ExpenseCodeFields.replace_field(
        acct_data.account.code,
        ExpenseCodeFields.OBJECT_CODE,
        object_code
    )
    return acct_data.to_dict()

def syncFiineAccounts(code=None, name=None):
    '''
    Sync accounts from fiine.  If neither code nor name are set, all are sync'd
    If all accounts are being sync'd, existing accounts are first disabled and then set enabled from fiine data.
    '''
    if not code and not name:
        accounts = FiineAPI.listAccounts()

    for account_data in accounts:
        organization_name = account_data.pop('organization')
        account_data.pop('id')
        try:
            account_data['organization'] = Organization.objects.get(name=organization_name, org_tree='Harvard')
        except Organization.DoesNotExist:
            raise Exception(f'While synchronizing accounts from fiine, organization {organization_name} in account {account_data["name"]} was not found.')

        try:
            models.Account.objects.get(code=account_data['code'], organization=account_data['organization'])
            models.Account.objects.filter(code=account_data['code'], organization=account_data['organization']).update(**account_data)
        except models.Account.DoesNotExist:
            models.Account.objects.create(**account_data)
        except Exception as e:
            raise Exception(f'Unable to create account {account_data["name"]}: {e}') from e


def updateUserAccounts(user, all_accounts=True):
    '''
    For a single user retrieve account strings from fiine.
    Invalidate any account string that are not represented in fiine.
    By default, all accounts will be pulled from fiine so that facility administrators have access to everything.
    '''
    if all_accounts:
        syncFiineAccounts()

    ifxid = user.ifxid
    fiine_person = FiineAPI.readPerson(ifxid=ifxid)

    # Collect user accounts and facility accounts for each facility
    # Substitute object code for the facility if it has one
    fiine_accounts = []
    product_accounts = []
    for facility in models.Facility.objects.all():
        facility_object_code = facility.object_code
        if not facility_object_code:
            raise Exception(f'Facility object code not set for {facility}')

        fiine_accounts.extend([replaceObjectCodeInFiineAccount(acct, facility_object_code) for acct in fiine_person.accounts])
        for facility_account in fiine_person.facility_accounts:
            if facility_account.facility == facility.name:
                facility_account = replaceObjectCodeInFiineAccount(facility_account, facility_object_code)
                facility_account_data = facility_account
                facility_account_data.pop('facility', None)
                fiine_accounts.append(facility_account_data)
        logger.debug('fiine_person has %d accounts', len(fiine_accounts))

        product_accounts = []
        for acct in [replaceObjectCodeInFiineAccount(pacct, facility_object_code) for pacct in fiine_person.product_accounts]:
            # Don't include authorizations from non-local products
            try:
                models.Product.objects.get(product_number=acct['product']['product_number'])
                product_accounts.append(acct)
            except models.Product.DoesNotExist:
                pass

    # Go through fiine_accounts and product accounts. Create any missing Account objects or update with Fiine information
    for person_account_data in fiine_accounts + product_accounts:
        account_data = person_account_data['account']
        try:
            account = models.Account.objects.get(code=account_data['code'], organization__name=account_data['organization'])

            # Update some of the account fields if it's available
            for field in ['name', 'active', 'valid_from', 'expiration_date']:
                if field in account_data:
                    setattr(account, field, account_data[field])

        except models.Account.DoesNotExist:
            try:
                acct_copy = deepcopy(account_data)
                name = acct_copy.pop('organization')
                acct_copy['organization'] = Organization.objects.get(name=name, org_tree='Harvard')
            except Organization.DoesNotExist:
                raise Exception(f'Unable to find organization {name}')
            acct_copy.pop('id')
            models.Account.objects.create(**acct_copy)

    # Update existing UserAccounts (is_valid flag) or create new
    for fiine_account_data in fiine_accounts:
        try:
            account = models.Account.objects.get(
                organization__name=fiine_account_data['account']['organization'],
                code=fiine_account_data['account']['code']
            )
            user_account = models.UserAccount.objects.get(user=user, account=account)
            user_account.is_valid = fiine_account_data['is_valid']
            user_account.save()
        except models.Account.DoesNotExist:
            raise Exception(f"For some reason account cannot be found from org {fiine_account_data['account']} and code {fiine_account_data['account']['code']}")
        except models.UserAccount.DoesNotExist:
            models.UserAccount.objects.create(account=account, user=user, is_valid=fiine_account_data['is_valid'])

    # Update UserProductAccounts (is_valid, percent) or create new
    for product_account_data in product_accounts:
        try:
            account = models.Account.objects.get(
                organization__name=product_account_data['account']['organization'],
                code=product_account_data['account']['code']
            )
            product = models.Product.objects.get(product_number=product_account_data['product']['product_number'])
            user_product_account = models.UserProductAccount.objects.get(account=account, user=user, product=product)
            user_product_account.is_valid = product_account_data['is_valid']
            if 'percent' not in product_account_data:
                product_account_data['percent'] = 100
            user_product_account.percent = product_account_data['percent']
            user_product_account.save()
        except models.Product.DoesNotExist as e:
            raise Exception(f"Product with number {product_account_data['product']['product_number']} is missing") from e
        except models.UserProductAccount.DoesNotExist:
            models.UserProductAccount.objects.create(
                user=user,
                product=product,
                account=account,
                is_valid=product_account_data['is_valid'],
                percent=product_account_data['percent']
            )
    user = get_user_model().objects.get(id=user.id)
    return user


def updateProducts():
    '''
    Get all of the products for this facility and update to apply any changes made in Fiine. Mainly product_name and product_description
    '''
    for facility in models.Facility.objects.all():
        fiine_products = FiineAPI.listProducts(facility=facility.name)
        for fiine_product in fiine_products:
            try:
                logger.info(f'updating {fiine_product.product_number}')
                product = models.Product.objects.get(product_number=fiine_product.product_number)
                for field in ['product_name', 'product_description']:
                    setattr(product, field, getattr(fiine_product, field))
                product.save()
            except models.Product.DoesNotExist:
                fiine_product_data = fiine_product.to_dict()
                fiine_product_data['facility'] = facility
                fiine_product_data.pop('object_code_category')
                fiine_product_data.pop('reporting_group')
                models.Product.objects.create(**fiine_product_data)


def getExpenseCodeStatus(account):
    '''
    Use expense code validator to check an account
    '''
    pass


def createNewProduct(product_name, product_description, facility, billing_calculator=None):
    '''
    Creates product record in fiine, and creates the local record with product number
    '''
    products = FiineAPI.listProducts(product_name=product_name)
    if products:
        raise IntegrityError(f'Product with name {product_name} exists in fiine.')

    try:
        product_obj = FiineAPI.createProduct(
            product_name=product_name,
            product_description=product_description,
            facility=facility.name,
        )
        product = models.Product(
            product_number=product_obj.product_number,
            product_name=product_obj.product_name,
            product_description=product_obj.product_description,
            facility=facility,
        )
        if billing_calculator:
            product.billing_calculator = billing_calculator
        product.save()
        return product

    except ApiException as e:
        if e.status == status.HTTP_400_BAD_REQUEST:
            raise ValidationError(
                detail={
                    'product': str(e)
                }
            )
        if e.status == status.HTTP_401_UNAUTHORIZED:
            raise NotAuthenticated(detail=str(e))
