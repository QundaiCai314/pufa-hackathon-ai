#!/bin/bash
# =============================================================
# MinerU PDF 解析环境初始化脚本
# 在容器内执行，完成以下工作：
#   1. 安装 MinerU 及其依赖（固定版本）
#   2. 从 ModelScope 下载 PDF-Extract-Kit 模型
#   3. 从 HuggingFace 下载 PyTorch OCR 模型
#   4. 创建 LayoutLMv3 配置和权重链接
#   5. 应用 backbone.py PyTorch 2.x 兼容性修复
#   6. 覆盖 models_config.yml
#   7. 创建 magic-pdf 配置
# =============================================================
set -e

echo "========================================"
echo "  MinerU Setup Script - Start"
echo "========================================"

# --- 0. 环境变量 ---
MINERU_CACHE="/root/.cache/mineru"
SITE_PACKAGES=$(python3 -c "import site; print(site.getsitepackages()[0])")
MAGIC_PDF="${SITE_PACKAGES}/magic_pdf"
echo "SITE_PACKAGES: ${SITE_PACKAGES}"
echo "MAGIC_PDF: ${MAGIC_PDF}"

# --- 1. 安装 MinerU 及依赖 ---
echo "--- [1/7] Installing MinerU and dependencies ---"

# MinerU
pip install --no-cache-dir magic-pdf==1.3.12

# 依赖版本固定
pip install --no-cache-dir \
    transformers==4.49.0 \
    timm==1.0.28

# detectron2（从源码编译安装）
pip install --no-cache-dir 'git+https://github.com/facebookresearch/detectron2.git@v0.6'

# pycocotools（detectron2 依赖）
pip install --no-cache-dir pycocotools

# --- 2. 从 ModelScope 下载 PDF-Extract-Kit ---
echo "--- [2/7] Downloading PDF-Extract-Kit from ModelScope ---"
python3 -c "
from modelscope import snapshot_download
import os
cache_dir = '/root/.cache/mineru'
os.makedirs(cache_dir, exist_ok=True)
cache_path = snapshot_download(
    'opendatalab/PDF-Extract-Kit',
    cache_dir=cache_dir,
    revision='master'
)
print(f'Models downloaded to: {cache_path}')
"

MODELSCOPE_SNAP="${MINERU_CACHE}/models/opendatalab--PDF-Extract-Kit/snapshots/master"

# --- 3. 从 HuggingFace 下载 PyTorch OCR 模型 ---
echo "--- [3/7] Downloading PyTorch OCR models from HuggingFace ---"
python3 -c "
from huggingface_hub import snapshot_download
import os, shutil

ocr_dir = '/root/.cache/mineru/OCR/paddleocr_torch'
os.makedirs(ocr_dir, exist_ok=True)

cache_path = snapshot_download(
    'opendatalab/PDF-Extract-Kit-1.0',
    allow_patterns=['models/OCR/paddleocr_torch/*'],
    cache_dir='/root/.cache/huggingface/hub'
)

# Copy .pth files to the target directory
src = os.path.join(cache_path, 'models/OCR/paddleocr_torch')
for f in os.listdir(src):
    src_file = os.path.join(src, f)
    dst_file = os.path.join(ocr_dir, f)
    if os.path.isfile(src_file) and f.endswith('.pth'):
        shutil.copy2(src_file, dst_file)
        print(f'  Copied: {f}')
    elif os.path.isfile(src_file) and f.endswith('.safetensors'):
        shutil.copy2(src_file, dst_file)
        print(f'  Copied: {f}')
print('OCR models ready.')
"

# --- 4. 创建 LayoutLMv3 配置和权重链接 ---
echo "--- [4/7] Setting up LayoutLMv3 config and weights ---"

LAYOUT_DIR="${MINERU_CACHE}/Layout/LayoutLMv3"
mkdir -p "${LAYOUT_DIR}"

# 复制 config.json
cp /app/scripts/mineru/layoutlmv3_config.json "${LAYOUT_DIR}/config.json"

# 链接 model_final.pth
LAYOUT_WEIGHTS="${MODELSCOPE_SNAP}/models/Layout/model_final.pth"
if [ -f "${LAYOUT_WEIGHTS}" ]; then
    ln -sf "${LAYOUT_WEIGHTS}" "${LAYOUT_DIR}/model_final.pth"
    echo "  Linked model_final.pth -> ${LAYOUT_WEIGHTS}"
else
    echo "  WARNING: model_final.pth not found at ${LAYOUT_WEIGHTS}"
fi

# 也创建 /root/.cache/mineru/Layout/model_final.pth 链接
mkdir -p "${MINERU_CACHE}/Layout"
ln -sf "${LAYOUT_WEIGHTS}" "${MINERU_CACHE}/Layout/model_final.pth"

# 复制 detectron2 yaml 配置
DETECTRON2_CFG_DIR="${MAGIC_PDF}/resources/model_config/layoutlmv3"
mkdir -p "${DETECTRON2_CFG_DIR}"
cp /app/scripts/mineru/layoutlmv3_base_inference.yaml "${DETECTRON2_CFG_DIR}/layoutlmv3_base_inference.yaml"
echo "  Copied layoutlmv3_base_inference.yaml"

# --- 5. 应用 backbone.py 兼容性修复 ---
echo "--- [5/7] Patching backbone.py for PyTorch 2.x compatibility ---"

BACKBONE_FILE="${MAGIC_PDF}/model/sub_modules/layout/layoutlmv3/backbone.py"
python3 << 'PATCH_EOF'
import re

