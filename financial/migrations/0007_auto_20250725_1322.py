from django.db import migrations

def assign_unique_transaction_ids(apps, schema_editor):
    Opex = apps.get_model('financial', 'Opex')
    for i, opex in enumerate(Opex.objects.all().order_by('created_at'), start=1):
        opex.transaction_id = i
        opex.save()

class Migration(migrations.Migration):
    dependencies = [
        ('financial', '0006_opex_transaction_id'),  # Use the actual migration name from step 4
    ]

    operations = [
        migrations.RunPython(assign_unique_transaction_ids),
    ]