from tortoise import migrations
from tortoise.migrations import operations as ops


async def forwards(apps, _schema_editor) -> None:
    oauth_connection = apps.get_model("models", "OAuthConnection")
    connections = await oauth_connection.filter(provider="gemini-cli").all()
    for connection in connections:
        locator = connection.credential_locator
        if not isinstance(locator, dict):
            continue
        service = locator.get("service")
        if not isinstance(service, str) or not service.startswith("aigateway:gemini-cli:"):
            continue
        connection.credential_locator = {
            **locator,
            "service": service.replace("aigateway:gemini-cli:", "aigateway:gemini:", 1),
        }
        await connection.save(update_fields=["credential_locator"])


async def backwards(apps, _schema_editor) -> None:
    oauth_connection = apps.get_model("models", "OAuthConnection")
    connections = await oauth_connection.filter(provider="gemini-cli").all()
    for connection in connections:
        locator = connection.credential_locator
        if not isinstance(locator, dict):
            continue
        service = locator.get("service")
        if not isinstance(service, str) or not service.startswith("aigateway:gemini:"):
            continue
        connection.credential_locator = {
            **locator,
            "service": service.replace("aigateway:gemini:", "aigateway:gemini-cli:", 1),
        }
        await connection.save(update_fields=["credential_locator"])


class Migration(migrations.Migration):
    dependencies = [("models", "0003_credential_blobs")]

    operations = [ops.RunPython(forwards, backwards)]
