# Sub-chunk 6 | pages 1–10

## Uvicorn Server Configuration

### Command Line Options

* `--reload-dir PATH`: Set reload directories explicitly (default: current working directory)
* `--reload-include TEXT`: Include files while watching (includes `*.py` by default)
* `--reload-exclude TEXT`: Exclude files while watching
* `--reload-delay FLOAT`: Delay between previous and next check (default: 0.25)
* `-loop [auto|asyncio|uvloop]`: Event loop implementation (default: auto)
* `--http [auto|h11|httptools]`: HTTP protocol implementation (default: auto)
* `--interface [auto|asgi|wsgi]`: Select application interface (default: auto)
* `--env-file PATH`: Environment configuration file
* `--log-config PATH`: Logging configuration file (supports .ini, .json, .yaml)
* `--version`: Display Uvicorn version and exit
* `--app-dir TEXT`: Look for APP in the specified directory (default: current directory)
* `--help`: Show this message and exit

## Launching Uvicorn Programmatically

* Use `uvicorn.run()` method in Python code
* Pass any of the above command line options as parameters
* Example:
```python
import uvicorn
from fastapi import FastAPI
app = FastAPI()

uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
```
[CONTINUES: Uvicorn Configuration]