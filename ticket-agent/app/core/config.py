from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """环境变量配置，唯一来源是 .env；代码里不出现明文密钥。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "ticket-agent"
    app_env: str = "dev"

    database_url: str = "postgresql+psycopg://ticket:ticket@localhost:5432/ticket"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 120
    refresh_token_days: int = 7
    # 同一 IP 每分钟登录尝试上限；<=0 表示关闭（测试用）
    login_rate_limit_per_minute: int = 5

    log_enc_key: str = ""
    bootstrap_admin_password: str = ""
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    embedding_provider: str = "local"
    embedding_backend: str = "torch"
    embedding_model_path: str = ""
    embedding_onnx_path: str = ""
    embedding_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    embedding_api_key: str = ""
    embedding_model: str = "bge-m3"
    embedding_dim: int = 1024

    storage_backend: str = "local"
    storage_root: str = "storage"

    # V3 本地语音：SenseVoice int8 + Silero VAD，模型文件缺失时仅语音接口不可用
    voice_asr_model_dir: str = ""
    voice_asr_vad_model: str = ""
    voice_asr_threads: int = 2
    # 本地/外部 CosyVoice2 TTS 服务地址
    cosyvoice_base_url: str = "http://127.0.0.1:15000"
    cosyvoice_speaker: str = "中文女"
    voice_tts_timeout_seconds: int = 60
    # 音视频转写用的 ffmpeg 可执行文件；为空时从 PATH 查找
    ffmpeg_bin: str = ""
    # 声纹模型（CAM++）；为空或文件缺失时唤醒不做说话人校验
    voice_sv_model: str = ""
    # 云 OCR 服务地址；未配置时图片 OCR 直接失败
    aliyun_ocr_endpoint: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
