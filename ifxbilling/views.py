# -*- coding: utf-8 -*-

'''
Common views for expense codes
'''

import logging
import json
import re
from collections import defaultdict
from decimal import Decimal
import requests
from django.db import connection
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.http import urlencode
from django.core.validators import validate_email, ValidationError
from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework.authtoken.models import Token
from ifxmail.client import send, FieldErrorsException
from ifxmail.client.views import messages, mailings
from ifxurls.urls import FIINE_URL_BASE, getIfxUrl
from ifxuser import models as ifxuser_models
from ifxbilling.fiine import update_user_accounts, sync_fiine_accounts, sync_facilities
from ifxbilling import models, permissions
from ifxbilling.calculator import calculateBillingMonth, getClassFromName, get_rebalancer_class


logger = logging.getLogger(__name__)


def get_remote_user_auth_token(request):
    '''
    Get the token
    '''
    try:
        token = Token.objects.get(user=request.user)
    except Token.DoesNotExist:
        return Response({'error': f'User record for {request.user} is not complete- missing token.'}, status=401)

    if not request.user.is_active:
        logger.info('User %s is not active', request.user.username)
        return Response({'error': 'User is inactive.'}, status=401)

    return Response({
        'token': str(token),
        'is_staff': request.user.is_staff is True,
        'username': request.user.username,
        'first_name': request.user.first_name,
        'last_name': request.user.last_name,
        'groups': [g.name for g in request.user.groups.all()]
    })

