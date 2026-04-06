#!/bin/bash

# Package script for jin-ce-zhi-suan
PROJECT_NAME="jin-ce-zhi-suan"
OUTPUT_NAME="jin_ce_zhi_suan_migration_package.tar.gz"

echo "📦 正在打包进策智算项目..."

# Remove logs, caches, and unnecessary files
rm -rf __pycache__ .pytest_cache .DS_Store data/cache/* live.log server.log

# Create tarball
tar -czvf $OUTPUT_NAME \
    main.py \
    run_live.py \
    server.py \
    config.json \
    requirements.txt \
    WSL_Setup_Guide.md \
    modern_console.html \
    dashboard.html \
    realtime.html \
    status_report.py \
    src/ \
    data/ \
    test_feishu.py

echo "✅ 打包完成！文件名：$OUTPUT_NAME"
echo "👉 请将此文件移动到 Windows 电脑的 WSL2 目录下，并解压："
echo "   tar -xzvf $OUTPUT_NAME"
