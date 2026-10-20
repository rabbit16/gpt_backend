# -*- coding: utf-8 -*-
import os

import uvicorn

from app.factory import create_app

app = create_app()

if __name__ == '__main__':
    # APP_PORT 可控，便于新功能在独立端口灰度，不影响线上 8888。
    port = int(os.environ.get("APP_PORT", "8888"))
    uvicorn.run(app, host="0.0.0.0", port=port)
