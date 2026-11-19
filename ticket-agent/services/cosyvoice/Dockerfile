FROM pytorch/pytorch:2.3.1-cuda11.8-cudnn8-runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/opt/CosyVoice:/opt/CosyVoice/third_party/Matcha-TTS

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        git \
        build-essential \
        libsndfile1 \
        libgl1 \
        libglib2.0-0 \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

ARG COSYVOICE_REPO=https://github.com/FunAudioLLM/CosyVoice.git
ARG COSYVOICE_REF=main

RUN git clone --depth 1 --branch ${COSYVOICE_REF} ${COSYVOICE_REPO} /opt/CosyVoice \
    && cd /opt/CosyVoice \
    && git submodule update --init --recursive

WORKDIR /opt/CosyVoice

# 固定 cu118 版本，GTX 1060（sm_61）可用；避免 requirements 把 torch 换成 cu121
RUN pip install --no-cache-dir \
        --index-url https://download.pytorch.org/whl/cu118 \
        torch==2.3.1+cu118 torchaudio==2.3.1+cu118

# 只装推理依赖，过滤训练、TensorRT、Gradio、Whisper 等大包和额外源
RUN grep -v -E '^(--|deepspeed|tensorrt|onnxruntime-gpu|openai-whisper|gradio|tensorboard|lightning|grpcio|grpcio-tools|gdown)' \
        requirements.txt > /tmp/requirements-inference.txt \
    && pip install --no-cache-dir -r /tmp/requirements-inference.txt \
    && pip install --no-cache-dir onnxruntime==1.18.0 python-multipart==0.0.12

COPY server.py /opt/server.py
COPY start.sh /opt/start.sh
RUN chmod +x /opt/start.sh

WORKDIR /opt
EXPOSE 50000
CMD ["/opt/start.sh"]
