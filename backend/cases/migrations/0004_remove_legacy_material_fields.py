from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('cases', '0003_legacy_material_data'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='material',
            name='submit_date',
        ),
        migrations.RemoveField(
            model_name='material',
            name='submitted_to',
        ),
    ]
