import os


# Unit/API tests must not depend on a developer's live database configuration.
os.environ["IFC_DATA_MODE"] = "sample"
