from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('backup', '0005_alter_piholeconfig_env_prefix'),
    ]

    operations = [
        migrations.AlterField(
            model_name='piholeconfig',
            name='env_prefix',
            field=models.CharField(
                default='PRIMARY',
                help_text='Environment variable prefix (e.g., PRIMARY reads PIHOLE_PRIMARY_URL)',
                max_length=50,
                unique=True,
                validators=[django.core.validators.RegexValidator(
                    message='Prefix must start with a letter and contain only uppercase letters, numbers, and underscores.',
                    regex='^[A-Z][A-Z0-9_]*$',
                )],
            ),
        ),
    ]
