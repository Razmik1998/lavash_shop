from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("orders", "0002_reconcile_order_status_and_add_sync_models")]

    operations = [
        migrations.AddField(
            model_name="order",
            name="confirmed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="order",
            name="confirmed_by",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="order",
            name="confirmation_source",
            field=models.CharField(
                blank=True,
                choices=[("ADMIN_PANEL", "Admin Panel"), ("TELEGRAM", "Telegram")],
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="rejected_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="order",
            name="rejected_by",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="order",
            name="rejection_reason",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="order",
            name="rejection_source",
            field=models.CharField(
                blank=True,
                choices=[("ADMIN_PANEL", "Admin Panel"), ("TELEGRAM", "Telegram")],
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="telegram_chat_id",
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="order",
            name="telegram_message_id",
            field=models.BigIntegerField(blank=True, null=True),
        ),
    ]