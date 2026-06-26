# Sub-chunk 4 | pages 11–20

## Type Hinting in Python

### Overview

* Type hinting is a feature in Python that provides dynamic autocomplete features in IDEs like PyCharm and VS Code.
* It helps the IDE understand the type of variables, making it easier to provide suggestions.

### Using Type Hints in Functions

* Include type hints in function definitions to provide autocomplete suggestions.
* Use the `str` class as a type hint for string variables.
* Use the `capitalize()` method to ensure the first letter of a string is in upper case.

### Example Code

```python
def sayhello(name: str) -> str:
    return "Hello " + name.capitalize()
```

### Using Type Hints with User-Defined Classes

* Define a class with type hints for arguments to the `__init__()` constructor.
* Use the class name as a type hint in function declarations.
* The IDE will provide autocomplete support for instance attributes.

### Example Code

```python
class Rectangle:
    def __init__(self, w: int, h: int) -> None:
        self.width = w
        self.height = h

def area(r: Rectangle) -> int:
    return r.width * r.height
```

### Benefits of Type Hinting

* Provides dynamic autocomplete features in IDEs.
* Helps catch type-related errors at runtime.
* Improves code readability and maintainability.

### IDE Support

* PyCharm and VS Code support type hinting.
* Other IDEs may also support type hinting, but the extent of support may vary.

### [CONTINUES: Type Hinting]