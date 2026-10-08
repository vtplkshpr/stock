# 🧩 Module Template - Setup Guide

**Complete guide for setting up and using the module template**

## 📋 Overview

This guide will help you set up the module template and create your own AI-powered module based on the standardized structure and patterns provided.

## 🚀 Getting Started

### Step 1: Copy the Template

```bash
# Copy the template to your desired location
cp -r module_template your_module_name
cd your_module_name
```

### Step 2: Update Module Information

Edit `module_info.py` to customize your module:

```python
# module_info.py
from dataclasses import dataclass
from typing import List, Dict, Any

@dataclass
class ModuleInfo:
    name: str = "your_module_name"
    version: str = "1.0.0"
    description: str = "Your module description"
    author: str = "Your Name"
    dependencies: List[str] = None
    supported_languages: List[str] = None
    required_services: List[str] = None
    cli_commands: List[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = [
                "click>=8.0.0",
                "rich>=12.0.0",
                "python-dotenv>=0.19.0"
            ]
        
        if self.supported_languages is None:
            self.supported_languages = ["en"]
        
        if self.required_services is None:
            self.required_services = []
        
        if self.cli_commands is None:
            self.cli_commands = [
                {
                    "name": "run",
                    "help": "Run the module",
                    "options": [
                        {"name": "--input", "help": "Input parameter", "required": True}
                    ]
                }
            ]
```

### Step 3: Implement Your Logic

#### Core Service (`core/module_service.py`)

```python
# core/module_service.py
from .base_service import BaseService

class YourModuleService(BaseService):
    def __init__(self):
        super().__init__()
        self.module_name = "your_module_name"
    
    async def process(self, input_data: str) -> dict:
        """Process input data and return results"""
        try:
            # Your processing logic here
            result = {
                "status": "success",
                "data": input_data,
                "processed_at": self.get_current_time()
            }
            
            self.logger.info(f"Processed data: {input_data}")
            return result
            
        except Exception as e:
            self.logger.error(f"Processing error: {str(e)}")
            raise
    
    async def validate_input(self, input_data: str) -> bool:
        """Validate input data"""
        return bool(input_data and len(input_data.strip()) > 0)
```

#### Main CLI Interface (`main.py`)

```python
# main.py
import asyncio
import click
from rich.console import Console
from rich.panel import Panel

from core.module_service import YourModuleService
from utils.config import Config
from module_info import ModuleInfo

console = Console()
config = Config()
module_info = ModuleInfo()

class YourModuleInterface:
    def __init__(self):
        self.service = YourModuleService()
    
    async def run(self, input_data: str, **kwargs):
        """Main execution method"""
        try:
            # Validate input
            if not await self.service.validate_input(input_data):
                console.print("[red]Error: Invalid input data[/red]")
                return
            
            # Process data
            result = await self.service.process(input_data)
            
            # Display results
            console.print(Panel(
                f"[green]Success![/green]\n"
                f"Input: {input_data}\n"
                f"Result: {result['data']}\n"
                f"Processed at: {result['processed_at']}",
                title="Module Result"
            ))
            
        except Exception as e:
            console.print(f"[red]Error: {str(e)}[/red]")
            raise

@click.command()
@click.option('--input', '-i', required=True, help='Input data to process')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose output')
def main(input, verbose):
    """Your Module CLI"""
    if verbose:
        console.print(f"[blue]Running {module_info.name} v{module_info.version}[/blue]")
    
    # Initialize and run module
    module = YourModuleInterface()
    asyncio.run(module.run(input))

if __name__ == "__main__":
    main()
```

### Step 4: Configure Environment

Create `.env` file based on `config.env.example`:

```bash
# Copy environment template
cp config.env.example .env

# Edit configuration
nano .env
```

Example `.env` content:

```env
# Module Configuration
MODULE_NAME=your_module_name
MODULE_VERSION=1.0.0
DEBUG=true

# Logging Configuration
LOG_LEVEL=INFO
LOG_FILE=./logs/your_module.log

# Database Configuration (if needed)
DATABASE_URL=sqlite:///./data/your_module.db

# External Services (if needed)
API_KEY=your_api_key_here
API_URL=https://api.example.com

# Performance Configuration
MAX_CONCURRENT_TASKS=5
TIMEOUT_SECONDS=30
```

### Step 5: Setup Dependencies

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Step 6: Initialize Database (if needed)

```bash
# Run database initialization
python scripts/init_database.py
```

### Step 7: Test Your Module

```bash
# Run basic tests
python scripts/test_module.py

# Test with sample data
python main.py --input "test data" --verbose
```

## 🎮 Usage Examples

### Basic Usage

```bash
# Simple execution
python main.py --input "Hello World"

# With verbose output
python main.py --input "Hello World" --verbose
```

### Advanced Usage

```bash
# Using environment variables
export MODULE_INPUT="Advanced test data"
python main.py --input "$MODULE_INPUT"

# With custom configuration
MODULE_DEBUG=true python main.py --input "Debug test"
```