@api_view(('POST',))
def update_user_accounts_view(request):
    '''
    Take a list of ifxids and update data from fiine.  Body should be of the form:
    {
        'ifxids': [
            'IFXID0001',
            'IFXID0002',
        ]
    }
    If no data is specified, all accounts will be updated
    '''

    data = request.data

    if not data.keys():
        queryset = get_user_model().objects.filter(ifxid__isnull=False)
    else:
        queryset = get_user_model().objects.filter(ifxid__in=data['ifxids'])

    try:
        sync_facilities()
        sync_fiine_accounts()
    except Exception as e:
        logger.exception(e)
        return Response(data={'error': f'Error syncing fiine accounts: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    successes = 0
    errors = []
    for user in queryset:
        try:
            update_user_accounts(user)
            successes += 1
        except Exception as e:
            logger.exception(e)
            errors.append(f'Error updating {user}: {e}')

    if errors:
        return Response(data={'successes': successes, 'errors': errors}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    else:
        return Response(data={'successes': successes})



@api_view(('GET',))
def unauthorized(request):
    '''
    Return a list of product usages for which there is no expense code authorized
    '''
    year = request.GET.get('year', timezone.now().year)
    month = request.GET.get('month', timezone.now().month)

    results = []

    for pu in models.ProductUsage.objects.filter(year=year, month=month):
        valid_account_exists = False

        # Check that both the account is valid and the user's use of the account is valid
        for ua in pu.product_user.useraccount_set.filter(is_valid=True):
            if ua.account.active:
                valid_account_exists = True
        for upa in pu.product_user.userproductaccount_set.filter(is_valid=True, product=pu.product):
            if upa.account.active:
                valid_account_exists = True

        if not valid_account_exists:
            results.append(
                {
                    'user': {
                        'ifxid': pu.product_user.ifxid,
                        'full_name': pu.product_user.full_name,
                        'primary_email': pu.product_user.email,
                        'primary_affiliation': pu.product_user.primary_affiliation.slug if pu.product_user.primary_affiliation else '',
                        'user_accounts': [str(ua.account) for ua in pu.product_user.useraccount_set.all()],
                        'user_product_accounts': [str(ua.account) for ua in pu.product_user.userproductaccount_set.all()]
                    },
                    'product': {
                        'product_name': pu.product.product_name,
                        'product_description': pu.product.product_description,
                    },
                    'quantity': pu.quantity,
                    'units': pu.units,
                    'description': pu.description,
                }
            )

    return Response(data=results)


@api_view(('POST',))
def expense_code_request(request):
    '''
    email an expense code request
    '''
    user = request.user
    organization_name = request.data.get('organization')
    facility_name = request.data.get('facility')
    product_name = request.data.get('product')
    emails = request.data.get('emails')

    # ensure there is atleast one valid email
    email_list = [e.strip() for e in emails.split(',')]
    valid_emails = []
    for email in email_list:
        try:
            validate_email(email)
            valid_emails.append(email)
        except ValidationError:
            pass
    if not valid_emails:
        msg = f'None of the emails supplied were valid: {emails}.'
        logger.error(msg)
        return Response(data={'emails': msg}, status=status.HTTP_400_BAD_REQUEST)

    # ensure all parameters are passed in
    param_errors = {}
    if organization_name is None:
        msg = f'A required parameter is missing from data: organization_name - {organization_name}.'
        logger.error(msg)
        param_errors['organization'] = msg
    if facility_name is None:
        msg = f'A required parameter is missing from data: facility_name - {facility_name}'
        logger.error(msg)
        param_errors['facility'] = msg
    if product_name is None:
        msg = f'A required parameter is missing from data: product_name - {product_name}'
        logger.error(msg)
        param_errors['product'] = msg
    if param_errors:
        return Response(data=param_errors, status=status.HTTP_400_BAD_REQUEST)

    logger.info(f'Formatting message for {facility_name} {organization_name} request from {user.full_name} for {product_name}.')

    try:
        org = ifxuser_models.Organization.objects.get(slug=organization_name)
        models.Facility.objects.get(name=facility_name)
        qparams = {'facility': facility_name, 'product':product_name}
        url = f'{FIINE_URL_BASE}/labs/{org.ifxorg}/member/{user.ifxid}/?{urlencode(qparams)}'
    except ifxuser_models.Organization.DoesNotExist:
        msg = f'Organization not found: {organization_name}.'
        logger.error(msg)
        return Response(data={'organization': f'Error {msg}'}, status=status.HTTP_400_BAD_REQUEST)
    except models.Facility.DoesNotExist:
        msg = f'Facility not found: {facility_name}.'
        logger.error(msg)
        return Response(data={'facility': f'Error {msg}'}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.exception(e)
        return Response(data={'error': f'Error gathering information to create expense code request for {facility_name} {organization_name} by {user.full_name} for {product_name}.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    fromstr = settings.EMAILS.DEFAULT_EMAIL_FROM_ADDRESS
    tostr = ','.join(valid_emails)
    ccstr = user.email
    ifxmessage = settings.IFXMESSAGES.EXPENSE_CODE_REQUEST_MESSAGE_NAME
    data = {
        'user': user.full_name,
        'facility': facility_name,
        'product': product_name,
        'organization': organization_name,
        'link': url
    }

    logger.debug(f'Attempting to send message to {tostr} from {fromstr} with {ifxmessage} with {json.dumps(data)}.')
    try:
        send(
            to=tostr,
            fromaddr=fromstr,
            ifxmessage=ifxmessage,
            field_errors=True,
            cclist=ccstr.split(','),
            data=data
        )
        msg = 'Successfully sent mailing.'
        msg_status = status.HTTP_200_OK
        data = {'message': msg}
    except FieldErrorsException as e:
        logger.exception(e)
        data = e.field_errors
        msg_status = e.status
    return Response(data=data, status=msg_status)


@permission_classes((permissions.AdminPermissions, ))
@api_view(('POST',))
def calculate_billing_month(request, invoice_prefix, year, month):
    '''
    Calculate billing for the given invoice_prefix, year, and month
    '''
    recalculate = False
    try:
        data = json.loads(request.body.decode('utf-8'))
        if data and 'recalculate' in data:
            recalculate = data['recalculate']
    except json.JSONDecodeError as e:
        logger.exception(e)
        return Response(data={'error': 'Cannot parse request body'}, status=status.HTTP_400_BAD_REQUEST)

    logger.debug('Calculating billing records with invoice_prefix %s for month %d of year %d, with recalculate flag %s', invoice_prefix, month, year, str(recalculate))

    try:
        facility = models.Facility.objects.get(invoice_prefix=invoice_prefix)
    except models.Facility.DoesNotExist:
        return Response(data={ 'error': f'Facility cannot be found using invoice_prefix {invoice_prefix}' }, status=status.HTTP_400_BAD_REQUEST)

    try:
        (successes, errors) = calculateBillingMonth(month, year, facility, recalculate)
        return Response(data={ 'successes': successes, 'errors': errors }, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception(e)
        return Response(data={ 'error': f'Billing calculation failed {e}' }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@permission_classes((permissions.AdminPermissions, ))
@api_view(('POST',))
def send_billing_record_review_notification(request, invoice_prefix, year, month):
    '''
    Send billing record notification emails to organization contacts
    '''
    ifxorg_ids = []
    test = []
    try:
        data = json.loads(request.body.decode('utf-8'))
        if 'ifxorg_ids' in data:
            # get ifxorg_ids are valid
            r = re.compile('^IFXORG[0-9A-Z]{10}')
            ifxorg_ids = [id for id in data['ifxorg_ids'] if r.match(id)]
            if len(ifxorg_ids) is not len(data['ifxorg_ids']):
                return Response(data={'error': f'Some of the ifxorg_ids you passed in are invalid. valid ifxorg_ids included: {ifxorg_ids}'}, status=status.HTTP_400_BAD_REQUEST)
            logger.info(ifxorg_ids)
        if 'test' in data:
            test = data['test']
    except json.JSONDecodeError as e:
        logger.exception(e)
        return Response(data={'error': 'Cannot parse request body'}, status=status.HTTP_400_BAD_REQUEST)
    logger.info('Summarizing billing records with invoice_prefix %s for month %d of year %d, with ifxorg_ids %s', invoice_prefix, month, year, ifxorg_ids)

    try:
        facility = models.Facility.objects.get(invoice_prefix=invoice_prefix)
    except models.Facility.DoesNotExist:
        return Response(data={
            'error': f'Facility with invoice prefix {invoice_prefix} cannot be found'
        }, status=status.HTTP_400_BAD_REQUEST)

    organizations = []
    if ifxorg_ids:
        for ifxorg_id in ifxorg_ids:
            try:
                organizations.append(ifxuser_models.Organization.objects.get(ifxorg=ifxorg_id))
            except ifxuser_models.Organization.DoesNotExist:
                return Response(data={
                    'error': f'Organization with ifxorg number {ifxorg_id} cannot be found'
                }, status=status.HTTP_400_BAD_REQUEST)
    logger.debug(f'Processing organizations {organizations}')
    try:
        breg_class_name = 'ifxbilling.notification.BillingRecordEmailGenerator'
        if hasattr(settings, 'BILLING_RECORD_EMAIL_GENERATOR_CLASS') and settings.BILLING_RECORD_EMAIL_GENERATOR_CLASS:
            app_name = settings.IFX_APP['name']
            breg_class_name = f'{app_name}.{settings.BILLING_RECORD_EMAIL_GENERATOR_CLASS}'
        breg_class = getClassFromName(breg_class_name)
        gen = breg_class(year, month, facility, test)
        successes, errors, nobrs = gen.send_billing_record_emails(organizations)
        logger.info(f'Billing record email successes: {", ".join(sorted([s.name for s in successes]))}')
        logger.info(f'Orgs with no billing records for {month}/{year}: {", ".join(sorted([n.name for n in nobrs]))}')
        for org_name, error_messages in errors.items():
            logger.error(f'Email errors for {org_name}: {", ".join(error_messages)} ')
        return Response(
            data={
                'successes': [s.name for s in successes],
                'errors': errors,
                'nobrs': [n.name for n in nobrs]
            },
            status=status.HTTP_200_OK
        )
    except Exception as e:
        logger.exception(e)
        return Response(data={ 'error': f'Billing record summary failed {str(e)}' }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@permission_classes((permissions.AdminPermissions, ))
def ifx_messages(request):
    '''
    Messages
    '''
    return messages(request)


@permission_classes((permissions.AdminPermissions, ))
def ifx_mailings(request):
    '''
    Mailings
    '''
    return mailings(request)

def make_transaction_from_query_result(row_dict):
    '''
    Return a transaction dict from the row
    '''
    return {
        'description': row_dict['transaction_description'],
        'id': row_dict['transaction_id'],
        'charge': row_dict['transaction_charge'],
        'decimal_charge': row_dict['transaction_decimal_charge'],
        'rate': row_dict['transaction_rate'],
        'author': {
            'ifxid': row_dict['transaction_user_ifxid'],
            'full_name': row_dict['transaction_user_full_name']
        }
    }

@api_view(('GET', ))
def get_product_usage_list(request):
    '''
    Intended as a fast way to get product usage information for a given month and year, particularly
    for the Calculate Billing Month page.  This is a read-only view.
    '''
    local_tz = timezone.get_current_timezone()

    year = request.GET.get('year', None)
    month = request.GET.get('month', None)
    facility = request.GET.get('facility_name', None)
    organization = request.GET.get('organization_slug', None)
    invoice_prefix = request.GET.get('invoice_prefix', None)

    results = []
    sql = f'''
        select
            pu.id,
            pu.decimal_quantity,
            pu.description,
            CONVERT_TZ(pu.start_date, 'UTC', '{local_tz}') as start_date,
            CONVERT_TZ(pu.end_date, 'UTC', '{local_tz}') as end_date,
            pu.month,
            pu.year,
            o.slug as organization,
            p.product_name as product,
            product_user.full_name as product_user_full_name,
            product_user.ifxid as product_user_ifxid,
            pup.error_message,
            pup.resolved
        from
            product_usage pu
            inner join product p on p.id = pu.product_id
            inner join facility f on f.id = p.facility_id
            inner join ifxuser product_user on pu.product_user_id = product_user.id
            inner join nanites_organization o on o.id = pu.organization_id
            left join product_usage_processing pup on pup.product_usage_id = pu.id
    '''
    where_clauses = []
    query_args = []
    if year:
        try:
            year = int(year)
        except ValueError:
            return Response('year must be an integer', status=status.HTTP_400_BAD_REQUEST)
        where_clauses.append('pu.year = %s')
        query_args.append(year)

    if month:
        try:
            month = int(month)
        except ValueError:
            return Response('month must be an integer', status=status.HTTP_400_BAD_REQUEST)
        where_clauses.append('pu.month = %s')
        query_args.append(month)

    if invoice_prefix:
        where_clauses.append('f.invoice_prefix = %s')
        query_args.append(invoice_prefix)

    if organization:
        where_clauses.append('o.slug = %s')
        query_args.append(organization)

    if facility:
        where_clauses.append('f.name = %s')
        query_args.append(facility)

    if where_clauses:
        sql += ' where '
        sql += ' and '.join(where_clauses)

    sql += ' order by year, month, start_date'

    try:

        cursor = connection.cursor()
        cursor.execute(sql, query_args)

        desc = cursor.description

        for row in cursor.fetchall():
            # Make a dictionary labeled by column name
            row_dict = dict(zip([col[0] for col in desc], row))
            row_dict['product_user'] = {
                'full_name': row_dict['product_user_full_name'],
                'ifxid': row_dict['product_user_ifxid'],
            }
            row_dict['processing'] = []
            if row_dict.get('error_message'):
                row_dict['processing'] = [{
                    'error_message': row_dict['error_message'],
                    'resolved': row_dict['resolved']
                }]
            results.append(row_dict)
    except Exception as e:
        logger.exception(e)
        return Response(f'Error getting protocol usages {e}', status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response(
        data=results
    )

@api_view(('GET', ))
def get_billing_record_list(request):
    '''
    Return trimmed down listing for billing record displays
    '''
    local_tz = timezone.get_current_timezone()

    year = request.GET.get('year', None)
    month = request.GET.get('month', None)
    invoice_prefix = request.GET.get('invoice_prefix', None)
    facility = request.GET.get('facility', None)
    organization = request.GET.get('organization', None)
    root = request.GET.get('root', None)
    results = {}
    sql = f'''
        select
            br.id as billing_record_id,
            br.charge as billing_record_charge,
            br.decimal_charge as billing_record_decimal_charge,
            br.percent as billing_record_percent,
            br.current_state as billing_record_current_state,
            br.description as billing_record_description,
            br.year,
            br.month,
            br.product_usage_link_text,
            br.product_usage_url,
            CONVERT_TZ(br.start_date, 'UTC', '{local_tz}') as br_start_date,
            CONVERT_TZ(br.end_date, 'UTC', '{local_tz}') as br_end_date,
            br.decimal_quantity as billing_record_decimal_quantity,
            product_user.full_name as product_user_full_name,
            product_user.ifxid as product_user_ifxid,
            product_user_organization.slug as product_user_primary_affiliation,
            acct.id as account_id,
            acct.code as account_code,
            acct.name as account_name,
            acct.account_type,
            acct.root,
            acct.slug as account_slug,
            o.slug as account_organization,
            p.product_name,
            p.product_number,
            pu.id as product_usage_id,
            CONVERT_TZ(pu.start_date, 'UTC', '{local_tz}') as start_date,
            CONVERT_TZ(pu.end_date, 'UTC', '{local_tz}') as end_date,
            txn.id as transaction_id,
            txn.description as transaction_description,
            txn.charge as transaction_charge,
            txn.decimal_charge as transaction_decimal_charge,
            txn.rate as transaction_rate,
            txn_user.full_name as transaction_user_full_name,
            txn_user.ifxid as transaction_user_ifxid,
            r.name as rate_obj_name,
            r.id as rate_obj_id,
            r.decimal_price as rate_obj_decimal_price,
            r.is_active as rate_obj_is_active
        from
            billing_record br
            inner join product_usage pu on pu.id = br.product_usage_id
            inner join product p on p.id = pu.product_id
            inner join ifxuser product_user on pu.product_user_id = product_user.id
            inner join nanites_organization product_user_organization on product_user.primary_affiliation_id = product_user_organization.id
            inner join account acct on acct.id = br.account_id
            inner join nanites_organization o on o.id = acct.organization_id
            inner join transaction txn on txn.billing_record_id = br.id
            inner join ifxuser txn_user on txn_user.id = txn.author_id
            inner join facility f on f.id = p.facility_id
            left join rate r on br.rate_obj_id = r.id
    '''
    where_clauses = []
    query_args = []
    if year:
        try:
            year = int(year)
        except ValueError:
            return Response('year must be an integer', status=status.HTTP_400_BAD_REQUEST)
        where_clauses.append('br.year = %s')
        query_args.append(year)

    if month:
        try:
            month = int(month)
        except ValueError:
            return Response('month must be an integer', status=status.HTTP_400_BAD_REQUEST)
        where_clauses.append('br.month = %s')
        query_args.append(month)

    if invoice_prefix:
        where_clauses.append('f.invoice_prefix = %s')
        query_args.append(invoice_prefix)
    if organization:
        where_clauses.append('o.slug = %s')
        query_args.append(organization)
    if facility:
        where_clauses.append('f.name = %s')
        query_args.append(facility)
    if root:
        where_clauses.append('acct.root = %s')
        query_args.append(root)

    if where_clauses:
        sql += ' where '
        sql += ' and '.join(where_clauses)

    sql += ' order by year, month, account_organization, start_date, billing_record_id'

    try:

        cursor = connection.cursor()
        cursor.execute(sql, query_args)

        desc = cursor.description

        for row in cursor.fetchall():
            # Make a dictionary labeled by column name
            row_dict = dict(zip([col[0] for col in desc], row))
            billing_record_id = row_dict['billing_record_id']
            if billing_record_id in results:
                # Additional transaction
                results[billing_record_id]['transactions'].append(
                    make_transaction_from_query_result(row_dict)
                )
            else:
                results[billing_record_id] = {
                    'id': billing_record_id,
                    'charge': row_dict['billing_record_charge'],
                    'decimal_charge': row_dict['billing_record_decimal_charge'],
                    'decimal_quantity': row_dict['billing_record_decimal_quantity'],
                    'description': row_dict['billing_record_description'],
                    'percent': row_dict['billing_record_percent'],
                    'current_state': row_dict['billing_record_current_state'],
                    'year': row_dict['year'],
                    'month': row_dict['month'],
                    'product_usage_link_text': row_dict['product_usage_link_text'],
                    'product_usage_url': row_dict['product_usage_url'],
                    'start_date': row_dict['br_start_date'],
                    'end_date': row_dict['br_end_date'],
                    'account': {
                        'id': row_dict['account_id'],
                        'code': row_dict['account_code'],
                        'name': row_dict['account_name'],
                        'slug': row_dict['account_slug'],
                        'organization': row_dict['account_organization'],
                        'account_type': row_dict['account_type'],
                        'root': row_dict['root'],
                    },
                    'product_usage': {
                        'id': row_dict['product_usage_id'],
                        'product': row_dict['product_name'],
                        'product_user': {
                            'ifxid': row_dict['product_user_ifxid'],
                            'primary_affiliation': row_dict['product_user_primary_affiliation'],
                            'full_name': row_dict['product_user_full_name']
                        },
                        'start_date': row_dict['start_date'],
                        'end_date': row_dict.get('end_date', None),
                    },
                    'transactions': [
                        make_transaction_from_query_result(row_dict)
                    ],
                    'rate_obj': {
                        'id': row_dict['rate_obj_id'],
                        'name': row_dict['rate_obj_name'],
                        'decimal_price': row_dict['rate_obj_decimal_price'],
                        'is_active': row_dict['rate_obj_is_active'],
                    }
                }
    except Exception as e:
        logger.exception(e)
        return Response(f'Error getting billing records {e}', status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response(
        data=list(results.values())
    )

@api_view(('GET', ))
def get_summary_by_account(request):
    '''
    Return summary by account
    '''
    year = request.GET.get('year', None)
    month = request.GET.get('month', None)
    invoice_prefix = request.GET.get('invoice_prefix', None)
    facility = request.GET.get('facility', None)
    organization = request.GET.get('organization', None)
    results = []

    sql = '''
        select
            acct.id as id,
            acct.code as code,
            acct.name as name,
            acct.account_type,
            o.name as organization,
            sum(br.decimal_charge) as total_decimal_charge
        from
            billing_record br
            inner join product_usage pu on pu.id = br.product_usage_id
            inner join product p on p.id = pu.product_id
            inner join facility f on f.id = p.facility_id
            inner join account acct on acct.id = br.account_id
            inner join nanites_organization o on o.id = acct.organization_id
    '''
    where_clauses = []
    query_args = []
    if year:
        try:
            year = int(year)
        except ValueError:
            return Response('year must be an integer', status=status.HTTP_400_BAD_REQUEST)
        where_clauses.append('br.year = %s')
        query_args.append(year)

    if month:
        try:
            month = int(month)
        except ValueError:
            return Response('month must be an integer', status=status.HTTP_400_BAD_REQUEST)
        where_clauses.append('br.month = %s')
        query_args.append(month)

    if invoice_prefix:
        where_clauses.append('f.invoice_prefix = %s')
        query_args.append(invoice_prefix)

    if organization:
        where_clauses.append('o.slug = %s')
        query_args.append(organization)

    if facility:
        where_clauses.append('f.name = %s')
        query_args.append(facility)

    if where_clauses:
        sql += ' where '
        sql += ' and '.join(where_clauses)

    sql += ' group by id, code, name, account_type, organization order by name'

    try:
        cursor = connection.cursor()
        cursor.execute(sql, query_args)

        desc = cursor.description

        for row in cursor.fetchall():
            # Make a dictionary labeled by column name
            row_dict = dict(zip([col[0] for col in desc], row))
            results.append(row_dict)
    except Exception as e:
        logger.exception(e)
        return Response(f'Error getting billing records {e}', status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response(
        data=results
    )

@api_view(('GET', ))
def get_summary_by_product_rate(request):
    '''
    Return summary by product
    '''
    year = request.GET.get('year', None)
    month = request.GET.get('month', None)
    invoice_prefix = request.GET.get('invoice_prefix', None)
    facility = request.GET.get('facility', None)
    organization = request.GET.get('organization', None)
    results = []

    sql = '''
        select
            p.id as product_id,
            p.product_name,
            p.product_number,
            r.name as rate_name,
            r.units,
            sum(pu.decimal_quantity) as total_decimal_quantity,
            sum(br.decimal_charge) as total_decimal_charge
        from
            billing_record br
            inner join product_usage pu on pu.id = br.product_usage_id
            inner join product p on p.id = pu.product_id
            inner join rate r on r.id = br.rate_obj_id
            inner join facility f on f.id = p.facility_id
            inner join account acct on acct.id = br.account_id
            inner join nanites_organization o on o.id = acct.organization_id
    '''
    where_clauses = []
    query_args = []
    if year:
        try:
            year = int(year)
        except ValueError:
            return Response('year must be an integer', status=status.HTTP_400_BAD_REQUEST)
        where_clauses.append('br.year = %s')
        query_args.append(year)

    if month:
        try:
            month = int(month)
        except ValueError:
            return Response('month must be an integer', status=status.HTTP_400_BAD_REQUEST)
        where_clauses.append('br.month = %s')
        query_args.append(month)

    if invoice_prefix:
        where_clauses.append('f.invoice_prefix = %s')
        query_args.append(invoice_prefix)

    if organization:
        where_clauses.append('o.slug = %s')
        query_args.append(organization)

    if facility:
        where_clauses.append('f.name = %s')
        query_args.append(facility)

    if where_clauses:
        sql += ' where '
        sql += ' and '.join(where_clauses)

    sql += ' group by product_id, product_name, product_number, rate_name, units order by product_name'

    try:
        cursor = connection.cursor()
        cursor.execute(sql, query_args)

        desc = cursor.description

        for row in cursor.fetchall():
            # Make a dictionary labeled by column name
            row_dict = dict(zip([col[0] for col in desc], row))
            results.append(row_dict)
    except Exception as e:
        logger.exception(e)
        return Response(f'Error getting summary by product {e}', status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response(
        data=results
    )

@api_view(('GET', ))
def get_summary_by_user(request):
    '''
    Return summary by user
    '''
    year = request.GET.get('year', None)
    month = request.GET.get('month', None)
    invoice_prefix = request.GET.get('invoice_prefix', None)
    facility = request.GET.get('facility', None)
    organization = request.GET.get('organization', None)

    results = []

    sql = '''
        select
            product_user.id as product_user_id,
            product_user.full_name as product_user_full_name,
            product_user.ifxid as product_user_ifxid,
            sum(br.decimal_charge) as total_decimal_charge
        from
            billing_record br
            inner join product_usage pu on pu.id = br.product_usage_id
            inner join product p on p.id = pu.product_id
            inner join facility f on f.id = p.facility_id
            inner join account acct on acct.id = br.account_id
            inner join nanites_organization o on o.id = acct.organization_id
            inner join ifxuser product_user on pu.product_user_id = product_user.id
    '''
    where_clauses = []
    query_args = []
    if year:
        try:
            year = int(year)
        except ValueError:
            return Response('year must be an integer', status=status.HTTP_400_BAD_REQUEST)
        where_clauses.append('br.year = %s')
        query_args.append(year)

    if month:

        try:
            month = int(month)
        except ValueError:
            return Response('month must be an integer', status=status.HTTP_400_BAD_REQUEST)
        where_clauses.append('br.month = %s')
        query_args.append(month)

    if invoice_prefix:
        where_clauses.append('f.invoice_prefix = %s')
        query_args.append(invoice_prefix)

    if organization:
        where_clauses.append('o.slug = %s')
        query_args.append(organization)

    if facility:
        where_clauses.append('f.name = %s')
        query_args.append(facility)

    if where_clauses:
        sql += ' where '
        sql += ' and '.join(where_clauses)

    sql += ' group by product_user_id, product_user_full_name, product_user_ifxid order by product_user_full_name'

    try:
        cursor = connection.cursor()
        cursor.execute(sql, query_args)

        desc = cursor.description

        for row in cursor.fetchall():
            # Make a dictionary labeled by column name
            row_dict = dict(zip([col[0] for col in desc], row))
            results.append(row_dict)

    except Exception as e:
        logger.exception(e)
        return Response(f'Error getting summary by user {e}', status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response(
        data=results
    )

@api_view(('GET', ))
def get_orgs_with_billing(request, invoice_prefix, year, month):
    '''
    Return a list of organization slugs for which there are billing records
    '''

    results = []
    sql = '''
        select
            distinct o.slug
        from
            nanites_organization o
        where
            exists (
                select
                    1
                from
                    billing_record br
                    inner join account acct on acct.id = br.account_id
                    inner join product_usage pu on pu.id = br.product_usage_id
                    inner join product p on p.id = pu.product_id
                    inner join facility f on f.id = p.facility_id
                where
                    acct.organization_id = o.id
                    and br.year = %s
                    and br.month = %s
                    and f.invoice_prefix = %s
            )
    '''
    query_args = [year, month, invoice_prefix]

    try:
        cursor = connection.cursor()
        cursor.execute(sql, query_args)

        for row in cursor.fetchall():
            results.append(row[0])

    except Exception as e:
        logger.exception(e)
        return Response(f'Error getting organizations with billing records for {year}, {month} {e}', status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response(
        data=results
    )


@api_view(('GET', ))
def get_charge_history(request):
    '''
    Return organizations with billing record totals for the specified date range
    '''
    start_year = request.GET.get('start_year', None)
    start_month = request.GET.get('start_month', None)

    today = timezone.now()
    end_year = request.GET.get('end_year', today.year)
    end_month = request.GET.get('end_month', today.month)

    invoice_prefix = request.GET.get('invoice_prefix', None)

    try:
        start_date = timezone.datetime(int(start_year), int(start_month), 1)
    except ValueError:
        return Response(f'Invalid start date {start_year}-{start_month}-1', status=status.HTTP_400_BAD_REQUEST)

    try:
        end_date = timezone.datetime(int(end_year), int(end_month), 1)
    except ValueError:
        return Response(f'Invalid end date {end_year}-{end_month}-1', status=status.HTTP_400_BAD_REQUEST)

    try:
        models.Facility.objects.get(invoice_prefix=invoice_prefix)
    except models.Facility.DoesNotExist:
        return Response(data={ 'error': f'Facility cannot be found using invoice_prefix {invoice_prefix}' }, status=status.HTTP_400_BAD_REQUEST)


    sql = '''
        select
            o.name,
            concat(br.year, '-', lpad(br.month, 2, '0')) as month_key,
            sum(br.decimal_charge) as total_decimal_charge
        from
            billing_record br
            inner join account acct on acct.id = br.account_id
            inner join product_usage pu on pu.id = br.product_usage_id
            inner join product p on p.id = pu.product_id
            inner join facility f on f.id = p.facility_id
            inner join nanites_organization o on o.id = acct.organization_id
        where
            br.year >= %s
            and br.month >= %s
            and br.year <= %s
            and br.month <= %s
            and f.invoice_prefix = %s
            and o.org_tree = 'Harvard'
        group by o.name, month_key
    '''
    query_args = [start_date.year, start_date.month, end_date.year, end_date.month, invoice_prefix]

    try:
        cursor = connection.cursor()
        cursor.execute(sql, query_args)

        desc = cursor.description
        results = defaultdict(lambda: defaultdict(Decimal))

        for row in cursor.fetchall():
            # Make a dictionary labeled by column name
            row_dict = dict(zip([col[0] for col in desc], row))
            results[row_dict['name']][row_dict['month_key']] = row_dict['total_decimal_charge']

    except Exception as e:
        logger.exception(e)
        return Response(f'Error getting charge history {e}', status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response(
        data=results
    )

@api_view(('GET', ))
def get_pending_year_month(request, invoice_prefix):
    '''
    Return the year and month of the most recent pending billing record for the organization.
    Used by fiine to indicate what month will be rebalanced after saving coding changes.
    '''
    try:
        facility = models.Facility.objects.get(invoice_prefix=invoice_prefix)
    except models.Facility.DoesNotExist:
        return Response(data={ 'error': f'Facility cannot be found using invoice_prefix {invoice_prefix}' }, status=status.HTTP_400_BAD_REQUEST)

    try:
        br = models.BillingRecord.objects.filter(product_usage__product__facility=facility, current_state='PENDING_LAB_APPROVAL').latest('year', 'month')
        return Response(data={ 'year': br.year, 'month': br.month })

    except models.BillingRecord.DoesNotExist:
        return Response(data={ 'error': 'No pending billing records found' }, status=status.HTTP_404_NOT_FOUND)


@api_view(('POST', ))
def rebalance(request):
    '''
    Rebalance the billing records for the given facility, user, year, and month
    '''
    try:
        data = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError as e:
        logger.exception(e)
        return Response(data={'error': 'Cannot parse request body'}, status=status.HTTP_400_BAD_REQUEST)

    invoice_prefix = data.get('invoice_prefix', None)
    ifxid = data.get('ifxid', None)
    year = data.get('year', None)
    month = data.get('month', None)
    account_data = data.get('account_data', None)
    requestor_ifxid = data.get('requestor_ifxid', None)

    if not invoice_prefix:
        return Response(data={ 'error': 'invoice_prefix is required' }, status=status.HTTP_400_BAD_REQUEST)
    if not ifxid:
        return Response(data={ 'error': 'ifxid is required' }, status=status.HTTP_400_BAD_REQUEST)
    if not year:
        return Response(data={ 'error': 'year is required' }, status=status.HTTP_400_BAD_REQUEST)
    if not month:
        return Response(data={ 'error': 'month is required' }, status=status.HTTP_400_BAD_REQUEST)
    if not requestor_ifxid:
        return Response(data={ 'error': 'requestor_ifxid is required' }, status=status.HTTP_400_BAD_REQUEST)


    try:
        facility = models.Facility.objects.get(invoice_prefix=invoice_prefix)
    except models.Facility.DoesNotExist:
        return Response(data={ 'error': f'Facility cannot be found using invoice_prefix {invoice_prefix}' }, status=status.HTTP_400_BAD_REQUEST)

    try:
        user = ifxuser_models.IfxUser.objects.get(ifxid=ifxid)
    except ifxuser_models.IfxUser.DoesNotExist:
        return Response(data={ 'error': f'User cannot be found using ifxid {ifxid}' }, status=status.HTTP_400_BAD_REQUEST)

    try:
        requestor = ifxuser_models.IfxUser.objects.get(ifxid=requestor_ifxid)
    except ifxuser_models.IfxUser.DoesNotExist:
        return Response(data={ 'error': f'Requestor cannot be found using ifxid {requestor_ifxid}' }, status=status.HTTP_400_BAD_REQUEST)


    auth_token_str = request.META.get('HTTP_AUTHORIZATION')
    rebalancer = get_rebalancer_class()(year, month, facility, auth_token_str, requestor)
    try:
        rebalancer.rebalance_user_billing_month(user, account_data)
        result = f'Rebalance of accounts for {user.full_name} for billing month {month}/{year} was successful.'
        # rebalancer.send_result_notification(result)
        return Response(data={ 'success':  result })
    except Exception as e:
        logger.exception(e)
        result = f'Rebalance of accounts for {user.full_name} for billing month {month}/{year} failed: {e}'
        # rebalancer.send_result_notification(result)
        return Response(data={ 'error': f'Rebalance failed {e}' }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
