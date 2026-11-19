"""语音合成切换为本地 CosyVoice2

Revision ID: 0031
Revises: 0030
Create Date: 2026-11-19
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE system_configs
        SET config_value = '"cosyvoice2"',
            description = '本地 CosyVoice2 语音合成服务'
        WHERE config_key = 'voice.tts.model'
        """
    )
    op.execute(
        """
        UPDATE system_configs
        SET config_value = '"中文女"',
            description = 'CosyVoice2 发音人'
        WHERE config_key = 'voice.tts.voice'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE system_configs
        SET config_value = '"edge-tts"',
            description = '语音合成服务标识'
        WHERE config_key = 'voice.tts.model'
        """
    )
    op.execute(
        """
        UPDATE system_configs
        SET config_value = '"zh-CN-XiaoxiaoNeural"',
            description = 'Edge-TTS 发音人'
        WHERE config_key = 'voice.tts.voice'
        """
    )
