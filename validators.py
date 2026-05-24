from marshmallow import EXCLUDE, Schema, ValidationError, fields, validate


class PlayerCreationSchema(Schema):
    email = fields.Email(required=True)
    displayName = fields.String(
        required=True,
        validate=validate.Length(min=1, max=80),
    )
    age = fields.Integer(
        required=False,
        load_default=18,
        validate=validate.Range(min=1, max=120),
    )
    edad = fields.Integer(
        required=False,
        validate=validate.Range(min=1, max=120),
    )


def validate_player_creation_payload(payload):
    if not payload:
        raise ValidationError({"body": ["JSON body is required"]})

    data = PlayerCreationSchema(unknown=EXCLUDE).load(payload)

    if "edad" in data and "age" not in data:
        data["age"] = data.pop("edad")
    else:
        data.pop("edad", None)

    return data
