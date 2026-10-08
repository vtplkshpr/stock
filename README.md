# 🧩 Module Template

**Standard template for creating new AI modules**

This template provides a standardized structure and boilerplate code for creating new AI-powered modules. It includes all necessary components for a complete, standalone module that can be easily integrated into larger systems.

## 📁 Directory Structure

```
module_name/
├── __init__.py                    # Module initialization
├── main.py                        # CLI entry point
├── module_info.py                 # Module metadata and configuration
├── requirements.txt               # Module-specific dependencies
├── SETUP.md                       # Setup and usage documentation
├── README.md                      # Module documentation
├── config.env.example             # Environment configuration example
├── core/                          # Core business logic
│   ├── __init__.py
│   ├── base_service.py           # Base service class
│   └── module_service.py         # Main module service
├── models/                        # Database models
│   ├── __init__.py
│   └── module_models.py          # SQLAlchemy models
├── services/                      # Business logic services
│   ├── __init__.py
│   └── module_services.py        # Service implementations
├── utils/                         # Utility functions
│   ├── __init__.py
│   ├── config.py                 # Configuration management
│   └── helpers.py                # Helper functions
├── scripts/                       # Management scripts
│   ├── __init__.py
│   ├── init_database.py          # Database initialization
│   ├── test_module.py            # Module testing
│   └── setup_services.py         # Service setup
├── tests/                         # Unit tests
│   ├── __init__.py
│   ├── test_core.py
│   ├── test_services.py
│   └── test_models.py
└── logs/                          # Module logs (gitignored)
```

## 🚀 Quick Start

1. **Copy this template** to your desired location
2. **Rename the directory** to your module name
3. **Update configuration** in `module_info.py` with your module details
4. **Implement your logic** in `core/`, `services/`, and `models/`
5. **Update documentation** in `README.md` and `SETUP.md`
6. **Test your module** using the provided test scripts
7. **Deploy or integrate** your module as needed

## 📋 Required Files

### `module_info.py`
Contains module metadata, configuration schema, and CLI command definitions.

### `main.py`
Implements `ModuleInterface` and provides CLI integration.

### `core/base_service.py`
Base service class with common functionality.

### `utils/config.py`
Configuration management following ecosystem standards.

### `scripts/init_database.py`
Database initialization script.

### `scripts/test_module.py`
Module testing and validation script.

## 🔧 Configuration

Each module should have its own configuration namespace to avoid conflicts:

```python
# utils/config.py
class ModuleConfig:
    MODULE_SPECIFIC_SETTING = os.getenv('YOUR_MODULE_SETTING', 'default_value')
```

## 🧪 Testing

Follow the testing standards:

```python
# scripts/test_module.py
async def test_module_functionality():
    # Test your module
    pass
```

## 📚 Documentation

- `README.md`: Module overview and usage
- `SETUP.md`: Detailed setup instructions
- Inline code documentation following Python standards
