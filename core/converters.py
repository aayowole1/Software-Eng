from bson import ObjectId


class ObjectIdConverter:
    """URL converter for MongoDB ObjectIds, e.g. `<oid:pk>`.

    Anything that is not a 24-character hex string never matches, so bad ids
    give a clean 404 instead of a database error.
    """

    regex = "[0-9a-f]{24}"

    def to_python(self, value):
        return ObjectId(value)

    def to_url(self, value):
        return str(value)
