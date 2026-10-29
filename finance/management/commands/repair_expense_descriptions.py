from django.core.management.base import BaseCommand,CommandError
from django.contrib.auth import get_user_model
from django.db import transaction
from finance.models import Company
from finance.migration_descriptions import repair_company


class Command(BaseCommand):
    help='Preview/apply an audited correction of the historical DR expense description mapping.'
    def add_arguments(self,parser):
        parser.add_argument('--company',type=int,required=True)
        parser.add_argument('--actor',type=int,required=True)
        parser.add_argument('--apply',action='store_true')
    def handle(self,*args,**options):
        actor=get_user_model().objects.filter(pk=options['actor'],is_active=True).first()
        if not actor:raise CommandError('Choose an active audit actor.')
        with transaction.atomic():
            company=Company.objects.select_for_update().filter(pk=options['company']).first()
            if not company:raise CommandError('Choose an existing company.')
            result=repair_company(company,actor)
            self.stdout.write(f"{'Applied' if options['apply'] else 'Preview'}: {result}")
            if not options['apply']:transaction.set_rollback(True)
