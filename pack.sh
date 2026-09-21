#!/usr/bin/env bash
set -e

# Omnididact 项目构建与打包脚本
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VERSION="${1:-release}"
PKG_NAME="omnididact-${VERSION}"
PKG_ZIP="$PROJECT_DIR/${PKG_NAME}.zip"
PKG_TAR="$PROJECT_DIR/${PKG_NAME}.tar.gz"

echo "=========================================="
echo "1. 构建前端 SPA (frontend: npm run build)..."
echo "=========================================="
cd "$PROJECT_DIR/frontend"
if ! npm run build; then
    echo "[错误] 前端构建失败，打包终止！" >&2
    exit 1
fi
echo "前端构建成功！"

echo ""
echo "=========================================="
echo "2. 打包发布归档文件..."
echo "=========================================="
cd "$PROJECT_DIR"
rm -f "$PKG_ZIP" "$PKG_TAR"

# Temporary staging dir for clean release structure
STAGE_DIR="$(mktemp -d)"
TARGET_DIR="$STAGE_DIR/$PKG_NAME"
mkdir -p "$TARGET_DIR"

# Copy essential runtime files
cp -r config_store.py config_app.py doc_converter.py proxy.py study_router.py study_service.py "$TARGET_DIR/"
cp -r config.example.json requirements.txt Dockerfile docker-compose.yml "$TARGET_DIR/"
cp -r README.md README.en.md "$TARGET_DIR/" 2>/dev/null || cp README.md "$TARGET_DIR/"
cp -r providers "$TARGET_DIR/"
cp -r plugins "$TARGET_DIR/"
cp -r study "$TARGET_DIR/"
cp -r templates "$TARGET_DIR/"
cp -r static "$TARGET_DIR/"
mkdir -p "$TARGET_DIR/frontend"
cp -r frontend/dist "$TARGET_DIR/frontend/"

# Clean any pycache in stage
find "$TARGET_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$TARGET_DIR" -name "*.pyc" -delete 2>/dev/null || true
find "$TARGET_DIR" -name ".DS_Store" -delete 2>/dev/null || true

# Archive zip & tar.gz
cd "$STAGE_DIR"
zip -r "$PKG_ZIP" "$PKG_NAME"
tar -czf "$PKG_TAR" "$PKG_NAME"

rm -rf "$STAGE_DIR"

echo "=========================================="
echo "打包完成:"
echo "  - $PKG_ZIP"
echo "  - $PKG_TAR"
echo "=========================================="
