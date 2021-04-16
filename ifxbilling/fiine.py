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
from django.db import IntegrityError
from django.conf import settings
from rest_framework import status
from rest_framework.exceptions import ValidationError, NotAuthenticated
from fiine.client import API as FiineAPI
from fiine.client import ApiException
from ifxbilling import models


logger = logging.getLogger(__name__)


def updateUserAccounts(user):
    '''
    For a single user retrieve account strings from fiine.
    Remove any account string that are not represented in fiine.
    '''
    pass

def getExpenseCodeStatus(account):
    '''
    Use expense code validator to check an account
    '''
    pass


def createNewProduct(product_name, product_description, billing_calculator=None):
    '''
    Creates product record in fiine, and creates the local record with product number
    '''
    products = FiineAPI.listProducts(product_name=product_name)
    if products:
        raise IntegrityError(f'Product with name {product_name} exists in fiine.')

    facility = settings.FACILITY_NAME

    try:
        product_obj = FiineAPI.createProduct(
            product_name=product_name,
            product_description=product_description,
            facility=facility,
        )
        product = models.Product(
            product_number=product_obj.product_number,
            product_name=product_obj.product_name,
            product_description=product_obj.product_description,
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