## 🔧 Customization Guide

### Adding New Features

1. **Add new service methods** in `core/module_service.py`
2. **Update CLI commands** in `module_info.py`
3. **Add configuration options** in `utils/config.py`
4. **Update tests** in `scripts/test_module.py`

### Adding Database Models

```python
# models/module_models.py
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class YourData(Base):
    __tablename__ = 'your_data'
    
    id = Column(Integer, primary_key=True)
    content = Column(String(1000), nullable=False)
    created_at = Column(DateTime, nullable=False)
    
    def __repr__(self):
        return f"<YourData(id={self.id}, content='{self.content[:50]}...')>"
```

### Adding External API Integration

```python
# services/external_api.py
import aiohttp
import asyncio

class ExternalAPIService:
    def __init__(self, api_key: str, base_url: str):
        self.api_key = api_key
        self.base_url = base_url
    
    async def call_api(self, endpoint: str, data: dict) -> dict:
        """Call external API"""
        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            async with session.post(
                f"{self.base_url}/{endpoint}",
                json=data,
                headers=headers
            ) as response:
                return await response.json()
```

## 🧪 Testing

### Running Tests

```bash
# Run all tests
python scripts/test_module.py

# Run specific test
python scripts/test_module.py --test-core

# Run with verbose output
python scripts/test_module.py --verbose
```

### Writing Tests

```python
# tests/test_core.py
import pytest
from core.module_service import YourModuleService

class TestYourModuleService:
    @pytest.fixture
    def service(self):
        return YourModuleService()
    
    @pytest.mark.asyncio
    async def test_process_valid_input(self, service):
        result = await service.process("test input")
        assert result["status"] == "success"
        assert "data" in result
    
    @pytest.mark.asyncio
    async def test_validate_input(self, service):
        assert await service.validate_input("valid input") == True
        assert await service.validate_input("") == False
        assert await service.validate_input(None) == False
```

## 📊 Monitoring and Logging

### Log Configuration

```python
# utils/config.py
import logging
import os

def setup_logging():
    log_level = os.getenv('LOG_LEVEL', 'INFO')
    log_file = os.getenv('LOG_FILE', './logs/your_module.log')
    
    # Create logs directory
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    
    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
```

### Health Checks

```python
# scripts/health_check.py
import asyncio
from core.module_service import YourModuleService

async def health_check():
    """Check module health"""
    service = YourModuleService()
    
    try:
        # Test basic functionality
        result = await service.process("health check")
        print("✅ Module is healthy")
        return True
    except Exception as e:
        print(f"❌ Module health check failed: {e}")
        return False

if __name__ == "__main__":
    asyncio.run(health_check())
```

## 🚀 Deployment

### Standalone Deployment

```bash
# Create deployment package
tar -czf your_module.tar.gz your_module/

# On target system
tar -xzf your_module.tar.gz
cd your_module
pip install -r requirements.txt
python main.py --input "test"
```

### Docker Deployment

```dockerfile
# Dockerfile
FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py", "--help"]
```

### Integration with Larger Systems

```python
# Integration example
from your_module.main import YourModuleInterface

async def integrate_with_system():
    module = YourModuleInterface()
    result = await module.run("system input")
    return result
```

## 🛠️ Troubleshooting

### Common Issues

#### Import Errors
```bash
# Check Python path
python -c "import sys; print('\n'.join(sys.path))"

# Check virtual environment
which python
```

#### Configuration Issues
```bash
# Check environment variables
env | grep MODULE

# Test configuration loading
python -c "from utils.config import Config; print(Config().get_all())"
```

#### Database Issues
```bash
# Check database connection
python scripts/test_module.py --test-db

# Recreate database
python scripts/init_database.py --force
```

### Debug Mode

```bash
# Enable debug logging
export LOG_LEVEL=DEBUG
python main.py --input "test" --verbose
```

## 📚 Best Practices

1. **Error Handling**: Always wrap external calls in try-catch blocks
2. **Logging**: Log important events and errors
3. **Configuration**: Use environment variables for sensitive data
4. **Testing**: Write comprehensive tests for all functionality
5. **Documentation**: Keep documentation up to date
6. **Versioning**: Use semantic versioning for releases
7. **Security**: Never commit API keys or passwords
8. **Performance**: Monitor resource usage and optimize bottlenecks

## 📖 Additional Resources

- **[README](README.md)**: Module overview and structure
- **[Python Best Practices](https://docs.python.org/3/tutorial/)**: Python coding standards
- **[Click Documentation](https://click.palletsprojects.com/)**: CLI framework
- **[Rich Documentation](https://rich.readthedocs.io/)**: Terminal formatting
- **[SQLAlchemy Documentation](https://docs.sqlalchemy.org/)**: Database ORM

---

**Module Template Setup Guide - Ready to build your AI module!** 🚀
