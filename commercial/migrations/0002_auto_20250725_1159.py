from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('common', '0001_initial'),
        ('commercial', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='dailycollection',
            name='transformer',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                to='common.distributiontransformer'
            ),
        ),
    ]