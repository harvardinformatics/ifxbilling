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
import re
from copy import deepcopy

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from fiine.client import API as FiineAPI
from fiine.client import ApiException
from ifxmail.client import API as IfxMailAPI
from ifxuser.models import Organization
from ifxec import ExpenseCodeFields, OBJECT_CODES
from rest_framework import status
from rest_framework.exceptions import NotAuthenticated, ValidationError

from ifxbilling import models

logger = logging.getLogger(__name__)

def replace_object_code_in_fiine_account(acct_data, object_code):
    '''
    Replace object code and return dictionary version of FiineAPI account for expense codes.
    Expense code should be in acct_data.account.code (it should be an account from FiineAPI)
    '''
    if acct_data['account']['account_type'] == 'Expense Code':
        acct_data['account']['code'] = ExpenseCodeFields.replace_field(
            acct_data['account']['code'],
            ExpenseCodeFields.OBJECT_CODE,
            object_code
        )
    return acct_data

def get_facility_object_codes(facility):
    '''
    Get a unique set of object codes for a facility based on object code category of the facility codes
    '''
    facility_codes = facility.facilitycodes_set.all()
    if not facility_codes:
        raise Exception(f'Facility codes not set for {facility}')
    object_codes = set()
    for facility_code in facility_codes:
        object_codes.add(OBJECT_CODES[facility_code.debit_object_code_category].debit_code)

    return object_codes

def sync_facilities():
    '''
    Sync local facilities with fiine facilities.
    '''
    if not models.Facility.objects.exists():
        raise Exception('No facilities found in database')

    successes = 0
    errors = []
    for facility in models.Facility.objects.all():
        try:
            with transaction.atomic():
                fiine_facilities = FiineAPI.listFacilities(ifxfac=facility.ifxfac)
                if not fiine_facilities:
                    raise Exception(f'Facility {facility.ifxfac} not found in fiine')
                fiine_facility = fiine_facilities[0]
                facility.name = fiine_facility.name
                facility.application_username = fiine_facility.application_username
                facility.invoice_prefix = fiine_facility.invoice_prefix
                facility.save()
                facility.facilitycodes_set.all().delete()
                for facility_code in fiine_facility.facility_codes:
                    organization = Organization.objects.get(name=facility_code.organization, org_tree='Harvard')
                    facility_code_obj = models.FacilityCodes(
                        facility=facility,
                        credit_code=facility_code.credit_code,
                        debit_object_code_category=facility_code.debit_object_code_category,
                        organization=organization,
                    )
                    facility_code_obj.save()
                successes += 1
        except Organization.DoesNotExist as e:
            logger.error(f'Organization {facility_code.organization} not found')
            errors.append(f'Organization {facility_code.organization} not found')
        except Exception as e:
            logger.exception(e)
            errors.append(f'Error syncing facility {facility.ifxfac} ({facility.name}): {e}')

    update_products()

    return successes, errors

