from django.core.management.base import BaseCommand
from common.models import State, BusinessDistrict, InjectionSubstation, Feeder, Band
from financial.models import Expense, ExpenseCategory, GLBreakdown
from technical.models import HourlyLoad, FeederInterruption
from hr.models import Staff, Department, Role
from django.utils.dateparse import parse_date
from decouple import config
from datetime import date, timedelta
from django.utils.text import slugify
from django.utils.timezone import make_aware
from django.conf import settings
from datetime import datetime, time
import pymysql


def parse_nullable(value, fallback=None):
    return value if value not in [None, '', 'NULL'] else fallback


class Command(BaseCommand):
    help = 'Import legacy data from external MySQL database'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.MIGRATE_HEADING("Connecting to external MySQL database..."))

        conn = pymysql.connect(
            host=config("legacy_mysql_server"),
            user=config("legacy_user"),
            password=config("legacy_password"),
            db=config("legacy_db"),
            cursorclass=pymysql.cursors.DictCursor
        )

        with conn:
            # self.import_states(conn)
            # self.import_districts(conn)
            # self.import_injection_stations(conn)
            # self.import_feeders(conn)
            # self.import_feeder_interruptions(conn)
            # self.import_gl_breakdowns(conn)
            # self.import_expenses(conn)
            # self.import_hourly_load(conn)
            # self.import_staff(conn)
            self.import_sales_reps(conn)

        self.stdout.write(self.style.SUCCESS('Legacy data imported successfully.'))

    def import_states(self, conn):
        self.stdout.write(self.style.HTTP_INFO("\nImporting States..."))
        count = 0
        with conn.cursor() as cursor:
            cursor.execute("SELECT state_id, state_name FROM states")
            for row in cursor.fetchall():
                name = row["state_name"].strip()
                slug = row["state_id"].strip()  # Use ID as slug
                _, created = State.objects.get_or_create(
                    slug=slug,
                    defaults={"name": name}
                )
                count += int(created)
        self.stdout.write(self.style.SUCCESS(f"States imported: {count} new entries."))


    def import_districts(self, conn):
        self.stdout.write(self.style.HTTP_INFO("\nImporting Business Districts..."))
        count = 0
        with conn.cursor() as cursor:
            cursor.execute("SELECT district_id, district_name, state_id FROM business_districts")
            for row in cursor.fetchall():
                name = row["district_name"].strip()
                slug = row["district_id"].strip()
                state = State.objects.filter(slug=row["state_id"].strip()).first()
                if state:
                    _, created = BusinessDistrict.objects.get_or_create(
                        slug=slug,
                        defaults={"name": name, "state": state}
                    )
                    count += int(created)
        self.stdout.write(self.style.SUCCESS(f"Business Districts imported: {count} new entries."))


    def import_injection_stations(self, conn):
        self.stdout.write(self.style.HTTP_INFO("\nImporting Injection Substations..."))
        count = 0
        imported_names = set()

        with conn.cursor() as cursor:
            cursor.execute("SELECT injection_station_id, injection_station_name FROM injection_stations")
            for row in cursor.fetchall():
                name = row["injection_station_name"].strip()
                slug = row["injection_station_id"].strip()

                # Skip if we've already imported a substation with this name
                if name.lower() in imported_names:
                    continue

                _, created = InjectionSubstation.objects.get_or_create(
                    slug=slug,
                    defaults={"name": name}
                )

                if created:
                    imported_names.add(name.lower())
                    count += 1

        self.stdout.write(self.style.SUCCESS(f"Substations imported: {count} new entries."))





    def import_feeders(self, conn):
        self.stdout.write(self.style.HTTP_INFO("\nImporting Feeders..."))
        count = 0
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT feeder_id, feeder_name, injection_station_id, district_id, feeder_type
                FROM feeders
            """)
            for row in cursor.fetchall():
                name = row["feeder_name"].strip()
                slug = row["feeder_id"].strip()
                feeder_type = (row.get("feeder_type") or "").strip().upper()
                voltage_level = "11kv" if "11" in feeder_type else "33kv"

                substation = InjectionSubstation.objects.filter(slug=row["injection_station_id"].strip()).first()
                district = BusinessDistrict.objects.filter(slug=row["district_id"].strip()).first()

                if substation and district:
                    _, created = Feeder.objects.get_or_create(
                        slug=slug,
                        defaults={
                            "name": name,
                            "substation": substation,
                            "voltage_level": voltage_level,
                            "business_district": district,
                        }
                    )
                    count += int(created)

        self.stdout.write(self.style.SUCCESS(f"Feeders imported: {count} new entries."))



    def import_gl_breakdowns(self, conn):
        self.stdout.write(self.style.HTTP_INFO("\nImporting GL Breakdowns..."))
        count = 0
        with conn.cursor() as cursor:
            cursor.execute("SELECT DISTINCT `GL Account opex break down` FROM financialopex")
            for row in cursor.fetchall():
                name = row["GL Account opex break down"]
                if name:
                    _, created = GLBreakdown.objects.get_or_create(name=name.strip())
                    count += int(created)
        self.stdout.write(self.style.SUCCESS(f"GL Breakdowns imported: {count} new entries."))


    def import_expenses(self, conn):
        self.stdout.write(self.style.HTTP_INFO("\nImporting Expenses..."))
        count = 0
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT district_id, date, `Purpose of transaction`, `Payment to`, 
                       Debit, Credit, `GL Account code number`, `GL Account opex break down`, `opex categorization`
                FROM financialopex
            """)
            for row in cursor.fetchall():
                district = BusinessDistrict.objects.filter(slug=row["district_id"].strip()).first()
                if not district:
                    self.stdout.write(self.style.WARNING(f"Skipping expense — unknown district {row['district_id']}"))
                    continue

                category, _ = ExpenseCategory.objects.get_or_create(name=row["opex categorization"].strip())
                breakdown = GLBreakdown.objects.filter(name=row["GL Account opex break down"].strip()).first()
                

                if breakdown:
                    Expense.objects.create(
                        district=district,
                        date=parse_date(str(row["date"])),
                        purpose=parse_nullable(row["Purpose of transaction"], 'N/A'),
                        payee=parse_nullable(row["Payment to"], "N/A"),
                        debit=parse_nullable(row["Debit"], 0.0),
                        credit=parse_nullable(row["Credit"], 0.0),
                        gl_account_number=str(row["GL Account code number"]).strip(),
                        gl_breakdown=breakdown,
                        opex_category=category
                    )

                if not breakdown:
                    self.stdout.write(self.style.WARNING(f"Skipping expense — unknown GL breakdown"))
                    continue
        self.stdout.write(self.style.SUCCESS(f"Expenses imported: {count} entries."))




    def import_hourly_load(self, conn):
        self.stdout.write(self.style.HTTP_INFO("\nImporting Hourly Load Data (chunked by date)..."))
        count = 0
        interruptions_created = 0
        skipped = 0

        with conn.cursor() as cursor:
            # Get date range
            cursor.execute("SELECT MIN(reading_date), MAX(reading_date) FROM hourly_load")
            result = cursor.fetchone()
            start_date, end_date = result

            if not start_date or not end_date:
                self.stdout.write(self.style.WARNING("⚠️ No data found in hourly_load table."))
                return

            current = start_date
            while current <= end_date:
                next_day = current + timedelta(days=1)

                self.stdout.write(self.style.HTTP_INFO(f"→ Importing for {current}"))

                cursor.execute("""
                    SELECT feeder_id, reading_date, reading_hour, load_mw
                    FROM hourly_load
                    WHERE reading_date >= %s AND reading_date < %s
                """, (current, next_day))

                rows = cursor.fetchall()

                for feeder_id, reading_date, reading_hour, load_raw in rows:
                    feeder_slug = (feeder_id or "").strip()
                    feeder = Feeder.objects.filter(slug=feeder_slug).first()

                    if not feeder:
                        self.stdout.write(self.style.WARNING(f"Feeder not found: {feeder_slug}"))
                        skipped += 1
                        continue

                    try:
                        parsed_date = parse_date(str(reading_date))
                        if not parsed_date or reading_hour is None:
                            raise ValueError
                    except Exception:
                        self.stdout.write(self.style.WARNING(
                            f"Invalid date/hour for feeder {feeder_slug}: {reading_date}, {reading_hour}"
                        ))
                        skipped += 1
                        continue

                    load_str = str(load_raw).strip() if load_raw is not None else ""
                    try:
                        load_value = float(load_str)
                        load_flag = None
                    except ValueError:
                        load_value = None
                        load_flag = load_str.upper()

                    if load_value is not None:
                        HourlyLoad.objects.update_or_create(
                            feeder=feeder,
                            date=parsed_date,
                            hour=reading_hour,
                            defaults={"load_mw": load_value}
                        )
                        count += 1
                    elif load_flag:
                        occurred_at = datetime.combine(parsed_date, time(hour=reading_hour))
                        if settings.USE_TZ:
                            occurred_at = make_aware(occurred_at)

                        obj, created = FeederInterruption.objects.get_or_create(
                            feeder=feeder,
                            occurred_at=occurred_at,
                            interruption_type=load_flag,
                            defaults={"description": "Logged from hourly load record"}
                        )
                        if created:
                            interruptions_created += 1
                    else:
                        self.stdout.write(self.style.WARNING(
                            f"Skipped: Empty or invalid load for feeder {feeder_slug} at {parsed_date} {reading_hour}"
                        ))
                        skipped += 1

                current = next_day

        self.stdout.write(self.style.SUCCESS(f"Hourly loads imported: {count}"))
        self.stdout.write(self.style.SUCCESS(f"Interruption events created: {interruptions_created}"))
        self.stdout.write(self.style.WARNING(f"Skipped rows: {skipped}"))



    def import_staff(self, conn):
        self.stdout.write(self.style.HTTP_INFO("\nImporting HR Staff..."))
        count = 0
        previous_hire_date = None
        previous_birth_date = None

        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT staff_id, district_id, name, email, phone_number, gender, salary, 
                       start_date, end_date, Department, grade, age
                FROM hr_staff
            """)
            for row in cursor.fetchall():
                district = BusinessDistrict.objects.filter(slug=row["district_id"].strip()).first()
                dept_name = row["Department"].strip()
                grade_name = row["grade"].strip()

                slug = slugify(dept_name)
                department, _ = Department.objects.get_or_create(
                    slug=slug,
                    defaults={"name": dept_name}
                )

                role_slug = slugify(grade_name)
                role, _ = Role.objects.get_or_create(
                    slug=role_slug,
                    defaults={"title": grade_name, "department": department}
                )

                raw_hire_date = row.get("start_date")
                hire_date = parse_date(str(raw_hire_date)) if raw_hire_date else previous_hire_date
                if hire_date:
                    previous_hire_date = hire_date
                else:
                    self.stdout.write(self.style.WARNING(
                        f"Staff {row['name'].strip()} skipped: no valid hire date and no fallback available."))
                    continue

                raw_age = row.get("age")
                if raw_age and isinstance(raw_age, (int, float)):
                    birth_date = date.today() - timedelta(days=round(float(raw_age) * 365.25))
                    previous_birth_date = birth_date
                elif previous_birth_date:
                    birth_date = previous_birth_date
                else:
                    birth_date = date.today() - timedelta(days=30 * 365)

                Staff.objects.create(
                    full_name=row["name"].strip(),
                    email=parse_nullable(row["email"]),
                    phone_number=parse_nullable(row["phone_number"], "N/A"),
                    gender=row["gender"],
                    birth_date=birth_date,
                    salary=parse_nullable(row["salary"], 0),
                    hire_date=hire_date,
                    exit_date=parse_date(str(row["end_date"])) if row["end_date"] else None,
                    grade=grade_name,
                    role=role,
                    department=department,
                    district=district,
                    state=district.state if district else None
                )
                count += 1
        self.stdout.write(self.style.SUCCESS(f"Staff imported: {count} entries."))


    def import_feeder_interruptions(self, conn):
        from technical.models import FeederInterruption
        self.stdout.write(self.style.HTTP_INFO("\nImporting Feeder Interruptions..."))
        count = 0
        skipped = 0

        FAULT_TYPE_MAP = {
            "Earth Fault": "E/F",
            "Overcurrent Fault": "O/C",
            "Overcurrent and Earth Fault": "O/C & E/F",
            None: "N/A",
            "": "N/A",
        }

        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT feeder_id, fault_occurrence, fault_resolve, fault_type, brief_description
                FROM feeder_faults
            """)
            for row in cursor.fetchall():
                feeder_slug = row["feeder_id"].strip()
                feeder = Feeder.objects.filter(slug=feeder_slug).first()

                if not feeder:
                    self.stdout.write(self.style.WARNING(f"Feeder not found: {feeder_slug}"))
                    skipped += 1
                    continue

                interruption_type = FAULT_TYPE_MAP.get(row["fault_type"], row["fault_type"] or "N/A")
                occurred_at = row["fault_occurrence"]
                restored_at = row.get("fault_resolve") or None  # Could be NULL
                description = parse_nullable(row.get("brief_description"), "").strip()

                if occurred_at and isinstance(occurred_at, datetime.datetime) and occurred_at.tzinfo is None:
                    occurred_at = make_aware(occurred_at)

                if restored_at and isinstance(restored_at, datetime.datetime) and restored_at.tzinfo is None:
                    restored_at = make_aware(restored_at)


                # Ensure no duplicates
                exists = FeederInterruption.objects.filter(
                    feeder=feeder,
                    occurred_at=occurred_at,
                    interruption_type=interruption_type,
                ).exists()

                if not exists:
                    FeederInterruption.objects.create(
                        feeder=feeder,
                        occurred_at=occurred_at,
                        restored_at=restored_at,
                        interruption_type=interruption_type,
                        description=description
                    )
                    count += 1

        self.stdout.write(self.style.SUCCESS(f"Feeder interruptions imported: {count} entries."))
        self.stdout.write(self.style.WARNING(f"Skipped: {skipped} rows (e.g., missing feeder)"))



    def import_sales_reps(self, conn):
        from commercial.models import SalesRepresentative
        from common.models import Feeder

        self.stdout.write(self.style.HTTP_INFO("\nImporting Sales Representatives and assigning feeders..."))
        created_count = 0
        linked_count = 0
        skipped = 0

        with conn.cursor() as cursor:
            # We'll process unique sales reps and their feeder links
            cursor.execute("SELECT DISTINCT sales_rep_id, sales_rep_name FROM sales_rep_feeder_map")
            reps = cursor.fetchall()

            for row in reps:
                slug = parse_nullable(row.get("sales_rep_id"), "").strip()
                name = parse_nullable(row.get("sales_rep_name"), "").strip()

                if not slug or not name:
                    self.stdout.write(self.style.WARNING("Skipping row with missing ID or name."))
                    continue

                rep, created = SalesRepresentative.objects.get_or_create(
                    slug=slug,
                    defaults={"name": name}
                )
                created_count += int(created)

            # Now fetch and assign feeders
            cursor.execute("SELECT sales_rep_id, feeder_id FROM sales_rep_feeder_map")
            mapping_rows = cursor.fetchall()

            for row in mapping_rows:
                rep_slug = parse_nullable(row.get("sales_rep_id"), "").strip()
                feeder_slug = parse_nullable(row.get("feeder_id"), "").strip()

                rep = SalesRepresentative.objects.filter(slug=rep_slug).first()
                feeder = Feeder.objects.filter(slug=feeder_slug).first()

                if not rep or not feeder:
                    self.stdout.write(self.style.WARNING(
                        f"Could not assign feeder {feeder_slug} to rep {rep_slug} — missing entity."
                    ))
                    skipped += 1
                    continue

                rep.assigned_feeders.add(feeder)
                linked_count += 1

        self.stdout.write(self.style.SUCCESS(f"Sales Reps created: {created_count}"))
        self.stdout.write(self.style.SUCCESS(f"Feeder links established: {linked_count}"))
        self.stdout.write(self.style.WARNING(f"Feeder-rep links skipped: {skipped}"))
