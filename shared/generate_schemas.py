import json
from pathlib import Path
import models
from pydantic import BaseModel

def generate_schemas():
    """
    Generates JSON schemas from all Pydantic models in models.py
    and saves them to shared/schemas/.
    """
    # Use __file__ to make the path relative to the script's location
    script_dir = Path(__file__).parent
    schema_dir = script_dir / "schemas"
    schema_dir.mkdir(exist_ok=True)

    # Get all Pydantic model classes from the models module
    # This is done by inspecting the module and finding all classes that are
    # subclasses of BaseModel.
    pydantic_models = [
        getattr(models, name)
        for name in dir(models)
        if isinstance(getattr(models, name), type)
        and issubclass(getattr(models, name), BaseModel)
        and getattr(models, name) is not BaseModel
    ]

    print(f"Found {len(pydantic_models)} models to generate schemas for.")

    for model in pydantic_models:
        # Pydantic's schema() method returns a dict, schema_json() returns a string
        schema_json_str = model.schema_json(indent=2)

        # Define the output path for the schema file
        schema_path = schema_dir / f"{model.__name__}.json"

        # Write the JSON schema to the file
        with open(schema_path, "w") as f:
            f.write(schema_json_str)

        print(f"  - Generated schema for {model.__name__} at {schema_path}")

if __name__ == "__main__":
    print("Starting JSON schema generation...")
    generate_schemas()
    print("JSON schema generation complete.")
