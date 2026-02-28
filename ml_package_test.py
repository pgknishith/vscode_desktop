import importlib

# List of common machine learning libraries to check
libraries = [
    "numpy",
    "pandas",
    "scikit-learn",
    "tensorflow",
    "keras",
    "torch",  # PyTorch
    "matplotlib",
    "seaborn",
    "xgboost",
    "lightgbm",
    "catboost",
]

print("Checking installed machine learning libraries...\n")

for lib in libraries:
    try:
        module = importlib.import_module(lib)
        version = getattr(module, "__version__", "Version not found")
        print(f"{lib}: Installed (Version: {version})")
    except ImportError:
        print(f"{lib}: Not Installed")

print("\nLibrary check complete.")