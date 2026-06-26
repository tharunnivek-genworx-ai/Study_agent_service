# Sub-chunk 2 | pages 11–20

## Type Hints in Python

### Function Parameters

* Use type hints for function parameters with the syntax `param_name: type`.
* Example: `def division(a: int, b: int) -> float:`

### Return Types

* Use the arrow operator `->` to specify the return type of a function.
* Example: `def division(a: int, b: int) -> float:`

### Static Type Checking

* Use a static type checker like **MyPy** to detect type errors before running the code.
* Install MyPy with `pip3 install mypy`.

### Example Code

```python
def division(x: int, y: int) -> int:
    return x // y
```

### Type Hints for Variables

* Use type hints for global variables, function parameters, and variables inside function definitions.
* Example: `x: int = 3`

### Running MyPy

* Save the code to be checked in a file (e.g., `typechk.py`).
* Run MyPy with `mypy typechk.py` to detect type errors.

### MyPy Output

* MyPy will report type errors with the following format:
  ```
typechk.py:7: error: Argument 2 to "division" has incompatible type "float"; expected "int"
```

### Common Type Hints

* Use the following types as type hints:
  + `int`
  + `float`
  + `str`
  + `bool`
  + `list`
  + `dict`
  + `tuple`
  + `set`
  + `None`

### Example Use Cases

* Use type hints to document function behavior and improve code readability.
* Use MyPy to catch type errors before running the code, reducing the risk of runtime errors.