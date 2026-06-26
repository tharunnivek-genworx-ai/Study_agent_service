# Sub-chunk 3 | pages 11–20

## Type Hints in Python
### Overview

* Type hints are used to specify the data type of a variable, function parameter, or return value.
* They are not enforced by Python at runtime but can be checked by static type checkers like mypy.

## Type Hints in Python
### Basic Types

* `int`: integer
* `float`: floating point number
* `str`: string
* `bool`: boolean
* `list`: list (e.g. `List[str]`)
* `tuple`: tuple (e.g. `Tuple[str, int, float]`)
* `dict`: dictionary (e.g. `Dict[str, int]`)

## Type Hints in Python
### Union and Optional Types

* `Union`: represents a union of types (e.g. `Union[int, float]`)
* `Optional`: represents a value that may or may not be present (e.g. `Optional[str]`)

## Type Hints in Python
### Example Usage

```python
from typing import List, Tuple, Dict

cities: List[str] = ['Mumbai', 'Delhi', 'Chennai']
employee: Tuple[str, int, float] = ('Ravi', 25, 35000)
marklist: Dict[str, int] = {'Ravi': 61, 'Anil': 72}
```

## Mypy Error Messages

* `Argument 2 to "division" has incompatible type "float"; expected "int"`: error message indicating that a float is being passed to a function that expects an integer.
* `Found 2 errors in 1 file (checked 1 source file)`: summary of errors found by mypy.

## IDE Support

* FastAPI supports type hints and can be used with IDEs that support type checking, such as PyCharm.
* IDEs can provide features like code completion and error highlighting based on type hints.

[CONTINUES: FastAPI]