backbone_path = __import__('os').path.join(
    __import__('os').environ.get('MAGIC_PDF', ''),
    'model/sub_modules/layout/layoutlmv3/backbone.py'
)

with open(backbone_path, 'r') as f:
    content = f.read()

old_code = '''        if "layoutlmv3" in self.name:
            return self.backbone.forward(
                input_ids=x["input_ids"],
                bbox=x["bbox"],
                images=x["images"],
                attention_mask=x["attention_mask"],
            )'''

new_code = '''        if "layoutlmv3" in self.name:
            if isinstance(x, dict):
                return self.backbone.forward(
                    input_ids=x.get("input_ids"),
                    bbox=x.get("bbox"),
                    images=x.get("images"),
                    attention_mask=x.get("attention_mask"),
                )
            else:
                return self.backbone.forward(
                    input_ids=None,
                    bbox=None,
                    images=x,
                    attention_mask=None,
                )'''

if old_code in content:
    content = content.replace(old_code, new_code)
    with open(backbone_path, 'w') as f:
        f.write(content)
    print("  backbone.py patched successfully (original pattern)")
elif "isinstance(x, dict)" in content:
    print("  backbone.py already patched")
else:
    # Fallback: find and replace the forward call pattern
    print("  WARNING: Original pattern not found, attempting fuzzy patch...")
    # Find the block starting with 'if "layoutlmv3" in self.name:'
    lines = content.split('\n')
    new_lines = []
    i = 0
    patched = False
    while i < len(lines):
        if 'if "layoutlmv3" in self.name:' in lines[i] and not patched:
            new_lines.append(lines[i])
            new_lines.append('            if isinstance(x, dict):')
            new_lines.append('                return self.backbone.forward(')
            new_lines.append('                    input_ids=x.get("input_ids"),')
            new_lines.append('                    bbox=x.get("bbox"),')
            new_lines.append('                    images=x.get("images"),')
            new_lines.append('                    attention_mask=x.get("attention_mask"),')
            new_lines.append('                )')
            new_lines.append('            else:')
            new_lines.append('                return self.backbone.forward(')
            new_lines.append('                    input_ids=None,')
            new_lines.append('                    bbox=None,')
            new_lines.append('                    images=x,')
            new_lines.append('                    attention_mask=None,')
            new_lines.append('                )')
            # Skip the original lines until we hit the assert or the next non-indented line
            i += 1
            while i < len(lines) and (lines[i].startswith('                ') or lines[i].strip() == ''):
                i += 1
            patched = True
        else:
            new_lines.append(lines[i])
            i += 1
    with open(backbone_path, 'w') as f:
        f.write('\n'.join(new_lines))
    print(f"  backbone.py patched (fuzzy mode), patched={patched}")
PATCH_EOF

export MAGIC_PDF="${MAGIC_PDF}"
python3 -c "
import os
backbone_path = os.path.join(os.environ['MAGIC_PDF'], 'model/sub_modules/layout/layoutlmv3/backbone.py')
with open(backbone_path) as f:
    content = f.read()
if 'isinstance(x, dict)' in content:
    print('  Verified: backbone.py patch is in place')
else:
    print('  ERROR: backbone.py patch NOT found!')
"

# --- 6. 覆盖 models_config.yml ---
echo "--- [6/7] Overriding models_config.yml ---"

OCR_CONFIG_DIR="${MAGIC_PDF}/model/sub_modules/ocr/paddleocr2pytorch/pytorchocr/utils/resources"
cp /app/scripts/mineru/models_config.yml "${OCR_CONFIG_DIR}/models_config.yml"
echo "  models_config.yml updated"

# --- 7. 创建 magic-pdf 配置 ---
echo "--- [7/7] Creating magic-pdf.json config ---"

cat > /root/.magic-pdf.json << 'JSON_EOF'
{
  "device-mode": "cpu",
  "layout-config": {
    "model": "layoutlmv3"
  },
  "formula-config": {
    "model": "unimernet_small"
  },
  "table-config": {
    "model": "tablemaster"
  },
  "ocr-config": {
    "model": "paddleocr_torch"
  }
}
JSON_EOF
echo "  magic-pdf.json created"

# --- 8. 修复 MFR/TabRec 符号链接问题 ---
echo "--- [8/7] Fixing MFR/TabRec symlinks ---"
python3 -c "
import os

snap = '${MODELSCOPE_SNAP}'

# Fix MFR unimernet symlinks
mfr_base = os.path.join(snap, 'models/MFR/unimernet_small')
if os.path.exists(mfr_base):
    for root, dirs, files in os.walk(mfr_base):
        for f in files:
            fp = os.path.join(root, f)
            if os.path.islink(fp) and not os.path.exists(fp):
                # Broken symlink - fix by pointing to actual file
                target = os.readlink(fp)
                if os.path.exists(target):
                    pass  # already valid
                else:
                    print(f'  Broken link: {fp} -> {target}')

# Fix TabRec symlinks
tab_base = os.path.join(snap, 'models/TabRec')
if os.path.exists(tab_base):
    for d in os.listdir(tab_base):
        model_dir = os.path.join(tab_base, d)
        if os.path.isdir(model_dir):
            for f in os.listdir(model_dir):
                fp = os.path.join(model_dir, f)
                if os.path.islink(fp) and not os.path.exists(fp):
                    print(f'  Broken link: {fp} -> {os.readlink(fp)}')

print('  Symlink check complete')
"

echo "========================================"
echo "  MinerU Setup Complete!"
echo "========================================"
echo ""
echo "Models cache: ${MINERU_CACHE}"
echo "To verify, run:"
echo "  magic-pdf -p /path/to/test.pdf -o /tmp/test_output -m auto"
