
# -*- coding: utf-8 -*-

'''
Calculate billing records for the given year and month
'''
from io import StringIO
from django.utils import timezone
from django.core.management.base import BaseCommand
from django.core.management import call_command
from ifxbilling.models import ProductUsage
from ifxbilling.calculator import getClassFromName


class Command(BaseCommand):
    '''
    Calculate billing records for the given year and month
    '''
    help = 'Calculate billing records for the given year and month Usage:\n' + \
        "./manage.py calculateBillingRecords --year 2021 --month 3"

    def handle(self, *args, **kwargs):
        year = timezone.now().year
        month = timezone.now().month
        if kwargs['month']:
            month = int(kwargs['month'])
        if kwargs['year']:
            year = int(kwargs['year'])
        product_usages = ProductUsage.objects.filter(month=month, year=year)
        calculators = {}
        for product_usage in product_usages:
            try:
                billing_calculator_name = product_usage.product.billing_calculator
                if billing_calculator_name not in calculators:
                    calculators[billing_calculator_name] = getClassFromName(billing_calculator_name)
                billing_calculator = calculators[billing_calculator_name]
                billing_calculator.createBillingRecordForUsage(product_usage)
            except Exception as e:
                print(f'Unable to create billing record for {product_usage}: {e}')

