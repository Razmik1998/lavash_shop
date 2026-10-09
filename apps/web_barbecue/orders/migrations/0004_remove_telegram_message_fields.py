from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("orders", "0003_order_lifecycle_audit_telegram")]

    operations = [
        migrations.RemoveField(
            model_name="order",
            name="telegram_chat_id",
        ),
        migrations.RemoveField(
            model_name="order",
            name="telegram_message_id",
        ),
    ]