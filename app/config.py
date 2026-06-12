from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_hostname: str
    database_port: str
    database_password: str
    database_name: str
    database_username: str
    test_database_name: str
    secret_key: str
    algorithm: str
    access_token_expire_minutes: int
    redis_url: str

    # Email settings - resend.com
    resend_api_key: str = ""
    
    # Email settings - ADD THESE
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    smtp_from_email: str
    smtp_from_name: str = "Your App Name"
    
    # Frontend URL for reset link - ADD THIS
    frontend_url: str
    
    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'
        case_sensitive = False

settings = Settings()