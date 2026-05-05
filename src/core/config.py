from pydantic import Field
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    MONGO_URI: str = Field(..., env="MONGO_URI")
    MONGO_DB: str = Field("intel", env="MONGO_DB")
    JWT_SECRET: str = Field(..., env="JWT_SECRET")
    JWT_ALGORITHM: str = Field("HS256", env="JWT_ALGORITHM")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(60 * 24, env="ACCESS_TOKEN_EXPIRE_MINUTES")
    ADMIN_CREATION_TOKEN: str = Field(..., env="ADMIN_CREATION_TOKEN")
    SENTRY_DSN: Optional[str] = Field(default=None, env="SENTRY_DSN")
    LOG_API: Optional[str] = Field(default=None, env="LOG_API")
    LOG_ID: Optional[str] = Field(default=None, env="LOG_ID")
    SHORTENER_BASE_URL: str = Field("https://go.dbpe.com.br", env="SHORTENER_BASE_URL")
    SHORTENER_USER: str = Field(...,env="SHORTENER_USER")
    SHORTENER_PASSWORD: str = Field(...,env="SHORTENER_PASSWORD")
    CADASTRO_BASE_URL: str = Field("https://docileelite.ngrok.app/api/docile/cta", env="CADASTRO_BASE_URL")
    UDP_PORT: int = Field(5004, env="UDP_PORT")
    SERIAL_PORT: str = Field("COM3", env="SERIAL_PORT")
    SERIAL_BAUDRATE: int = Field(9600, env="SERIAL_BAUDRATE")


    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

settings = Settings()