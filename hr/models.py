import uuid
from django.db import models
from common.models import UUIDModel, State, BusinessDistrict

class Department(UUIDModel, models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True, max_length=100)

    def __str__(self):
        return self.name

class Role(UUIDModel, models.Model):
    title = models.CharField(max_length=100)
    department = models.ForeignKey(Department, on_delete=models.CASCADE)
    slug = models.SlugField(unique=True, max_length=100)

    def __str__(self):
        return self.title


class Staff(UUIDModel, models.Model):
    GRADE_CHOICES = [
        ('associate', 'Associate'),
        ('graduate_trainee', 'Graduate Trainee'),
        ('management_trainee', 'Management Trainee'),
        ('junior_assistant', 'Junior Assistant'),
        ('senior_manager', 'Senior Manager'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    full_name = models.CharField(max_length=150)
    email = models.EmailField(null=True, blank=True)
    phone_number = models.CharField(null=True, blank=True, max_length=20)
    gender = models.CharField(max_length=10, choices=[('Male', 'Male'), ('Female', 'Female')])
    birth_date = models.DateField(null=True, blank=True)
    salary = models.DecimalField(max_digits=12, decimal_places=2)
    hire_date = models.DateField()
    exit_date = models.DateField(null=True, blank=True)
    grade = models.CharField(null=True, blank=True, max_length=100, choices=GRADE_CHOICES)

    role = models.ForeignKey(Role, on_delete=models.SET_NULL, null=True)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True)
    state = models.ForeignKey(State, on_delete=models.SET_NULL, null=True)
    district = models.ForeignKey(BusinessDistrict, on_delete=models.SET_NULL, null=True)

    def is_active(self):
        return self.exit_date is None

    def age(self):
        from datetime import date
        return (date.today() - self.birth_date).days // 365

    def __str__(self):
        return self.full_name
