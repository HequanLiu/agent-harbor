"""Windows-friendly single-worker entry point."""
import os

import uvicorn
from harbor.app import create_harbor_app

if __name__ == '__main__':
    app = create_harbor_app()
    uvicorn.run(app, host=os.getenv('HARBOR_HOST', '127.0.0.1'), port=int(os.getenv('HARBOR_API_PORT', '8017')))
