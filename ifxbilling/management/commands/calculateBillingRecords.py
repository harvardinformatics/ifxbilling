# -*- coding: utf-8 -*-

'''
Calculate billing records for the given year and month
'''
import logging
import datetime
from dateutil.relativedelta import relativedelta
from django.utils import timezone
from django.core.management.base import BaseCommand
from ifxbilling.calculator import calculateBillingMonth
from ifxbilling.models import Facility, Organization
from ifxbilling.util import get_class_from_name


logger = logging.getLogger('ifxbilling')


class Command(BaseCommand):
    '''
    Calculate billing records for the given year and month
    '''
    help = 'Calculate billing records for the given year and month.  Use --recalculate to remove existing records and recreate. Usage:\n' + \
        "./manage.py calculateBillingRecords 'Helium Recovery Service' --year 2021 --month 3"

    def add_arguments(self, parser):
        parser.add_argument(
            '--facility-name',
            dest='facility_name',
            help='Name of the facility to calculate for. Can be omitted if there is only one facility record.'
        )
        parser.add_argument(
            '--year',
            dest='year',
            default=(timezone.now() - relativedelta(months=1)).year,
            help='Year for calculation',
        )
        parser.add_argument(
            '--month',
            dest='month',
            default=(timezone.now() - relativedelta(months=1)).month,
            help='Month for calculation',
        )
        parser.add_argument(
            '--recalculate',
            action='store_true',
            help='Remove existing billing records and recalculate',
        )
        parser.add_argument(
            '--verbose',
            dest='verbose',
            type=int,
            help='Set verbosity: 0 - quiet, 1 - chatty, 2 - loud',
        )
        parser.add_argument(
            '--organization-names',
            dest='organization_names',
            help='Comma-separated list of organization names.'
        )

    def handle(self, *args, **kwargs):
        month = int(kwargs['month'])
        year = int(kwargs['year'])
        recalculate = kwargs['recalculate']
        verbose = kwargs['verbose']
        facility_name = kwargs.get('facility_name')
        organization_name_str = kwargs.get('organization_names')
        organization_objs = []
        if organization_name_str:
            organization_names = organization_name_str.split(',')
            for organization_name in organization_names:
                try:
                    organization_objs.append(Organization.objects.get(org_tree='Harvard', name=organization_name.strip()))
                except Organization.DoesNotExist:
                    raise Exception(f'Organization name {organization_name} cannot be found')

        if facility_name:
            try:
                facility = Facility.objects.get(name=facility_name)
            except Facility.DoesNotExist:
                raise Exception(f'Facility name {facility_name} cannot be found')
        else:
            facilities = Facility.objects.all()
            if len(facilities) == 1:
                facility = facilities[0]
            else:
                raise Exception(f'There are {len(facilities)} Facility records. Must specify facility if there is more than one.')

        if facility.billing_record_calculator: # if None then use the old calculator
            try:
                billing_record_calculator = get_class_from_name(facility.billing_record_calculator)
            except Exception as e:
                raise Exception(f'Facility billing record calculator class does not exist: {e}')
            billing_record_calculator = billing_record_calculator()
            results = billing_record_calculator.calculate_billing_month(year, month, organizations=organization_objs, recalculate=recalculate, verbosity=verbose)
            for org, res in results.items():
                print(f'{org} {res}')
        else:
            # use the old function
            (successes, errors) = calculateBillingMonth(month, year, facility, recalculate, (verbose > 0))
            print(f'{successes} product usages successfully processed')
            if errors:
                print('Errors: %s' % '\n'.join(errors))