def sync_fiine_accounts(code=None):
    '''
    Sync all accounts from fiine.
    If all accounts are being sync'd, existing accounts are first disabled and then set enabled from fiine data.
    :param code: Only sync a single code if specified
    :type code: str

    Returns tuple of integers (accounts_updated, accounts_created, and total_accounts)
    '''
    if code:
        accounts = FiineAPI.listAccounts(code=code)
    else:
        accounts = FiineAPI.listAccounts()

    total_accounts = 0
    accounts_updated = 0
    accounts_created = 0

    for account_obj in accounts:
        account_data = account_obj.to_dict()
        total_accounts += 1
        organization_name = account_data.pop('organization')
        account_data.pop('id')
        try:
            account_data['organization'] = Organization.objects.get(name=organization_name, org_tree='Harvard')
        except Organization.DoesNotExist:
            # pylint: disable=raise-missing-from
            raise Exception(f'While synchronizing accounts from fiine, organization {organization_name} in account {account_data["name"]} was not found.')

        if account_data['account_type'] == 'Expense Code':
            for facility in models.Facility.objects.all():
                for facility_object_code in get_facility_object_codes(facility):
                    account_data['code'] = ExpenseCodeFields.replace_field(
                        account_data['code'],
                        ExpenseCodeFields.OBJECT_CODE,
                        facility_object_code
                    )
                    try:
                        account = models.Account.objects.get(ifxacct=account_data['ifxacct'], code=account_data['code'])
                        for field in ['name', 'description', 'active', 'organization', 'valid_from', 'expiration_date', 'funding_category', 'root']:
                            setattr(account, field, account_data[field])
                        account.save()
                        accounts_updated += 1
                    except models.Account.DoesNotExist:
                        models.Account.objects.create(**account_data)
                        accounts_created += 1
                    except Exception as e:
                        raise Exception(f'Unable to create account {account_data["name"]}: {e}') from e
        else:
            try:
                models.Account.objects.get(ifxacct=account_data['ifxacct'])
                models.Account.objects.filter(ifxacct=account_data['ifxacct']).update(**account_data)
                accounts_updated += 1
            except models.Account.DoesNotExist:
                models.Account.objects.create(**account_data)
                accounts_created += 1
            except Exception as e:
                raise Exception(f'Unable to create account {account_data["name"]}: {e}') from e
    return (accounts_updated, accounts_created, total_accounts)


def update_user_accounts(user):
    '''
    For a single user, update UserAccounts from fiine PersonAccounts and PersonFacilityAccounts and UserProductAccounts from fiine PersonProductAccounts

    fiine data is collected first.  Existing UserAccounts and UserProductAccounts are all invalidated.  Then the fiine data is
    iterated to either re-validate or create new records.

    Only one valid record for PersonAccount or PersonFacilityAccount is added to UserAccount for a given organization
    with PersonFacilityAccount having priority.  You could end up with more than one from the same organzation, but not with both
    UserAccount.is_valid and Account.active

    :param user: The user whose account authorizations should be updated
    :type user: :class:`~ifxuser.models.IfxUser`

    :return: Updated user.
    :rtype: :class:`~ifxuser.models.IfxUser`
    '''

    ifxid = user.ifxid
    fiine_person = FiineAPI.readPerson(ifxid=ifxid)

    # Collect user accounts and facility accounts for each facility
    # Substitute object code for the facility if it has one
    fiine_accounts = []
    product_accounts = []

    # Setup facility accounts first. Then, go through default accounts and add if organization is not already covered
    organizations_covered_by_facility_account = []
    for facility in models.Facility.objects.all():

        for facility_account in fiine_person.facility_accounts:
            if facility_account.facility == facility.name:
                # replace code and dict-ify
                for facility_object_code in get_facility_object_codes(facility):
                    facility_account_data = facility_account.to_dict()
                    fiine_accounts.append({
                        'ifxacct': facility_account_data['account']['ifxacct'],
                        'is_valid': facility_account_data['is_valid'],
                    })
                    if facility_account_data['is_valid'] and facility_account_data['account']['active']:
                        organizations_covered_by_facility_account.append(facility_account_data['account']['organization'])

    for default_account in fiine_person.accounts:
        try:
            if default_account.account.active and default_account.is_valid and default_account.account.organization not in organizations_covered_by_facility_account:
                default_account_data = default_account.to_dict()
                fiine_accounts.append({
                    'ifxacct': default_account_data['account']['ifxacct'],
                    'is_valid': default_account_data['is_valid'],
                })
        except Exception as e:
            logger.error(f'Error with default account {default_account}: {e}')

    logger.debug('fiine_person has %d accounts', len(fiine_accounts))


    product_accounts = []
    for product_account in fiine_person.product_accounts:
        # Don't include authorizations from non-local products
        try:
            product = models.Product.objects.get(product_number=product_account.product.product_number)
            product_account_data = replace_object_code_in_fiine_account(product_account.to_dict(), OBJECT_CODES[product.object_code_category].debit_code)
            product_accounts.append(product_account_data)
        except models.Product.DoesNotExist:
            pass


   # Go through fiine_accounts and product accounts.
    with transaction.atomic():

        # Invalidate all UserAccounts and UserProductAccounts; sync will re-validate
        models.UserAccount.objects.filter(user=user).update(is_valid=False)
        models.UserProductAccount.objects.filter(user=user).update(is_valid=False)


        # Update existing UserAccounts (is_valid flag) or create new
        for fiine_account_data in fiine_accounts:
            for account in models.Account.objects.filter(ifxacct=fiine_account_data['ifxacct']):
                try:
                    user_account = models.UserAccount.objects.get(user=user, account=account)
                    user_account.is_valid = fiine_account_data['is_valid']
                    user_account.save()
                except models.Account.DoesNotExist:
                    # pylint: disable=raise-missing-from
                    raise Exception(f"For some reason account cannot be found from org {fiine_account_data['account']} and code {fiine_account_data['account']['code']}")
                except models.UserAccount.DoesNotExist:
                    models.UserAccount.objects.create(account=account, user=user, is_valid=fiine_account_data['is_valid'])

        # Update UserProductAccounts (is_valid, percent) or create new
        for product_account_data in product_accounts:
            try:
                account = models.Account.objects.get(
                    ifxacct=product_account_data['account']['ifxacct'],
                    code=product_account_data['account']['code']
                )
                product = models.Product.objects.get(product_number=product_account_data['product']['product_number'])
                user_product_account = models.UserProductAccount.objects.get(account=account, user=user, product=product)
                user_product_account.is_valid = product_account_data['is_valid']
                if 'percent' not in product_account_data:
                    product_account_data['percent'] = 100
                user_product_account.percent = product_account_data['percent']
                user_product_account.save()
            except models.Account.DoesNotExist as e:
                raise Exception(f"Account {product_account_data['account']} for product {product_account_data['product']} is missing") from e
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


