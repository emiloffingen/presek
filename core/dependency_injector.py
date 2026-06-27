"""
dependency_injector.py - Dependency injection system to resolve circular dependencies

Provides:
- Service locator pattern
- Lazy loading of dependencies
- Circular dependency detection
- Dependency registration and resolution
"""

import logging
import inspect
import sys
from typing import Any, Callable, Dict, Optional, Type, TypeVar, Union
from functools import wraps

from core.logging_config import get_logger

log = get_logger("presek.di")

T = TypeVar('T')

class DependencyInjector:
    """Simple dependency injector to resolve circular dependencies."""
    
    def __init__(self):
        self._services: Dict[str, Any] = {}
        self._factories: Dict[str, Callable] = {}
        self._initializing: set = set()
        self._dependency_graph: Dict[str, set] = {}
    
    def register_service(self, name: str, service: Any):
        """Register a service instance."""
        if name in self._services:
            log.warning(f"Overwriting existing service: {name}")
        self._services[name] = service
        log.debug(f"Registered service: {name}")
    
    def register_factory(self, name: str, factory: Callable):
        """Register a factory function for lazy loading."""
        if name in self._factories:
            log.warning(f"Overwriting existing factory: {name}")
        self._factories[name] = factory
        log.debug(f"Registered factory: {name}")
    
    def get(self, name: str) -> Any:
        """Get a service by name, initializing if necessary."""
        # Check for circular dependencies
        if name in self._initializing:
            raise CircularDependencyError(f"Circular dependency detected: {name}")
        
        # Return existing service if available
        if name in self._services:
            return self._services[name]
        
        # Initialize using factory if available
        if name in self._factories:
            self._initializing.add(name)
            try:
                service = self._factories[name]()
                self._services[name] = service
                return service
            finally:
                self._initializing.discard(name)
        
        raise DependencyNotFoundError(f"Service not found: {name}")
    
    def has(self, name: str) -> bool:
        """Check if a service is available."""
        return name in self._services or name in self._factories
    
    def reset(self):
        """Reset the injector (for testing)."""
        self._services.clear()
        self._factories.clear()
        self._initializing.clear()

class CircularDependencyError(Exception):
    """Raised when circular dependency is detected."""
    pass

class DependencyNotFoundError(Exception):
    """Raised when dependency is not found."""
    pass

# Global dependency injector instance
di = DependencyInjector()

def inject(*dependencies: str):
    """Decorator to inject dependencies into a function."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Resolve dependencies
            resolved_deps = []
            for dep_name in dependencies:
                if di.has(dep_name):
                    resolved_deps.append(di.get(dep_name))
                else:
                    raise DependencyNotFoundError(f"Dependency not available: {dep_name}")
            
            # Call function with resolved dependencies
            return func(*resolved_deps, *args, **kwargs)
        
        # Preserve function signature for FastAPI
        if hasattr(func, '__signature__'):
            wrapper.__signature__ = func.__signature__
        
        return wrapper
    return decorator

def lazy_import(module_name: str, attribute_name: str = None):
    """Lazy import a module or attribute to break circular dependencies."""
    def _import():
        try:
            module = sys.modules.get(module_name)
            if module is None:
                module = __import__(module_name, fromlist=[''])
            
            if attribute_name:
                return getattr(module, attribute_name)
            return module
        except ImportError as e:
            log.error(f"Failed to lazy import {module_name}.{attribute_name}: {e}")
            raise
    
    return _import

def register_common_dependencies():
    """Register commonly used dependencies."""
    # Register database
    di.register_factory('db', lambda: __import__('core.database', fromlist=['db_manager']).db_manager)
    
    # Register Redis
    di.register_factory('redis', lambda: __import__('utils', fromlist=['redis_client']).redis_client)
    
    # Register configuration
    di.register_factory('config', lambda: __import__('core.config', fromlist=['']).core.config)
    
    log.info("Registered common dependencies")

# Auto-register common dependencies
register_common_dependencies()

def get_service(name: str) -> Any:
    """Get a service from the dependency injector."""
    return di.get(name)

def safe_import(module_path: str, default=None):
    """Safely import a module with fallback."""
    try:
        parts = module_path.rsplit('.', 1)
        if len(parts) == 2:
            module_name, attr_name = parts
            module = __import__(module_name, fromlist=[attr_name])
            return getattr(module, attr_name)
        else:
            return __import__(module_path, fromlist=[''])
    except (ImportError, AttributeError) as e:
        log.warning(f"Safe import failed for {module_path}: {e}")
        return default

class ServiceLocator:
    """Alternative service locator pattern."""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ServiceLocator, cls).__new__(cls)
            cls._instance._services = {}
        return cls._instance
    
    def register(self, name: str, service: Any):
        """Register a service."""
        self._services[name] = service
    
    def get(self, name: str) -> Any:
        """Get a service."""
        return self._services.get(name)
    
    def __getattr__(self, name: str) -> Any:
        """Get service using attribute access."""
        if name in self._services:
            return self._services[name]
        raise AttributeError(f"Service {name} not found")

# Global service locator
services = ServiceLocator()

def init_dependency_injection():
    """Initialize the dependency injection system."""
    log.info("Dependency injection system initialized")
    
    # Register services in service locator for backward compatibility
    services.register('di', di)
    services.register('db', di.get('db'))
    services.register('redis', di.get('redis'))
    services.register('config', di.get('config'))

# Auto-initialize
init_dependency_injection()

# Utility functions for breaking circular imports

def import_string(dotted_path: str) -> Any:
    """Import a dotted module path and return the attribute/class."""
    try:
        module_path, class_name = dotted_path.rsplit('.', 1)
        module = __import__(module_path, fromlist=[class_name])
        return getattr(module, class_name)
    except (ImportError, AttributeError, ValueError) as e:
        log.error(f"Failed to import {dotted_path}: {e}")
        raise

def circular_import_guard(func):
    """Decorator to guard against circular imports."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        module = inspect.getmodule(func)
        if module and hasattr(module, '_initializing'):
            raise CircularDependencyError(f"Circular import detected in {module.__name__}")
        
        # Mark as initializing
        if module:
            module._initializing = True
        
        try:
            return func(*args, **kwargs)
        finally:
            if module:
                delattr(module, '_initializing')
    
    return wrapper