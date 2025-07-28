from django.db import migrations, models
import django.db.models.deletion
import uuid

class Migration(migrations.Migration):
    dependencies = [
        ('commercial', '0001_initial'),  # adjust to your last migration
        ('common', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='MonthlyRevenueBilled',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('month', models.DateField()),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('customers_billed', models.PositiveIntegerField(default=0, help_text='Number of customers billed in this month')),
                ('sales_rep', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='commercial.salesrepresentative')),
                ('transformer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='common.distributiontransformer')),
            ],
            options={
                'ordering': ['-month', 'sales_rep', 'transformer'],
            },
        ),
        migrations.AlterUniqueTogether(
            name='monthlyrevenuebilled',
            unique_together={('sales_rep', 'transformer', 'month')},
        ),
    ]