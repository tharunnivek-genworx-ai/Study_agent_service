# Sub-chunk 1 | pages 11–20

## FastAPI – Uvicorn

* **Uvicorn**: a Python ASGI server for running FastAPI applications.
* **ASGI**: Asynchronous Server Gateway Interface, a standard for building asynchronous web servers.
* **FastAPI**: a modern, fast (high-performance), web framework for building APIs with Python 3.7+.
* **uvicorn.run**: a function to run the FastAPI application.
* **reload=True**: enables automatic reloading of the application when code changes are detected.

## Running the FastAPI Application

* Run the **app.py** file as a Python script using the command: `python app.py`
* This will launch the Uvicorn server in debug mode.

## FastAPI – Type Hints

* **Type hinting**: a feature in Python 3.5+ that allows specifying the expected data type of a variable or function parameter.
* **Dynamic typing**: Python is a dynamically typed language, where the data type of a variable is determined at runtime.
* **Type errors**: occur when a function is called with an argument of the wrong type.

## Using Type Hints in FastAPI

* Add a colon and data type after a function parameter to specify its expected type.
* Example: `def division(a: int, b: int): return a / b`
* Type hints help prompt the user with the expected type of parameters to be passed.
* This improves code readability and helps catch type-related errors at runtime.