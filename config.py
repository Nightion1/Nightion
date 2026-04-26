import os

class ConfigSchema:
    """ Base immutable constants tracking explicit bounds linearly offline. """
    MEMORY_DB_PATH = "memory_core.db"
    BACKUP_DIR = "brain_backups"
    SEARCH_TIMEOUT = 5.0
    LLM_TEMPERATURE = 0.0

class DevConfig(ConfigSchema):
    DEBUG = True
    MAX_RETRIES = 2
    DB_PRAGMA = "PRAGMA journal_mode=WAL;"
    
class StagingConfig(ConfigSchema):
    DEBUG = True
    MAX_RETRIES = 1
    SEARCH_TIMEOUT = 2.0  # Tightened timeout bounds

class ProdConfig(ConfigSchema):
    DEBUG = False
    MAX_RETRIES = 3
    SEARCH_TIMEOUT = 5.0

def get_config() -> ConfigSchema:
    env = os.getenv("NIGHTION_ENV", "dev").lower()
    if env == "staging":
        return StagingConfig()
    elif env == "prod":
        return ProdConfig()
    return DevConfig()

config = get_config()