def update_products():
    '''
    Get all of the products for this facility and update to apply any changes made in Fiine. Mainly product_name and product_description
    '''
    for facility in models.Facility.objects.all():
        fiine_products = FiineAPI.listProducts(facility=facility.name)
        for fiine_product in fiine_products:
            try:
                product = models.Product.objects.get(product_number=fiine_product.product_number)
                for field in ['product_name', 'product_description']:
                    setattr(product, field, getattr(fiine_product, field))
                product.save()
            except models.Product.DoesNotExist:
                fiine_product_data = fiine_product.to_dict()
                fiine_product_data['facility'] = facility
                models.Product.objects.create(**fiine_product_data)


def create_new_product(product_name, product_description, facility, object_code_category='Technical Services', billing_calculator=None, billable=True, parent=None, product_category=None):
    '''
    Creates product record in fiine, and creates the local record with product number
    '''
    products = FiineAPI.listProducts(product_name=product_name)
    if products:
        raise IntegrityError(f'Product with name {product_name} exists in fiine.')

    try:
        product_data = {
            'product_name': product_name,
            'product_description': product_description,
            'facility': facility.name,
            'object_code_category': object_code_category,
            'product_category': product_category,
        }
        if parent:
            product_data['parent'] = {
                'product_number': parent.product_number
            }
        product_obj = FiineAPI.createProduct(
            **product_data
        )
        product = models.Product(
            product_number=product_obj.product_number,
            product_name=product_obj.product_name,
            product_description=product_obj.product_description,
            facility=facility,
            product_category=product_obj.product_category,
            object_code_category=product_obj.object_code_category,
        )
        if billing_calculator:
            product.billing_calculator = billing_calculator
        if product_obj.parent:
            try:
                product_number = product_obj.parent.product_number
                parent = models.Product.objects.get(product_number=product_number)
            except models.Product.DoesNotExist as dne:
                logger.exception(f'Unable to find parent product {product_number}')
                raise Exception(f'Unable to find parent product {product_number}') from dne
            product.parent = parent
        product.save()
        return product

    except ApiException as e:
        logger.exception(e)
        if e.status == status.HTTP_400_BAD_REQUEST:
            raise ValidationError(
                detail={
                    'product': str(e)
                }
            ) from e
        if 'Duplicate' in str(e):
            raise Exception('Duplicate entry for product') from e
        if e.status == status.HTTP_401_UNAUTHORIZED:
            raise NotAuthenticated(detail=str(e)) from e

        raise Exception(str(e)) from e



