"""Exceptions of package aiohttp-openapi."""

import json

import pydantic


class AiohttpOpenapiException(Exception):
    pass


class UnacceptableSignature(AiohttpOpenapiException, TypeError):
    """
    Raised when function signature does not allow to apply @openapi_view.

    Also raised when callable from the package is called with wrong type or
    amount of arguments.
    """


class ValidationError(AiohttpOpenapiException):
    def __init__(self, param_name, location, original_exc=None):
        self.param_name = param_name
        self.location = location
        self.original_exc = original_exc

    def errors(self):
        if isinstance(self.original_exc, pydantic.ValidationError):
            errors = self.original_exc.errors()
            for e in errors:
                e["in"] = self.location.value
            return errors
        else:
            return [
                {
                    "in": self.location.value,
                    "loc": [self.param_name],
                    "msg": self.msg,
                    "type": self.type_,
                }
            ]

    def json(self):
        return json.dumps(self.errors())

    @property
    def msg(self):
        return str(self.original_exc)

    @property
    def type_(self):
        return type(self.original_exc).__name__


class MissingValueError(ValidationError):
    @property
    def msg(self):
        return 'Parameter "{}" is required in {}'.format(
            self.param_name, self.location.value
        )

    @property
    def type_(self):
        return type(self).__name__


class WrongValueError(ValidationError):
    pass


"""
    [
      {
        "loc": [
          "is_required"
        ],
        "msg": "field required",
        "type": "value_error.missing"
      },
      {
        "loc": [
          "gt_int"
        ],
        "msg": "ensure this value is greater than 42",
        "type": "value_error.number.not_gt",
        "ctx": {
          "limit_value": 42
        }
      },
      {
        "loc": [
          "list_of_ints",
          2
        ],
        "msg": "value is not a valid integer",
        "type": "type_error.integer"
      },
      {
        "loc": [
          "a_float"
        ],
        "msg": "value is not a valid float",
        "type": "type_error.float"
      },
      {
        "loc": [
          "recursive_model",
          "lng"
        ],
        "msg": "value is not a valid float",
        "type": "type_error.float"
      }
    ]
"""
