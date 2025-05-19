from django.core.management.base import BaseCommand
from common.models import State, BusinessDistrict, InjectionSubstation, Feeder, Band
from financial.models import Expense, ExpenseCategory, GLBreakdown
from technical.models import HourlyLoad
from hr.models import Staff, Department, Role
from django.utils.dateparse import parse_date
import uuid
from decouple import config

# Connect to external DB
import pyodbc

def parse_nullable(value, fallback=None):
    return value if value not in [None, '', 'NULL'] else fallback

class Command(BaseCommand):
    help = 'Import legacy data from external database'

    def handle(self, *args, **kwargs):
        self.stdout.write("Connecting to external database...")
        conn = pyodbc.connect("DRIVER={SQL Server};SERVER=" +config('legacy_mysql_server') + ";DATABASE="+ config('legacy_db') + ";UID=" + config("legacy_user") + ";PWD=" + config("legacy_password"))
        cursor = conn.cursor()

        self.import_states(cursor)
        self.import_districts(cursor)
        self.import_injection_stations(cursor)
        self.import_feeders(cursor)
        self.import_gl_breakdowns(cursor)
        self.import_expenses(cursor)
        self.import_hourly_load(cursor)
        self.import_staff(cursor)

        self.stdout.write(self.style.SUCCESS('Legacy data imported successfully.'))

    def import_states(self, cursor):
        cursor.execute("SELECT state_id, state_name FROM states")
        for row in cursor.fetchall():
            State.objects.get_or_create(slug=row.state_id.strip(), defaults={"name": row.state_name.strip()})

    def import_districts(self, cursor):
        cursor.execute("SELECT district_id, district_name, state_id FROM business_districts")
        for row in cursor.fetchall():
            state = State.objects.filter(slug=row.state_id.strip()).first()
            if state:
                BusinessDistrict.objects.get_or_create(
                    slug=row.district_id.strip(),
                    defaults={"name": row.district_name.strip(), "state": state}
                )

    def import_injection_stations(self, cursor):
        cursor.execute("SELECT injection_station_id, injection_station_name, district_id FROM injection_stations")
        for row in cursor.fetchall():
            district = BusinessDistrict.objects.filter(slug=row.district_id.strip()).first()
            if district:
                InjectionSubstation.objects.get_or_create(
                    slug=row.injection_station_id.strip(),
                    defaults={"name": row.injection_station_name.strip(), "district": district}
                )

    def import_feeders(self, cursor):
        cursor.execute("SELECT feeder_id, feeder_name, injection_station_id, service_band FROM feeders")
        for row in cursor.fetchall():
            substation = InjectionSubstation.objects.filter(slug=row.injection_station_id.strip()).first()
            band = Band.objects.filter(name__iexact=row.service_band.strip()).first()
            if substation:
                Feeder.objects.get_or_create(
                    slug=row.feeder_id.strip(),
                    defaults={
                        "name": row.feeder_name.strip(),
                        "substation": substation,
                        "band": band,
                        "voltage_level": "11kv" if "11KV" in row.feeder_name.upper() else "33kv"
                    }
                )

    def import_gl_breakdowns(self, cursor):
        cursor.execute("SELECT DISTINCT [GL Account opex break down] FROM gl_codes")
        for row in cursor.fetchall():
            name = row[0].strip()
            if name:
                GLBreakdown.objects.get_or_create(name=name)

    def import_expenses(self, cursor):
        cursor.execute("""
            SELECT district_id, date, [Purpose of transaction], [Payment to], 
                   Debit, Credit, [GL Account code number], [GL Account opex break down], [opex categorization]
            FROM financialopex
        """)
        for row in cursor.fetchall():
            district = BusinessDistrict.objects.filter(slug=row.district_id.strip()).first()
            category, _ = ExpenseCategory.objects.get_or_create(name=row[8].strip())
            breakdown = GLBreakdown.objects.filter(name=row[7].strip()).first()

            if district and breakdown:
                Expense.objects.create(
                    district=district,
                    date=parse_date(str(row.date)),
                    purpose=parse_nullable(row[2]),
                    payee=parse_nullable(row[3]),
                    debit=parse_nullable(row[4], 0.0),
                    credit=parse_nullable(row[5], 0.0),
                    gl_account_number=row[6],
                    gl_breakdown=breakdown,
                    opex_category=category
                )

    def import_hourly_load(self, cursor):
        cursor.execute("SELECT feeder_id, reading_date, reading_hour, load_mw FROM hourly_load")
        for row in cursor.fetchall():
            feeder = Feeder.objects.filter(slug=row.feeder_id.strip()).first()
            if feeder and isinstance(row.load_mw, (int, float)):
                HourlyLoad.objects.create(
                    feeder=feeder,
                    date=parse_date(str(row.reading_date)),
                    hour=row.reading_hour,
                    load_mw=row.load_mw
                )

    def import_staff(self, cursor):
        cursor.execute("SELECT staff_id, district_id, name, email, phone_number, gender, salary, start_date, end_date, Department, grade FROM hr_staff")
        for row in cursor.fetchall():
            district = BusinessDistrict.objects.filter(slug=row.district_id.strip()).first()
            dept, _ = Department.objects.get_or_create(name=row.Department.strip())
            role, _ = Role.objects.get_or_create(title=row.grade.strip(), department=dept)

            Staff.objects.create(
                full_name=row.name.strip(),
                email=parse_nullable(row.email),
                phone_number=parse_nullable(row.phone_number),
                gender=row.gender,
                birth_date=date.today(),  # placeholder if age not given
                salary=row.salary,
                hire_date=parse_date(str(row.start_date)),
                exit_date=parse_date(str(row.end_date)) if row.end_date else None,
                grade=row.grade,
                role=role,
                department=dept,
                district=district,
                state=district.state if district else None
            )
