"""Category configuration loader.

Loads and caches category definitions from YAML for category presence detection.
"""

import os
from typing import Dict, Any, Optional, List
from functools import lru_cache
from dataclasses import dataclass

import yaml


@dataclass
class CategoryConfig:
    """Parsed category configuration."""
    key: str
    display_name: str
    description: str
    direction: Optional[str]  # DR, CR, or None for both
    min_count: int
    category_matches: List[str]
    keywords: List[str]
    aliases: List[str]


@lru_cache(maxsize=1)
def load_category_config() -> Dict[str, Any]:
    """Load and cache category configuration from YAML."""
    config_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "categories.yaml"
    )

    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def get_category_config(category_key: str) -> Optional[CategoryConfig]:
    """
    Get configuration for a specific category.

    Args:
        category_key: The canonical category key (e.g., 'salary', 'betting_gaming')

    Returns:
        CategoryConfig if found, None otherwise
    """
    config = load_category_config()
    categories = config.get('categories', {})

    if category_key not in categories:
        return None

    cat = categories[category_key]
    return CategoryConfig(
        key=category_key,
        display_name=cat.get('display_name', category_key),
        description=cat.get('description', ''),
        direction=cat.get('direction'),
        min_count=cat.get('min_count', 1),
        category_matches=cat.get('category_matches', []),
        keywords=cat.get('keywords', []),
        aliases=cat.get('aliases', [])
    )


def resolve_category_alias(user_category: str) -> Optional[str]:
    """
    Resolve user-provided category name to canonical category key.

    Checks category keys, display names, and aliases for matches.
    Uses case-insensitive matching.

    Args:
        user_category: User-provided category string

    Returns:
        Canonical category key if found, None otherwise
    """
    if not user_category:
        return None

    config = load_category_config()
    categories = config.get('categories', {})
    user_lower = user_category.lower().strip()

    # Remove common prefixes/suffixes
    user_lower = user_lower.replace('_', ' ').replace('-', ' ')

    for key, cat_config in categories.items():
        # Check key directly
        if key.lower() == user_lower:
            return key

        # Check key with underscores replaced
        if key.lower().replace('_', ' ') == user_lower:
            return key

        # Check display name
        display_name = cat_config.get('display_name', '').lower()
        if display_name == user_lower:
            return key

        # Check aliases
        aliases = cat_config.get('aliases', [])
        for alias in aliases:
            if alias.lower() == user_lower:
                return key
            # Partial match for compound terms
            if user_lower in alias.lower() or alias.lower() in user_lower:
                return key

    # Fuzzy fallback: check if user input contains any key or alias
    for key, cat_config in categories.items():
        if key.lower() in user_lower:
            return key
        aliases = cat_config.get('aliases', [])
        for alias in aliases:
            if alias.lower() in user_lower:
                return key

    return None


def get_all_category_keys() -> List[str]:
    """Get list of all configured category keys."""
    config = load_category_config()
    return list(config.get('categories', {}).keys())


def get_fallback_config() -> Dict[str, Any]:
    """Get fallback configuration for unknown categories."""
    config = load_category_config()
    return config.get('fallback', {
        'min_count': 1,
        'direction': None,
        'use_fuzzy_match': True,
        'fuzzy_threshold': 70
    })


def get_all_keywords_for_category(category_key: str) -> List[str]:
    """Get all keywords (including category matches) for a category."""
    cat_config = get_category_config(category_key)
    if not cat_config:
        return []

    keywords = list(cat_config.keywords)
    # Add category matches as keywords too
    keywords.extend([m.lower() for m in cat_config.category_matches])
    return keywords
