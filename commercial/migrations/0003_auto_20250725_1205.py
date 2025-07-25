from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('common', '0001_initial'),
        ('commercial', '0002_auto_20250725_1159'),
    ]

    operations = [
        migrations.AddField(
            model_name='monthlycommercialsummary',
            name='transformer',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                to='common.distributiontransformer'
            ),
        ),
        # Add any other missing transformer fields here if needed
    ]