from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('blog', '0002_customuser_email'),
    ]

    operations = [
        migrations.AddField(
            model_name='customuser',
            name='avatar',
            field=models.ImageField(blank=True, null=True, upload_to='avatars/'),
        ),
    ]
