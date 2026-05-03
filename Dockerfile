# syntax=docker/dockerfile:1.7

FROM pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime

WORKDIR /app

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# System deps (rarely changes → cached layer)
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    pkg-config \
    default-libmysqlclient-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip

# ONLY dependencies (this is your stable layer)
COPY requirements.txt .

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt
