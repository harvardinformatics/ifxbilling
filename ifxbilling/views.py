# -*- coding: utf-8 -*-

'''
Common views for expense codes
'''

import logging
import json
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.response import Response
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view
from ifxbilling.fiine import updateUserAccounts
from ifxbilling import models


logger = logging.getLogger(__name__)


def get_remote_user_auth_token(request):
    '''
    Get the token
    '''
    try:
        token = Token.objects.get(user=request.user)
    except Token.DoesNotExist:
        return Response({'error': 'User record for %s is not complete- missing token.' % str(request.user)}, status=401)

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
def update_user_accounts(request):
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

    try:
        data = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError as e:
        logger.exception(e)
        return Response(data={'error': 'Cannot parse request body'}, status=status.HTTP_400_BAD_REQUEST)

    if not data:
        queryset = get_user_model().objects.filter(ifxid__isnull=False)
    else:
        queryset = get_user_model().objects.filter(ifxid__in=data['ifxids'])

    successes = 0
    errors = []
    for user in queryset:
        try:
            updateUserAccounts(user)
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
                        'primary_affiliation': pu.product_user.primary_affiliation.slug,
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
