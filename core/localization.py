import json
import logging
import os
import threading
from typing import Any, Dict, List, Set

log = logging.getLogger("presek.localization")

# Absolute path to localization rules
RULES_FILE_PATH = os.path.join(os.path.dirname(__file__), "localization_rules.json")

# Thread-safe global references that keep identity for backward-compatible hot-reloads
ENTITY_NOISE_WORDS: Set[str] = set()
TAG_NOISE_WORDS: Set[str] = set()
SOURCE_NOISE_WORDS: Set[str] = set()
TAG_GENERIC_STARTERS: Set[str] = set()
TAG_MAPPINGS: Dict[str, str] = {}
PROTECTED_NAMES: Set[str] = set()


class LocalizationEngine:
    """Thread-safe dynamic configuration manager for Presek's localization and NLP rules."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(LocalizationEngine, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.load_rules()
        self._initialized = True

    def load_rules(self) -> bool:
        """Loads rules from JSON file and updates references in-place."""
        with self._lock:
            try:
                if not os.path.exists(RULES_FILE_PATH):
                    log.warning(f"Localization rules file not found at {RULES_FILE_PATH}, using hardcoded defaults.")
                    self._load_fallback_defaults()
                    return False

                with open(RULES_FILE_PATH, "r", encoding="utf-8") as f:
                    rules = json.load(f)

                self._apply_rules_dict(rules)
                log.info(f"Successfully loaded and initialized dynamic localization rules from {RULES_FILE_PATH}")
                return True
            except Exception as e:
                log.error(f"Failed to load localization rules: {e}", exc_info=True)
                self._load_fallback_defaults()
                return False

    def update_rules(self, rules: Dict[str, Any]) -> bool:
        """Saves new rules to the JSON file and hot-reloads them dynamically."""
        with self._lock:
            try:
                # Basic validation
                required_keys = {
                    "entity_noise_words",
                    "tag_noise_words",
                    "source_noise_words",
                    "tag_generic_starters",
                    "tag_mappings",
                    "protected_names"
                }
                if not all(k in rules for k in required_keys):
                    log.warning("Rejected rule update: Missing one or more required keys.")
                    return False

                # Ensure maps are structured properly
                if not isinstance(rules["tag_mappings"], dict):
                    log.warning("Rejected rule update: tag_mappings must be a dictionary.")
                    return False

                # Write to disk
                with open(RULES_FILE_PATH, "w", encoding="utf-8") as f:
                    json.dump(rules, f, indent=2, ensure_ascii=False)

                # Hot-reload in memory
                self._apply_rules_dict(rules)
                log.info("Successfully updated on disk and hot-reloaded dynamic localization rules.")
                
                # Dynamic cache clearing trigger if Redis client is available
                try:
                    from utils.cache import delete_cache_prefix
                    delete_cache_prefix("api:news:v2:")
                    delete_cache_prefix("api:home:v2:")
                    log.info("Successfully invalidated news and homepage caches to apply new rules immediately.")
                except Exception as cache_err:
                    log.debug(f"Redis cache invalidation skipped during localization update: {cache_err}")

                return True
            except Exception as e:
                log.error(f"Failed to update localization rules: {e}", exc_info=True)
                return False

    def get_rules_dict(self) -> Dict[str, Any]:
        """Returns the active rules as a dictionary."""
        with self._lock:
            return {
                "entity_noise_words": sorted(list(ENTITY_NOISE_WORDS)),
                "tag_noise_words": sorted(list(TAG_NOISE_WORDS)),
                "source_noise_words": sorted(list(SOURCE_NOISE_WORDS)),
                "tag_generic_starters": sorted(list(TAG_GENERIC_STARTERS)),
                "tag_mappings": dict(TAG_MAPPINGS),
                "protected_names": sorted(list(PROTECTED_NAMES)),
            }

    def _apply_rules_dict(self, rules: Dict[str, Any]):
        """Helper to clear and populate references in-place."""
        ENTITY_NOISE_WORDS.clear()
        ENTITY_NOISE_WORDS.update(w.strip().lower() for w in rules.get("entity_noise_words", []))

        TAG_NOISE_WORDS.clear()
        TAG_NOISE_WORDS.update(w.strip().lower() for w in rules.get("tag_noise_words", []))

        SOURCE_NOISE_WORDS.clear()
        SOURCE_NOISE_WORDS.update(w.strip().lower() for w in rules.get("source_noise_words", []))

        TAG_GENERIC_STARTERS.clear()
        TAG_GENERIC_STARTERS.update(w.strip().lower() for w in rules.get("tag_generic_starters", []))

        TAG_MAPPINGS.clear()
        TAG_MAPPINGS.update({k.strip().lower(): v.strip() for k, v in rules.get("tag_mappings", {}).items()})

        PROTECTED_NAMES.clear()
        PROTECTED_NAMES.update(w.strip().lower() for w in rules.get("protected_names", []))

    def _load_fallback_defaults(self):
        """Standard fail-safe defaults in case config file is deleted or corrupt."""
        ENTITY_NOISE_WORDS.clear()
        ENTITY_NOISE_WORDS.update(["dnes", "deneska", "vesti", "izvor"])

        TAG_NOISE_WORDS.clear()
        TAG_NOISE_WORDS.update(["dnes", "deneska", "vesti", "izvor"])

        SOURCE_NOISE_WORDS.clear()
        SOURCE_NOISE_WORDS.update(["reuters", "ap", "afp", "mia", "bbc"])

        TAG_GENERIC_STARTERS.clear()
        TAG_GENERIC_STARTERS.update(["novo", "nova", "glavno"])

        TAG_MAPPINGS.clear()
        TAG_MAPPINGS.update({
            "makedonsk": "Makedonija",
            "mickoski": "Hristijan Mickoski",
            "filipce": "Venko Filipce",
            "evropski": "Evropa"
        })

        PROTECTED_NAMES.clear()
        PROTECTED_NAMES.update(["srbija", "makedonci", "makedonski", "makedonec", "makedon"])


# Initialize engine singleton immediately
localization_engine = LocalizationEngine()