def handle_fiine_ifxapps_messages(messages):
    '''
    Go through fiine ifxapps messages and update relevant authorizations and accounts. Marks them seen using IfxAPI.markSeen
    Returns success count and error list.

    If the message has an IFXID in it and the user exists locally, updateUserAccounts will be called for that user.

    :param messages: List of dicts of the form {'id': 123, 'subject': 'fiine reports update of authorizations for Aaron Kitzmiller (IFXID: IFXID0000000001)}
    :type messages: list
    '''
    ifxid_re = re.compile(r'.*?\(IFXID: ([A-Z0-9]{15})\)$')
    account_re = re.compile(r'.*? account code ([^\s]+) for organization .*')
    seen_ids = []
    successes = 0
    errors = []
    ifxids_to_be_updated = set()
    account_codes_to_be_updated = set()
    for message in messages:
        if message['subject'] and message['subject'].startswith('fiine'):
            subject = message['subject']
            logger.debug(f'Checking subject {subject}')

            # Check for an ifxid (an authorization message). If an ifxid is found, add to to be updated list
            match = ifxid_re.match(subject)
            if match:
                ifxid = match.group(1)
                logger.debug(f'Matched an ifxid {ifxid}')
                ifxids_to_be_updated.add(ifxid)
                seen_ids.append(message['id'])
            else:
                # Check for an account
                match = account_re.match(subject)
                if match:
                    account_code = match.group(1)
                    logger.debug(f'Matched an account code {account_code}')
                    account_codes_to_be_updated.add(account_code)
                    seen_ids.append(message['id'])


    if ifxids_to_be_updated:
        logger.debug(f'Updating accounts for ids {ifxids_to_be_updated}')
        for ifxid in ifxids_to_be_updated:
            try:
                for user in get_user_model().objects.filter(ifxid=ifxid):
                    update_user_accounts(user)
                successes += 1
            except Exception as e:
                logger.exception(e)
                errors.append(f'Error updating user accounts for {ifxid}: {e}')

    if account_codes_to_be_updated:
        logger.debug(f'Updating accounts {account_codes_to_be_updated}')
        for account_code in account_codes_to_be_updated:
            try:
                sync_fiine_accounts(code=account_code)
                successes += 1
            except Exception as e:
                logger.exception(e)
                errors.append(f'Error syncing account code {account_code}: {e}')

    if seen_ids:
        logger.debug(f'Marking ids as seen {seen_ids}')
        IfxMailAPI.markSeen(data={'ids': seen_ids})

    return successes, errors

def set_ifxaccts():
    '''
    Meant to be used to set ifxaccts for all accounts in the database.  This should only be used once.
    All accounts are retrieved using FiineApi.listAccounts and then the ifxacct is set for each account
    by matching local Accounts via code / organization.
    '''
    accounts = FiineAPI.listAccounts()
    for account in accounts:
        try:
            local_account = models.Account.objects.get(code=account.code, organization__name=account.organization)
            if not local_account.ifxacct:
                local_account.ifxacct = account.ifxacct
                local_account.save()
        except models.Account.DoesNotExist:
            logger.error(f'Account {account.code} for {account.organization} not found in local database')
            continue
        except models.Account.MultipleObjectsReturned:
            logger.error(f'Multiple accounts found for {account.code} for {account.organization}')
            continue