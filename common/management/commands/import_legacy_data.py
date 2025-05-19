from django.core.management.base import BaseCommand
from common.models import State, BusinessDistrict, InjectionSubstation, Feeder, Band
from financial.models import Expense, ExpenseCategory, GLBreakdown
from technical.models import HourlyLoad
from hr.models import Staff, Department, Role
from django.utils.dateparse import parse_date
from decouple import config
from datetime import date
import pymysql


def parse_nullable(value, fallback=None):
    return value if value not in [None, '', 'NULL'] else fallback


class Command(BaseCommand):
    help = 'Import legacy data from external MySQL database'

    def handle(self, *args, **kwargs):
        self.stdout.write("Connecting to external MySQL database...")

        conn = pymysql.connect(
            host=config("legacy_mysql_server"),
            user=config("legacy_user"),
            password=config("legacy_password"),
            db=config("legacy_db"),
            cursorclass=pymysql.cursors.DictCursor
        )

        with conn:
            self.import_states(conn)
            self.import_districts(conn)
            self.import_injection_stations(conn)
            self.import_feeders(conn)
            self.import_gl_breakdowns(conn)
            self.import_expenses(conn)
            self.import_hourly_load(conn)
            self.import_staff(conn)

        self.stdout.write(self.style.SUCCESS('Legacy data imported successfully.'))

    def import_states(self, conn):
        with conn.cursor() as cursor:
            cursor.execute("SELECT state_id, state_name FROM states")
            for row in cursor.fetchall():
                State.objects.get_or_create(
                    slug=row["state_id"].strip(),
                    defaults={"name": row["state_name"].strip()}
                )

    def import_districts(self, conn):
        with conn.cursor() as cursor:
            cursor.execute("SELECT district_id, district_name, state_id FROM business_districts")
            for row in cursor.fetchall():
                state = State.objects.filter(slug=row["state_id"].strip()).first()
                if state:
                    BusinessDistrict.objects.get_or_create(
                        slug=row["district_id"].strip(),
                        defaults={"name": row["district_name"].strip(), "state": state}
                    )

    def import_injection_stations(self, conn):
        with conn.cursor() as cursor:
            cursor.execute("SELECT injection_station_id, injection_station_name, district_id FROM injection_stations")
            for row in cursor.fetchall():
                district = BusinessDistrict.objects.filter(slug=row["district_id"].strip()).first()
                if district:
                    InjectionSubstation.objects.get_or_create(
                        slug=row["injection_station_id"].strip(),
                        defaults={"name": row["injection_station_name"].strip(), "district": district}
                    )

    def import_feeders(self, conn):
        with conn.cursor() as cursor:
            cursor.execute("SELECT feeder_id, feeder_name, injection_station_id, service_band FROM feeders")
            for row in cursor.fetchall():
                substation = InjectionSubstation.objects.filter(slug=row["injection_station_id"].strip()).first()
                band = Band.objects.filter(name__iexact=row["service_band"].strip()).first()
                if substation:
                    Feeder.objects.get_or_create(
                        slug=row["feeder_id"].strip(),
                        defaults={
                            "name": row["feeder_name"].strip(),
                            "substation": substation,
                            "band": band,
                            "voltage_level": "11kv" if "11KV" in row["feeder_name"].upper() else "33kv"
                        }
                    )

    def import_gl_breakdowns(self, conn):
        with conn.cursor() as cursor:
            cursor.execute("SELECT DISTINCT `GL Account opex break down` FROM financialopex")
            for row in cursor.fetchall():
                name = row["GL Account opex break down"]
                if name:
                    GLBreakdown.objects.get_or_create(name=name.strip())

    def import_expenses(self, conn):
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT district_id, date, `Purpose of transaction`, `Payment to`, 
                       Debit, Credit, `GL Account code number`, `GL Account opex break down`, `opex categorization`
                FROM financialopex
            """)
            for row in cursor.fetchall():
                district = BusinessDistrict.objects.filter(slug=row["district_id"].strip()).first()
                if not district:
                    continue

                category, _ = ExpenseCategory.objects.get_or_create(name=row["opex categorization"].strip())
                breakdown = GLBreakdown.objects.filter(name=row["GL Account opex break down"].strip()).first()

                if breakdown:
                    Expense.objects.create(
                        district=district,
                        date=parse_date(str(row["date"])),
                        purpose=parse_nullable(row["Purpose of transaction"]),
                        payee=parse_nullable(row["Payment to"]),
                        debit=parse_nullable(row["Debit"], 0.0),
                        credit=parse_nullable(row["Credit"], 0.0),
                        gl_account_number=str(row["GL Account code number"]).strip(),
                        gl_breakdown=breakdown,
                        opex_category=category
                    )

    def import_hourly_load(self, conn):
        with conn.cursor() as cursor:
            cursor.execute("SELECT feeder_id, reading_date, reading_hour, load_mw FROM hourly_load")
            for row in cursor.fetchall():
                feeder = Feeder.objects.filter(slug=row["feeder_id"].strip()).first()
                load = row["load_mw"]
                try:
                    load_value = float(load)
                except (ValueError, TypeError):
                    continue
                if feeder:
                    HourlyLoad.objects.create(
                        feeder=feeder,
                        date=parse_date(str(row["reading_date"])),
                        hour=row["reading_hour"],
                        load_mw=load_value
                    )

    def import_staff(self, conn):
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT staff_id, district_id, name, email, phone_number, gender, salary, 
                       start_date, end_date, Department, grade 
                FROM hr_staff
            """)
            for row in cursor.fetchall():
                district = BusinessDistrict.objects.filter(slug=row["district_id"].strip()).first()
                dept_name = row["Department"].strip()
                grade_name = row["grade"].strip()

                department, _ = Department.objects.get_or_create(name=dept_name)
                role, _ = Role.objects.get_or_create(title=grade_name, department=department)

                Staff.objects.create(
                    full_name=row["name"].strip(),
                    email=parse_nullable(row["email"]),
                    phone_number=parse_nullable(row["phone_number"]),
                    gender=row["gender"],
                    birth_date=date.today(),  # Placeholder for now
                    salary=row["salary"],
                    hire_date=parse_date(str(row["start_date"])),
                    exit_date=parse_date(str(row["end_date"])) if row["end_date"] else None,
                    grade=grade_name,
                    role=role,
                    department=department,
                    district=district,
                    state=district.state if district else None
                )
