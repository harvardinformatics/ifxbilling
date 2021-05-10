# -*- coding: utf-8 -*-

'''
Calculate billing records for the given year and month
'''
from io import StringIO
from django.utils import timezone
from django.core.management.base import BaseCommand
from django.core.management import call_command
from ifxbilling.models import ProductUsage, BillingRecord
from ifxbilling.calculator import getClassFromName


class Command(BaseCommand):
    '''
    Calculate billing records for the given year and month
    '''
    help = 'Calculate billing records for the given year and month.  Use --recalculate to remove existing records and recreate. Usage:\n' + \
        "./manage.py calculateBillingRecords --year 2021 --month 3"

    def add_arguments(self, parser):
        parser.add_argument(
            '--year',
            dest='year',
            default=timezone.now().year,
            help='Year for calculation',
        )
        parser.add_argument(
            '--month',
            dest='month',
            default=timezone.now().month,
            help='Month for calculation',
        )
        parser.add_argument(
            '--recalculate',
            action='store_true',
            help='Remove existing billing records and recalculate',
        )

    def handle(self, *args, **kwargs):
        month = int(kwargs['month'])
        year = int(kwargs['year'])
        recalculate = kwargs['recalculate']

        product_usages = ProductUsage.objects.filter(month=month, year=year)
        calculators = {}
        for product_usage in product_usages:
            if BillingRecord.objects.filter(product_usage=product_usage).exists():
                if recalculate:
                    BillingRecord.objects.filter(product_usage=product_usage).delete()
                else:
                    continue
            try:
                billing_calculator_name = product_usage.product.billing_calculator
                if billing_calculator_name not in calculators:
                     billing_calculator_class = getClassFromName(billing_calculator_name)
                     calculators[billing_calculator_name] = billing_calculator_class()
                billing_calculator = calculators[billing_calculator_name]
                billing_calculator.createBillingRecordForUsage(product_usage)
            except Exception as e:
                print(f'Unable to create billing record for {product_usage}: {e}')

