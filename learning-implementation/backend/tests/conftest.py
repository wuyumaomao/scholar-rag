"""Keep unit tests independent of services configured in the developer .env."""

import os


os.environ["MILVUS_ENABLED"] = "false"
