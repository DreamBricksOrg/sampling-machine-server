from pydantic import Field
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    BASE_URL: str = Field(..., env="BASE_URL")
    APP_NAME: str = Field("Sample Machine", env="APP_NAME")
    ENV: str = Field("dev", env="ENV")
    HOST: str = Field("0.0.0.0", env="HOST")
    PORT: int = Field(8000, env="PORT")

    # Mongo (Atlas ou self-hosted)
    MONGO_URI: str = Field(..., env="MONGO_URI")
    MONGO_DB: str = Field("logcenter", env="MONGO_DB")
    MONGO_DEBUG: bool = Field(False, env="MONGO_DEBUG")

    # JWT
    JWT_SECRET: str = Field(..., env="JWT_SECRET")
    JWT_ALGORITHM: str = Field("HS256", env="JWT_ALGORITHM")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(60 * 24, env="ACCESS_TOKEN_EXPIRE_MINUTES")
    ADMIN_CREATION_TOKEN: str = Field(..., env="ADMIN_CREATION_TOKEN")

    # Sentry
    SENTRY_DSN: Optional[str] = Field(default=None, env="SENTRY_DSN")

    # Cache
    REDIS_URL: str = Field(..., env="REDIS_URL")
    
    # LogCenter
    LOG_API: Optional[str] = Field(default=None, env="LOG_API")
    LOG_API_KEY: Optional[str] = Field(default=None, env="LOG_API_KEY")
    LOG_PROJECT_ID: Optional[str] = Field(default=None, env="LOG_PROJECT_ID")
    DEVICE_ID_HEADER: str = Field(..., env="DEVICE_ID_HEADER") 
    API_KEY_HEADER: str = Field(..., env="API_KEY_HEADER")

    # Shortener
    SHORTENER_BASE_URL: str = Field("https://go.dbpe.com.br", env="SHORTENER_BASE_URL")
    SHORTENER_USER: str = Field(...,env="SHORTENER_USER")
    SHORTENER_PASSWORD: str = Field(...,env="SHORTENER_PASSWORD")
    
    # Cadastro
    CADASTRO_BASE_URL: str = Field("https://samplemachine.ngrok.app/api/sample/welcome", env="CADASTRO_BASE_URL")
    
    # Serial
    SERIAL_PORT: str = Field("COM3", env="SERIAL_PORT")
    SERIAL_BAUDRATE: int = Field(9600, env="SERIAL_BAUDRATE")

    # UDP
    UDP_PORT: int = Field(5004, env="UDP_PORT")

    #SMS
    SMS_API_URL: Optional[str] = Field(default=None, env='SMS_API_URL')
    SMS_API_KEY: Optional[str] = Field(default=None, env='SMS_API_KEY')
    SMS_TIMEOUT_SECONDS: int = Field(default=10, env="SMS_TIMEOUT_SECONDS")

    #MACHINE
    DROP_CODE: str = Field(..., env="DROP_CODE")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

settings = Settings()