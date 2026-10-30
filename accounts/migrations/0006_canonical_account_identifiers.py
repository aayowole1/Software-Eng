"""Enforce identifier uniqueness even when concurrent signup prechecks pass.

MongoDB collation strength 2 is case-insensitive but retains accent differences.
The supported $type/$gt partial filter leaves empty/missing email values outside
the email constraint. No application records are rewritten by this migration.
"""
from django.conf import settings
from django.db import migrations
from pymongo import ASCENDING, IndexModel
from pymongo.collation import Collation
from pymongo.errors import PyMongoError

USERNAME_INDEX = "orgflow_auth_username_ci_unique"
EMAIL_INDEX = "orgflow_auth_email_ci_unique"
IDENTIFIER_COLLATION = Collation(locale="en", strength=2)
NONBLANK_EMAIL = {"email": {"$type": "string", "$gt": ""}}


def _has_duplicate(collection, field, match=None):
    pipeline = [{"$match": match}] if match else []
    pipeline.extend([
        {"$group": {"_id": "$" + field, "count": {"$sum": 1}}},
        {"$match": {"count": {"$gt": 1}}},
        {"$project": {"_id": 0, "count": 1}},
        {"$limit": 1},
    ])
    # No identifier value is returned to the migration process or its output.
    return next(collection.aggregate(pipeline, collation=IDENTIFIER_COLLATION), None) is not None


def ensure_identifier_indexes(collection):
    try:
        duplicates = []
        if _has_duplicate(collection, "username"):
            duplicates.append("usernames")
        if _has_duplicate(collection, "email", NONBLANK_EMAIL):
            duplicates.append("nonblank emails")
        if duplicates:
            raise RuntimeError(
                "Account identifier migration stopped: case-insensitive duplicate "
                + " and ".join(duplicates)
                + " exist. An authorized data owner must resolve legacy account conflicts "
                "before rerunning this migration. No accounts were changed or deleted; "
                "identifier values are intentionally omitted."
            )
        collection.create_indexes([
            IndexModel([("username", ASCENDING)], name=USERNAME_INDEX,
                       unique=True, collation=IDENTIFIER_COLLATION),
            IndexModel([("email", ASCENDING)], name=EMAIL_INDEX,
                       unique=True, collation=IDENTIFIER_COLLATION,
                       partialFilterExpression=NONBLANK_EMAIL),
        ])
    except PyMongoError:
        # Duplicate-key details can contain email addresses. A concurrent write
        # during index creation can also invalidate a successful preflight.
        raise RuntimeError(
            "Account identifier indexes could not be installed. Check MongoDB availability "
            "and resolve legacy identifier conflicts with an authorized data owner, then "
            "rerun the migration. No automatic account deletion or deduplication was attempted."
        ) from None


def add_identifier_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "mongodb":
        raise RuntimeError("Account identifier uniqueness migration requires MongoDB.")
    user = apps.get_model(settings.AUTH_USER_MODEL)
    ensure_identifier_indexes(schema_editor.connection.get_collection(user._meta.db_table))


def remove_identifier_indexes(apps, schema_editor):
    user = apps.get_model(settings.AUTH_USER_MODEL)
    collection = schema_editor.connection.get_collection(user._meta.db_table)
    names = {index["name"] for index in collection.list_indexes()}
    for name in (USERNAME_INDEX, EMAIL_INDEX):
        if name in names:
            collection.drop_index(name)


class Migration(migrations.Migration):
    atomic = False
    dependencies = [
        ("accounts", "0005_profile_role_audit"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [migrations.RunPython(add_identifier_indexes, remove_identifier_indexes)]
