import warnings

# Completely suppress LangChain/LangGraph warnings before any submodules are loaded
warnings.filterwarnings("ignore", message=".*allowed_objects.*")
warnings.filterwarnings("ignore", message=".*LangChain.*")
warnings.filterwarnings("ignore", module="langgraph.*")
warnings.filterwarnings("ignore", module="langchain.*")

try:
    from importlib.metadata import version
    __version__ = version("deeplens-cli")
except Exception:
    __version__ = "unknown"
