import os
import sys

import uvicorn

if __name__ == "__main__":
    # Add the parent directory to sys.path to allow importing 'backend'
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    uvicorn.run("backend.api.main:app", host="0.0.0.0", port=8000, reload=True)
